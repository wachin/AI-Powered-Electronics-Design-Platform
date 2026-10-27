"""
Build a validated Circuit IR from an LLM-produced circuit specification.

This module is the missing handoff between the LLM layer and the hardware
layer. It consumes `CircuitSpecification` data (as plain dicts or dataclasses)
and produces a `CircuitIR` whose:

* reference designators are deterministic and collision-free
* MPNs resolve to real catalog parts, or are explicitly substituted
* pins exist on the chosen symbol
* power nets are marked as power nets
* every component carries the reasoning the LLM gave for it

Design rule: the LLM decides *what* the circuit is; this builder decides
whether that is physically expressible. Anything it cannot express is
reported, never silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from src.core.circuit_ir import (
    CircuitIR,
    Component,
    ComponentType,
    PowerDomain,
)
from src.core.component_resolver import (
    DesignatorAssigner,
    ResolvedComponent,
    find_pin_in,
    infer_component_type,
    is_power_net,
    resolve_mpn,
    resolve_pins,
    role_to_component_type,
    synthesize_passive_passport,
)


def find_component_pin(component: Component, identifier: str):
    """
    Locate a pin on a Circuit IR component by number, name, or known alias.

    The alias step is what lets an LLM write "U1.VOUT" and still land on the
    symbol's real "VO" pin. Without it, a correct instruction is discarded.

    Returns the component's own ``Pin`` object, not a tuple copy, so callers
    can use ``pin.number`` / ``pin.name`` directly.
    """
    match = find_pin_in(
        [(p.number, p.name, p.pin_type) for p in component.pins], identifier
    )
    if match is None:
        return None
    number, name, _ = match
    for pin in component.pins:
        if pin.number == number and pin.name == name:
            return pin
    return None

# ---------------------------------------------------------------------------
# Small helpers for the loose data shapes LLMs actually emit
# ---------------------------------------------------------------------------


def _as_mapping(item: Any) -> Dict[str, Any]:
    """Coerce a spec component (dict or dataclass) into a plain dict."""
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "keys"):
        try:
            return {key: item[key] for key in item.keys()}
        except Exception:  # pragma: no cover - defensive
            pass
    if hasattr(item, "__dict__"):
        return dict(vars(item))
    return {}


def _first(mapping: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            value = mapping[key]
            if isinstance(value, (list, tuple)):
                value = " ".join(str(v) for v in value)
            text = str(value).strip()
            if text:
                return text
    return default


_REF_SPLIT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:[.:/]\s*(.+?))?\s*$")
_PIN_IN_NAME_RE = re.compile(r"\(([^)]+)\)\s*$")


def _normalize_net_name(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return "NET"
    text = text.replace(" ", "_").replace("-", "_")
    return text.upper()


@dataclass
class _Connection:
    """A single normalized connection request."""

    net: str
    ref: str
    pin: Optional[str]


def _parse_endpoint(value: Any) -> Tuple[str, Optional[str]]:
    """
    Parse "U1.VIN", "U1:VIN", "regulator.VIN", "U1", or {"ref":..,"pin":..}.

    The reference part may be a designator ("U1") or a role name from the
    components array ("regulator"), because models use both interchangeably.
    """
    if isinstance(value, dict):
        ref = _first(value, "ref", "component", "component_ref", "id", "designator")
        pin = _first(value, "pin", "pin_name", "pin_number", "terminal") or None
        return ref.strip(), pin

    text = str(value or "").strip()
    if not text:
        return "", None

    # A trailing "(PIN)" annotation, e.g. "U1 (VIN)".
    annotation = _PIN_IN_NAME_RE.search(text)
    if annotation and "." not in text and ":" not in text:
        pin = annotation.group(1).strip()
        return text[: annotation.start()].strip(), pin or None

    match = _REF_SPLIT_RE.match(text)
    if match:
        return match.group(1).strip(), (match.group(2) or "").strip() or None
    return text, None


def _extract_connections(spec: Dict[str, Any]) -> List[_Connection]:
    """Normalize every connection shape we have seen LLMs emit."""
    raw = spec.get("connections") or spec.get("nets") or []
    if isinstance(raw, dict):
        expanded: List[Dict[str, Any]] = []
        for net_name, endpoints in raw.items():
            if isinstance(endpoints, (list, tuple)):
                for endpoint in endpoints:
                    expanded.append(
                        {"net": net_name, "from": endpoint, "to": endpoint}
                        if not isinstance(endpoint, dict)
                        else {"net": net_name, **endpoint}
                    )
            elif isinstance(endpoints, dict):
                for ref, pin in endpoints.items():
                    expanded.append({"net": net_name, "from": ref, "pin": pin})
        raw = expanded

    if not isinstance(raw, (list, tuple)):
        return []

    connections: List[_Connection] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        # Net name.
        net = _first(
            entry,
            "net", "net_name", "name", "signal", "node", "netName",
        )

        # Endpoint A.
        from_ref = _first(entry, "from", "from_component", "source", "src", "a", "start")
        to_ref = _first(entry, "to", "to_component", "target", "dst", "b", "end")
        from_pin = _first(entry, "from_pin", "source_pin", "pin_a", "fromPin")
        to_pin = _first(entry, "to_pin", "target_pin", "pin_b", "toPin")

        # `pins` may enumerate all endpoints of a net.
        pin_list = entry.get("pins") or entry.get("endpoints") or entry.get("nodes")

        if pin_list and not from_ref:
            for endpoint in pin_list:
                ref, pin = _parse_endpoint(endpoint)
                if ref:
                    connections.append(_Connection(net=net, ref=ref, pin=pin))
            continue

        if from_ref:
            ref, inline_pin = _parse_endpoint(from_ref)
            connections.append(
                _Connection(net=net, ref=ref, pin=from_pin or inline_pin)
            )
        if to_ref:
            ref, inline_pin = _parse_endpoint(to_ref)
            connections.append(
                _Connection(net=net, ref=ref, pin=to_pin or inline_pin)
            )

    return connections


# Net name -> pin names that the net conventionally attaches to. Used only to
# resolve *power* connections that arrive without an explicit pin; a signal net
# without a pin is reported rather than guessed.
_CONVENTIONAL_PIN_NAMES: Dict[str, Tuple[str, ...]] = {
    "VIN": ("VIN", "IN", "V+", "VCC", "VDD", "PWR_IN", "INPUT"),
    "VOUT": ("VOUT", "OUT", "PWR_OUT", "OUTPUT"),
    "GND": ("GND", "V-", "VSS", "AGND", "DGND"),
    "VCC": ("VCC", "V+", "VDD", "VIN"),
    "VDD": ("VDD", "V+", "VCC"),
    "VSS": ("VSS", "V-", "GND"),
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

@dataclass
class BuildReport:
    """Everything the builder had to change or could not honor."""

    total_components: int = 0
    resolved_from_catalog: int = 0
    substituted_mpns: List[str] = field(default_factory=list)
    unverified_mpns: List[str] = field(default_factory=list)
    missing_footprints: List[str] = field(default_factory=list)
    skipped_connections: List[str] = field(default_factory=list)
    dropped_components: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_components": self.total_components,
            "resolved_from_catalog": self.resolved_from_catalog,
            "substituted_mpns": list(self.substituted_mpns),
            "unverified_mpns": list(self.unverified_mpns),
            "missing_footprints": list(self.missing_footprints),
            "skipped_connections": list(self.skipped_connections),
            "dropped_components": list(self.dropped_components),
            "notes": list(self.notes),
        }


class CircuitIRBuilder:
    """
    Converts an LLM circuit specification into a Circuit IR.

    The builder is intentionally forgiving about the *shape* of the spec but
    strict about its *physical meaning*: unknown references and pins become
    recorded problems rather than silent omissions.
    """

    def __init__(self, component_db: Any = None) -> None:
        self.db = component_db

    def build(
        self,
        spec: Any,
        requirements: Any = None,
        name: Optional[str] = None,
        description: str = "",
    ) -> Tuple[CircuitIR, BuildReport]:
        spec_dict = _as_mapping(spec)
        report = BuildReport()

        req_dict = _as_mapping(requirements) if requirements is not None else {}
        circuit_type = _first(req_dict, "circuit_type", "type", default="generic")
        if not description:
            description = _first(
                spec_dict, "description",
                default=_first(req_dict, "description", "original"),
            )

        circuit_name = name or f"Generated {circuit_type.replace('_', ' ').title()}"
        circuit = CircuitIR(name=circuit_name, description=description)

        raw_components = spec_dict.get("components") or []
        if not isinstance(raw_components, (list, tuple)):
            raw_components = []

        assigner = DesignatorAssigner()
        # Two lookup tables: LLM reference designator -> ours, and role -> ours.
        ref_map: Dict[str, str] = {}
        role_map: Dict[str, str] = {}
        resolved_components: List[ResolvedComponent] = []

        # Pass 1: resolve components and reserve explicit designators.
        for raw in raw_components:
            item = _as_mapping(raw)
            role = _first(item, "role", "function", "name", "type")

            requested_mpn = _first(item, "mpn", "part_number", "part", "lcsc")
            value = _first(item, "value", "rating")
            package = _first(item, "package", "footprint_package", "case")
            manufacturer = _first(item, "manufacturer", "mfr", "vendor")
            reasoning = _first(item, "reasoning", "rationale", "why")
            explicit_ref = _first(item, "ref", "reference", "designator", "id")

            component_type = infer_component_type(
                role,
                role_to_component_type(role),
                mpn=requested_mpn,
                value=value,
                package=package,
            )

            if explicit_ref:
                assigner.reserve(explicit_ref)
            resolved_components.append(
                self._resolve_one(
                    role, component_type, requested_mpn, manufacturer,
                    value, package, reasoning, report,
                )
            )

        # Pass 2: assign final designators and record lookups.
        final_components: List[Tuple[ResolvedComponent, str]] = []
        for raw, component in zip(raw_components, resolved_components):
            item = _as_mapping(raw)
            explicit_ref = _first(item, "ref", "reference", "designator", "id")
            ref = explicit_ref or assigner.assign(component.component_type)
            component.ref = ref
            final_components.append((component, ref))

            if explicit_ref:
                ref_map[explicit_ref.strip().upper()] = ref
            role = (component.role or "").strip()
            if role:
                role_map[role.lower()] = ref
                role_map[_normalize_net_name(role).lower()] = ref

        report.total_components = len(final_components)

        # Pass 3: materialize Circuit IR components.
        for component, ref in final_components:
            circuit.add_component(self._to_ir_component(component, ref))

        # Pass 4: resolve and apply connections.
        self._apply_connections(spec_dict, circuit, ref_map, role_map, report)

        # Pass 5: power domains and metadata.
        self._apply_power_domains(spec_dict, circuit, req_dict)
        self._merge_notes(circuit, spec_dict, report)

        return circuit, report

    # -- component resolution ------------------------------------------------

    def _resolve_one(
        self,
        role: str,
        component_type: ComponentType,
        requested_mpn: str,
        manufacturer: str,
        value: str,
        package: str,
        reasoning: str,
        report: BuildReport,
    ) -> ResolvedComponent:
        # 1. Ask the catalog for a real part.
        mpn_resolution = resolve_mpn(
            component_type, requested_mpn, self.db, package=package, value=value
        )
        catalog_part = mpn_resolution.resolved

        if mpn_resolution.substituted and mpn_resolution.note:
            report.substituted_mpns.append(mpn_resolution.note)
        elif catalog_part is None and requested_mpn:
            report.unverified_mpns.append(requested_mpn)
            if mpn_resolution.note:
                report.notes.append(mpn_resolution.note)

        # 2. Determine symbol / footprint: catalog wins, then synthesis.
        symbol = footprint = ""
        resolved_mpn = requested_mpn
        resolved_manufacturer = manufacturer
        resolved_value = value
        resolved_package = package
        from_catalog = catalog_part is not None

        if catalog_part is not None:
            symbol = getattr(catalog_part, "symbol", "") or ""
            footprint = getattr(catalog_part, "footprint", "") or ""
            resolved_mpn = getattr(catalog_part, "mpn", requested_mpn)
            resolved_manufacturer = getattr(catalog_part, "manufacturer", manufacturer)
            # Keep the requested electrical value: an MPN substitution exists to
            # give the design a purchasable part number and land pattern, not to
            # silently change 47k into 10k.
            resolved_value = value or str(getattr(catalog_part, "value", ""))
            resolved_package = package or str(getattr(catalog_part, "package", ""))
            report.resolved_from_catalog += 1

        if not symbol or not footprint:
            synth_symbol, synth_footprint = synthesize_passive_passport(
                component_type, resolved_package
            )
            symbol = symbol or synth_symbol
            footprint = footprint or synth_footprint

        # 3. Pins from the authoritative template/pinout table.
        pins = resolve_pins(component_type, resolved_mpn, symbol, resolved_value)

        if not footprint:
            report.missing_footprints.append(resolved_mpn or role or component_type.value)

        resolved = ResolvedComponent(
            ref="",
            role=role,
            component_type=component_type,
            value=resolved_value,
            package=resolved_package,
            symbol=symbol,
            footprint=footprint,
            pins=pins,
            mpn=resolved_mpn,
            manufacturer=resolved_manufacturer,
            reasoning=reasoning,
            from_catalog=from_catalog,
            substituted=mpn_resolution.substituted,
        )

        if not pins and component_type is not ComponentType.CUSTOM:
            resolved.notes.append(
                f"no known pinout for {resolved_mpn or component_type.value}"
            )
        return resolved

    @staticmethod
    def _to_ir_component(component: ResolvedComponent, ref: str) -> Component:
        ir = Component(
            ref=ref,
            value=component.value or component.mpn or ref,
            component_type=component.component_type,
            footprint=component.footprint,
            symbol=component.symbol,
            mpn=component.mpn or None,
            manufacturer=component.manufacturer or None,
            description=component.reasoning or None,
            package=component.package or "",
        )
        for number, pin_name, pin_type in component.pins:
            ir.add_pin(number, pin_name, pin_type)
        ir.attributes["role"] = component.role
        ir.attributes["from_catalog"] = component.from_catalog
        if component.reasoning:
            ir.attributes["reasoning"] = component.reasoning
        if component.notes:
            ir.attributes["resolution_notes"] = list(component.notes)
        return ir

    # -- connections ---------------------------------------------------------

    def _lookup_ref(
        self,
        candidate: str,
        ref_map: Dict[str, str],
        role_map: Dict[str, str],
        circuit: CircuitIR,
    ) -> Optional[str]:
        """
        Resolve a connection endpoint to a real reference designator.

        LLMs refer to components inconsistently: by assigned designator ("U1"),
        by the role from the components array ("input_capacitor"), or by a
        near-synonym ("led_resistor" for "current_limit_resistor"). We match
        exact identifiers first and only fall back to token overlap.
        """
        if not candidate:
            return None
        text = candidate.strip()
        upper = text.upper()

        # 1. Exact designator, mapped or already valid.
        if upper in ref_map:
            return ref_map[upper]
        if upper in circuit.components:
            return upper

        # 2. Exact role.
        lowered = text.lower()
        if lowered in role_map:
            return role_map[lowered]
        normalized = _normalize_net_name(text).lower()
        if normalized in role_map:
            return role_map[normalized]

        # 3. Substring containment, preferring the longest role match.
        best: Optional[Tuple[int, str]] = None
        for role, ref in role_map.items():
            if not role:
                continue
            if lowered in role or role in lowered:
                length = min(len(lowered), len(role))
                if best is None or length > best[0]:
                    best = (length, ref)
        if best is not None:
            return best[1]

        # 4. Token overlap ("led_resistor" ~ "current_limit_resistor").
        wanted_tokens = {t for t in re.split(r"[_\W]+", lowered) if t}
        if not wanted_tokens:
            return None
        best_overlap = 0
        best_ref: Optional[str] = None
        for role, ref in role_map.items():
            role_tokens = {t for t in re.split(r"[_\W]+", role) if t}
            overlap = len(wanted_tokens & role_tokens)
            if overlap > best_overlap:
                best_overlap, best_ref = overlap, ref
        if best_overlap > 0:
            return best_ref

        return None

    def _apply_connections(
        self,
        spec_dict: Dict[str, Any],
        circuit: CircuitIR,
        ref_map: Dict[str, str],
        role_map: Dict[str, str],
        report: BuildReport,
    ) -> None:
        connections = _extract_connections(spec_dict)
        if not connections:
            report.notes.append("specification contained no usable connections")
            return

        # Remember which pins of each component are already on a net. This
        # lets an omitted pin be resolved unambiguously: if pin 1 of a resistor
        # is already on VOUT, a later pinless connection must mean pin 2.
        used_pins: Dict[str, set] = {}

        for connection in connections:
            ref = self._lookup_ref(connection.ref, ref_map, role_map, circuit)
            if ref is None:
                report.skipped_connections.append(
                    f"unknown component reference '{connection.ref}'"
                )
                continue

            component = circuit.components[ref]
            net_name = _normalize_net_name(connection.net) if connection.net else ""
            pin = self._resolve_pin(
                component, connection.pin, net_name, report, used_pins.get(ref, set())
            )

            if pin is None:
                report.skipped_connections.append(
                    f"no pin given for {ref} on net "
                    f"'{net_name or connection.net}' and none could be inferred"
                )
                continue

            if not net_name:
                net_name = f"N_{ref}_{pin.number}"

            self._connect(circuit, ref, pin.number, net_name)
            used_pins.setdefault(ref, set()).add(pin.number)

    @staticmethod
    def _resolve_pin(
        component: Component,
        requested_pin: Optional[str],
        net_name: str,
        report: BuildReport,
        used_pins: Optional[set] = None,
    ) -> Optional[Any]:
        """
        Resolve which pin a connection refers to.

        Explicit pins always win. Otherwise we try, in order: the conventional
        pin for a power/ground net, the only pin not already committed to a net,
        and finally a non-polarised two-terminal passive. Every inference is
        recorded so the caller can see what was assumed.
        """
        used_pins = used_pins or set()

        if requested_pin:
            pin = find_component_pin(component, str(requested_pin))
            if pin is None:
                report.skipped_connections.append(
                    f"{component.ref} has no pin '{requested_pin}' "
                    f"(available: {[p.number for p in component.pins]})"
                )
            return pin

        conventional = _CONVENTIONAL_PIN_NAMES.get(net_name.upper())
        if conventional:
            for wanted in conventional:
                pin = find_component_pin(component, wanted)
                if pin is not None:
                    report.notes.append(
                        f"no pin given for {component.ref} on net {net_name}; "
                        f"inferred pin {pin.number} ({pin.name})"
                    )
                    return pin

        # If exactly one pin is still free, a pinless connection can only mean
        # that one. This resolves chains like "R1" -> "D1" reliably.
        free_pins = [p for p in component.pins if p.number not in used_pins]
        if len(free_pins) == 1:
            chosen = free_pins[0]
            report.notes.append(
                f"no pin given for {component.ref} on net {net_name}; "
                f"used the remaining free pin {chosen.number}"
            )
            return chosen

        # Last resort for non-polarised two-terminal passives: a resistor or
        # capacitor is electrically identical whichever way round it is, and
        # models frequently omit the pin for them. Only do this for exactly two
        # pins, and record it, so polarity-sensitive parts are never guessed.
        if len(component.pins) == 2 and component.component_type in (
            ComponentType.RESISTOR,
            ComponentType.CAPACITOR,
            ComponentType.INDUCTOR,
        ):
            connected = [p for p in component.pins if p.connected_net]
            chosen = connected[0] if len(connected) == 1 else None
            if chosen is None:
                unconnected = [p for p in component.pins if not p.connected_net]
                chosen = unconnected[0] if len(unconnected) == 1 else component.pins[0]
            report.notes.append(
                f"no pin given for {component.ref} on net {net_name}; "
                f"assumed pin {chosen.number} for a non-polarised "
                f"{component.component_type.value}"
            )
            return chosen

        return None

    @staticmethod
    def _connect(circuit: CircuitIR, ref: str, pin_number: str, net_name: str) -> None:
        power = is_power_net(net_name)
        net = circuit.get_or_create_net(net_name, is_power=power)
        if power and not net.is_power:
            net.is_power = True

        # Avoid duplicate pin entries on the same net.
        for existing in net.connected_pins:
            if existing.get("ref") == ref and existing.get("pin") == pin_number:
                return

        circuit.connect(ref, pin_number, net_name)

    # -- power domains / notes ----------------------------------------------

    def _apply_power_domains(
        self,
        spec_dict: Dict[str, Any],
        circuit: CircuitIR,
        req_dict: Dict[str, Any],
    ) -> None:
        domains = spec_dict.get("power_domains") or {}
        if isinstance(domains, dict):
            for domain_name, payload in domains.items():
                voltage = 0.0
                max_current = 0.0
                if isinstance(payload, dict):
                    voltage = _safe_float(
                        _first(payload, "voltage", "v", "nominal_voltage", "volts")
                    )
                    max_current = _safe_float(
                        _first(payload, "max_current_ma", "max_current", "current_ma", "current")
                    )
                else:
                    voltage = _safe_float(payload)

                circuit.power_domains[domain_name] = PowerDomain(
                    name=domain_name,
                    voltage=voltage,
                    max_current_ma=max_current,
                    ground_net=_first(
                        payload if isinstance(payload, dict) else {}, "ground_net",
                        default="GND",
                    ),
                )

        # Ensure the rails the requirement mentions exist as domains.
        output_voltage = _safe_float(_first(req_dict, "output_voltage"))
        input_voltage = _safe_float(_first(req_dict, "input_voltage"))
        output_current = _safe_float(_first(req_dict, "output_current"))

        if output_voltage and "VOUT" not in circuit.power_domains:
            circuit.power_domains["VOUT"] = PowerDomain(
                name="VOUT",
                voltage=output_voltage,
                max_current_ma=output_current * 1000.0 if output_current else 0.0,
            )
        if input_voltage and "VIN" not in circuit.power_domains:
            circuit.power_domains["VIN"] = PowerDomain(
                name="VIN", voltage=input_voltage, max_current_ma=0.0
            )

    def _merge_notes(
        self,
        circuit: CircuitIR,
        spec_dict: Dict[str, Any],
        report: BuildReport,
    ) -> None:
        design_notes = spec_dict.get("design_notes") or []
        warnings = spec_dict.get("warnings") or []
        circuit.metadata["build_report"] = report.to_dict()
        circuit.metadata["design_notes"] = [str(n) for n in design_notes]
        circuit.metadata["llm_warnings"] = [str(w) for w in warnings]


def _safe_float(value: Any) -> float:
    """Parse a float from the loose string/number shapes LLMs emit."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace("v", "").replace("a", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    try:
        number = float(match.group(0))
    except ValueError:
        return 0.0
    if "ma" in text:
        number /= 1000.0
    return number


__all__ = ["BuildReport", "CircuitIRBuilder"]
