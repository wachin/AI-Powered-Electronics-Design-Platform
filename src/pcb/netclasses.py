"""
Per-net trace widths, and the KiCad project settings that carry them.

Why this exists
---------------
The generated board had **no net classes at all**. The project file set
``board.design_settings.defaults.track_width = 0.25``, which looks like a width
setting and is not one: it is the default for *interactive* routing in the GUI.
With no ``net_settings`` block, KiCad falls back to its built-in Default class of
0.2 mm and hands that to the router. So every net — including the 1 A output of a
regulator — was routed at 0.2 mm, which carries about 0.74 A on 1 oz outer copper
at a 10 °C rise. Verified by experiment: a project with
``defaults.track_width = 0.33`` and no net classes produced a Specctra DSN
carrying ``(width 200)``.

A 0.2 mm trace on a 1 A net is not a cosmetic problem. It is a resistor that
heats up, and the failure — intermittent resets, a browned board — appears only
under load, after the boards are made.

How the width is chosen
-----------------------
IPC-2221's empirical relation, the industry default for sizing a trace for a
current::

    I = k · ΔT^0.44 · A^0.725

with ``I`` in amps, ``A`` the copper cross-section in mils², ``ΔT`` the allowed
temperature rise in °C, and ``k`` = 0.048 for an outer layer and 0.024 for an
inner one. Rearranged for a required current::

    A = (I / (k · ΔT^0.44))^(1 / 0.725)
    width_mil = A / (copper_oz · 1.378)

IPC-2152 is the newer standard and is less conservative; IPC-2221 is used here
because erring towards a wider trace costs nothing and erring narrow costs a
board. The two agree closely for the currents this platform generates.

The decision the caller makes is which *class* a net belongs to; the width
follows from the class. Nothing here inspects geometry, so it cannot tell that a
wide trace will not fit between two pads. It states the width the current needs
and leaves the router to fail loudly if that is impossible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# IPC-2221
# ---------------------------------------------------------------------------

# Empirical constants, outer and inner layers.
IPC2221_K_EXTERNAL = 0.048
IPC2221_K_INTERNAL = 0.024
# One ounce of copper, spread over a square inch, is 1.378 mil thick.
MIL_PER_OUNCE = 1.378
# The conventional allowed temperature rise for a conservative design.
DEFAULT_TEMPERATURE_RISE_C = 10.0

# The narrowest trace this platform will ask for. JLCPCB can etch 0.10 mm on
# 1 oz 1-2 layer boards, but 0.2 mm is what KiCad's own Default class uses and
# what leaves margin for etching tolerance.
MIN_TRACE_WIDTH_MM = 0.20


def trace_width_mm(
    current_a: float,
    temperature_rise_c: float = DEFAULT_TEMPERATURE_RISE_C,
    external: bool = True,
    copper_oz: float = 1.0,
) -> float:
    """
    The trace width needed to carry a current, in millimetres (IPC-2221).

    Args:
        current_a: The current the trace must carry, in amps.
        temperature_rise_c: Allowed temperature rise above ambient.
        external: True for an outer layer, False for an inner one. An inner
            trace cannot dissipate heat into air and needs about twice the
            copper, which is why ``k`` halves.
        copper_oz: Copper weight. 1 oz on a hobby board; 2 oz for high current.

    Returns:
        The width in millimetres, never below :data:`MIN_TRACE_WIDTH_MM`.

    A current of zero returns the minimum width rather than zero: a trace is
    still a trace.
    """
    if current_a <= 0:
        return MIN_TRACE_WIDTH_MM
    if copper_oz <= 0:
        raise ValueError("copper weight must be positive")
    if temperature_rise_c <= 0:
        raise ValueError("temperature rise must be positive")

    k = IPC2221_K_EXTERNAL if external else IPC2221_K_INTERNAL
    area_mils2 = (current_a / (k * temperature_rise_c**0.44)) ** (1 / 0.725)
    width_mil = area_mils2 / (copper_oz * MIL_PER_OUNCE)
    width_mm = width_mil * 0.0254
    return max(width_mm, MIN_TRACE_WIDTH_MM)


def current_capacity_a(
    width_mm: float,
    temperature_rise_c: float = DEFAULT_TEMPERATURE_RISE_C,
    external: bool = True,
    copper_oz: float = 1.0,
) -> float:
    """
    The current a trace of a given width can carry (IPC-2221).

    The inverse of :func:`trace_width_mm`, used to state the capacity of a class
    so the choice can be checked rather than trusted.
    """
    if width_mm <= 0:
        return 0.0
    k = IPC2221_K_EXTERNAL if external else IPC2221_K_INTERNAL
    area_mils2 = (width_mm / 0.0254) * copper_oz * MIL_PER_OUNCE
    return k * temperature_rise_c**0.44 * area_mils2**0.725


# ---------------------------------------------------------------------------
# Net classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetClass:
    """A KiCad net class, as this platform defines it."""

    name: str
    track_width: float
    clearance: float
    via_diameter: float
    via_drill: float
    priority: int = 0
    description: str = ""

    def capacity_a(self, external: bool = True) -> float:
        """The current this class's width can carry."""
        return current_capacity_a(self.track_width, external=external)

    def to_kicad(self) -> Dict[str, Any]:
        """
        The class as KiCad writes it in a project file.

        Every field is present because KiCad writes every field; omitting them
        makes the file look hand-made and risks a version-dependent default.
        """
        return {
            "bus_width": 12,
            "clearance": round(self.clearance, 4),
            "diff_pair_gap": 0.25,
            "diff_pair_via_gap": 0.25,
            "diff_pair_width": 0.2,
            "line_style": 0,
            "microvia_diameter": 0.3,
            "microvia_drill": 0.1,
            "name": self.name,
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "priority": self.priority,
            "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": round(self.track_width, 4),
            "via_diameter": round(self.via_diameter, 4),
            "via_drill": round(self.via_drill, 4),
            "wire_width": 6,
        }


DEFAULT_CLASS = NetClass(
    name="Default",
    track_width=0.25,
    clearance=0.20,
    via_diameter=0.8,
    via_drill=0.4,
    # KiCad gives the Default class the largest possible priority and expects it
    # to be first in the list.
    priority=2147483647,
    description="Anything that is not a power net.",
)

SIGNAL_CLASS = NetClass(
    name="SIG",
    track_width=0.25,
    clearance=0.20,
    via_diameter=0.8,
    via_drill=0.4,
    priority=1,
    description="Signal nets.",
)

# 0.6 mm carries about 1.65 A on 1 oz outer copper at a 10 C rise, which is a
# 65 % margin over the 1 A this platform's designs regulate. A 2-layer board
# routes only on outer layers, so that is the case sized for.
POWER_CLASS = NetClass(
    name="PWR",
    track_width=0.6,
    clearance=0.25,
    via_diameter=1.0,
    via_drill=0.5,
    priority=0,
    description="Power and ground.",
)

# For a rail above 1.2 A, or any design that may be built on more than two
# layers, where the same width has to carry the current on an inner layer.
HIGH_POWER_CLASS = NetClass(
    name="PWR_HI",
    track_width=0.8,
    clearance=0.30,
    via_diameter=1.2,
    via_drill=0.6,
    priority=0,
    description="Rails above 1.2 A, or routing on inner layers.",
)

# The current above which the high-power class is used instead.
HIGH_POWER_THRESHOLD_A = 1.2


def class_for_current(current_a: float, layers: int = 2) -> NetClass:
    """
    The narrowest class that comfortably carries a current.

    On a board with more than two layers an inner trace is assumed, because the
    same net may route there, and inner traces need roughly twice the copper.
    Guessing wrong in that direction costs a little board area; guessing wrong
    the other way costs the board.
    """
    if layers > 2 and current_a > 0:
        return HIGH_POWER_CLASS
    if current_a > HIGH_POWER_THRESHOLD_A:
        return HIGH_POWER_CLASS
    if current_a > 0:
        return POWER_CLASS
    return SIGNAL_CLASS


def build_net_settings(
    assignments: Dict[str, str],
    layers: int = 2,
    extra_classes: Sequence[NetClass] = (),
) -> Dict[str, Any]:
    """
    Build the ``net_settings`` block of a KiCad project file.

    Args:
        assignments: Net name -> class name. Kept explicit rather than using
            KiCad's regex patterns, because net names are not regex-safe:
            ``+5V`` and ``Net-(D1-K)`` would need escaping, and a pattern that
            escapes wrongly silently classifies the wrong net.
        layers: Copper layer count, used only to decide which classes exist.
        extra_classes: Additional classes to declare.

    Returns:
        The dictionary to place under the ``net_settings`` key. The Default
        class is always first, as KiCad expects.
    """
    classes: List[NetClass] = [DEFAULT_CLASS]
    known = {DEFAULT_CLASS.name}

    wanted = set(assignments.values())
    for candidate in (SIGNAL_CLASS, POWER_CLASS, HIGH_POWER_CLASS, *extra_classes):
        if candidate.name in wanted and candidate.name not in known:
            classes.append(candidate)
            known.add(candidate.name)

    # Only assign nets whose class was actually declared, so the file cannot
    # reference a class that does not exist.
    net_assignments = {
        net: class_name
        for net, class_name in assignments.items()
        if class_name in known and class_name != DEFAULT_CLASS.name
    }

    return {
        "classes": [cls.to_kicad() for cls in classes],
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": net_assignments or None,
        "netclass_patterns": [],
    }


def netclass_assignments(
    nets: Iterable[Any],
    power_domains: Optional[Dict[str, Any]] = None,
    layers: int = 2,
) -> Dict[str, str]:
    """
    Decide which class each net belongs to.

    Ground and any net the design marks as a power rail get a power class; every
    other net gets the signal class. A rail's declared maximum current is used
    when the design states one, so a 2 A rail is not sized like a 0.2 A one.

    Nets with no name are skipped rather than guessed at. An unassigned net keeps
    KiCad's Default class, which is a width this platform has chosen rather than
    an accident.
    """
    domains = power_domains or {}
    assignments: Dict[str, str] = {}

    for net in nets:
        name = getattr(net, "name", None) or (net if isinstance(net, str) else "")
        name = str(name).strip()
        if not name:
            continue

        is_power = bool(getattr(net, "is_power", False))
        if not is_power and name.upper() in ("GND", "GROUND", "VSS", "0V"):
            is_power = True

        if not is_power:
            assignments[name] = SIGNAL_CLASS.name
            continue

        current = _declared_current(name, net, domains)

        # A power net is a power net even when the design states no current for
        # it. Falling back to the signal class here would give a 1 A rail a
        # 0.25 mm trace — the exact failure this module exists to prevent.
        if layers > 2 or current > HIGH_POWER_THRESHOLD_A:
            assignments[name] = HIGH_POWER_CLASS.name
        else:
            assignments[name] = POWER_CLASS.name

    return assignments


def _declared_current(name: str, net: Any, domains: Dict[str, Any]) -> float:
    """
    The maximum current declared for a power net, or 0 if none was.

    Three lookups, because a design rarely names a rail and its power domain the
    same thing: the net name, then the net's voltage against each domain's
    voltage. Getting this wrong is not harmless — an unstated current is treated
    as small, and a small current earns a thin trace.
    """
    for key in (name, name.upper(), name.lstrip("+").upper()):
        domain = domains.get(key)
        if domain is not None:
            current = _domain_current(domain)
            if current:
                return current

    net_voltage = getattr(net, "voltage", None)
    if not isinstance(net_voltage, (int, float)):
        return 0.0
    for domain in domains.values():
        domain_voltage = (
            domain.get("voltage") if isinstance(domain, dict)
            else getattr(domain, "voltage", None)
        )
        if not isinstance(domain_voltage, (int, float)):
            continue
        # A rail and its domain agree to within a tolerance; 5.0 and 5 are the
        # same rail written two ways.
        if abs(float(domain_voltage) - float(net_voltage)) < 0.05:
            current = _domain_current(domain)
            if current:
                return current
    return 0.0


def _domain_current(domain: Any) -> float:
    """Read a maximum current from a power domain, in amps."""
    if isinstance(domain, dict):
        raw = domain.get("max_current_ma", domain.get("max_current_a"))
    else:
        raw = getattr(domain, "max_current_ma", None)
    try:
        value = float(raw or 0.0)
    except (TypeError, ValueError):
        return 0.0
    # The attribute is in milliamps; a value large enough to be amps is assumed
    # to be amps, because a design will not ask for 5000 mA through one trace
    # without meaning it.
    return value / 1000.0 if value > 10 else value


def width_shortfalls(
    routed_widths: Dict[str, float],
    assignments: Dict[str, str],
    tolerance: float = 0.001,
) -> List[str]:
    """
    Nets the router laid down narrower than their class requires.

    The platform asks for a width and then has to check it got one. FreeRouting
    was observed narrowing two segments of a 0.6 mm power net to 0.45 mm where
    the wider trace did not fit; a narrower trace is not necessarily a fault, but
    it *is* a different current capacity than the one the design was checked
    against, so it has to be reported rather than assumed away.

    Args:
        routed_widths: The narrowest track width actually laid, per net, in mm.
        assignments: Net name -> class name, as passed to :func:`build_net_settings`.
        tolerance: Slack allowed before a width counts as short, in mm.

    Returns:
        One message per short net. Empty when every net got its width or was not
        routed at all.
    """
    required = {cls.name: cls.track_width for cls in (SIGNAL_CLASS, POWER_CLASS, HIGH_POWER_CLASS)}
    messages: List[str] = []
    for net, class_name in sorted(assignments.items()):
        actual = routed_widths.get(net)
        expected = required.get(class_name)
        if actual is None or expected is None:
            continue
        if actual + tolerance < expected:
            capacity = current_capacity_a(actual)
            messages.append(
                f"{net} was routed at {actual:g} mm but its {class_name} class asks "
                f"for {expected:g} mm; {actual:g} mm carries about {capacity:.2f} A "
                f"on 1 oz copper at a 10 °C rise. Check the current this net "
                f"carries."
            )
    return messages


def describe_netclasses(assignments: Dict[str, str], layers: int = 2) -> List[str]:
    """
    One line per class, stating its width and the current that width carries.

    Returned so a design can report *why* a width was chosen. A width with no
    stated capacity is a number the reader has to take on trust.
    """
    wanted = set(assignments.values())
    lines: List[str] = []
    for cls in (SIGNAL_CLASS, POWER_CLASS, HIGH_POWER_CLASS):
        if cls.name not in wanted:
            continue
        external = layers <= 2
        capacity = cls.capacity_a(external=external)
        where = "outer layer" if external else "inner layer"
        lines.append(
            f"{cls.name}: {cls.track_width:g} mm track, {cls.clearance:g} mm "
            f"clearance — carries {capacity:.2f} A on 1 oz copper at a 10 °C rise "
            f"({where})"
        )
    return lines
