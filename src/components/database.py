"""
Component Database and Parts Registry for AI-Powered Electronics Design Platform.

Provides component search, parametric matching, symbol/footprint resolution,
and distributor inventory data.

Priority:
1. JLCPCB/LCSC offline catalog (yaqwsx/jlcparts dataset) - 600k+ parts
2. Built-in fallback catalog - common parts for offline development
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from src.components.jlcparts import JLCPartsDatabase, JLCPart, download_catalog


@dataclass
class ComponentSpec:
    """Unified component specification for the design platform."""
    mpn: str
    manufacturer: str
    category: str
    value: str
    package: str
    symbol: str
    footprint: str
    description: str
    stock: int
    price: float
    attributes: Dict[str, Any] = field(default_factory=dict)
    lcsc_part: Optional[str] = None
    is_basic: bool = False
    is_preferred: bool = False
    datasheet_url: str = ""
    product_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "category": self.category,
            "value": self.value,
            "package": self.package,
            "symbol": self.symbol,
            "footprint": self.footprint,
            "description": self.description,
            "stock": self.stock,
            "price": self.price,
            "attributes": self.attributes,
            "lcsc_part": self.lcsc_part,
            "is_basic": self.is_basic,
            "is_preferred": self.is_preferred,
            "datasheet_url": self.datasource_url,
            "product_url": self.product_url,
        }

    @property
    def datasource_url(self) -> str:
        return self.datasheet_url


class ComponentDatabase:
    """
    Unified component database with JLCPCB/LCSC integration.
    
    Automatically uses the yaqwsx/jlcparts offline catalog when available
    (download with `ComponentDatabase.download_catalog()`), otherwise falls
    back to a built-in catalog of common parts.
    """

    def __init__(self, db_path: Optional[Path] = None, prefer_jlcparts: bool = True):
        self.prefer_jlcparts = prefer_jlcparts
        self._jlcparts_db: Optional[JLCPartsDatabase] = None
        self._fallback_catalog: List[ComponentSpec] = []
        
        if prefer_jlcparts:
            self._jlcparts_db = JLCPartsDatabase(db_path)
        
        self._load_fallback_catalog()

    def _load_fallback_catalog(self):
        """Loads a standard set of common electronic components as fallback."""
        self._fallback_catalog = [
            # Regulators
            ComponentSpec(
                mpn="AMS1117-3.3",
                manufacturer="Advanced Monolithic Systems",
                category="regulator_ldo",
                value="3.3V",
                package="SOT-223",
                symbol="Regulator_Linear:AMS1117-3.3",
                footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                description="1A Low Dropout Voltage Regulator 3.3V",
                stock=50000,
                price=0.15,
                attributes={"v_in_max": 15.0, "v_out": 3.3, "i_max": 1.0},
            ),
            ComponentSpec(
                mpn="LM7805",
                manufacturer="Texas Instruments",
                category="regulator_ldo",
                value="5V",
                package="TO-220",
                symbol="Regulator_Linear:LM7805",
                footprint="Package_TO_SOT_THT:TO-220-3_Vertical",
                description="1.5A Positive Voltage Regulator 5V",
                stock=25000,
                price=0.35,
                attributes={"v_in_max": 35.0, "v_out": 5.0, "i_max": 1.5},
            ),
            ComponentSpec(
                mpn="LM2596S-5.0",
                manufacturer="Texas Instruments",
                category="regulator_buck",
                value="5V",
                package="TO-220-5",
                symbol="Regulator_Switching:LM2596",
                footprint="Package_TO_SOT_THT:TO-220-5_Vertical",
                description="3A Step-Down Switching Regulator 5V",
                stock=10000,
                price=0.85,
                attributes={"v_in_max": 40.0, "v_out": 5.0, "i_max": 3.0},
            ),
            # Passives - Resistors
            ComponentSpec(
                mpn="RC0805FR-0710KL",
                manufacturer="Yageo",
                category="resistor",
                value="10k",
                package="0805",
                symbol="Device:R",
                footprint="Resistor_SMD:R_0805_2012Metric",
                description="Resistor 10k Ohm 1% 1/8W 0805",
                stock=200000,
                price=0.01,
                attributes={"power_rating": 0.125, "tolerance": "1%"},
            ),
            ComponentSpec(
                mpn="RC0805FR-07330RL",
                manufacturer="Yageo",
                category="resistor",
                value="330",
                package="0805",
                symbol="Device:R",
                footprint="Resistor_SMD:R_0805_2012Metric",
                description="Resistor 330 Ohm 1% 1/8W 0805",
                stock=200000,
                price=0.01,
                attributes={"power_rating": 0.125, "tolerance": "1%"},
            ),
            ComponentSpec(
                mpn="RC0603FR-0710KL",
                manufacturer="Yageo",
                category="resistor",
                value="10k",
                package="0603",
                symbol="Device:R",
                footprint="Resistor_SMD:R_0603_1608Metric",
                description="Resistor 10k Ohm 1% 1/10W 0603",
                stock=200000,
                price=0.008,
                attributes={"power_rating": 0.1, "tolerance": "1%"},
            ),
            ComponentSpec(
                mpn="RC0402FR-0710KL",
                manufacturer="Yageo",
                category="resistor",
                value="10k",
                package="0402",
                symbol="Device:R",
                footprint="Resistor_SMD:R_0402_1005Metric",
                description="Resistor 10k Ohm 1% 1/16W 0402",
                stock=200000,
                price=0.006,
                attributes={"power_rating": 0.0625, "tolerance": "1%"},
            ),
            # Passives - Capacitors
            ComponentSpec(
                mpn="CC0805KRX7R9BB106",
                manufacturer="Yageo",
                category="capacitor",
                value="10uF",
                package="0805",
                symbol="Device:C",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                description="Capacitor MLCC 10uF 25V X7R 0805",
                stock=100000,
                price=0.02,
                attributes={"voltage_rating": 25.0, "dielectric": "X7R"},
            ),
            ComponentSpec(
                mpn="CC0805KRX5R7BB226",
                manufacturer="Yageo",
                category="capacitor",
                value="22uF",
                package="0805",
                symbol="Device:C",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                description="Capacitor MLCC 22uF 16V X5R 0805",
                stock=80000,
                price=0.03,
                attributes={"voltage_rating": 16.0, "dielectric": "X5R"},
            ),
            ComponentSpec(
                mpn="CC0603KRX7R9BB104",
                manufacturer="Yageo",
                category="capacitor",
                value="100nF",
                package="0603",
                symbol="Device:C",
                footprint="Capacitor_SMD:C_0603_1608Metric",
                description="Capacitor MLCC 100nF 50V X7R 0603",
                stock=200000,
                price=0.01,
                attributes={"voltage_rating": 50.0, "dielectric": "X7R"},
            ),
            ComponentSpec(
                mpn="CC0402KRX7R8BB104",
                manufacturer="Yageo",
                category="capacitor",
                value="100nF",
                package="0402",
                symbol="Device:C",
                footprint="Capacitor_SMD:C_0402_1005Metric",
                description="Capacitor MLCC 100nF 25V X7R 0402",
                stock=200000,
                price=0.008,
                attributes={"voltage_rating": 25.0, "dielectric": "X7R"},
            ),
            # LEDs
            ComponentSpec(
                mpn="LTST-C190KGKT",
                manufacturer="Lite-On",
                category="led",
                value="Green",
                package="0805",
                symbol="Device:LED",
                footprint="LED_SMD:LED_0805_2012Metric",
                description="LED Green Clear 0805 SMD",
                stock=150000,
                price=0.04,
                attributes={"forward_voltage": 2.1, "current_ma": 20, "wavelength_nm": 570},
            ),
            ComponentSpec(
                mpn="LTST-C190KRKT",
                manufacturer="Lite-On",
                category="led",
                value="Red",
                package="0805",
                symbol="Device:LED",
                footprint="LED_SMD:LED_0805_2012Metric",
                description="LED Red Clear 0805 SMD",
                stock=150000,
                price=0.04,
                attributes={"forward_voltage": 2.0, "current_ma": 20, "wavelength_nm": 625},
            ),
            ComponentSpec(
                mpn="LTST-C190KSKT",
                manufacturer="Lite-On",
                category="led",
                value="Blue",
                package="0805",
                symbol="Device:LED",
                footprint="LED_SMD:LED_0805_2012Metric",
                description="LED Blue Clear 0805 SMD",
                stock=100000,
                price=0.06,
                attributes={"forward_voltage": 3.2, "current_ma": 20, "wavelength_nm": 470},
            ),
            # Microcontrollers
            ComponentSpec(
                mpn="ESP32-WROOM-32E",
                manufacturer="Espressif Systems",
                category="microcontroller",
                value="ESP32",
                package="Module",
                symbol="RF_Module:ESP32-WROOM-32",
                footprint="RF_Module:ESP32-WROOM-32",
                description="Wi-Fi & Bluetooth MCU Module",
                stock=30000,
                price=2.80,
                attributes={"voltage": 3.3, "wifi": True, "bluetooth": True, "cores": 2},
            ),
            ComponentSpec(
                mpn="STM32F103C8T6",
                manufacturer="STMicroelectronics",
                category="microcontroller",
                value="STM32F103",
                package="LQFP-48",
                symbol="MCU_ST_STM32F1:STM32F103C8T6",
                footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",
                description="ARM Cortex-M3 MCU 72MHz 64KB Flash",
                stock=5000,
                price=1.85,
                attributes={"voltage": 3.3, "flash_kb": 64, "ram_kb": 20, "speed_mhz": 72},
            ),
            ComponentSpec(
                mpn="RP2040",
                manufacturer="Raspberry Pi",
                category="microcontroller",
                value="RP2040",
                package="QFN-56",
                symbol="MCU_RaspberryPi:RP2040",
                footprint="Package_QFN:QFN-56_7x7mm_P0.5mm",
                description="Dual ARM Cortex-M0+ MCU",
                stock=20000,
                price=0.80,
                attributes={"voltage": 3.3, "cores": 2, "speed_mhz": 133},
            ),
            # Diodes
            ComponentSpec(
                mpn="1N4148W",
                manufacturer="Vishay",
                category="diode",
                value="1N4148",
                package="SOD-123",
                symbol="Device:D",
                footprint="Diode_SMD:D_SOD-123",
                description="Fast Switching Diode 100V 300mA",
                stock=100000,
                price=0.015,
                attributes={"v_reverse": 100, "i_forward": 0.3},
            ),
            ComponentSpec(
                mpn="SS14",
                manufacturer="Vishay",
                category="diode",
                value="SS14",
                package="SMA",
                symbol="Device:D",
                footprint="Diode_SMD:D_SMA",
                description="Schottky Rectifier 40V 1A",
                stock=50000,
                price=0.03,
                attributes={"v_reverse": 40, "i_forward": 1.0, "vf_max": 0.55},
            ),
            # Transistors
            ComponentSpec(
                mpn="2N7002",
                manufacturer="Nexperia",
                category="mosfet",
                value="2N7002",
                package="SOT-23",
                symbol="Device:MOSFET_N",
                footprint="Package_TO_SOT_SMD:SOT-23-3",
                description="N-Channel MOSFET 60V 115mA",
                stock=100000,
                price=0.025,
                attributes={"v_ds": 60, "i_d": 0.115, "r_ds_on": 7.5},
            ),
            ComponentSpec(
                mpn="SI2302",
                manufacturer="Vishay",
                category="mosfet",
                value="SI2302",
                package="SOT-23",
                symbol="Device:MOSFET_N",
                footprint="Package_TO_SOT_SMD:SOT-23-3",
                description="N-Channel MOSFET 20V 2.3A",
                stock=50000,
                price=0.05,
                attributes={"v_ds": 20, "i_d": 2.3, "r_ds_on": 0.065},
            ),
            # OpAmps
            ComponentSpec(
                mpn="LM358",
                manufacturer="Texas Instruments",
                category="opamp",
                value="LM358",
                package="SOIC-8",
                symbol="Amplifier_Operational:LM358",
                footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                description="Dual Operational Amplifier",
                stock=50000,
                price=0.12,
                attributes={"channels": 2, "gbw_mhz": 1, "v_supply_max": 32},
            ),
            ComponentSpec(
                mpn="TL072",
                manufacturer="Texas Instruments",
                category="opamp",
                value="TL072",
                package="SOIC-8",
                symbol="Amplifier_Operational:TL072",
                footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
                description="Dual JFET-Input OpAmp Low Noise",
                stock=30000,
                price=0.25,
                attributes={"channels": 2, "gbw_mhz": 3, "v_supply_max": 36, "noise_nVrtHz": 18},
            ),
            # Voltage References
            ComponentSpec(
                mpn="TL431",
                manufacturer="Texas Instruments",
                category="voltage_reference",
                value="TL431",
                package="SOT-23",
                symbol="Voltage_Reference:TL431",
                footprint="Package_TO_SOT_SMD:SOT-23-3",
                description="Programmable Precision Reference 2.5V",
                stock=50000,
                price=0.08,
                attributes={"v_ref": 2.5, "accuracy": "0.5%"},
            ),
            # Crystals
            ComponentSpec(
                mpn="8MHz",
                manufacturer="Generic",
                category="crystal",
                value="8MHz",
                package="HC-49S",
                symbol="Crystal:Crystal_GND2",
                footprint="Crystal:Crystal_HC49S",
                description="8MHz Crystal 20pF",
                stock=10000,
                price=0.15,
                attributes={"frequency_mhz": 8, "load_pf": 20},
            ),
            ComponentSpec(
                mpn="16MHz",
                manufacturer="Generic",
                category="crystal",
                value="16MHz",
                package="HC-49S",
                symbol="Crystal:Crystal_GND2",
                footprint="Crystal:Crystal_HC49S",
                description="16MHz Crystal 20pF",
                stock=10000,
                price=0.15,
                attributes={"frequency_mhz": 16, "load_pf": 20},
            ),
        ]

    # ============================================================
    # Public API
    # ============================================================

    @property
    def using_jlcparts(self) -> bool:
        """Whether the JLCPCB catalog is available and being used."""
        return self._jlcparts_db is not None and self._jlcparts_db.available

    @property
    def catalog_size(self) -> int:
        """Total number of parts in active catalog."""
        if self.using_jlcparts:
            return self._jlcparts_db.count()
        return len(self._fallback_catalog)

    @property
    def data_source(self) -> str:
        """Description of active data source."""
        if self.using_jlcparts:
            return f"JLCPCB/LCSC offline catalog ({self.catalog_size:,} parts)"
        return f"Built-in fallback catalog ({len(self._fallback_catalog)} parts)"

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        package: Optional[str] = None,
        min_stock: int = 0,
        limit: int = 50
    ) -> List[ComponentSpec]:
        """
        Search for components.
        
        Args:
            query: Free-text search (e.g., "10k 0402", "ldo 3.3v", "esp32")
            category: Category filter (e.g., "resistor", "regulator_ldo")
            package: Package filter (e.g., "0805", "SOT-23")
            min_stock: Minimum stock quantity
            limit: Maximum results
        """
        # Try JLCParts first if available
        if self.using_jlcparts:
            jlc_results = self._jlcparts_db.search(
                query=query,
                package=package,
                min_stock=min_stock,
                category=category,
                limit=limit
            )
            if jlc_results:
                return [self._jlcpart_to_spec(p) for p in jlc_results]

        # Fallback to built-in catalog
        return self._search_fallback(query, category, package, min_stock, limit)

    def get_by_mpn(self, mpn: str) -> Optional[ComponentSpec]:
        """Find exact component by Manufacturer Part Number (MPN) or LCSC part."""
        # Try JLCParts first
        if self.using_jlcparts:
            # Try as LCSC part number
            if mpn.upper().startswith("C") and mpn[1:].isdigit():
                jlc_part = self._jlcparts_db.lookup(mpn)
                if jlc_part:
                    return self._jlcpart_to_spec(jlc_part)
            
            # Try as MPN via search
            results = self._jlcparts_db.search(query=mpn, limit=1)
            if results and results[0].mfr_part.lower() == mpn.lower():
                return self._jlcpart_to_spec(results[0])

        # Fallback
        for part in self._fallback_catalog:
            if part.mpn.lower() == mpn.lower():
                return part
        return None

    def get_by_lcsc(self, lcsc_part: str) -> Optional[ComponentSpec]:
        """Find component by LCSC part number (e.g., 'C123456')."""
        if self.using_jlcparts:
            jlc_part = self._jlcparts_db.lookup(lcsc_part)
            if jlc_part:
                return self._jlcpart_to_spec(jlc_part)
        return None

    def find_regulator(
        self,
        v_out: float,
        i_max: float,
        v_in_max: Optional[float] = None,
        package: Optional[str] = None,
        ldo: bool = True
    ) -> List[ComponentSpec]:
        """Find voltage regulators matching specifications."""
        if ldo:
            query = f"ldo {v_out}v"
            category = "regulator_ldo"
        else:
            query = f"buck {v_out}v"
            category = "regulator_buck"
        
        results = self.search(query=query, category=category, package=package, min_stock=100)
        
        # Filter by current rating
        filtered = []
        for part in results:
            i_max_attr = part.attributes.get("i_max") or part.attributes.get("current_a")
            if i_max_attr and float(i_max_attr) >= i_max:
                if v_in_max is None or part.attributes.get("v_in_max", 100) >= v_in_max:
                    filtered.append(part)
        
        return filtered

    def find_mcu(self, cores: Optional[int] = None, wifi: bool = False, bluetooth: bool = False) -> List[ComponentSpec]:
        """Find microcontrollers matching requirements."""
        results = self.search(query="mcu", category="microcontroller", min_stock=100)
        
        filtered = []
        for part in results:
            if cores and part.attributes.get("cores", 0) < cores:
                continue
            if wifi and not part.attributes.get("wifi", False):
                continue
            if bluetooth and not part.attributes.get("bluetooth", False):
                continue
            filtered.append(part)
        
        return filtered

    def get_categories(self) -> List[str]:
        """Get list of available categories."""
        cats = set()
        if self.using_jlcparts:
            # We can't easily get categories from JLCParts without full scan
            return [
                "resistor", "capacitor", "inductor", "diode", "led",
                "transistor", "mosfet", "regulator_ldo", "regulator_buck",
                "regulator_boost", "microcontroller", "opamp", "crystal",
                "connector", "switch", "sensor", "rf_module", "memory"
            ]
        for part in self._fallback_catalog:
            cats.add(part.category)
        return sorted(cats)

    def download_catalog(
        self,
        dest: Optional[Path] = None,
        force: bool = False,
        progress: bool = True
    ) -> Path:
        """
        Download the JLCPCB/LCSC component catalog (yaqwsx/jlcparts dataset).
        
        This downloads ~300-500MB of data from GitHub Pages.
        """
        path = download_catalog(dest=dest, force=force, progress=progress)
        # Reinitialize with new catalog
        self._jlcparts_db = JLCPartsDatabase(path)
        return path

    # ============================================================
    # Internal helpers
    # ============================================================

    def _jlcpart_to_spec(self, jlc: JLCPart) -> ComponentSpec:
        """Convert JLCPart to unified ComponentSpec."""
        # Get price from lowest tier
        unit_price = 0.0
        if jlc.prices:
            unit_price = min(p["unit_price"] for p in jlc.prices)
        
        return ComponentSpec(
            mpn=jlc.mfr_part or jlc.lcsc_part,
            manufacturer=jlc.manufacturer,
            category=jlc.category,
            value=jlc.description,
            package=jlc.package,
            symbol=jlc.symbol,
            footprint=jlc.footprint,
            description=jlc.description,
            stock=jlc.stock,
            price=unit_price,
            attributes={},
            lcsc_part=jlc.lcsc_part,
            is_basic=jlc.is_basic,
            is_preferred=jlc.is_preferred,
            datasheet_url=jlc.datasheet_url,
            product_url=jlc.product_url,
        )

    def _search_fallback(
        self,
        query: str,
        category: Optional[str],
        package: Optional[str],
        min_stock: int,
        limit: int
    ) -> List[ComponentSpec]:
        """Search built-in fallback catalog."""
        results = []
        q = query.lower().strip()

        for part in self._fallback_catalog:
            if category and part.category != category:
                continue
            if package and part.package.lower() != package.lower():
                continue
            if part.stock < min_stock:
                continue

            if not q or (
                q in part.mpn.lower()
                or q in part.manufacturer.lower()
                or q in part.value.lower()
                or q in part.description.lower()
                or q in part.category.lower()
            ):
                results.append(part)

        return results[:limit]


# Convenience function
def get_database(db_path: Optional[Path] = None) -> ComponentDatabase:
    """Get a component database instance (singleton-like)."""
    return ComponentDatabase(db_path)