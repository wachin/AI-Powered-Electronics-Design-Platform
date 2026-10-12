"""
Parsing of electronic values and the parametric attributes a catalog provides.

Why this exists
---------------
A component catalog stores specifications as human-readable strings:
``"10kΩ"``, ``"100nF"``, ``"±0.1%"``, ``"100mW"``, ``"40V"``. Searching those
with a substring match is wrong in a way that matters: ``LIKE '%10k%'`` also
matches ``110kΩ`` and ``910kΩ``, so a "10k resistor" query happily returns a
910k part.

This module turns those strings into numbers with a unit, so:

* a search for 10k matches 10k exactly, not 110k;
* parts can be compared by value, tolerance and rating;
* a substitute can be found by specification rather than by luck.

Parsing is deliberately forgiving for catalog data and strict for user queries.
A user typing ``esp32`` must not be read as the number 32, while a catalog cell
reading ``±200ppm/℃`` should still yield its magnitude.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# SI prefixes, as used in component values
# ---------------------------------------------------------------------------

# Multipliers relative to the base unit. `k` and `K` both mean 1000 in practice.
# `m` is ambiguous (milli vs mega) and is resolved by case: lower-case `m` after
# a number is milli, `M` is mega. Component values never use a bare `m` for mega.
_PREFIXES: Dict[str, float] = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,   # Greek mu, a common variant
    "m": 1e-3,
    "c": 1e-2,   # centi, occasionally seen in capacitance values
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

# A digit string, an optional SI prefix, an optional trailing digit, an optional
# unit. "10k"     -> 10, k, "", ""      -> 10000
# "1M0"          -> 1,  M, "0", ""     -> 1e6
# "100nF"        -> 100, n, "", "F"    -> 1e-7 F
# "3.3V"         -> 3.3, "", "", "V"
_NUMBER_RE = re.compile(
    r"^(?P<number>\d+(?:[.,]\d+)?)"
    r"\s*(?P<prefix>[pnuµμmcKkMG])?"
    r"\s*(?P<trail>\d*)"
    r"\s*(?P<unit>[a-zA-ZΩµμ]*)$"
)

# "4R7" -> 4.7 and "1R0" -> 1.0, the notation used for sub-ohm resistors.
_R_NOTATION_RE = re.compile(r"^(?P<whole>\d*)[Rr](?P<frac>\d+)$")

# Unit spellings seen in catalog data.
_UNIT_ALIASES: Dict[str, str] = {
    "Ω": "ohm",
    "OHM": "ohm",
    "OHMS": "ohm",
    "R": "ohm",
    "F": "F",
    "FARAD": "F",
    "H": "H",
    "HENRY": "H",
    "V": "V",
    "VOLT": "V",
    "VOLTS": "V",
    "A": "A",
    "AMP": "A",
    "AMPS": "A",
    "W": "W",
    "WATT": "W",
    "WATTS": "W",
    "HZ": "Hz",
    "KHZ": "Hz",
    "MHZ": "Hz",
    "GHZ": "Hz",
    "S": "s",
    "SEC": "s",
}

# Which quantity a unit measures. Used to compare like with like: a parsed
# 1e-7 with unit "F" is a capacitance, and must never be compared against a
# 1e-7 inductance.
UNIT_FAMILY: Dict[str, str] = {
    "ohm": "resistance",
    "F": "capacitance",
    "H": "inductance",
    "Hz": "frequency",
}

# Units that describe a limit rather than the part's identity. A query for
# "50V" on a capacitor means "rated at least 50 V", not "is a 50 V part".
RATING_UNITS = frozenset({"V", "A", "W"})


@dataclass(frozen=True)
class ParsedValue:
    """A numeric value with its unit, plus the text it came from."""

    value: float
    unit: str
    raw: str = ""

    @property
    def family(self) -> Optional[str]:
        """The measured quantity, or None when the unit does not imply one."""
        return UNIT_FAMILY.get(self.unit)

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.value:g} {self.unit}".strip()


def parse_value(text: Any, strict: bool = False) -> Optional[ParsedValue]:
    """
    Parse an electronic value string into a number and unit.

    Understands ``10kΩ``, ``4R7``, ``100nF``, ``2.2uF``, ``40V``, ``100mW``,
    ``1M0``, ``±0.1%`` (the sign is dropped) and plain numbers.

    Args:
        text: The value to parse.
        strict: When true, the whole string must be a value. This is what query
            parsing uses, so that ``esp32`` is not read as the number 32. When
            false (the default, for catalog cells) the first number in a longer
            string is used instead of giving up.

    Returns:
        A :class:`ParsedValue`, or ``None`` when no number can be read. Callers
        should fall back to text search rather than treating that as zero.
    """
    if text is None:
        return None
    if isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        return ParsedValue(value=float(text), unit="", raw=str(text))

    raw = str(text).strip()
    if not raw or raw in {"-", "—", "N/A", "n/a", "null", "None"}:
        return None

    # Tolerances and other signed values: keep the magnitude so that "+/-1%"
    # and "±1%" compare equal. Strip units of measure that would confuse the
    # grammar ("100mW@10mA", "0.1uF/16V").
    cleaned = raw.replace("±", "").replace("+/-", "").replace("+", "").strip()
    cleaned = cleaned.split("@")[0].split("/")[0].strip()
    percent = cleaned.endswith("%")
    if percent:
        cleaned = cleaned[:-1].strip()
    cleaned = cleaned.replace(" ", "")

    if not cleaned:
        return None

    # Try the R-notation first: "4R7" is 4.7 ohm, not 4 with unit "R".
    # "ppm" is parts per million. Without this it would be read as the prefix
    # "p" followed by the unit "pm", turning 200 ppm into 2e-10.
    for suffix in ("ppm", "PPM"):
        if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
            head = cleaned[: -len(suffix)].rstrip(".")
            try:
                return ParsedValue(value=float(head), unit="ppm", raw=raw)
            except ValueError:
                break

    match = _R_NOTATION_RE.match(cleaned)
    if match:
        whole = match.group("whole") or "0"
        return ParsedValue(
            value=float(f"{whole}.{match.group('frac')}"), unit="ohm", raw=raw
        )

    match = _NUMBER_RE.match(cleaned)
    if match is not None:
        number = match.group("number").replace(",", ".")
        trail = match.group("trail") or ""
        prefix = match.group("prefix")
        if trail:
            # "1M0" and "4k7" carry a single trailing digit as a decimal place.
            # A run of three or more digits is a part number ("1n4148"), not a
            # value, so it is not treated as one.
            if len(trail) > 2:
                if strict:
                    return None
                trail = ""
            else:
                number = f"{number}.{trail}"
        try:
            value = float(number)
        except ValueError:
            return None
        if prefix:
            value *= _PREFIXES.get(prefix, 1.0)

        if percent:
            unit = "%"
        else:
            unit_text = (match.group("unit") or "").upper()
            unit = _UNIT_ALIASES.get(unit_text, unit_text.lower() if unit_text else "")
        return ParsedValue(value=value, unit=unit, raw=raw)

    if strict:
        return None

    # Last resort for catalog cells: pull the first number out of the string.
    number_match = re.search(r"(\d+(?:[.,]\d+)?)", cleaned)
    if not number_match:
        return None
    try:
        value = float(number_match.group(1).replace(",", "."))
    except ValueError:
        return None
    unit = "%" if percent else ""
    return ParsedValue(value=value, unit=unit, raw=raw)


def parse_tolerance(text: Any) -> Optional[float]:
    """
    Parse a tolerance like ``±1%`` or ``±0.1%`` into a fraction (0.01, 0.001).

    Used to decide whether a substitute is at least as accurate as the original.
    """
    parsed = parse_value(text)
    if parsed is None:
        return None
    value = abs(parsed.value)
    if parsed.unit == "%" or "%" in str(text):
        return value / 100.0
    if value == 0:
        return None
    # A tolerance given as a bare number is a fraction already.
    return value if value <= 1 else value / 100.0


# ---------------------------------------------------------------------------
# Attribute extraction
# ---------------------------------------------------------------------------

# Canonical field -> the catalog keys that may hold it, in priority order.
# Catalog keys differ per category and drift between builds, so several are
# accepted. Keys are matched exactly; add new spellings here as they appear.
_ATTRIBUTE_KEYS: Dict[str, Tuple[str, ...]] = {
    "resistance": ("Resistance", "Resistance Value"),
    "capacitance": ("Capacitance",),
    "inductance": ("Inductance", "Inductance Value"),
    "frequency": ("Frequency", "Frequency - Self Resonant"),
    "tolerance": ("Tolerance",),
    "power": ("Power(Watts)", "Pd - Power Dissipation", "Power Dissipation"),
    "voltage": (
        "Voltage Rating",
        "Voltage - DC Reverse(Vr)",
        "Voltage - Rated",
        "Voltage - Breakdown",
        "Drain to Source Voltage",
        "Collector - Emitter Voltage VCEO",
    ),
    "current": (
        "Current - Rectified",
        "Current Rating",
        "Rated Current",
        "Current - Continuous Drain(Id)",
        "Current - Collector(Ic)",
    ),
    "output_voltage": ("Output Voltage", "Voltage - Output", "Voltage - Output(Fixed)"),
    "supply_voltage": ("Voltage - Supply", "Voltage - Supply(Max)", "Voltage-Supply(Max)"),
    "output_current": ("Output Current", "Current - Output"),
    "temperature_coefficient": ("Temperature Coefficient",),
    "temperature_range": ("Operating Temperature",),
    "type": ("Type", "Diode Configuration", "Topology", "Function"),
    "forward_voltage": ("Voltage - Forward(Vf@If)", "Voltage - Forward(Vf)"),
    "zener_voltage": ("Zener Voltage(Nom)",),
    "rds_on": ("RDS(on)",),
    # Text fields that describe what a part is rather than how much of something
    # it has. They matter for matching: an LED's colour is the property a design
    # asks for ("a green indicator LED"), and without it any LED looks the same.
    "illumination_color": ("Illumination Color",),
    "lens_color": ("Lens Color",),
    "wavelength": ("Wavelength - Dominant", "Peak Wavelength"),
    "luminous_intensity": ("Luminous Intensity",),
    "viewing_angle": ("Viewing Angle",),
    "mounting_type": ("Mounting Type",),
}

# Which canonical family a category is primarily described by. Used to match
# "the same part" without the caller having to know the category. Keyed on the
# platform's internal category name, which is stable across catalogue rebuilds.
_PRIMARY_FIELD: Dict[str, str] = {
    "resistor": "resistance",
    "capacitor": "capacitance",
    "inductor": "inductance",
    "crystal": "frequency",
    "oscillator": "frequency",
    "regulator_ldo": "output_voltage",
    "regulator_buck": "output_voltage",
    "regulator_boost": "output_voltage",
    "regulator_switching": "output_voltage",
    "voltage_reference": "output_voltage",
    "zener": "zener_voltage",
}

# Internal category guessed from the parsed attributes alone. Used only when the
# catalogue row carries neither a usable category nor a usable description,
# which is true for about 67,000 rows.
_CATEGORY_FROM_ATTRIBUTES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("crystal", ("frequency",)),
    ("resistor", ("resistance",)),
    ("capacitor", ("capacitance",)),
    ("inductor", ("inductance",)),
    ("zener", ("zener_voltage",)),
    ("power_management", ("output_voltage",)),
    ("mosfet", ("rds_on",)),
)

# Fields holding a number-with-unit to be parsed rather than kept as text.
_NUMERIC_FIELDS = frozenset(
    {
        "resistance",
        "capacitance",
        "inductance",
        "frequency",
        "tolerance",
        "power",
        "voltage",
        "current",
        "output_voltage",
        "supply_voltage",
        "output_current",
        "forward_voltage",
        "zener_voltage",
        "rds_on",
    }
)


# Reverse index of _ATTRIBUTE_KEYS: catalogue key -> (field, priority). Built
# once so that parsing walks the row's own keys (six or so) instead of probing
# every known key (eighteen) for every one of the ~55,000 indexed rows.
_KEY_TO_FIELD: Dict[str, Tuple[str, int]] = {}
for _field_name, _candidate_keys in _ATTRIBUTE_KEYS.items():
    for _priority, _key in enumerate(_candidate_keys):
        _KEY_TO_FIELD[_key] = (_field_name, _priority)
del _field_name, _candidate_keys, _priority, _key

_UNUSABLE = (None, "", "N/A")


def extract_parameters(attributes: Any, category: str = "") -> Dict[str, Any]:
    """
    Turn a catalog ``attributes`` JSON object into comparable parameters.

    Returns a dictionary containing, where available:

    * ``resistance`` / ``capacitance`` / ``inductance`` / ``frequency`` — in base
      units (ohms, farads, henries, hertz)
    * ``tolerance`` — a fraction, e.g. ``0.01`` for ±1%
    * ``power`` (W), ``voltage`` (V), ``current`` (A), ``output_voltage`` (V)
    * ``primary_field`` and ``primary`` — the value that identifies this part
      within its category, so callers can compare parts without knowing whether
      they are looking at a resistor or a capacitor
    * ``raw`` — the original attributes, kept for display and debugging

    Unparseable fields are omitted. Nothing is guessed: if a cell cannot be read
    the field is simply absent, and callers must treat that as "unknown" rather
    than as zero.
    """
    if isinstance(attributes, (str, bytes, bytearray)):
        import json

        text = attributes.decode() if isinstance(attributes, (bytes, bytearray)) else attributes
        try:
            attributes = json.loads(text)
        except (TypeError, ValueError):
            return {}
    if not isinstance(attributes, dict):
        return {}

    params: Dict[str, Any] = {}

    # Walk the row's own keys rather than probing every known key. When a
    # category carries two spellings of the same field, the one listed first in
    # _ATTRIBUTE_KEYS wins.
    selected: Dict[str, Tuple[int, Any]] = {}
    for key, raw_value in attributes.items():
        entry = _KEY_TO_FIELD.get(key)
        if entry is None or raw_value in _UNUSABLE:
            continue
        field_name, priority = entry
        current = selected.get(field_name)
        if current is None or priority < current[0]:
            selected[field_name] = (priority, raw_value)

    for field, (_priority, raw_value) in selected.items():
        if field in _NUMERIC_FIELDS:
            if field == "tolerance":
                # parse_tolerance already returns a fraction, not a ParsedValue.
                tolerance = parse_tolerance(raw_value)
                if tolerance is not None:
                    params[field] = tolerance
            else:
                parsed = parse_value(raw_value)
                if parsed is not None:
                    params[field] = parsed.value
        else:
            params[field] = str(raw_value)

    if not params:
        # Nothing recognisable. Returning {} rather than {"raw": ...} keeps
        # "has parameters" an honest question.
        return {}

    set_primary(params, category)
    params["raw"] = attributes
    return params


def set_primary(params: Dict[str, Any], category: str) -> None:
    """
    Record which value identifies this part within its category.

    Applied separately from :func:`extract_parameters` because the category is
    sometimes only known *after* the attributes have been parsed — about 67,000
    catalogue rows have no category of their own and are classified from their
    attributes. Without this second pass those parts would have a category but
    no identity value, and would drop out of substitute matching.
    """
    if "primary_field" in params:
        return
    primary_field = _PRIMARY_FIELD.get(category)
    if primary_field and primary_field in params:
        params["primary_field"] = primary_field
        params["primary"] = params[primary_field]


def values_match(
    a: Optional[float],
    b: Optional[float],
    tolerance: float = 0.0,
) -> bool:
    """
    Compare two parsed values, allowing a relative tolerance.

    ``tolerance=0`` requires an exact match, which is what you want when
    replacing a resistor: 10k is not a substitute for 12k. Catalog strings are
    written many ways (``4.7kΩ``, ``4700Ω``, ``4K7``) but parse to the same
    number, so an exact comparison of parsed values is still forgiving of
    formatting. A tiny relative tolerance absorbs float noise.
    """
    if a is None or b is None:
        return False
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    if scale == 0:
        return False
    allowed = max(abs(b) * tolerance, scale * 1e-9)
    return abs(a - b) <= allowed


# Engineering notation, so that 1e-07 farads reads as "100n" and 1e6 hertz as
# "1M". Index 0 is the base unit; each step is a factor of 1000.
_SI_STEPS: Tuple[Tuple[float, str], ...] = (
    (1e9, "G"),
    (1e6, "M"),
    (1e3, "k"),
    (1.0, ""),
    (1e-3, "m"),
    (1e-6, "u"),
    (1e-9, "n"),
    (1e-12, "p"),
)


def format_value(value: Optional[float], unit: str = "") -> str:
    """
    Format a number the way an engineer writes it: 100n, 10k, 8M, 4.7.

    Used for display only. Never parse the output of this function back into a
    number; it is lossy about significant figures by design.
    """
    if value is None:
        return ""
    if value == 0:
        return f"0 {unit}".strip()
    magnitude = abs(value)
    for scale, prefix in _SI_STEPS:
        if magnitude >= scale:
            scaled = value / scale
            text = f"{scaled:.3f}".rstrip("0").rstrip(".")
            return f"{text}{prefix}{unit}"
    return f"{value:g}{unit}"


def category_from_parameters(
    params: Dict[str, Any], current: str = "unknown", package: str = ""
) -> str:
    """
    Fill in a category from the parsed attributes when the catalogue has none.

    Rows with no category and no description are not rare in this catalogue —
    about 67,000 of them — but many still carry an unambiguous ``Resistance`` or
    ``Capacitance`` attribute. Deriving the category from that is far better than
    leaving the part uncategorised, which would give it the wrong symbol.

    ``frequency`` is deliberately not used: an RF module also has a frequency
    attribute, and calling a module a crystal would give it the wrong symbol. It
    is only accepted for packages that actually look like a resonator.
    """
    if current and current != "unknown":
        return current

    if "frequency" in params and any(
        hint in package.lower()
        for hint in ("hc-49", "3225", "5032", "2520", "2016", "7050", "crystal", "xtal")
    ):
        return "crystal"

    for category, fields in _CATEGORY_FROM_ATTRIBUTES:
        if category == "crystal":
            continue
        if any(field in params for field in fields):
            return category
    return current


__all__ = [
    "RATING_UNITS",
    "UNIT_FAMILY",
    "ParsedValue",
    "category_from_parameters",
    "extract_parameters",
    "format_value",
    "parse_tolerance",
    "parse_value",
    "set_primary",
    "values_match",
]
