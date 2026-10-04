"""
JLCPCB/LCSC Component Database Integration for AI-Powered Electronics Design Platform.

Wraps the kicad-tools JlcpartsCatalog for offline LCSC part lookups and parametric search.
Supports the yaqwsx/jlcparts SQLite dataset.
"""

import sqlite3
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


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

        # Default fallback
        return f"Package_SMD:{package.upper()}"

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
            "tvs": "Protection:TVS",
            "varistor": "Protection:Varistor",
            "thermistor": "Device:Thermistor",
            "sensor": "Sensor:Generic",
            "rf_module": "RF_Module:Module_Generic",
            "memory": "Memory:EEPROM",
            "logic": "Logic_Gate:AND",
            "driver": "Driver:Gate_Driver",
            "isolation": "Isolation:Optocoupler",
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
        }


class JLCPartsDatabase:
    """
    JLCPCB/LCSC Component Database using the yaqwsx/jlcparts SQLite dataset.
    
    Usage:
        db = JLCPartsDatabase()
        if db.available:
            parts = db.search("10k 0402")
            part = db.lookup("C123456")
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or self._find_catalog()
        self._catalog_available = self.db_path is not None and self.db_path.exists()

    def _find_catalog(self) -> Optional[Path]:
        """Find the jlcparts SQLite catalog in standard locations."""
        candidates = [
            Path.home() / ".cache" / "kicad-tools" / "jlcparts.sqlite3",
            Path.home() / ".jlcparts" / "jlcparts.sqlite3",
            Path("/tmp") / "jlcparts.sqlite3",
            Path.cwd() / "jlcparts.sqlite3",
        ]
        for c in candidates:
            if c.exists():
                return c
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

        return JLCPart(
            lcsc_part=lcsc_part,
            mfr_part=get_str("mfr"),
            manufacturer=get_str("manufacturer"),
            description=get_str("description"),
            category=get_str("category") or self._categorize(get_str("description"), get_str("package")),
            package=get_str("package"),
            package_type=self._guess_package_type(get_str("package")),
            stock=get_int("stock", 0),
            min_order=get_int("min_order", 1),
            prices=parse_prices(row["price"] if "price" in row.keys() else None),
            is_basic=get_str("library_type").lower() == "basic",
            is_preferred=get_str("library_type").lower() == "preferred",
            datasheet_url=get_str("datasheet"),
            product_url=f"https://jlcpcb.com/partdetail/{lcsc_part}" if lcsc_part else "",
        )

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

    def _categorize(self, description: str, package: str) -> str:
        """Simple categorization based on description/package."""
        desc = description.lower()
        pkg = package.lower()

        if any(k in desc for k in ["resistor", "res ", "ohm", "ω", "kΩ", "mΩ"]):
            return "resistor"
        if any(k in desc for k in ["capacitor", "cap ", "uf", "pf", "nf", "µf"]):
            return "capacitor"
        if any(k in desc for k in ["inductor", "ind ", "uh", "mh", "nh"]):
            return "inductor"
        if any(k in desc for k in ["zener", "zener diode"]):
            return "zener"
        if any(k in desc for k in ["schottky", "schottky diode"]):
            return "schottky"
        if any(k in desc for k in ["led", "light emitting"]):
            return "led"
        if any(k in desc for k in ["diode", "rectifier"]):
            return "diode"
        if any(k in desc for k in ["mosfet", "mosfet "]):
            return "mosfet"
        if any(k in desc for k in ["transistor", "bjt "]):
            return "transistor"
        if any(k in desc for k in ["ldo", "linear regulator", "voltage regulator"]):
            return "regulator_ldo"
        if any(k in desc for k in ["buck", "step-down", "dc-dc buck"]):
            return "regulator_buck"
        if any(k in desc for k in ["boost", "step-up", "dc-dc boost"]):
            return "regulator_boost"
        if any(k in desc for k in ["microcontroller", "mcu ", "arm cortex", "esp32", "stm32", "rp2040"]):
            return "microcontroller"
        if any(k in desc for k in ["opamp", "operational amplifier"]):
            return "opamp"
        if any(k in desc for k in ["comparator"]):
            return "comparator"
        if any(k in desc for k in ["crystal", "oscillator", "xtal"]):
            return "crystal"
        if any(k in desc for k in ["connector", "conn ", "header", "socket"]):
            return "connector"
        if any(k in desc for k in ["switch", "button", "tactile"]):
            return "switch"
        if any(k in desc for k in ["fuse", "polyfuse", "ppx"]):
            return "fuse"
        if any(k in desc for k in ["tvs", "esd protection"]):
            return "tvs"
        if any(k in desc for k in ["sensor", "accelerometer", "gyro", "temperature"]):
            return "sensor"
        if any(k in desc for k in ["rf ", "wifi", "bluetooth", "zigbee", "lora", "module"]):
            return "rf_module"
        if any(k in desc for k in ["memory", "eeprom", "flash", "ram", "spi", "i2c"]):
            return "memory"
        if any(k in desc for k in ["logic gate", "74hc", "74ls", "and ", "or ", "not "]):
            return "logic"
        if any(k in desc for k in ["driver", "gate driver", "motor driver"]):
            return "driver"
        if any(k in desc for k in ["optocoupler", "optocoupler", "isolation"]):
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

    def search(
        self,
        query: str,
        package: Optional[str] = None,
        min_stock: int = 0,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List[JLCPart]:
        """
        Parametric search by free-text query, package, category, and stock.
        
        Args:
            query: Free-text search (e.g., "10k 0402", "ldo 3.3v", "esp32")
            package: Exact package filter (e.g., "0402", "SOT-23")
            min_stock: Minimum stock quantity
            category: Category filter (e.g., "resistor", "regulator_ldo")
            limit: Maximum results
        """
        if not self.available:
            return []

        terms = [t for t in query.split() if t]
        if not terms:
            return []

        conditions = []
        params = []

        # Each term matches description OR mfr (manufacturer part number)
        for term in terms:
            like = f"%{term.replace('%', '\\%').replace('_', '\\_')}%"
            conditions.append(
                "(description LIKE ? ESCAPE '\\' COLLATE NOCASE "
                "OR mfr LIKE ? ESCAPE '\\' COLLATE NOCASE)"
            )
            params.extend([like, like])

        if package:
            conditions.append("package = ? COLLATE NOCASE")
            params.append(package)

        if category:
            # Category is not a column, we'll post-filter
            pass

        if min_stock > 0:
            conditions.append("stock >= ?")
            params.append(min_stock)

        where_clause = " AND ".join(conditions)
        sql = (
            "SELECT * FROM jlc_components "
            f"WHERE {where_clause} "
            "ORDER BY CASE library_type "
            "WHEN 'basic' THEN 0 WHEN 'preferred' THEN 1 ELSE 2 END, "
            "stock DESC "
            "LIMIT ?"
        )
        params.append(int(limit * 3))  # Fetch more for category post-filter

        try:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()
        except sqlite3.Error as e:
            logger.warning(f"JLCParts search failed for {query!r}: {e}")
            return []

        parts = [self._row_to_part(row) for row in rows]

        # Post-filter by category if specified
        if category:
            parts = [p for p in parts if category.lower() in p.category.lower()]

        return parts[:limit]

    def count(self) -> int:
        """Return total component count in catalog."""
        if not self.available:
            return 0
        try:
            with self._connect() as conn:
                return int(conn.execute("SELECT COUNT(*) FROM jlc_components").fetchone()[0])
        except sqlite3.Error:
            return 0


def download_catalog(
    dest: Optional[Path] = None,
    base_url: str = "https://yaqwsx.github.io/jlcparts/data",
    force: bool = False,
    progress: bool = True
) -> Path:
    """
    Download and assemble the jlcparts catalog from yaqwsx/jlcparts dataset.
    
    This downloads the split-zip SQLite dataset (hundreds of MB) from GitHub Pages.
    """
    import requests
    import zipfile
    import zlib
    import struct

    dest = dest or Path.home() / ".cache" / "kicad-tools" / "jlcparts.sqlite3"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        if progress:
            print(f"Catalog already exists: {dest}")
        return dest

    def log(msg: str):
        if progress:
            print(msg)

    log(f"Discovering dataset segments at {base_url}...")

    # Discover split parts (cache.z01, cache.z02, ..., cache.zip)
    part_urls = []
    index = 1
    while True:
        url = f"{base_url}/cache.z{index:02d}"
        try:
            resp = requests.head(url, timeout=30, allow_redirects=True)
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            part_urls.append(url)
            index += 1
            if index > 100:
                break
        except requests.RequestException:
            break

    part_urls.append(f"{base_url}/cache.zip")
    log(f"Found {len(part_urls)} archive segment(s).")

    # Download and concatenate
    combined_zip = dest.with_suffix(".download.zip")
    total_bytes = 0
    try:
        with combined_zip.open("wb") as out:
            for idx, url in enumerate(part_urls, 1):
                log(f"  [{idx}/{len(part_urls)}] Downloading...")
                with requests.get(url, stream=True, timeout=120) as resp:
                    resp.raise_for_status()
                    for chunk in resp.iter_content(chunk_size=1 << 20):
                        if chunk:
                            out.write(chunk)
                            total_bytes += len(chunk)
        log(f"Downloaded {total_bytes / (1 << 20):.1f} MiB")

        # Extract
        log("Extracting SQLite database...")
        _extract_catalog(combined_zip, dest)
    finally:
        combined_zip.unlink(missing_ok=True)

    count = JLCPartsDatabase(dest).count()
    log(f"Catalog ready: {dest} ({count:,} components)")
    return dest


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