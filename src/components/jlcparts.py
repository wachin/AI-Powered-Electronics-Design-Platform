"""
JLCPCB/LCSC Component Database Integration for AI-Powered Electronics Design Platform.

Reads the SQLite catalogue republished by CDFER from JLCPCB's parts database, and
offers text lookup, numeric parametric search and substitute finding over it.

The catalogue is an external data file the user downloads (``catalog-setup``); it
is never committed, and everything here works without it, returning no results
rather than failing.
"""

import json
import sqlite3
import logging
from pathlib import Path
import os
from dataclasses import dataclass, field, replace as _dataclass_replace
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .parametric import (
    IndexedPart,
    ParsedQuery,
    ValueConstraint,
    cached_index,
    parse_query,
)
from .parameters import (
    category_from_parameters,
    extract_parameters,
    format_value,
    set_primary,
    values_match,
)

logger = logging.getLogger(__name__)


# The catalogue's category tree mapped onto this platform's component
# categories. Kept as data, not code, so a catalogue reorganisation is a
# one-line change. Categories missing from this table fall back to keyword
# matching on the description (see ``JLCPartsDatabase._categorize``).
_CATALOG_CATEGORY_MAP: Dict[str, str] = {
    "Resistors": "resistor",
    "Capacitors": "capacitor",
    "Inductors, Coils, Chokes": "inductor",
    "Inductors/Coils/Transformers": "inductor",
    "Inductors & Chokes & Transformers": "inductor",
    "Crystals, Oscillators, Resonators": "crystal",
    "Crystal Oscillator/Oscillator/Resonator": "crystal",
    "Resonators/Oscillators": "crystal",
    "Clock/Timing": "crystal",
    "Diodes": "diode",
    "Optoelectronics": "led",
    "LED/Photoelectric Devices": "led",
    "Photoelectric Devices": "led",
    "Transistors/Thyristors": "transistor",
    "Transistors": "transistor",
    "Triode/MOS Tube/Transistor": "transistor",
    "Silicon Carbide (SiC) Devices": "mosfet",
    "Gallium Nitride (GaN) Devices": "mosfet",
    # "Power Management (PMIC)" is a grab bag: linear regulators, switching
    # converters, voltage references, supervisors, chargers and load switches all
    # live under it. It is refined by description below; classifying the whole
    # leaf as an LDO would give a TL431 voltage reference an LDO symbol and LDO
    # pinouts.
    "Power Management (PMIC)": "power_management",
    "Power Management ICs": "power_management",
    "Power Management": "power_management",
    "Power Supply Chip": "power_management",
    "Connectors": "connector",
    "Terminal": "connector",
    "Wire/Cable/DataCable": "connector",
    "Wires And Cables": "connector",
    "Wires and cables": "connector",
    "Switches": "switch",
    "Key/Switch": "switch",
    "Circuit Protection": "fuse",
    "Relays": "relay",
    "Optoisolators": "isolation",
    "Optocouplers/Photocouplers": "isolation",
    "Optocoupler": "isolation",
    "Optocoupler/LED/Digital Tube/Photoelectric Device": "isolation",
    "Signal Isolation Devices": "isolation",
    "Amplifiers/Comparators": "opamp",
    "Amplifiers": "opamp",
    "Embedded Processors & Controllers": "microcontroller",
    "Memory": "memory",
    "Logic": "logic",
    "Sensors": "sensor",
    "Magnetic Sensors": "sensor",
    "Data Acquisition": "data_acquisition",
    "Interface": "interface",
    "Communication Interface Chip/UART/485/232": "interface",
    "RF And Wireless": "rf_module",
    "IoT/Communication Modules": "rf_module",
    "Functional Modules": "rf_module",
    "Displays": "display",
    "Motor Driver ICs": "driver",
    "LED Drivers": "driver",
    "Nixie Tube Driver/LED Driver": "driver",
    "Filters": "filter",
    "Bead/Filter/EMI Optimization": "filter",
    "Power Modules": "power_module",
    "Audio Products / Vibration Motors": "audio",
    "Audio Components/Vibration Motors": "audio",
    "Development Boards & Tools": "module",
    "Educational Kits": "module",
    "Hardware/Fasteners/Sealing": "hardware",
    "Hardware Fasteners": "hardware",
    "Industrial Control Electrical": "hardware",
    "Global Sourcing Parts": "unknown",
    "Others": "unknown",
    "Other": "unknown",
    "Test": "unknown",
    "Consumables": "unknown",
    "Consumables And Auxiliary Materials": "unknown",
}

# The reverse mapping, for turning an internal category into the catalogue
# categories worth querying. One internal name can span several leaves.
_INTERNAL_TO_CATALOG: Dict[str, Tuple[str, ...]] = {}
for _catalog_name, _internal_name in _CATALOG_CATEGORY_MAP.items():
    _INTERNAL_TO_CATALOG.setdefault(_internal_name, ())
    _INTERNAL_TO_CATALOG[_internal_name] += (_catalog_name,)
del _catalog_name, _internal_name

# "Power Management (PMIC)" is split into several internal categories in Python,
# after the SQL has already run. Each of them therefore has to map back to the
# PMIC leaves, or searching by that category would query an empty set.
_INTERNAL_TO_CATALOG["circuit_protection"] = ("Circuit Protection",)

# About 67,000 rows carry no catalogue category at all, so they are stored under
# the empty string. Leaving it out would make the "unknown" category miss most of
# the parts it is meant to describe.
_INTERNAL_TO_CATALOG["unknown"] = tuple(
    dict.fromkeys(("",) + _INTERNAL_TO_CATALOG.get("unknown", ()))
)

_PMIC_LEAVES: Tuple[str, ...] = tuple(
    catalog_name
    for catalog_name, internal_name in _CATALOG_CATEGORY_MAP.items()
    if internal_name == "power_management"
)
for _derived in (
    "analog",
    "regulator_ldo",
    "regulator_buck",
    "regulator_boost",
    "regulator_switching",
    "voltage_reference",
    "supervisor",
    "battery_management",
    "power_switch",
):
    _INTERNAL_TO_CATALOG[_derived] = tuple(
        dict.fromkeys(_INTERNAL_TO_CATALOG.get(_derived, ()) + _PMIC_LEAVES)
    )
del _derived

# Names that the refinement can produce but that no catalogue leaf maps to
# directly. Without these, searching by the category would query an empty set.
for _refined, _source_leaves in (
    ("zener", ("Diodes",)),
    ("schottky", ("Diodes",)),
    ("diode", ("Diodes",)),
    ("tvs", ("Circuit Protection",)),
    ("varistor", ("Circuit Protection",)),
    ("fuse", ("Circuit Protection",)),
):
    _INTERNAL_TO_CATALOG[_refined] = tuple(
        dict.fromkeys(_INTERNAL_TO_CATALOG.get(_refined, ()) + _source_leaves)
    )
del _refined, _source_leaves

# The catalogue's leaves are broader than this platform's categories: "Power
# Management (PMIC)" covers linear regulators, switching converters, references,
# supervisors, chargers and load switches, and "Diodes" covers zeners, Schottkys
# and LEDs. Splitting them happens in Python, after reading the row.
#
# That creates a problem for the text-search path. If the SQL applies a LIMIT
# before Python splits the leaf, the rows belonging to a rarer subtype are
# crowded out by the commoner ones and the query silently returns nothing:
# a "supervisor" search that only ever sees the 50 highest-stock regulators finds
# no supervisors at all. For these categories the LIMIT is therefore dropped and
# the whole leaf is considered. A leaf is at most ~35,000 rows and reads in under
# half a second, which is a fair price for a correct answer.
#
# The keyword-based alternative was tried and rejected: a large share of these
# rows have an empty description, so a description filter loses parts that the
# attributes identify unambiguously.
_REFINED_CATEGORIES = frozenset(
    {
        "power_management",
        "regulator_ldo",
        "regulator_buck",
        "regulator_boost",
        "regulator_switching",
        "voltage_reference",
        "supervisor",
        "battery_management",
        "power_switch",
        "driver",
        "interface",
        "analog",
        "diode",
        "zener",
        "schottky",
        "led",
        "fuse",
        "tvs",
        "varistor",
        "circuit_protection",
        "unknown",
    }
)


# Words that identify a category in a query. Used by the text-search path, which
# has to translate the same vocabulary into SQL.
_CATEGORY_QUERY_ALIASES: Dict[str, Tuple[str, ...]] = {
    "resistor": ("resistor", "ohm", "Ω"),
    "capacitor": ("capacitor", "farad"),
    "inductor": ("inductor", "choke", "henry"),
    "crystal": ("crystal", "oscillator", "resonator"),
    "diode": ("diode", "rectifier"),
    "zener": ("zener",),
    "schottky": ("schottky",),
    "led": ("led", "light emitting"),
    "mosfet": ("mosfet", "n-channel", "p-channel"),
    "transistor": ("transistor", "bipolar"),
    "regulator_ldo": ("ldo", "low drop", "linear regulator"),
    "regulator_buck": ("buck", "step-down"),
    "regulator_boost": ("boost", "step-up"),
    "microcontroller": ("microcontroller", "mcu", "cortex"),
    "opamp": ("operational amplifier", "opamp"),
    "comparator": ("comparator",),
    "connector": ("connector", "header", "socket"),
    "switch": ("switch", "button", "tactile"),
    "fuse": ("fuse", "ptc"),
    "tvs": ("tvs", "esd"),
    "sensor": ("sensor", "accelerometer"),
    "memory": ("memory", "eeprom", "flash"),
    "logic": ("logic gate", "74hc", "74ls"),
    "isolation": ("optocoupler", "isolation"),
    "relay": ("relay",),
    "display": ("display", "lcd", "oled"),
    "rf_module": ("wifi", "bluetooth", "lora", "module"),
}


@dataclass
class JLCPart:
    """Represents a component from the JLCPCB/LCSC catalog."""
    lcsc_part: str              # e.g., "C123456"
    mfr_part: str               # Manufacturer Part Number
    manufacturer: str
    description: str            # Free-text spec string
    category: str               # Normalized category (resistor, capacitor, etc.)
    package: str                # Package/footprint (e.g., "0805", "SOT-23")
    package_type: str           # SMD/THT/module
    stock: int                  # Available stock
    min_order: int              # Minimum order quantity
    prices: List[Dict[str, Any]] = field(default_factory=list)  # Price breaks
    is_basic: bool = False      # JLCPCB Basic library
    is_preferred: bool = False  # JLCPCB Preferred library
    datasheet_url: str = ""
    product_url: str = ""
    stock_source: str = "offline_catalog"
    read_at: datetime = field(default_factory=datetime.now)
    catalog_category: str = ""  # The catalogue's own category string
    parameters: Dict[str, Any] = field(default_factory=dict)  # Parsed specs
    # JLCPCB's own ordering figures, as published: the minimum purchase
    # quantity and the extra parts consumed per board. Kept verbatim rather than
    # interpreted, because the exact meaning of "leastNumber" is JLCPCB's to
    # define. Not yet used to round BOM quantities.
    attrition: Dict[str, Any] = field(default_factory=dict)

    @property
    def primary_value(self) -> Optional[float]:
        """The numeric value that identifies this part within its category."""
        return self.parameters.get("primary")

    @property
    def tolerance(self) -> Optional[float]:
        """Tolerance as a fraction, e.g. 0.01 for ±1%."""
        return self.parameters.get("tolerance")

    def specification_summary(self) -> str:
        """
        A short list of the parsed specifications, for display.

        Used instead of the raw description, which for catalogued parts is a
        whitespace-separated field dump that is hard to read and easy to
        misinterpret. Values are written in engineering notation, so 1e-07 farads
        appears as ``100n``.
        """
        units = {
            "resistance": "Ω",
            "capacitance": "F",
            "inductance": "H",
            "frequency": "Hz",
            "power": "W",
            "voltage": "V",
            "current": "A",
            "output_voltage": "V",
            "output_current": "A",
            "forward_voltage": "V",
            "zener_voltage": "V",
            "rds_on": "Ω",
        }
        labels = {
            "output_voltage": "Vout",
            "output_current": "Iout",
            "forward_voltage": "Vf",
            "zener_voltage": "Vz",
            "rds_on": "Rds(on)",
            "frequency": "f",
        }
        pieces: List[str] = []
        for field_name, unit in units.items():
            value = self.parameters.get(field_name)
            if value is None:
                continue
            label = labels.get(field_name, "")
            pieces.append(f"{label}{format_value(value, unit)}".strip())
        tolerance = self.parameters.get("tolerance")
        if tolerance is not None:
            pieces.append(f"±{tolerance * 100:g}%")
        return " ".join(pieces)

    @property
    def unit_price(self) -> float:
        """Get lowest unit price (highest quantity tier)."""
        if not self.prices:
            return 0.0
        return min(p["unit_price"] for p in self.prices)

    @property
    def footprint(self) -> str:
        """KiCad footprint string based on package."""
        return self._package_to_footprint(self.package)

    @property
    def symbol(self) -> str:
        """KiCad symbol string based on category."""
        return self._category_to_symbol(self.category)

    def _package_to_footprint(self, package: str) -> str:
        """Map package string to KiCad footprint library path."""
        package_lower = package.lower().strip()

        # SMD Passive packages
        passive_map = {
            "0402": "Resistor_SMD:R_0402_1005Metric",
            "0603": "Resistor_SMD:R_0603_1608Metric",
            "0805": "Resistor_SMD:R_0805_2012Metric",
            "1206": "Resistor_SMD:R_1206_3216Metric",
            "1210": "Resistor_SMD:R_1210_3225Metric",
            "2010": "Resistor_SMD:R_2010_5025Metric",
            "2512": "Resistor_SMD:R_2512_6332Metric",
            "0508": "Resistor_SMD:R_0508_1220Metric",
            "0612": "Resistor_SMD:R_0612_1632Metric",
        }
        if package_lower in passive_map:
            return passive_map[package_lower]

        # SOT packages
        sot_map = {
            "sot-23": "Package_TO_SOT_SMD:SOT-23-3",
            "sot-23-3": "Package_TO_SOT_SMD:SOT-23-3",
            "sot-23-5": "Package_TO_SOT_SMD:SOT-23-5",
            "sot-23-6": "Package_TO_SOT_SMD:SOT-23-6",
            "sot-323": "Package_TO_SOT_SMD:SOT-323",
            "sot-363": "Package_TO_SOT_SMD:SOT-363",
            "sot-223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
            "sot-223-3": "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
            "sot-89": "Package_TO_SOT_SMD:SOT-89-3_TabPin2",
            "sot-89-3": "Package_TO_SOT_SMD:SOT-89-3_TabPin2",
        }
        if package_lower in sot_map:
            return sot_map[package_lower]

        # SOIC/SOP packages
        soic_map = {
            "soic-8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            "soic-14": "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
            "soic-16": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
            "sop-8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
            "sop-14": "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
            "sop-16": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
            "tsop-8": "Package_SO:TSSOP-8_3x3mm_P0.65mm",
            "tssop-8": "Package_SO:TSSOP-8_3x3mm_P0.65mm",
            "tssop-14": "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
            "tssop-16": "Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
            "tssop-20": "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm",
            "tssop-24": "Package_SO:TSSOP-24_4.4x7.8mm_P0.65mm",
            "tssop-28": "Package_SO:TSSOP-28_4.4x9.7mm_P0.65mm",
        }
        if package_lower in soic_map:
            return soic_map[package_lower]

        # QFP/QFN packages
        qfp_map = {
            "qfn-16": "Package_QFN:QFN-16_3x3mm_P0.5mm",
            "qfn-20": "Package_QFN:QFN-20_3x3mm_P0.4mm",
            "qfn-24": "Package_QFN:QFN-24_4x4mm_P0.5mm",
            "qfn-28": "Package_QFN:QFN-28_4x4mm_P0.4mm",
            "qfn-32": "Package_QFN:QFN-32_5x5mm_P0.5mm",
            "qfn-48": "Package_QFN:QFN-48_7x7mm_P0.5mm",
            "lqfp-48": "Package_QFP:LQFP-48_7x7mm_P0.5mm",
            "lqfp-64": "Package_QFP:LQFP-64_10x10mm_P0.5mm",
            "lqfp-100": "Package_QFP:LQFP-100_14x14mm_P0.5mm",
            "lqfp-144": "Package_QFP:LQFP-144_20x20mm_P0.5mm",
        }
        if package_lower in qfp_map:
            return qfp_map[package_lower]

        # BGA
        if "bga" in package_lower:
            return "Package_BGA:BGA_GENERIC"

        # Connectors
        conn_map = {
            "usb-c": "Connector:USB_C_Receptacle_USB2.0_16P",
            "usb-a": "Connector:USB_A_Receptacle",
            "micro-usb": "Connector:USB_Micro-B_Receptacle",
            "mini-usb": "Connector:USB_Mini-B_Receptacle",
            "hdmi": "Connector:HDMI_Receptacle",
            "rj45": "Connector:RJ45_Receptacle",
            "dc-jack": "Connector:DC_Jack",
            "terminal-block": "Connector:Terminal_Block",
        }
        for key, val in conn_map.items():
            if key in package_lower:
                return val

        # No mapping. Returning a fabricated footprint name would look like a
        # real KiCad identifier and then fail, or worse, resolve by accident. An
        # empty footprint is an honest "the generator must resolve this itself",
        # and src/generators/kicad_footprints.py does exactly that from the
        # package name.
        return ""

    def _category_to_symbol(self, category: str) -> str:
        """Map category to KiCad symbol library path."""
        symbol_map = {
            "resistor": "Device:R",
            "capacitor": "Device:C",
            "inductor": "Device:L",
            "diode": "Device:D",
            "led": "Device:LED",
            "zener": "Device:D_Zener",
            "schottky": "Device:D_Schottky",
            "transistor": "Device:Q_NPN_BEC",
            "mosfet": "Device:MOSFET_N",
            "jfet": "Device:JFET_N",
            "regulator_ldo": "Regulator_Linear:LDO_Generic",
            "regulator_buck": "Regulator_Switching:Buck_Controller",
            "regulator_boost": "Regulator_Switching:Boost_Controller",
            "microcontroller": "MCU_Microcontroller:MCU_Generic",
            "opamp": "Amplifier_Operational:Opamp",
            "comparator": "Amplifier_Comparator:Comparator",
            "voltage_reference": "Voltage_Reference:VREF",
            "crystal": "Crystal:Crystal",
            "oscillator": "Crystal:Oscillator",
            "connector": "Connector:Conn_Generic",
            "switch": "Switch:SW_Push",
            "fuse": "Device:Fuse",
            "tvs": "Power_Protection:TVS",
            "varistor": "Device:Varistor",
            "thermistor": "Device:Thermistor",
            "sensor": "Sensor:Generic",
            "rf_module": "RF_Module:Module_Generic",
            "memory": "Memory:EEPROM",
            "logic": "Logic_Gate:AND",
            "driver": "Driver:Gate_Driver",
            "isolation": "Isolation:Optocoupler",
            "power_management": "Regulator_Linear:LDO_Generic",
            "regulator_switching": "Regulator_Switching:Buck_Controller",
            "voltage_reference": "Reference_Voltage:VREF",
            "supervisor": "Power_Supervisor:Supervisor",
            "battery_management": "Battery_Management:Charger",
            "power_switch": "Power_Protection:Load_Switch",
            "analog": "Analog:Generic",
            "interface": "Interface:Generic",
            "data_acquisition": "Analog_ADC:ADC_Generic",
            "display": "Display_Character:Display_Generic",
            "filter": "Filter:Filter_Generic",
            "power_module": "Converter_DCDC:Module_Generic",
            "relay": "Relay:Relay_Generic",
            "audio": "Device:Speaker",
            "hardware": "Mechanical:MountingHole",
            "module": "Module:Module_Generic",
        }
        cat_lower = category.lower().strip()
        for key, val in symbol_map.items():
            if key in cat_lower:
                return val
        return "Device:R"  # Default fallback

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lcsc_part": self.lcsc_part,
            "mfr_part": self.mfr_part,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "category": self.category,
            "catalog_category": self.catalog_category,
            "package": self.package,
            "package_type": self.package_type,
            "stock": self.stock,
            "min_order": self.min_order,
            "prices": self.prices,
            "unit_price": self.unit_price,
            "is_basic": self.is_basic,
            "is_preferred": self.is_preferred,
            "datasheet_url": self.datasheet_url,
            "product_url": self.product_url,
            "footprint": self.footprint,
            "symbol": self.symbol,
            "parameters": {k: v for k, v in self.parameters.items() if k != "raw"},
            "specification": self.specification_summary(),
            "min_order": self.min_order,
            "attrition": self.attrition,
        }


@dataclass
class SearchOutcome:
    """
    The result of a search, with the interpretation that produced it.

    ``notes`` records what the search understood and what it had to relax, so a
    user interface can show reasoning instead of an unexplained list.
    """

    query: ParsedQuery
    parts: List[JLCPart] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.parts)

    @property
    def is_parametric(self) -> bool:
        return self.query.is_parametric


@dataclass
class Substitute:
    """
    A candidate replacement for a part, and the evidence for and against it.

    ``reasons`` lists properties that were checked and matched. ``caveats`` lists
    differences and anything that could not be verified from the catalogue. A
    candidate with caveats is not rejected — it is disclosed.
    """

    part: JLCPart
    reasons: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Whether every comparable property matched or was verified."""
        return not self.caveats

    def explain(self) -> str:
        """A readable account of the comparison, for a terminal or a tooltip."""
        lines = [f"{self.part.lcsc_part} {self.part.mfr_part}"]
        lines += [f"  + {reason}" for reason in self.reasons]
        lines += [f"  ! {caveat}" for caveat in self.caveats]
        return "\n".join(lines)


class JLCPartsDatabase:
    """
    JLCPCB/LCSC Component Database using the CDFER-republished SQLite dataset.

    Usage:
        db = JLCPartsDatabase()
        if db.available:
            parts = db.search("10k 0402")
            part = db.lookup("C123456")
            alternatives = db.find_substitutes("C123456")
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or self._find_catalog()
        self._catalog_available = self.db_path is not None and self.db_path.exists()

    def _find_catalog(self) -> Optional[Path]:
        """
        Locate the component catalog, in order of preference.

        The `JLC_PARTS_CATALOG` environment variable wins, which makes it easy to
        point at a catalog kept somewhere unusual. Repository-relative paths come
        next, so running from the project directory finds a checked-out catalog,
        and the per-user cache is the normal location.
        """
        import os

        candidates: List[Path] = []
        from_env = os.environ.get("JLC_PARTS_CATALOG")
        if from_env:
            candidates.append(Path(from_env))

        candidates += [
            default_catalog_path(),
            Path.home() / ".jlcparts" / "jlcparts.sqlite3",
            # Repository root, independent of the current working directory.
            Path(__file__).resolve().parents[2] / "jlcparts.sqlite3",
            Path("/tmp") / "jlcparts.sqlite3",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    @property
    def available(self) -> bool:
        return self._catalog_available

    def _connect(self) -> sqlite3.Connection:
        """Create read-only connection to catalog."""
        if not self.available:
            raise RuntimeError("JLCParts catalog not available. Run 'jlcparts sync' or download dataset.")
        return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)

    def _row_to_part(self, row: sqlite3.Row) -> JLCPart:
        """Convert database row to JLCPart object."""
        def get_str(name: str) -> str:
            val = row[name] if name in row.keys() else None
            return str(val) if val not in (None, "") else ""

        def get_int(name: str, default: int = 0) -> int:
            val = row[name] if name in row.keys() else None
            if val in (None, ""):
                return default
            try:
                return int(str(val))
            except (TypeError, ValueError):
                return default

        def parse_prices(raw) -> List[Dict[str, Any]]:
            if not raw:
                return []
            if isinstance(raw, (list, tuple)):
                return self._parse_price_list(raw)
            if isinstance(raw, (str, bytes, bytearray)):
                text = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
                text = text.strip()
                if not text:
                    return []
                if text.startswith("["):
                    try:
                        import json
                        data = json.loads(text)
                        return self._parse_price_list(data) if isinstance(data, list) else []
                    except (json.JSONDecodeError, TypeError):
                        pass
                return self._parse_price_tiers(text)
            return []

        lcsc_id = row["lcsc"] if "lcsc" in row.keys() else None
        lcsc_part = f"C{lcsc_id}" if lcsc_id is not None else ""
        catalog_category = get_str("category")
        description = get_str("description")
        package = get_str("package")

        # The catalogue marks Preferred with its own column. It has almost no
        # Basic parts, so `is_basic` is false for all but a handful; rank on
        # Preferred instead. `library_type` ("base"/"expand") is not the
        # JLCPCB basic/preferred flag and must not be read as one.
        is_preferred = bool(get_int("preferred", 0)) or get_str("library_type").lower() == "preferred"
        is_basic = bool(get_int("basic", 0)) or get_str("library_type").lower() == "basic"

        # The minimum order quantity is not a column; JLCPCB publishes it inside
        # the `attrition` JSON. Ignoring it makes every part look orderable in
        # ones, which is not true.
        attrition: Dict[str, Any] = {}
        raw_attrition = row["attrition"] if "attrition" in row.keys() else None
        if raw_attrition:
            try:
                parsed_attrition = json.loads(raw_attrition)
                if isinstance(parsed_attrition, dict):
                    attrition = parsed_attrition
            except (TypeError, ValueError):
                attrition = {}

        attributes = row["attributes"] if "attributes" in row.keys() else None
        category = self._categorize(catalog_category, description, package)
        parameters = extract_parameters(attributes, category)
        if category == "unknown":
            # Some rows carry neither a category nor a description, but still
            # have an unambiguous attribute such as "Resistance". The identity
            # value can only be recorded once the category is known.
            category = category_from_parameters(parameters, category, package)
            set_primary(parameters, category)

        return JLCPart(
            lcsc_part=lcsc_part,
            mfr_part=get_str("mfr"),
            manufacturer=get_str("manufacturer"),
            description=description,
            category=category,
            catalog_category=catalog_category,
            package=package,
            package_type=self._guess_package_type(package),
            stock=get_int("stock", 0),
            min_order=self._min_order(attrition),
            prices=parse_prices(row["price"] if "price" in row.keys() else None),
            is_basic=is_basic,
            is_preferred=is_preferred,
            datasheet_url=get_str("datasheet"),
            product_url=f"https://jlcpcb.com/partdetail/{lcsc_part}" if lcsc_part else "",
            parameters=parameters,
            attrition=attrition,
        )

    @staticmethod
    def _min_order(attrition: Dict[str, Any]) -> int:
        """
        The minimum quantity JLCPCB sells, from the `attrition` JSON.

        Falls back to 1, which is the common case, rather than to 0: a minimum
        order of zero would make a part look like it can be bought in no
        quantity at all.
        """
        try:
            value = int(attrition.get("minPurchaseNum") or 1)
        except (TypeError, ValueError):
            return 1
        return value if value > 0 else 1

    def _parse_price_tiers(self, text: str) -> List[Dict[str, Any]]:
        import re
        prices = []
        for segment in text.split(","):
            segment = segment.strip()
            if not segment or ":" not in segment:
                continue
            qty_range, _, price_str = segment.rpartition(":")
            match = re.match(r"\s*(\d+)", qty_range)
            if not match:
                continue
            try:
                qty = int(match.group(1))
                price = float(price_str.strip())
                if qty > 0 and price > 0:
                    prices.append({"quantity": qty, "unit_price": price})
            except (TypeError, ValueError):
                continue
        prices.sort(key=lambda p: p["quantity"])
        return prices

    def _parse_price_list(self, data: list) -> List[Dict[str, Any]]:
        prices = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            qty = entry.get("qFrom") or entry.get("startNumber") or entry.get("quantity") or 0
            unit_price = entry.get("price") or entry.get("productPrice") or entry.get("unit_price") or 0
            try:
                qty_i = int(qty)
                price_f = float(unit_price)
                if qty_i > 0 and price_f > 0:
                    prices.append({"quantity": qty_i, "unit_price": price_f})
            except (TypeError, ValueError):
                continue
        prices.sort(key=lambda p: p["quantity"])
        return prices

    def _categorize(self, catalog_category: str, description: str, package: str) -> str:
        """
        Map a catalogue row to this platform's component category.

        The catalogue has its own category tree (``Power Management (PMIC)``,
        ``Crystals, Oscillators, Resonators``) which is not the set of names the
        rest of the platform uses (``regulator_ldo``, ``crystal``). Everything
        downstream — pin resolution, symbol selection, validation — is written
        against the internal names, so translating here keeps those names stable
        even if the upstream catalogue reorganises its tree.

        The catalogue leaf is used first because it is far more reliable than
        guessing from text. A few broad leaves (PMIC, Diodes, Circuit
        Protection) are then refined by keyword, because "regulator" is too
        coarse to pick an LDO symbol.
        """
        desc = (description or "").lower()
        catalog = (catalog_category or "").strip()

        internal = _CATALOG_CATEGORY_MAP.get(catalog)

        if internal == "power_management":
            # Every sub-type of a PMIC leaf has to be identified positively.
            # Defaulting to "LDO" would be the most dangerous possible answer,
            # because an LDO symbol carries IN/OUT/GND pin assumptions.
            if any(k in desc for k in ("low drop out", "ldo", "linear regulator")):
                return "regulator_ldo"
            if "buck" in desc or "step-down" in desc or "step down" in desc:
                return "regulator_buck"
            if "boost" in desc or "step-up" in desc or "step up" in desc:
                return "regulator_boost"
            if "dc-dc" in desc or "dc to dc" in desc or "switching regulator" in desc:
                return "regulator_switching"
            if "voltage reference" in desc:
                return "voltage_reference"
            if any(k in desc for k in ("supervisor", "voltage monitor", "watchdog", "reset")):
                return "supervisor"
            if any(k in desc for k in ("battery", "charger", "fuel gauge", "power path")):
                return "battery_management"
            if any(k in desc for k in ("load switch", "power switch", "hot swap", "ideal diode", "or-ing")):
                return "power_switch"
            if "gate driver" in desc or "led driver" in desc or "motor driver" in desc:
                return "driver"
            if any(k in desc for k in ("usb", "pd controller", "power delivery")):
                return "interface"
            if "multiplier" in desc or "divider" in desc:
                return "analog"
            return "power_management"

        if internal == "diode":
            if "zener" in desc:
                return "zener"
            if "schottky" in desc:
                return "schottky"
            if "led" in desc or "light emitting" in desc:
                return "led"
            return "diode"

        if internal == "led":
            if "infrared" in desc or "ir " in desc:
                return "led"
            return "led"

        if internal == "fuse":
            if "tvs" in desc or "esd" in desc or "transient" in desc:
                return "tvs"
            if "varistor" in desc:
                return "varistor"
            if "fuse" in desc or "ptc" in desc:
                return "fuse"
            return "circuit_protection"

        if internal is not None:
            return internal

        # No catalogue category (about 67,000 rows). Fall back to keywords.
        if any(k in desc for k in ["resistor", "ohm", "Ω"]):
            return "resistor"
        if any(k in desc for k in ["capacitor", "cap ", "uf", "pf", "nf", "µf"]):
            return "capacitor"
        if any(k in desc for k in ["inductor", "inductance", "uh", "mh", "nh"]):
            return "inductor"
        if "zener" in desc:
            return "zener"
        if "schottky" in desc:
            return "schottky"
        if "led" in desc or "light emitting" in desc:
            return "led"
        if any(k in desc for k in ["diode", "rectifier"]):
            return "diode"
        if "mosfet" in desc:
            return "mosfet"
        if any(k in desc for k in ["transistor", "bjt "]):
            return "transistor"
        if any(k in desc for k in ["ldo", "linear regulator", "voltage regulator"]):
            return "regulator_ldo"
        if "buck" in desc or "step-down" in desc:
            return "regulator_buck"
        if "boost" in desc or "step-up" in desc:
            return "regulator_boost"
        if any(k in desc for k in ["microcontroller", "mcu", "arm cortex", "esp32", "stm32", "rp2040"]):
            return "microcontroller"
        if any(k in desc for k in ["opamp", "operational amplifier"]):
            return "opamp"
        if "comparator" in desc:
            return "comparator"
        if any(k in desc for k in ["crystal", "oscillator", "xtal"]):
            return "crystal"
        if any(k in desc for k in ["connector", "conn ", "header", "socket", "terminal block", "插件"]):
            return "connector"
        if any(k in desc for k in ["switch", "button", "tactile"]):
            return "switch"
        if any(k in desc for k in ["fuse", "polyfuse"]):
            return "fuse"
        if any(k in desc for k in ["tvs", "esd protection"]):
            return "tvs"
        if any(k in desc for k in ["sensor", "accelerometer", "gyro"]):
            return "sensor"
        if any(k in desc for k in ["wifi", "bluetooth", "zigbee", "lora", "module"]):
            return "rf_module"
        if any(k in desc for k in ["memory", "eeprom", "flash", "ram"]):
            return "memory"
        if any(k in desc for k in ["logic gate", "74hc", "74ls"]):
            return "logic"
        if "driver" in desc:
            return "driver"
        if any(k in desc for k in ["optocoupler", "isolation"]):
            return "isolation"

        return "unknown"

    def _guess_package_type(self, package: str) -> str:
        pkg = package.lower()
        tht_keywords = ["dip", "sip", "to-", "radial", "axial", "through", "tht"]
        if any(k in pkg for k in tht_keywords):
            return "THT"
        if "module" in pkg or "bga" in pkg or "qfn" in pkg or "lqfp" in pkg:
            return "SMD"
        return "SMD"

    def lookup(self, lcsc_part: str) -> Optional[JLCPart]:
        """Look up a single part by exact LCSC number (e.g., 'C123456')."""
        if not self.available:
            return None

        # Normalize LCSC part number
        normalized = lcsc_part.strip().upper()
        if not normalized.startswith("C"):
            normalized = f"C{normalized}"
        try:
            lcsc_id = int(normalized[1:])
        except ValueError:
            return None

        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM jlc_components WHERE lcsc = ?",
                    (lcsc_id,)
                )
                row = cursor.fetchone()
        except sqlite3.Error as e:
            logger.warning(f"JLCParts lookup failed for {lcsc_part}: {e}")
            return None

        if row is None:
            return None
        return self._row_to_part(row)

    # -- search -------------------------------------------------------------

    def search(
        self,
        query: str = "",
        package: Optional[str] = None,
        min_stock: int = 0,
        category: Optional[str] = None,
        limit: int = 50,
        sort: str = "stock",
    ) -> List[JLCPart]:
        """
        Search the catalogue by value, rating, package, category and text.

        Values are matched numerically, so ``"10k 0603"`` returns 10 kΩ parts
        only — not 110 kΩ or 910 kΩ. ``"100nF 50V"`` returns capacitors of
        100 nF rated at least 50 V. If nothing matches numerically the query
        falls back to a text search, so a query that is really a description
        ("10k potentiometer") still returns something instead of an empty page.

        Args:
            query: Free-text query, e.g. ``"10k 0603"``, ``"ldo 3.3v"``,
                ``"esp32"``.
            package: Package filter, e.g. ``"0402"``, ``"SOT-23"``.
            min_stock: Minimum stock quantity.
            category: Category filter, e.g. ``"resistor"``, ``"regulator_ldo"``.
            limit: Maximum results.
            sort: ``"stock"`` (default, most stock first), ``"price"``
                (cheapest first), or ``"value"``.

        Returns:
            Matching parts, best first. Empty when the catalogue is absent.
        """
        return self.search_explained(
            query, package=package, min_stock=min_stock, category=category,
            limit=limit, sort=sort,
        ).parts

    def lookup_mpn(self, mpn: str) -> List[JLCPart]:
        """
        Find every catalogue part with this exact manufacturer part number.

        The same MPN is sold under several LCSC numbers — different packages,
        different stock, different prices — so all of them are returned, best
        stock first, and the caller decides.

        This is a separate query from :meth:`search` because a text search ranks
        by stock and then checks whether the first hit happens to match, which
        misses the part whenever a near-match outsells it. "AMS1117-3.3" is in
        the catalogue six times, and the fuzzy path returned none of them.
        """
        if not self.available or not mpn:
            return []
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM jlc_components "
                    "WHERE mfr = ? COLLATE NOCASE "
                    "ORDER BY preferred DESC, stock DESC",
                    (mpn.strip(),),
                ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Catalog MPN lookup failed for %r: %s", mpn, exc)
            return []
        return [self._row_to_part(row) for row in rows]

    def lookup_mpn_prefix(self, prefix: str, limit: int = 40) -> List[JLCPart]:
        """
        Catalogue entries whose part number starts with this prefix, best stock
        first.

        Used to find a figure published for a *sibling* of a part. Datasheet
        summaries differ between manufacturers of the same part number, and they
        also differ between variants: ``AMS1117-3.3`` states a 150 °C junction
        limit while ``AMS1117-3.3OE`` states nothing usable. Reading the family is
        better than declaring the figure unknown.
        """
        if not self.available or len(prefix) < 4:
            return []
        escaped = prefix.replace("%", "\\%").replace("_", "\\_")
        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM jlc_components "
                    "WHERE mfr LIKE ? ESCAPE '\\' COLLATE NOCASE "
                    "ORDER BY preferred DESC, stock DESC LIMIT ?",
                    (f"{escaped}%", int(limit)),
                ).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Catalog prefix lookup failed for %r: %s", prefix, exc)
            return []
        return [self._row_to_part(row) for row in rows]

    def search_explained(
        self,
        query: str = "",
        package: Optional[str] = None,
        min_stock: int = 0,
        category: Optional[str] = None,
        limit: int = 50,
        sort: str = "stock",
    ) -> "SearchOutcome":
        """
        Search and report how the query was interpreted.

        Returned alongside the parts so that a UI can show *why* these results
        came back — which value was matched, which package was relaxed — rather
        than presenting a list the user has to trust blindly.
        """
        parsed = parse_query(
            query, package=package, category=category,
            min_stock=min_stock, limit=limit,
        )
        outcome = SearchOutcome(query=parsed, parts=[], notes=[])

        if not self.available:
            outcome.notes.append("Component catalogue is not installed")
            return outcome

        if parsed.is_parametric:
            outcome.parts, notes = self._parametric_search(parsed, sort=sort)
            outcome.notes.extend(notes)
            if outcome.parts:
                return outcome
            outcome.notes.append(
                "No part matched those numbers; falling back to a text search"
            )

        outcome.parts = self._text_search(parsed, sort=sort)
        if not outcome.parts and not parsed.text_terms and not parsed.category:
            outcome.notes.append("Empty query")
        return outcome

    def _parametric_search(
        self, parsed: ParsedQuery, sort: str = "stock"
    ) -> Tuple[List[JLCPart], List[str]]:
        """Run a numeric query against the in-memory parametric index."""
        notes: List[str] = []
        try:
            with self._connect() as conn:
                index = cached_index(conn, self.db_path, self._categorize)
                hits = index.find(parsed, limit=parsed.limit)

                if not hits and parsed.packages:
                    # A package is a preference, not a hard requirement: a 10 kΩ
                    # 0402 part is more useful to offer than nothing at all.
                    relaxed = _dataclass_replace(parsed, packages=[])
                    hits = index.find(relaxed, limit=parsed.limit)
                    if hits:
                        notes.append(
                            "No match in package "
                            + "/".join(parsed.packages)
                            + "; showing other packages"
                        )

                if not hits:
                    return [], notes

                hits = self._apply_sort(hits, sort)
                ordered = [h.lcsc for h in hits]
                parts = self._hydrate(conn, ordered)
        except sqlite3.Error as exc:
            logger.warning("Parametric search failed for %r: %s", parsed.raw, exc)
            return [], [f"Catalog query failed: {exc}"]

        notes.append(
            f"Matched numerically: {parsed.summary()}"
        )
        return parts, notes

    @staticmethod
    def _apply_sort(hits: List[IndexedPart], sort: str) -> List[IndexedPart]:
        """
        Re-rank index hits.

        The default puts Preferred parts first, because they avoid JLCPCB's
        extended-part handling and are the pragmatic choice to assemble. An
        explicit price sort does not: "cheapest first" that does not start with
        the cheapest part would be a lie, so there the Preferred flag only breaks
        ties.
        """
        if sort == "price":
            return sorted(
                hits,
                key=lambda p: (
                    p.unit_price if p.unit_price else 1e9,
                    0 if p.preferred else (1 if p.basic else 2),
                    -p.stock,
                ),
            )
        if sort == "value":
            return sorted(
                hits,
                key=lambda p: (
                    p.params.get("primary", 0.0),
                    0 if p.preferred else (1 if p.basic else 2),
                    -p.stock,
                ),
            )
        return hits

    def _hydrate(
        self, conn: sqlite3.Connection, ordered_lcsc: List[int]
    ) -> List[JLCPart]:
        """
        Load full rows for the given LCSC ids, preserving the requested order.

        The index keeps only the values needed for matching; everything else —
        prices, datasheet, description — is read from the catalogue for the
        handful of parts actually being returned.
        """
        if not ordered_lcsc:
            return []
        placeholders = ",".join("?" * len(ordered_lcsc))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM jlc_components WHERE lcsc IN ({placeholders})",
            ordered_lcsc,
        ).fetchall()
        by_id = {int(row["lcsc"]): self._row_to_part(row) for row in rows}
        return [by_id[lcsc] for lcsc in ordered_lcsc if lcsc in by_id]

    def _text_search(self, parsed: ParsedQuery, sort: str = "stock") -> List[JLCPart]:
        """
        Substring search over description and part number.

        Used for queries that are names rather than values ("ESP32-WROOM",
        "AMS1117") and as the fallback when a numeric query finds nothing.
        """
        conditions: List[str] = []
        params: List[Any] = []

        for term in parsed.text_terms:
            like = f"%{term.replace('%', '\\%').replace('_', '\\_')}%"
            conditions.append(
                "(description LIKE ? ESCAPE '\\' COLLATE NOCASE "
                "OR mfr LIKE ? ESCAPE '\\' COLLATE NOCASE)"
            )
            params.extend([like, like])

        for pkg in parsed.packages:
            conditions.append("package LIKE ? COLLATE NOCASE")
            params.append(f"%{pkg}%")

        if parsed.category:
            catalog_categories = _INTERNAL_TO_CATALOG.get(parsed.category)
            if catalog_categories:
                placeholders = ",".join("?" * len(catalog_categories))
                conditions.append(f"category IN ({placeholders})")
                params.extend(catalog_categories)

        if parsed.min_stock > 0:
            conditions.append("stock >= ?")
            params.append(parsed.min_stock)

        if not conditions:
            return []

        where_clause = " AND ".join(conditions)
        order = {
            "price": "preferred DESC, stock DESC",
            "value": "preferred DESC, stock DESC",
            "stock": "preferred DESC, stock DESC",
        }.get(sort, "preferred DESC, stock DESC")

        # A refined category is decided in Python from the row, so the whole
        # leaf has to be read: applying a LIMIT first would let a common sibling
        # subtype crowd out a rarer one. For everything else, fetch more than
        # asked for so the category post-filter has something to work with.
        refined = parsed.category in _REFINED_CATEGORIES
        fetch: Optional[int] = None if refined else max(int(parsed.limit * 5), 50)

        sql = (
            "SELECT * FROM jlc_components "
            f"WHERE {where_clause} "
            f"ORDER BY {order}"
        )
        if fetch is not None:
            sql += " LIMIT ?"
            params.append(fetch)

        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            logger.warning("Catalog text search failed for %r: %s", parsed.raw, exc)
            return []

        parts = [self._row_to_part(row) for row in rows]

        if parsed.category:
            parts = [p for p in parts if parsed.category in p.category]

        return parts[: parsed.limit]

    # -- substitution -------------------------------------------------------

    def find_substitutes(
        self,
        lcsc_part: str,
        limit: int = 10,
        min_stock: Optional[int] = None,
        same_package: bool = True,
    ) -> List["Substitute"]:
        """
        Find parts that can stand in for a given part.

        This is the question that matters when a part is out of stock: *what can
        I buy instead?* The answer is only trustworthy if the comparison is
        mechanical, so each candidate is returned with the checks that were made
        and the differences that were found. Nothing is called "equivalent"
        without saying what was compared.

        The comparison requires the original to have a parsed value (resistance,
        capacitance, inductance or frequency). A part identified only by a part
        number has no specification to match on, and an empty list is returned
        rather than a guess.

        Args:
            lcsc_part: LCSC number of the part being replaced.
            limit: Maximum substitutes to return.
            min_stock: Minimum stock for a candidate. Defaults to the original's
                minimum order quantity, so a substitute cannot be less available
                than what it replaces.
            same_package: Require the same package, so the footprint still fits.

        Returns:
            Candidates, best first, each with reasons and caveats. Properties
            that cannot be compared mechanically — tolerance, voltage rating,
            power rating — are reported as caveats rather than used to filter
            candidates out, so a usable part is disclosed rather than hidden.
        """
        original = self.lookup(lcsc_part)
        if original is None:
            return []

        params = original.parameters
        primary_field = params.get("primary_field")
        primary_value = params.get("primary")
        if not primary_field or primary_value is None:
            logger.info(
                "No parsed value for %s; cannot judge substitutes", lcsc_part
            )
            return []

        if min_stock is None:
            min_stock = original.min_order or 1

        query = ParsedQuery(
            raw=f"substitute for {lcsc_part}",
            category=original.category,
            min_stock=min_stock,
            limit=limit,
        )
        query.values.append(
            ValueConstraint(
                value=primary_value,
                unit="",
                family=primary_field,
                raw=original.specification_summary() or f"{primary_value:g}",
                mode="exact",
            )
        )
        if same_package and original.package:
            query.packages.append(original.package.lower())
        # Tolerance is deliberately not used as a filter here, even when the
        # original states one. Filtering would hide a usable part instead of
        # disclosing that its tolerance is looser, and the point of this method
        # is to show the evidence rather than to pre-judge it. _compare_parts
        # reports any difference as a caveat.

        try:
            with self._connect() as conn:
                index = cached_index(conn, self.db_path, self._categorize)
                hits = index.find(query, limit=limit * 4)
                hits = [h for h in hits if h.lcsc != int(original.lcsc_part[1:])]
                candidates = self._hydrate(conn, [h.lcsc for h in hits])[:limit]
        except sqlite3.Error as exc:
            logger.warning("Substitute search failed for %s: %s", lcsc_part, exc)
            return []

        results: List[Substitute] = []
        for candidate in candidates:
            if candidate.mfr_part and candidate.mfr_part == original.mfr_part:
                continue
            reasons, caveats = self._compare_parts(original, candidate, primary_field)
            results.append(Substitute(part=candidate, reasons=reasons, caveats=caveats))

        results.sort(
            key=lambda s: (
                0 if s.part.is_preferred else 1,
                len(s.caveats),
                -s.part.stock,
            )
        )
        return results[:limit]

    @staticmethod
    def _compare_parts(
        original: JLCPart, candidate: JLCPart, primary_field: str
    ) -> Tuple[List[str], List[str]]:
        """
        State what makes a candidate usable and what a buyer should check.

        Only claims that were actually verified are listed as reasons. Anything
        that could not be verified, or that differs, becomes a caveat — the
        point is to leave the user with an honest account, not a green tick.
        """
        reasons: List[str] = []
        caveats: List[str] = []

        field_labels = {
            "resistance": "resistance",
            "capacitance": "capacitance",
            "inductance": "inductance",
            "frequency": "frequency",
            "output_voltage": "output voltage",
            "zener_voltage": "zener voltage",
        }
        label = field_labels.get(primary_field, primary_field.replace("_", " "))

        original_value = original.parameters.get(primary_field)
        candidate_value = candidate.parameters.get(primary_field)
        if values_match(original_value, candidate_value, 0.0):
            reasons.append(f"same {label} ({original.specification_summary() or original_value})")
        else:
            caveats.append(
                f"{label} differs: {candidate_value} vs {original_value}"
            )

        if original.package and candidate.package:
            if original.package.lower() == candidate.package.lower():
                reasons.append(f"same package ({original.package})")
            else:
                caveats.append(
                    f"package differs: {candidate.package} vs {original.package}"
                )

        if original.catalog_category and candidate.catalog_category:
            if original.catalog_category != candidate.catalog_category:
                caveats.append(
                    f"catalogue category differs: {candidate.catalog_category}"
                )

        original_tolerance = original.tolerance
        candidate_tolerance = candidate.tolerance
        if original_tolerance is not None:
            if candidate_tolerance is None:
                caveats.append("tolerance not listed for this part; verify it")
            elif candidate_tolerance <= original_tolerance * 1.0001:
                reasons.append(
                    f"tolerance ±{candidate_tolerance * 100:g}% is at least as tight "
                    f"as ±{original_tolerance * 100:g}%"
                )
            else:
                caveats.append(
                    f"looser tolerance: ±{candidate_tolerance * 100:g}% vs "
                    f"±{original_tolerance * 100:g}%"
                )

        for field_name, readable in (
            ("voltage", "voltage rating"),
            ("power", "power rating"),
            ("current", "current rating"),
        ):
            original_rating = original.parameters.get(field_name)
            candidate_rating = candidate.parameters.get(field_name)
            if original_rating is None:
                continue
            if candidate_rating is None:
                caveats.append(f"{readable} not listed for this part; verify it")
            elif candidate_rating + 1e-12 >= original_rating:
                units = {"voltage": "V", "power": "W", "current": "A"}[field_name]
                reasons.append(
                    f"{readable} at least as high "
                    f"({format_value(candidate_rating, units)})"
                )
            else:
                units = {"voltage": "V", "power": "W", "current": "A"}[field_name]
                caveats.append(
                    f"lower {readable}: {format_value(candidate_rating, units)} vs "
                    f"{format_value(original_rating, units)}"
                )

        if candidate.stock:
            reasons.append(f"in stock ({candidate.stock:,})")
        else:
            caveats.append("no stock reported")

        if original.unit_price and candidate.unit_price:
            difference = candidate.unit_price - original.unit_price
            if difference < 0:
                reasons.append(
                    f"cheaper ({candidate.unit_price:g} vs {original.unit_price:g})"
                )

        return reasons, caveats

    def warm(self) -> int:
        """
        Build the parametric index now instead of on the first search.

        Parsing every quantitative value in 180,000 rows takes a few seconds and
        happens once per process. Calling this at start-up, in the background,
        keeps that cost off the first user-visible search. Safe to call twice:
        the index is cached. Returns the number of indexed parts.
        """
        if not self.available:
            return 0
        try:
            with self._connect() as conn:
                index = cached_index(conn, self.db_path, self._categorize)
            # Also count the categories, which the API serves to populate the
            # search filters. Both costs then land here rather than on the first
            # user-visible request.
            self.internal_category_counts()
            return len(index)
        except sqlite3.Error as exc:
            logger.warning("Could not build the parametric index: %s", exc)
            return 0

    def internal_category_counts(self) -> Dict[str, int]:
        """
        Count the catalogue by this platform's categories.

        The catalogue's own leaves are broader than the platform's categories —
        "Diodes" covers zeners, Schottkys and LEDs — so a category list derived
        from the leaves alone would omit every refined subtype and offer the user
        a category they cannot then select. Splitting each row is a scan of two
        columns and takes about a second, so the result is cached per catalogue
        file and prepared by :meth:`warm`.
        """
        if not self.available:
            return {}

        key = _catalog_stamp(self.db_path)
        cached = _CATEGORY_COUNT_CACHE.get(key)
        if cached is not None:
            return cached

        counts: Dict[str, int] = {}
        try:
            with self._connect() as conn:
                for catalog_category, description in conn.execute(
                    "SELECT category, description FROM jlc_components"
                ):
                    category = self._categorize(
                        catalog_category or "", description or "", ""
                    )
                    counts[category] = counts.get(category, 0) + 1
        except sqlite3.Error as exc:
            logger.warning("Could not count catalog categories: %s", exc)
            return {}

        _CATEGORY_COUNT_CACHE.clear()
        _CATEGORY_COUNT_CACHE[key] = counts
        return counts

    def count(self) -> int:
        """Return total component count in catalog."""
        if not self.available:
            return 0
        try:
            with self._connect() as conn:
                return int(conn.execute("SELECT COUNT(*) FROM jlc_components").fetchone()[0])
        except sqlite3.Error:
            return 0

    def category_counts(self, min_stock: int = 0) -> Dict[str, int]:
        """
        Count the catalogue's own categories.

        Returned with the catalogue's names, not the platform's, because this is
        used to show what the downloaded file actually contains.
        """
        if not self.available:
            return {}
        conditions = "WHERE stock >= ?" if min_stock > 0 else ""
        params: Tuple[Any, ...] = (min_stock,) if min_stock > 0 else ()
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT category, COUNT(*) FROM jlc_components "
                    f"{conditions} GROUP BY category ORDER BY 2 DESC",
                    params,
                ).fetchall()
        except sqlite3.Error:
            return {}
        return {(category or "(uncategorized)"): count for category, count in rows}


# Where the catalog comes from.
#
# The upstream yaqwsx/jlcparts dataset is a ~10 GB multi-volume zip that most zip
# libraries cannot open, and its old download URL no longer resolves. CDFER's
# republished copy carries the same data, rebuilt daily by GitHub Actions, as a
# single SQLite file filtered to parts that are in stock.
CATALOG_URL = (
    "https://cdfer.github.io/jlcpcb-parts-database/jlcpcb-components.sqlite3"
)
CATALOG_CSV_URL = (
    "https://cdfer.github.io/jlcpcb-parts-database/"
    "jlcpcb-components-basic-preferred.csv"
)
CATALOG_SCHEMA_FORMAT = "source-db-v2"


def default_catalog_path() -> Path:
    """
    Standard location for the downloaded catalog.

    Follows the XDG base-directory convention, so setting ``XDG_CACHE_HOME``
    relocates it. ``JLC_PARTS_CATALOG`` overrides discovery entirely (see
    ``JLCPartsDatabase._find_catalog``).
    """
    import os

    cache_root = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_root) if cache_root else Path.home() / ".cache"
    return base / "kicad-tools" / "jlcparts.sqlite3"


def download_catalog(
    dest: Optional[Path] = None,
    url: str = CATALOG_URL,
    force: bool = False,
    progress: bool = True,
    timeout: float = 1800.0,
) -> Path:
    """
    Download the SQLite component catalog.

    Fetches a single ~145 MB SQLite file holding roughly 180,000 in-stock
    JLCPCB/LCSC parts, verifies that it opens and contains components, then
    installs it at ``dest``.

    The transfer goes to a temporary file first and is promoted only after
    verification, so an interrupted download can never leave a half-written
    catalog silently degrading search results.

    Args:
        dest: Where to install the catalog. Defaults to
            ``~/.cache/kicad-tools/jlcparts.sqlite3``.
        url: Override the download URL.
        force: Download again even if a catalog is already present.
        progress: Print progress to stdout.
        timeout: Request timeout in seconds.

    Returns:
        Path to the installed catalog.

    Raises:
        RuntimeError: if the download fails or the file is not a usable catalog.
    """
    import requests

    dest = Path(dest) if dest else default_catalog_path()

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot write to {dest.parent} ({exc}). "
            f"Choose another location with --dest, or set XDG_CACHE_HOME or "
            f"JLC_PARTS_CATALOG to a writable directory."
        ) from exc

    # Fail early with a clear message rather than after a 145 MB transfer.
    if not os.access(dest.parent, os.W_OK):
        raise RuntimeError(
            f"{dest.parent} is not writable. Choose another location with "
            f"--dest, or set XDG_CACHE_HOME or JLC_PARTS_CATALOG."
        )

    def log(message: str) -> None:
        if progress:
            print(message)

    if dest.exists() and not force:
        try:
            count = JLCPartsDatabase(dest).count()
            log(f"Catalog already present: {dest} ({count:,} components)")
            return dest
        except Exception:
            log(f"Existing catalog at {dest} is unusable; downloading again")

    partial = dest.with_suffix(".download.part")
    partial.unlink(missing_ok=True)

    log(f"Downloading component catalog (~145 MB) from {url}")
    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length") or 0)
            written = 0
            reported = 0
            with partial.open("wb") as out:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if not chunk:
                        continue
                    out.write(chunk)
                    written += len(chunk)
                    if progress and total and written - reported >= (10 << 20):
                        reported = written
                        print(
                            f"  {written / (1 << 20):5.1f} / "
                            f"{total / (1 << 20):.1f} MiB "
                            f"({written * 100 // total}%)"
                        )
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"Could not download the component catalog from {url}: {exc}"
        ) from exc

    log(f"Downloaded {partial.stat().st_size / (1 << 20):.1f} MiB; verifying...")

    count = 0
    try:
        probe = JLCPartsDatabase(partial)
        count = probe.count()
        if count <= 0:
            raise RuntimeError("the catalog contains no components")
    except Exception as exc:
        for leftover in _sqlite_sidecars(partial):
            leftover.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"Downloaded file is not a usable catalog ({exc}); it may be an "
            "error page or a truncated transfer"
        ) from exc

    partial.replace(dest)
    # Opening the file to verify it can create -wal/-shm sidecars; clean up the
    # ones that belonged to the temporary name.
    for leftover in _sqlite_sidecars(partial):
        leftover.unlink(missing_ok=True)

    log(f"Catalog ready: {dest} ({count:,} components)")
    return dest


def _catalog_stamp(path: Any) -> Tuple[str, int]:
    """Identify a catalogue file by path and modification time, for caching."""
    import os

    try:
        return (str(path), os.stat(str(path)).st_mtime_ns)
    except OSError:
        return (str(path), 0)


# Category counts are a scan of the whole catalogue, so they are cached per file.
_CATEGORY_COUNT_CACHE: Dict[Tuple[str, int], Dict[str, int]] = {}


def _sqlite_sidecars(path: Path) -> List[Path]:
    """Return the -wal/-shm files SQLite may have created for `path`."""
    return [Path(f"{path}-wal"), Path(f"{path}-shm")]


# Split archive extraction helpers
_SPLIT_MARKER = b"PK\x07\x08"
_LOCAL_HEADER = b"PK\x03\x04"

def _is_split_archive(archive: Path) -> bool:
    try:
        with archive.open("rb") as f:
            return f.read(4)[:4] == _SPLIT_MARKER
    except Exception:
        return False


def _extract_catalog(archive: Path, dest: Path) -> None:
    if _is_split_archive(archive):
        _extract_split_archive(archive, dest)
    else:
        _extract_single_disk(archive, dest)


def _extract_single_disk(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        sqlite_members = [n for n in names if n.lower().endswith((".sqlite3", ".sqlite", ".db"))]
        member = sqlite_members[0] if sqlite_members else (names[0] if len(names) == 1 else None)
        if not member:
            raise RuntimeError(f"No SQLite member found in archive: {names}")

        tmp = dest.with_suffix(".extract.tmp")
        try:
            with zf.open(member) as src, tmp.open("wb") as out:
                while chunk := src.read(1 << 20):
                    out.write(chunk)
            import os
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)


def _extract_split_archive(archive: Path, dest: Path) -> None:
    """Stream-extract first member of split zip -s archive."""
    tmp = dest.with_suffix(".extract.tmp")
    try:
        with archive.open("rb") as fh:
            marker = fh.read(4)
            if marker[:4] != _SPLIT_MARKER:
                fh.seek(0)

            header = fh.read(30)
            if len(header) < 30 or header[:4] != _LOCAL_HEADER:
                raise RuntimeError("Split archive missing local file header")

            method = struct.unpack_from("<H", header, 8)[0]
            name_len = struct.unpack_from("<H", header, 26)[0]
            extra_len = struct.unpack_from("<H", header, 28)[0]

            if method != 8:
                raise RuntimeError(f"Member not deflate-compressed (method={method})")

            fh.read(name_len + extra_len)

            decompressor = zlib.decompressobj(-15)  # raw deflate
            with tmp.open("wb") as out:
                while not decompressor.eof:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        out.write(decompressor.flush())
                        break
                    out.write(decompressor.decompress(chunk))
                else:
                    out.write(decompressor.flush())

        import os
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)