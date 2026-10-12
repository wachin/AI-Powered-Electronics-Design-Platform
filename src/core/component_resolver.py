"""
Component and pin resolution for AI-generated circuit specifications.

Why this module exists
----------------------
An LLM can produce a syntactically perfect JSON specification that is still
physically meaningless: manufacturer part numbers that do not exist, pin names
that the chosen symbol does not have, or passives with no footprint at all.

This module is the authority that turns an LLM's *intent* into something the
Circuit IR and KiCad generator can actually consume:

* role strings ("input_capacitor", "freewheel_diode", ...) -> ComponentType
* deterministic reference designators (U1, C2, R1, ...)
* pin lists matching real KiCad symbol pin numbers/names
* KiCad symbol + footprint identifiers for passives and common ICs
* MPN resolution against the component database, with explicit substitution

Nothing here calls an LLM. It is deterministic and unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.circuit_ir import ComponentType, PinType

# ---------------------------------------------------------------------------
# SMD package -> KiCad footprint identifiers
# ---------------------------------------------------------------------------

_PASSIVE_FOOTPRINTS: Dict[str, Dict[str, str]] = {
    "resistor": {
        "0402": "Resistor_SMD:R_0402_1005Metric",
        "0603": "Resistor_SMD:R_0603_1608Metric",
        "0805": "Resistor_SMD:R_0805_2012Metric",
        "1206": "Resistor_SMD:R_1206_3216Metric",
        "1210": "Resistor_SMD:R_1210_3225Metric",
        "2010": "Resistor_SMD:R_2010_5025Metric",
        "2512": "Resistor_SMD:R_2512_6332Metric",
    },
    "capacitor": {
        "0402": "Capacitor_SMD:C_0402_1005Metric",
        "0603": "Capacitor_SMD:C_0603_1608Metric",
        "0805": "Capacitor_SMD:C_0805_2012Metric",
        "1206": "Capacitor_SMD:C_1206_3216Metric",
        "1210": "Capacitor_SMD:C_1210_3225Metric",
        "1812": "Capacitor_SMD:C_1812_4532Metric",
    },
    "inductor": {
        "0402": "Inductor_SMD:L_0402_1005Metric",
        "0603": "Inductor_SMD:L_0603_1608Metric",
        "0805": "Inductor_SMD:L_0805_2012Metric",
        "1206": "Inductor_SMD:L_1206_3216Metric",
        "1210": "Inductor_SMD:L_1210_3225Metric",
    },
}


def normalize_package(package: str) -> str:
    """Reduce a free-text package string to a canonical short token."""
    if not package:
        return ""
    text = package.strip().upper().replace(" ", "")
    # Metric imperial conversions people write interchangeably.
    text = text.replace("METRIC", "")
    match = re.search(r"\b(0402|0603|0805|1206|1210|1812|2010|2512)\b", text)
    if match:
        return match.group(1)
    aliases = {
        "SOT23": "SOT-23",
        "SOT223": "SOT-223",
        "SOIC8": "SOIC-8",
        "SO8": "SOIC-8",
        "DIP8": "DIP-8",
        "TO220": "TO-220",
        "TO92": "TO-92",
        "HC49S": "HC-49S",
        "SMA": "SMA",
        "SOD123": "SOD-123",
        "SMB": "SMB",
    }
    return aliases.get(text, package.strip())


# ---------------------------------------------------------------------------
# Role -> ComponentType
# ---------------------------------------------------------------------------

# Order matters: the first matching keyword wins. Compound roles such as
# "led_resistor" or "input_capacitor" are named after their *governing* noun,
# so part-kind keywords are tested before modifier keywords.
_ROLE_RULES: Sequence[Tuple[Tuple[str, ...], ComponentType]] = (
    (("buck",), ComponentType.REGULATOR_BUCK),
    (("boost",), ComponentType.REGULATOR_BOOST),
    (("voltage_reference", "voltage_ref", "vref", "shunt_regulator"), ComponentType.CHIP),
    (("ldo", "linear_regulator", "regulator", "vreg"), ComponentType.REGULATOR_LDO),
    (("microcontroller", "mcu", "processor", "soc"), ComponentType.MICROCONTROLLER),
    (("crystal", "resonator", "oscillator"), ComponentType.CRYSTAL),
    (("opamp", "op_amp", "operational_amplifier", "amplifier"), ComponentType.OPAMP),
    (("mosfet", "nmos", "pmos", "fet"), ComponentType.MOSFET),
    (("transistor", "bjt"), ComponentType.TRANSISTOR),
    (("inductor", "choke"), ComponentType.INDUCTOR),
    (("freewheel", "freewheeling", "flyback", "catch", "schottky", "rectifier"), ComponentType.DIODE),
    (("resistor", "res_", "_res", "potentiometer"), ComponentType.RESISTOR),
    (("capacitor", "cap_", "_cap", "bypass", "decoupling"), ComponentType.CAPACITOR),
    (("led",), ComponentType.LED),
    (("diode", "zener", "tvs"), ComponentType.DIODE),
    (("connector", "jack", "header", "terminal", "socket", "plug", "clip", "receptacle"), ComponentType.CONNECTOR),
    (("switch", "button", "toggle"), ComponentType.SWITCH),
    (("testpoint", "test_point", "probe"), ComponentType.TESTPOINT),
    (("fuse", "ferrite", "bead"), ComponentType.CUSTOM),
)

# Positional fallbacks for roles that encode the part kind as an index rather
# than a word, e.g. "riaa_r1_left", "gain_c2", "stage2_r3".
_POSITIONAL_RULES: Sequence[Tuple["re.Pattern[str]", ComponentType]] = (
    (re.compile(r"(?:^|_)(?:r|rn|rf|rin)\d*(?:_|$)"), ComponentType.RESISTOR),
    (re.compile(r"(?:^|_)(?:c|cn|cf|cin|cout)\d*(?:_|$)"), ComponentType.CAPACITOR),
    (re.compile(r"(?:^|_)(?:l|ln)\d*(?:_|$)"), ComponentType.INDUCTOR),
    (re.compile(r"(?:^|_)d\d*(?:_|$)"), ComponentType.DIODE),
    (re.compile(r"(?:^|_)q\d*(?:_|$)"), ComponentType.TRANSISTOR),
    (re.compile(r"(?:^|_)u\d*(?:_|$)"), ComponentType.CHIP),
)

# Role words that name an IC-style part whose exact kind we cannot infer.
_GENERIC_IC_ROLES = ("controller", "converter", "chip", "ic", "module", "sensor")

# Types that are effectively "a chip" for ERC decoupling purposes.
_IC_LIKE = {
    ComponentType.REGULATOR_LDO,
    ComponentType.REGULATOR_BUCK,
    ComponentType.REGULATOR_BOOST,
    ComponentType.MICROCONTROLLER,
    ComponentType.OPAMP,
    ComponentType.CHIP,
}

_DESIGNATOR_PREFIX: Dict[ComponentType, str] = {
    ComponentType.RESISTOR: "R",
    ComponentType.CAPACITOR: "C",
    ComponentType.INDUCTOR: "L",
    ComponentType.DIODE: "D",
    ComponentType.LED: "D",
    ComponentType.TRANSISTOR: "Q",
    ComponentType.MOSFET: "Q",
    ComponentType.OPAMP: "U",
    ComponentType.REGULATOR_LDO: "U",
    ComponentType.REGULATOR_BUCK: "U",
    ComponentType.REGULATOR_BOOST: "U",
    ComponentType.MICROCONTROLLER: "U",
    ComponentType.CHIP: "U",
    ComponentType.SWITCH: "SW",
    ComponentType.CRYSTAL: "Y",
    ComponentType.CONNECTOR: "J",
    ComponentType.TESTPOINT: "TP",
    ComponentType.VOLTAGE_SOURCE: "V",
    ComponentType.CURRENT_SOURCE: "I",
    ComponentType.CUSTOM: "X",
}


def infer_component_type(
    role: str,
    component_type: ComponentType,
    mpn: str = "",
    value: str = "",
    package: str = "",
) -> ComponentType:
    """
    Refine an ambiguous component type using the part number and value.

    A role like "controller" is genuinely ambiguous: switched-mode converters
    and LDOs both use it. The MPN or value usually disambiguates, and getting
    this right matters because the pinout table is keyed on component type.
    """
    if component_type not in (
        ComponentType.CHIP,
        ComponentType.CUSTOM,
        ComponentType.REGULATOR_LDO,
    ):
        return component_type

    haystack = " ".join([mpn or "", value or "", package or ""]).lower()

    if "buck" in haystack or "step-down" in haystack or "step down" in haystack:
        return ComponentType.REGULATOR_BUCK
    if "boost" in haystack or "step-up" in haystack or "step up" in haystack:
        return ComponentType.REGULATOR_BOOST
    if any(token in haystack for token in ("ldo", "1117", "7805", "7803", "317")):
        return ComponentType.REGULATOR_LDO

    # Known switched-mode controller families.
    if any(token in haystack for token in ("2596", "34063", "lm2576")):
        return ComponentType.REGULATOR_BUCK
    if any(token in haystack for token in ("mt3608", "boost")):
        return ComponentType.REGULATOR_BOOST

    # "controller" plus an inductor value in the role still means a switcher.
    role_text = (role or "").lower()
    if "controller" in role_text and "inductor" not in role_text:
        if value and any(unit in value.lower() for unit in ("uh", "µh", "mh")):
            return ComponentType.REGULATOR_BUCK

    return component_type


def role_to_component_type(role: str, fallback: ComponentType = ComponentType.CUSTOM) -> ComponentType:
    """Map a free-text component role onto a canonical ComponentType."""
    if not role:
        return fallback
    text = role.strip().lower()
    normalized = re.sub(r"[\s\-]+", "_", text)

    # A trailing passive noun governs the whole role: "regulator_adj_resistor"
    # is a resistor that belongs to a regulator, not a regulator.
    for suffix, component_type in (
        ("_resistor", ComponentType.RESISTOR),
        ("_capacitor", ComponentType.CAPACITOR),
        ("_inductor", ComponentType.INDUCTOR),
        ("_res", ComponentType.RESISTOR),
        ("_cap", ComponentType.CAPACITOR),
    ):
        if normalized.endswith(suffix):
            return component_type

    for keywords, component_type in _ROLE_RULES:
        for keyword in keywords:
            if keyword in normalized:
                return component_type

    for pattern, component_type in _POSITIONAL_RULES:
        if pattern.search(normalized):
            return component_type

    for word in _GENERIC_IC_ROLES:
        if word in normalized:
            return ComponentType.CHIP

    return fallback


# ---------------------------------------------------------------------------
# Pin templates
# ---------------------------------------------------------------------------

# Generic two-terminal / three-terminal parts. The first entry of each tuple is
# (pin_number, pin_name, PinType).
_TWO_TERMINAL: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "1", PinType.PASSIVE),
    ("2", "2", PinType.PASSIVE),
)

_LED_PINS: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "K", PinType.PASSIVE),
    ("2", "A", PinType.PASSIVE),
)

_DIODE_PINS: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "K", PinType.PASSIVE),
    ("2", "A", PinType.PASSIVE),
)

# Transistor_FET:Q_NMOS_GSD on SOT-23: 1=G, 2=S, 3=D (verified against KiCad 9
# libraries; pin numbers must match the footprint pads, which are 1/2/3).
_MOSFET_PINS: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "G", PinType.INPUT),
    ("2", "S", PinType.PASSIVE),
    ("3", "D", PinType.PASSIVE),
)

_TRANSISTOR_PINS: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "B", PinType.INPUT),
    ("2", "E", PinType.PASSIVE),
    ("3", "C", PinType.PASSIVE),
)

_CRYSTAL_PINS: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "1", PinType.PASSIVE),
    ("2", "2", PinType.PASSIVE),
)

_CONNECTOR_PINS: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "1", PinType.PASSIVE),
    ("2", "2", PinType.PASSIVE),
)

_SWITCH_PINS: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "1", PinType.PASSIVE),
    ("2", "2", PinType.PASSIVE),
)

_TESTPOINT_PINS: Tuple[Tuple[str, str, PinType], ...] = (
    ("1", "1", PinType.PASSIVE),
)

_PIN_TEMPLATES: Dict[ComponentType, Tuple[Tuple[str, str, PinType], ...]] = {
    ComponentType.RESISTOR: _TWO_TERMINAL,
    ComponentType.CAPACITOR: _TWO_TERMINAL,
    ComponentType.INDUCTOR: _TWO_TERMINAL,
    ComponentType.LED: _LED_PINS,
    ComponentType.DIODE: _DIODE_PINS,
    ComponentType.MOSFET: _MOSFET_PINS,
    ComponentType.TRANSISTOR: _TRANSISTOR_PINS,
    ComponentType.CRYSTAL: _CRYSTAL_PINS,
    ComponentType.CONNECTOR: _CONNECTOR_PINS,
    ComponentType.SWITCH: _SWITCH_PINS,
    ComponentType.TESTPOINT: _TESTPOINT_PINS,
    ComponentType.VOLTAGE_SOURCE: _TWO_TERMINAL,
    ComponentType.CURRENT_SOURCE: _TWO_TERMINAL,
}


def _named_pins(*specs: Tuple[str, str, PinType]) -> Tuple[Tuple[str, str, PinType], ...]:
    return tuple(specs)


# Pinouts for ICs we can resolve by symbol/MPN family. Keys are matched as
# substrings against the symbol lib_id or the MPN.
#
# Pin NUMBERS and NAMES are taken from the installed KiCad symbol libraries
# (verified against KiCad 9.0.2 /usr/share/kicad/symbols). The names matter:
# KiCad resolves pins by name in the generated schematic, so a made-up name
# like "VOUT" on a symbol whose real pin is "VO" produces a broken schematic.
# Pin-name *aliases* are handled separately in `_PIN_ALIAS_GROUPS`, so an LLM
# may still write "U1.VOUT" and have it resolve correctly.
_IC_PINOUTS: Dict[str, Tuple[Tuple[str, str, PinType], ...]] = {
    # Regulator_Linear:AMS1117-3.3 -> 1=GND, 2=VO, 3=VI
    "ams1117": _named_pins(
        ("1", "GND", PinType.POWER_IN),
        ("2", "VO", PinType.POWER_OUT),
        ("3", "VI", PinType.POWER_IN),
    ),
    "lm1117": _named_pins(
        ("1", "GND", PinType.POWER_IN),
        ("2", "VO", PinType.POWER_OUT),
        ("3", "VI", PinType.POWER_IN),
    ),
    # Regulator_Linear:LM7805_TO220 -> 1=VI, 2=GND, 3=VO
    "lm7805": _named_pins(
        ("1", "VI", PinType.POWER_IN),
        ("2", "GND", PinType.POWER_IN),
        ("3", "VO", PinType.POWER_OUT),
    ),
    # Regulator_Linear:LM317 -> 1=ADJ, 2=VO, 3=VI
    "lm317": _named_pins(
        ("1", "ADJ", PinType.INPUT),
        ("2", "VO", PinType.POWER_OUT),
        ("3", "VI", PinType.POWER_IN),
    ),
    # Regulator_Linear:LM337 -> 1=ADJ, 2=VI, 3=VO
    "lm337": _named_pins(
        ("1", "ADJ", PinType.INPUT),
        ("2", "VI", PinType.POWER_IN),
        ("3", "VO", PinType.POWER_OUT),
    ),
    # Regulator_Switching:LM2596S-5 -> 1=VIN, 2=OUT, 3=GND, 4=FB, 5=~{ON}/OFF
    "lm2596": _named_pins(
        ("1", "VIN", PinType.POWER_IN),
        ("2", "OUT", PinType.POWER_OUT),
        ("3", "GND", PinType.POWER_IN),
        ("4", "FB", PinType.INPUT),
        ("5", "ON", PinType.INPUT),
    ),
    # Regulator_Switching:MT3608 -> 1=SW, 2=GND, 3=FB, 4=EN, 5=VIN, 6=NC
    "mt3608": _named_pins(
        ("1", "SW", PinType.POWER_OUT),
        ("2", "GND", PinType.POWER_IN),
        ("3", "FB", PinType.INPUT),
        ("4", "EN", PinType.INPUT),
        ("5", "VIN", PinType.POWER_IN),
        ("6", "NC", PinType.PASSIVE),
    ),
    # Amplifier_Operational:LM358 / TL072 are 8-pin dual op-amps whose output
    # pins are unnamed in KiCad. We give them stable readable names ("OUT1",
    # "OUT2") so the netlist is expressible; the alias table lets a model write
    # "OUT" or "OUT1" and still hit the right pin.
    "lm358": _named_pins(
        ("1", "OUT1", PinType.OUTPUT),
        ("2", "IN1-", PinType.INPUT),
        ("3", "IN1+", PinType.INPUT),
        ("4", "V-", PinType.POWER_IN),
        ("5", "IN2+", PinType.INPUT),
        ("6", "IN2-", PinType.INPUT),
        ("7", "OUT2", PinType.OUTPUT),
        ("8", "V+", PinType.POWER_IN),
    ),
    "tl072": _named_pins(
        ("1", "OUT1", PinType.OUTPUT),
        ("2", "IN1-", PinType.INPUT),
        ("3", "IN1+", PinType.INPUT),
        ("4", "V-", PinType.POWER_IN),
        ("5", "IN2+", PinType.INPUT),
        ("6", "IN2-", PinType.INPUT),
        ("7", "OUT2", PinType.OUTPUT),
        ("8", "V+", PinType.POWER_IN),
    ),
    # Reference_Voltage:TL431DBZ -> 1=K, 2=REF, 3=A
    "tl431": _named_pins(
        ("1", "K", PinType.PASSIVE),
        ("2", "REF", PinType.INPUT),
        ("3", "A", PinType.PASSIVE),
    ),
}

# Conventional net names we mark as power nets so ERC treats them correctly.
_POWER_NET_NAMES = {
    "GND", "AGND", "DGND", "VSS", "VCC", "VDD", "VBUS", "VIN", "VOUT",
    "+5V", "+3V3", "3V3", "3.3V", "5V", "12V", "+12V", "-12V", "+15V", "-15V",
}

_IPIN_RE = re.compile(r"[\s\-]*IN[\s\-]*([0-9]?)\s*([\+\-])", re.IGNORECASE)


# Alias groups: a model may legitimately write any of these names for the same
# physical pin. The first entry is the canonical name used in the netlist and,
# where the KiCad symbol names its pins, it matches the real symbol pin name.
_PIN_ALIAS_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("GND", "VSS", "AGND", "DGND", "GROUND", "V-"),
    ("V+", "VCC", "VDD", "VIN", "VI", "VBUS"),
    ("VO", "VOUT", "OUT", "OUTPUT"),
    ("VI", "VIN", "VCC", "INPUT"),
    ("ON", "EN", "ENABLE", "~{ON}/OFF", "ON/OFF"),
    ("A", "ANODE", "AN", "+"),
    ("K", "CATHODE", "CAT", "-"),
    ("REF", "VREF", "ADJ", "FB", "VFB", "SENSE"),
)

# Canonical pin name -> its alias group, built once for fast lookup.
_PIN_ALIAS_LOOKUP: Dict[str, Tuple[str, ...]] = {}
for _group in _PIN_ALIAS_GROUPS:
    for _name in _group:
        _PIN_ALIAS_LOOKUP.setdefault(_name.upper(), _group)


def _pin_aliases(name: str) -> Tuple[str, ...]:
    """Return every accepted spelling of a pin name."""
    canonical = canonicalize_pin_name(name)
    group = _PIN_ALIAS_LOOKUP.get(canonical.upper())
    if group is None:
        group = _PIN_ALIAS_LOOKUP.get(str(name).strip().upper())
    if group is None:
        return (str(name),)
    return group


def canonicalize_pin_name(name: str) -> str:
    """Normalize an LLM-written pin name so it matches a symbol pin name."""
    if not name:
        return ""
    text = name.strip()
    # KiCad overbar syntax for active-low pins, e.g. "~{ON}/OFF".
    if text.startswith("~{") and "}" in text:
        text = text.split("}", 1)[1] or text
    # IN+ / IN- / IN1+ / IN1- variants used by op-amp symbols.
    match = _IPIN_RE.match(text)
    if match:
        idx, sign = match.group(1), match.group(2)
        return f"IN{idx or ''}{sign}"
    upper = text.upper()
    replacements = {
        "+": "P",
        "OUTPUT": "OUT",
        "INPUT": "IN",
        # VCC/VDD/VSS are left as-is so alias groups can map them to whatever
        # the symbol actually calls that pin (V+ on an op-amp, VIN on a
        # regulator); rewriting them here would defeat that lookup.
    }
    return replacements.get(upper, text)


def is_power_net(net_name: str) -> bool:
    """True when a net name denotes a power/ground rail."""
    if not net_name:
        return False
    return net_name.strip().upper() in _POWER_NET_NAMES


def _ic_pinout(mpn: str, symbol: str, value: str) -> Optional[Tuple[Tuple[str, str, PinType], ...]]:
    haystack = " ".join([mpn or "", symbol or "", value or ""]).lower()
    for key, pins in _IC_PINOUTS.items():
        if key in haystack:
            return pins
    return None


# ---------------------------------------------------------------------------
# Resolved component
# ---------------------------------------------------------------------------

def find_pin_in(
    pins: Sequence[Tuple[str, str, PinType]], identifier: str
) -> Optional[Tuple[str, str, PinType]]:
    """
    Locate a pin in a (number, name, type) sequence by number, name or alias.

    Resolution order matters. An exact pin *number* is unambiguous, so it wins
    first; then an exact name; then alias groups, which let a model write
    "VOUT", "OUT" or "VO" for the same physical pin.
    """
    if not identifier:
        return None
    raw = str(identifier).strip()
    if not raw:
        return None
    lowered = raw.lower()

    # 1. Exact pin number.
    for pin in pins:
        if pin[0].lower() == lowered:
            return pin

    # 2. Exact pin name.
    for pin in pins:
        if pin[1].strip().lower() == lowered:
            return pin

    # 3. Alias group.
    for alias in _pin_aliases(raw):
        alias_lower = alias.strip().lower()
        for pin in pins:
            if pin[1].strip().lower() == alias_lower:
                return pin

    # 4. Canonicalized comparison (handles IN+, IN1-, ~{ON}/OFF, ...).
    wanted = canonicalize_pin_name(raw).strip().lower()
    if wanted:
        for pin in pins:
            if canonicalize_pin_name(pin[1]).strip().lower() == wanted:
                return pin

    return None


@dataclass
class ResolvedComponent:
    """A specification component after physical resolution."""

    ref: str
    role: str
    component_type: ComponentType
    value: str
    package: str
    symbol: str
    footprint: str
    pins: List[Tuple[str, str, PinType]]
    mpn: str = ""
    manufacturer: str = ""
    description: str = ""
    reasoning: str = ""
    from_catalog: bool = False
    substituted: bool = False
    notes: List[str] = field(default_factory=list)

    def has_footprint(self) -> bool:
        return bool(self.footprint)

    def pin_numbers(self) -> List[str]:
        return [p[0] for p in self.pins]

    def pin_names(self) -> List[str]:
        return [p[1] for p in self.pins]

    def find_pin(self, identifier: str) -> Optional[Tuple[str, str, PinType]]:
        """Find a pin by number, name, or alias."""
        return find_pin_in(self.pins, identifier)


class DesignatorAssigner:
    """Assigns stable, conventional reference designators (U1, R2, ...)."""

    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}

    def assign(self, component_type: ComponentType) -> str:
        prefix = _DESIGNATOR_PREFIX.get(component_type, "X")
        self._counts[prefix] = self._counts.get(prefix, 0) + 1
        return f"{prefix}{self._counts[prefix]}"

    def reserve(self, ref: str) -> None:
        """Record an externally chosen designator so we never collide with it."""
        match = re.match(r"^([A-Za-z]+)(\d+)$", ref or "")
        if not match:
            return
        prefix, number = match.group(1).upper(), int(match.group(2))
        self._counts[prefix] = max(self._counts.get(prefix, 0), number)


def synthesize_passive_passport(
    component_type: ComponentType, package: str
) -> Tuple[str, str]:
    """
    Return (symbol, footprint) for a passive component.

    Falls back to the most common 0805 land pattern when the package is
    unknown, but records nothing here: the caller decides how to report it.
    """
    canonical = normalize_package(package)
    family = {
        ComponentType.RESISTOR: "resistor",
        ComponentType.CAPACITOR: "capacitor",
        ComponentType.INDUCTOR: "inductor",
    }.get(component_type)

    if family is None:
        return "", ""

    symbol = {
        "resistor": "Device:R",
        "capacitor": "Device:C",
        "inductor": "Device:L",
    }[family]

    footprints = _PASSIVE_FOOTPRINTS[family]
    footprint = footprints.get(canonical)
    if footprint is None:
        footprint = footprints["0805"]
    return symbol, footprint


def resolve_pins(
    component_type: ComponentType,
    mpn: str = "",
    symbol: str = "",
    value: str = "",
) -> List[Tuple[str, str, PinType]]:
    """Return the pin list for a component, or [] when no pinout is known."""
    template = _PIN_TEMPLATES.get(component_type)
    if template is not None:
        return list(template)

    if component_type in _IC_LIKE or component_type is ComponentType.CUSTOM:
        pinout = _ic_pinout(mpn, symbol, value)
        if pinout is not None:
            return list(pinout)

    return []


# ---------------------------------------------------------------------------
# MPN resolution
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: Dict[ComponentType, Tuple[str, ...]] = {
    ComponentType.REGULATOR_LDO: ("regulator_ldo", "regulator"),
    ComponentType.REGULATOR_BUCK: ("regulator_buck", "regulator"),
    ComponentType.REGULATOR_BOOST: ("regulator_boost", "regulator"),
    ComponentType.RESISTOR: ("resistor",),
    ComponentType.CAPACITOR: ("capacitor",),
    ComponentType.INDUCTOR: ("inductor",),
    ComponentType.DIODE: ("diode",),
    ComponentType.LED: ("led",),
    ComponentType.MOSFET: ("mosfet", "transistor"),
    ComponentType.TRANSISTOR: ("transistor",),
    ComponentType.OPAMP: ("opamp", "amplifier"),
    ComponentType.MICROCONTROLLER: ("microcontroller", "mcu"),
    ComponentType.CRYSTAL: ("crystal",),
}


@dataclass
class MPNResolution:
    """Outcome of resolving one requested MPN against the database."""

    requested_mpn: str
    resolved: Optional[Any] = None
    substituted: bool = False
    note: str = ""


def resolve_mpn(
    component_type: ComponentType,
    requested_mpn: str,
    database: Any,
    package: str = "",
    value: str = "",
) -> MPNResolution:
    """
    Resolve an LLM-requested MPN against the component database.

    Returns the exact catalog entry when it exists. When it does not, attempts
    a category search so the design still gets a real, purchasable part, and
    records that a substitution happened.
    """
    if database is None:
        return MPNResolution(requested_mpn=requested_mpn, note="no component database available")

    if requested_mpn:
        exact = database.get_by_mpn(requested_mpn)
        if exact is not None:
            return MPNResolution(requested_mpn=requested_mpn, resolved=exact)

    # Try a category match, preferring the requested package and value.
    for category in _CATEGORY_KEYWORDS.get(component_type, ()):
        # A component template that matches the requested value and package
        # exactly is the best answer available: its symbol and footprint have
        # been checked against the rest of the pipeline. Searching the catalogue
        # first would return whichever real part ranks highest, which for
        # "10uF 0805" was a 0402 capacitor.
        template = None
        if value:
            try:
                template = database.find_template(
                    category, value=value, package=package or None
                )
                if template is None:
                    template = database.find_template(category, value=value)
            except Exception:  # pragma: no cover - defensive against DB quirks
                template = None
        if template is not None:
            return MPNResolution(
                requested_mpn=requested_mpn,
                resolved=template,
                substituted=True,
                note=(
                    f"MPN '{requested_mpn}' not in catalog; using the component "
                    f"template for {template.value} {template.package} "
                    f"(value + package match)"
                ),
            )

        # Otherwise search the catalogue *by value*, so the candidates are
        # relevant rather than whatever the category happens to rank first.
        # Searching for "Green" among LEDs only works if the value is passed
        # through: a blind category scan returns an arbitrary colour.
        try:
            candidates = database.search(
                query=value or "",
                category=category,
                package=package or None,
                limit=25,
            )
            if not candidates and value:
                candidates = database.search(category=category, limit=25)
        except Exception:  # pragma: no cover - defensive against DB quirks
            candidates = []
        if not candidates:
            continue

        canonical_package = normalize_package(package)
        wanted_value = (value or "").strip().lower()

        def value_matches(candidate: Any) -> bool:
            """Match the requested value against value/description/attributes."""
            if not wanted_value:
                return False
            haystack = " ".join(
                [
                    str(getattr(candidate, "value", "")),
                    str(getattr(candidate, "description", "")),
                    " ".join(str(v) for v in (getattr(candidate, "attributes", {}) or {}).values()),
                ]
            ).lower()
            return wanted_value in haystack

        # Best: same value/description and same package.
        for candidate in candidates:
            if value_matches(candidate) and (
                not canonical_package
                or normalize_package(getattr(candidate, "package", "")) == canonical_package
            ):
                return MPNResolution(
                    requested_mpn=requested_mpn,
                    resolved=candidate,
                    substituted=True,
                    note=(
                        f"MPN '{requested_mpn}' not in catalog; substituted "
                        f"{candidate.mpn} (value + package match)"
                    ),
                )

        # Next: same value/description, any package.
        for candidate in candidates:
            if value_matches(candidate):
                return MPNResolution(
                    requested_mpn=requested_mpn,
                    resolved=candidate,
                    substituted=True,
                    note=(
                        f"MPN '{requested_mpn}' not in catalog; substituted "
                        f"{candidate.mpn} (value match)"
                    ),
                )

        # Next: same package.
        if canonical_package:
            for candidate in candidates:
                if normalize_package(getattr(candidate, "package", "")) == canonical_package:
                    return MPNResolution(
                        requested_mpn=requested_mpn,
                        resolved=candidate,
                        substituted=True,
                        note=(
                            f"MPN '{requested_mpn}' not in catalog; substituted "
                            f"{candidate.mpn} (package match)"
                        ),
                    )

        return MPNResolution(
            requested_mpn=requested_mpn,
            resolved=candidates[0],
            substituted=True,
            note=(
                f"MPN '{requested_mpn}' not in catalog; substituted "
                f"{candidates[0].mpn} (category match)"
            ),
        )

    note = f"MPN '{requested_mpn}' not in catalog and no substitute found"
    return MPNResolution(requested_mpn=requested_mpn, note=note)


__all__ = [
    "DesignatorAssigner",
    "MPNResolution",
    "ResolvedComponent",
    "canonicalize_pin_name",
    "find_pin_in",
    "infer_component_type",
    "is_power_net",
    "normalize_package",
    "resolve_mpn",
    "resolve_pins",
    "role_to_component_type",
    "synthesize_passive_passport",
]
