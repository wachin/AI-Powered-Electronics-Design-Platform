"""
Parametric search over the component catalog.

The problem this solves
-----------------------
A user asking for "10k 0603" wants 10 kΩ parts in a 0603 package. A catalog
stores that as the text ``"10kΩ"`` in a JSON attribute, so the naive query

.. code-block:: sql

    WHERE description LIKE '%10k%'

also returns ``110kΩ`` and ``910kΩ``. Wrong parts in a bill of materials are
expensive to discover after the boards arrive, so the search has to be numeric.
The catalog is also far too large to filter row by row in Python on every
keystroke: the values have to be parsed once and kept.

How it works
------------
:func:`parse_query` splits a query into three kinds of thing:

* a **value** — ``10k``, ``100nF``, ``8MHz``, ``4R7`` — matched numerically
  against the parsed catalogue attributes;
* a **rating** — ``50V``, ``1A``, ``250mW`` — matched as a lower bound, because
  a part rated above what you asked for is still usable;
* **text** — ``esp32``, ``AMS1117``, ``thick film`` — matched as a substring of
  the description and part number.

:class:`ParametricIndex` holds parsed values for the parts that have them, so a
parametric query is a scan over about 50,000 small in-memory records rather than
a scan over 180,000 rows of JSON. It is built once per catalogue file and reused.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .parameters import (
    RATING_UNITS,
    category_from_parameters,
    extract_parameters,
    parse_tolerance,
    parse_value,
    set_primary,
    values_match,
)

# ---------------------------------------------------------------------------
# Query parsing
# ---------------------------------------------------------------------------

# EIA chip packages. Kept as an explicit set because a bare four-digit token is
# ambiguous: "1206" is a package, but "1200" is a resistance. Only real chip
# sizes are listed, so "1000" is never mistaken for one.
CHIP_PACKAGES = frozenset(
    {
        "0201", "0402", "0603", "0805", "1206", "1210", "1218", "1812",
        "2010", "2512", "0508", "0612", "1020", "1225", "2220", "3640",
    }
)

# Package families written as a prefix and a pin/pad count: SOT-23-5, SOIC-8,
# QFN-32, DIP-8, TO-220, DO-214, LQFP-48, DPAK...
_PACKAGE_PREFIXES = (
    "sot", "sod", "soic", "sop", "ssop", "tssop", "msop", "qfn", "dfn",
    "lqfp", "tqfp", "dip", "to", "do", "sip", "bga", "dpak", "d2pak",
    "melf", "smd", "tht", "sma", "smb", "smc",
)

_PACKAGE_RE = re.compile(
    r"^(?:" + "|".join(_PACKAGE_PREFIXES) + r")[-]?\d+[a-z0-9-]*$"
)

# Named packages that carry no number.
_NAMED_PACKAGES = frozenset(
    {
        "smd", "tht", "melf", "axial", "radial", "sma", "smb", "smc",
        "usb-a", "usb-c", "micro-usb", "mini-usb", "dc-jack", "rj45", "hdmi",
    }
)


def is_package_token(token: str) -> bool:
    """Whether a query word names a package rather than a value or free text."""
    lowered = token.lower().strip()
    if not lowered:
        return False
    if lowered in CHIP_PACKAGES or lowered in _NAMED_PACKAGES:
        return True
    return bool(_PACKAGE_RE.match(lowered))


@dataclass(frozen=True)
class ValueConstraint:
    """
    One numeric requirement from a query.

    ``mode`` is ``"exact"`` for a part's identity (10k means 10 kΩ) and
    ``"at_least"`` for a rating (50 V means rated 50 V or more).
    """

    value: float
    unit: str
    family: Optional[str]
    raw: str
    mode: str = "exact"

    def describe(self) -> str:
        if self.mode == "at_least":
            return f"{self.raw} or better"
        return self.raw


# Words that name a component class. The key is the word; the value is the
# platform's internal category name (see ``JLCPartsDatabase._categorize``).
CATEGORY_WORDS: Dict[str, str] = {
    "resistor": "resistor", "resistors": "resistor", "res": "resistor",
    "ohm": "resistor", "ohms": "resistor", "kohm": "resistor",
    "capacitor": "capacitor", "capacitors": "capacitor", "cap": "capacitor",
    "caps": "capacitor",
    "inductor": "inductor", "inductors": "inductor", "choke": "inductor",
    "chokes": "inductor",
    "crystal": "crystal", "oscillator": "oscillator", "resonator": "crystal",
    "xtal": "crystal",
    "diode": "diode", "diodes": "diode", "rectifier": "diode",
    "zener": "zener", "schottky": "schottky",
    "led": "led", "leds": "led",
    "mosfet": "mosfet", "nmos": "mosfet", "pmos": "mosfet",
    "transistor": "transistor", "bjt": "transistor", "npn": "transistor",
    "pnp": "transistor", "thyristor": "transistor",
    "ldo": "regulator_ldo", "regulator": "regulator_ldo",
    "buck": "regulator_buck", "boost": "regulator_boost",
    "mcu": "microcontroller", "microcontroller": "microcontroller",
    "opamp": "opamp", "amplifier": "opamp", "comparator": "comparator",
    "connector": "connector", "header": "connector", "socket": "connector",
    "switch": "switch", "button": "switch", "tactile": "switch",
    "fuse": "fuse", "polyfuse": "fuse", "ptc": "fuse",
    "tvs": "tvs", "esd": "tvs",
    "sensor": "sensor",
    "memory": "memory", "eeprom": "memory", "flash": "memory",
    "sram": "memory", "ddr": "memory",
    "logic": "logic", "gate": "logic",
    "optocoupler": "isolation", "optoisolator": "isolation",
    "relay": "relay",
    "display": "display", "lcd": "display", "oled": "display",
    "adc": "data_acquisition", "dac": "data_acquisition",
    "rf": "rf_module", "wifi": "rf_module", "bluetooth": "rf_module",
    "lora": "rf_module",
}


@dataclass
class ParsedQuery:
    """A user query split into the parts that can be matched numerically."""

    raw: str
    values: List[ValueConstraint] = field(default_factory=list)
    packages: List[str] = field(default_factory=list)
    text_terms: List[str] = field(default_factory=list)
    category: Optional[str] = None
    tolerance: Optional[float] = None
    min_stock: int = 0
    limit: int = 50

    @property
    def is_parametric(self) -> bool:
        """Whether the query constrains a numeric value or rating."""
        return bool(self.values)

    def summary(self) -> str:
        """A short human-readable description of what was understood."""
        parts: List[str] = []
        if self.category:
            parts.append(self.category.replace("_", " "))
        for value in self.values:
            parts.append(value.describe())
        if self.tolerance is not None:
            parts.append(f"±{self.tolerance * 100:g}%")
        if self.packages:
            parts.append("package " + "/".join(self.packages))
        if self.text_terms:
            parts.append("text " + " ".join(self.text_terms))
        return ", ".join(parts) if parts else "(empty query)"


def parse_query(
    query: str,
    package: Optional[str] = None,
    category: Optional[str] = None,
    min_stock: int = 0,
    limit: int = 50,
) -> ParsedQuery:
    """
    Split a free-text query into values, packages, a category and text terms.

    Examples::

        "10k 0603"          -> value 10k, package 0603
        "100nF 0805 50V"    -> value 100nF, rating 50V, package 0805
        "resistor 4R7"      -> category resistor, value 4.7 ohm
        "ldo 3.3v"          -> category regulator_ldo, rating 3.3 V
        "esp32"             -> text esp32
        "3.3v ldo"          -> category regulator_ldo, rating 3.3 V

    An explicit ``package`` argument is added to any found in the query text.
    """
    parsed = ParsedQuery(raw=query or "", min_stock=min_stock, limit=limit)

    if category:
        parsed.category = category.strip().lower()

    if package:
        parsed.packages.append(package.strip().lower())

    for token in (query or "").split():
        cleaned = token.strip().strip(",;")
        if not cleaned:
            continue
        lowered = cleaned.lower()

        # A percentage is a tolerance, not a value.
        if lowered.endswith("%") and not lowered.startswith("±"):
            tolerance = parse_tolerance(cleaned)
            if tolerance is not None:
                parsed.tolerance = tolerance
                continue
        if cleaned.startswith("±"):
            tolerance = parse_tolerance(cleaned)
            if tolerance is not None:
                parsed.tolerance = tolerance
                continue

        if is_package_token(cleaned):
            if lowered not in parsed.packages:
                parsed.packages.append(lowered)
            continue

        if lowered in CATEGORY_WORDS:
            parsed.category = parsed.category or CATEGORY_WORDS[lowered]
            continue

        # Strict parsing means the whole token has to be a value. That is what
        # keeps "esp32", "1n4148" and "AMS1117" as text: reading them as the
        # numbers 32, 1.4148n and 1117 would produce a confident, wrong search.
        value = parse_value(cleaned, strict=True)
        if value is not None:
            family = value.family
            if family is None and value.unit in ("", "s"):
                # A bare number is most often a resistance; keep the family open
                # so that "100n" can still match a 100 nF capacitor or a 100 nH
                # inductor, but a plain "10k" resolves to ohms.
                mode = "exact"
            elif value.unit in RATING_UNITS:
                mode = "at_least"
            else:
                mode = "exact"
            parsed.values.append(
                ValueConstraint(
                    value=value.value,
                    unit=value.unit,
                    family=family,
                    raw=cleaned,
                    mode=mode,
                )
            )
            continue

        parsed.text_terms.append(cleaned)

    return parsed


# ---------------------------------------------------------------------------
# The in-memory index
# ---------------------------------------------------------------------------

# Attribute keys whose presence makes a part worth indexing. These are the ones
# that identify a part quantitatively; a row that has none of them cannot be
# found by a value query anyway.
INDEX_PRESENCE_KEYS: Tuple[str, ...] = (
    "Resistance",
    "Capacitance",
    "Inductance",
    "Frequency",
    "Zener Voltage(Nom)",
    "Output Voltage",
)


@dataclass(frozen=True, slots=True)
class IndexedPart:
    """A catalogue row reduced to what parametric matching needs."""

    lcsc: int
    category: str            # normalised platform category
    catalog_category: str    # the catalogue's own category string
    package: str
    stock: int
    preferred: bool
    basic: bool
    unit_price: float
    text: str                # lower-cased searchable text
    params: Dict[str, float]

    def value_of(self, family: str) -> Optional[float]:
        return self.params.get(family)


def lowest_unit_price(price_text: Any) -> float:
    """
    Cheapest unit price from a JLCPCB price tier string.

    The catalogue stores ``"1-49:0.0887,50-149:0.0707,6000-:0.0451"`` with the
    quantity tiers ascending, so the final tier is the cheapest. The last
    parseable tier is used rather than a scan of every tier, because this runs
    once per row while building the index; if the last tier is unreadable the
    whole string is scanned instead.
    """
    if not price_text:
        return 0.0
    if isinstance(price_text, (int, float)):
        return float(price_text)

    text = str(price_text)
    _, _, last = text.rpartition(":")
    try:
        value = float(last.strip())
        if value > 0:
            return value
    except ValueError:
        pass

    best: Optional[float] = None
    for segment in text.split(","):
        _, _, price = segment.partition(":")
        try:
            candidate = float(price.strip())
        except (TypeError, ValueError):
            continue
        if candidate > 0 and (best is None or candidate < best):
            best = candidate
    return best or 0.0


def _searchable_text(
    mfr: Any,
    description: Any,
    catalog_category: Any,
    params: Dict[str, Any],
) -> str:
    """
    The lower-cased text a query is matched against.

    The description is included, but for many rows it is empty, and for others it
    is a whitespace-separated field dump. The *text* attributes — an LED's
    illumination colour, a resistor's film type — are what a person actually
    searches for, so they are appended. Numeric attributes are not: "10k" should
    match as a value, not as a substring.
    """
    parts = [str(mfr or ""), str(description or ""), str(catalog_category or "")]
    parts.extend(
        str(value) for value in params.values() if isinstance(value, str)
    )
    return " ".join(parts).lower()


class ParametricIndex:
    """
    Parsed parametric values for every part in a catalogue, held in memory.

    Build it with :meth:`build`; it is cheap enough to do once per process
    (about a second for 180,000 parts) but not per query.
    """

    __slots__ = ("_parts", "_by_lcsc", "source", "build_seconds")

    def __init__(self) -> None:
        self._parts: List[IndexedPart] = []
        self._by_lcsc: Dict[int, IndexedPart] = {}
        self.source: str = ""
        self.build_seconds: float = 0.0

    def __len__(self) -> int:
        return len(self._parts)

    @property
    def parts(self) -> Sequence[IndexedPart]:
        return self._parts

    def get(self, lcsc: int) -> Optional[IndexedPart]:
        return self._by_lcsc.get(int(lcsc))

    @classmethod
    def build(
        cls,
        conn: sqlite3.Connection,
        categorize: Callable[[str, str, str], str],
        source: str = "",
    ) -> "ParametricIndex":
        """
        Read the catalogue and parse every part that has a quantitative value.

        Args:
            conn: An open SQLite connection to the catalogue (read-only is fine).
            categorize: Called as ``categorize(catalog_category, description,
                package)`` and must return the platform's category name. It is
                passed in so that the taxonomy lives in exactly one place.
            source: Free-text description of where the data came from, for logs.
        """
        import time

        started = time.monotonic()
        index = cls()
        index.source = source

        where = " OR ".join(
            f"json_extract(attributes,'$.\"{key}\"') IS NOT NULL"
            for key in INDEX_PRESENCE_KEYS
        )
        sql = (
            "SELECT lcsc, category, package, stock, preferred, basic, mfr, "
            "description, attributes, price "
            f"FROM jlc_components WHERE {where}"
        )

        parts: List[IndexedPart] = []
        by_lcsc: Dict[int, IndexedPart] = {}
        for row in conn.execute(sql):
            (lcsc, catalog_category, package, stock, preferred, basic,
             mfr, description, attributes, price) = row
            try:
                raw_attributes = json.loads(attributes) if attributes else {}
            except (TypeError, ValueError):
                raw_attributes = {}
            if not isinstance(raw_attributes, dict):
                raw_attributes = {}

            category = categorize(catalog_category or "", description or "", package or "")
            params = extract_parameters(raw_attributes, category)
            params.pop("raw", None)
            if not params:
                continue
            # Rows with neither a category nor a description still carry usable
            # attributes; deriving the category from those is what makes
            # "10k 0603" find the parts whose description is empty.
            if category == "unknown":
                category = category_from_parameters(params, category, package or "")
                set_primary(params, category)

            part = IndexedPart(
                lcsc=int(lcsc),
                category=category,
                catalog_category=catalog_category or "",
                package=(package or "").lower(),
                stock=int(stock or 0),
                preferred=bool(preferred),
                basic=bool(basic),
                unit_price=lowest_unit_price(price),
                text=_searchable_text(mfr, description, catalog_category, params),
                params=params,
            )
            parts.append(part)
            by_lcsc[part.lcsc] = part

        index._parts = parts
        index._by_lcsc = by_lcsc
        index.build_seconds = time.monotonic() - started
        return index

    # -- matching ----------------------------------------------------------

    def _value_matches(self, part: IndexedPart, constraint: ValueConstraint) -> bool:
        """
        Whether a part satisfies one numeric constraint.

        A constraint with a family (ohms, farads, henries, hertz) is compared
        against that family *as the part's identity*. This matters: an inductor
        has a ``Resistance`` attribute — its DC resistance — so without this an
        inductor whose winding happens to measure 4.7 Ω would answer a search for
        a 4.7 Ω resistor. Only a part whose primary value is a resistance can
        satisfy a resistance search.

        A constraint with no family — a bare ``10k`` — is compared against the
        part's primary value, so ``100n`` finds a 100 nF capacitor and a 100 nH
        inductor, while ``10k`` effectively finds only resistors.
        """
        if constraint.mode == "at_least":
            if constraint.unit == "V":
                # A regulator's output voltage is an identity, not a rating: a
                # 5 V regulator must not satisfy a search for 3.3 V just because
                # it tolerates 15 V on its input.
                output = part.params.get("output_voltage")
                if output is not None:
                    return values_match(output, constraint.value, 0.01)
                rating = part.params.get("voltage")
                if rating is None:
                    rating = part.params.get("supply_voltage")
                return rating is not None and rating >= constraint.value * 0.999

            for field_name in ("output_current", "current", "power"):
                candidate = part.params.get(field_name)
                if candidate is not None:
                    return candidate >= constraint.value * 0.999
            return False

        if constraint.family is not None:
            primary_field = part.params.get("primary_field")
            if primary_field is None:
                # No identified primary: fall back to the field if present.
                candidate = part.params.get(constraint.family)
            elif primary_field == constraint.family:
                candidate = part.params.get(constraint.family)
            else:
                return False
            return values_match(candidate, constraint.value, 0.0)

        # No family in the query: compare against the part's identity value.
        primary = part.params.get("primary")
        if primary is not None:
            return values_match(primary, constraint.value, 0.0)
        return any(
            values_match(part.params.get(family), constraint.value, 0.0)
            for family in ("resistance", "capacitance", "inductance", "frequency")
        )

    def _overshoot(self, part: IndexedPart, query: ParsedQuery) -> float:
        """
        How far above the requested ratings a part is, as a fraction.

        A search for "50 V 100 nF" should offer a 50 V part before a 500 V one.
        Both satisfy the requirement — a higher rating is genuinely usable — but
        the 500 V part is larger and dearer than necessary, so the excess is used
        to rank rather than to reject.
        """
        total = 0.0
        for constraint in query.values:
            if constraint.mode != "at_least" or constraint.value <= 0:
                continue
            if constraint.unit == "V":
                rating = part.params.get("output_voltage")
                if rating is None:
                    rating = part.params.get("voltage") or part.params.get("supply_voltage")
            else:
                rating = part.params.get("output_current") or part.params.get("current") or part.params.get("power")
            if rating is None:
                continue
            total += max(0.0, rating / constraint.value - 1.0)
        return total

    def find(
        self,
        query: ParsedQuery,
        limit: Optional[int] = None,
        require_package: bool = True,
    ) -> List[IndexedPart]:
        """
        Return parts matching a parsed query, best first.

        Ordering puts JLCPCB Preferred parts first, then the least over-specified
        ratings, then the most stock, then the lowest price. The point of the
        search is to end up with something that can actually be bought and
        assembled, not merely something that satisfies the constraints.
        """
        wanted = limit if limit is not None else query.limit
        matches: List[IndexedPart] = []

        for part in self._parts:
            if query.min_stock and part.stock < query.min_stock:
                continue
            if query.category and query.category not in part.category:
                continue
            if query.packages:
                if require_package:
                    if not any(pkg in part.package for pkg in query.packages):
                        continue
                else:
                    # Package is a preference, not a filter: used when nothing
                    # else matches, so a 10 kΩ part is still offered if the
                    # requested package is unavailable.
                    pass
            if query.tolerance is not None:
                part_tolerance = part.params.get("tolerance")
                if part_tolerance is None or part_tolerance > query.tolerance:
                    continue
            if not all(self._value_matches(part, v) for v in query.values):
                continue
            if query.text_terms:
                haystack = part.text
                if not all(term.lower() in haystack for term in query.text_terms):
                    continue
            matches.append(part)

        matches.sort(
            key=lambda p: (
                0 if p.preferred else (1 if p.basic else 2),
                round(self._overshoot(p, query), 3),
                -p.stock,
                p.unit_price if p.unit_price else 1e9,
            )
        )
        return matches[:wanted]


# ---------------------------------------------------------------------------
# Process-wide cache
# ---------------------------------------------------------------------------

_INDEX_CACHE: Dict[Tuple[str, int], ParametricIndex] = {}
_INDEX_LOCK = threading.Lock()


def cached_index(
    conn: sqlite3.Connection,
    catalog_path: Any,
    categorize: Callable[[str, str, str], str],
) -> ParametricIndex:
    """
    Return the index for a catalogue file, building it at most once per process.

    Keyed on the resolved path and the file's modification time, so replacing
    the catalogue on disk picks up the new one without restarting.
    """
    import os

    path = str(catalog_path)
    try:
        stamp = os.stat(path).st_mtime_ns
    except OSError:
        stamp = 0
    key = (path, stamp)

    with _INDEX_LOCK:
        existing = _INDEX_CACHE.get(key)
        if existing is not None:
            return existing
        built = ParametricIndex.build(conn, categorize, source=path)
        # Keep only the current catalogue's index; a replaced file would
        # otherwise leave a full copy of the old parsed data in memory.
        _INDEX_CACHE.clear()
        _INDEX_CACHE[key] = built
        return built
