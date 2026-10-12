"""
Component Database and Parts Registry for AI-Powered Electronics Design Platform.

Provides component search, parametric matching, symbol/footprint resolution,
substitute finding, and distributor inventory data.

Priority:
1. The downloaded JLCPCB/LCSC catalog (~180,000 in-stock parts)
2. Built-in fallback catalog - a few common parts, for offline development
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
    # Minimum quantity the distributor sells, and its own attrition figures.
    # Carried through so a bill of materials can round quantities up honestly.
    min_order: int = 1
    attrition: Dict[str, Any] = field(default_factory=dict)

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
            "datasheet_url": self.datasheet_url,
            "product_url": self.product_url,
            "min_order": self.min_order,
            "attrition": self.attrition,
        }

    @property
    def datasource_url(self) -> str:
        return self.datasheet_url

    def specifications(self) -> Dict[str, float]:
        """
        The numeric specifications of this part, parsed from its attributes.

        Returns a dictionary with any of ``resistance``, ``capacitance``,
        ``inductance``, ``frequency``, ``tolerance``, ``voltage``, ``power``,
        ``current``, ``output_voltage`` — in base SI units. Empty when the part
        carries no parseable specification, which is the honest answer for a
        part number that is not described by a value.
        """
        from src.components.parameters import extract_parameters

        if not self.attributes:
            return {}
        parsed = extract_parameters(self.attributes, self.category)
        return {k: v for k, v in parsed.items() if k != "raw"}


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
            ComponentSpec(
                mpn="MT3608",
                manufacturer="Aerosemi",
                category="regulator_boost",
                value="Adjustable",
                package="SOT-23-6",
                symbol="Regulator_Switching:MT3608",
                footprint="Package_TO_SOT_SMD:SOT-23-6",
                description="2A Boost Converter, up to 28V output",
                stock=50000,
                price=0.18,
                attributes={"v_in_max": 24.0, "v_out_max": 28.0, "i_max": 2.0},
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
                mpn="RC0603FR-07240RL",
                manufacturer="Yageo",
                category="resistor",
                value="240",
                package="0603",
                symbol="Device:R",
                footprint="Resistor_SMD:R_0603_1608Metric",
                description="Resistor 240 Ohm 1% 1/10W 0603",
                stock=180000,
                price=0.008,
                attributes={"power_rating": 0.1, "tolerance": "1%"},
            ),
            ComponentSpec(
                mpn="RC0603FR-071KL",
                manufacturer="Yageo",
                category="resistor",
                value="1k",
                package="0603",
                symbol="Device:R",
                footprint="Resistor_SMD:R_0603_1608Metric",
                description="Resistor 1k Ohm 1% 1/10W 0603",
                stock=180000,
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
            # Inductors
            ComponentSpec(
                mpn="SRN6045-470M",
                manufacturer="Bourns",
                category="inductor",
                value="47uH",
                package="1210",
                symbol="Device:L",
                footprint="Inductor_SMD:L_1210_3225Metric",
                description="47uH 1.6A Shielded Power Inductor",
                stock=40000,
                price=0.22,
                attributes={"inductance_uh": 47.0, "i_sat_a": 1.6, "dcr_ohm": 0.12},
            ),
            ComponentSpec(
                mpn="SRN4018-100M",
                manufacturer="Bourns",
                category="inductor",
                value="10uH",
                package="0805",
                symbol="Device:L",
                footprint="Inductor_SMD:L_0805_2012Metric",
                description="10uH 1.1A Shielded Power Inductor",
                stock=45000,
                price=0.18,
                attributes={"inductance_uh": 10.0, "i_sat_a": 1.1, "dcr_ohm": 0.15},
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
                symbol="Transistor_FET:Q_NMOS_GSD",
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
                symbol="Transistor_FET:Q_NMOS_GSD",
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
                symbol="Reference_Voltage:TL431DBZ",
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
                symbol="Device:Crystal",
                footprint="Crystal:Crystal_SMD_HC49-SD",
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
                symbol="Device:Crystal",
                footprint="Crystal:Crystal_SMD_HC49-SD",
                description="16MHz Crystal 20pF",
                stock=10000,
                price=0.15,
                attributes={"frequency_mhz": 16, "load_pf": 20},
            ),
            # Regulators (additional)
            ComponentSpec(
                mpn="LM317L",
                manufacturer="Texas Instruments",
                category="regulator_ldo",
                value="Adjustable",
                package="TO-92",
                symbol="Regulator_Linear:LM317L",
                footprint="Package_TO_SOT_THT:TO-92_Inline",
                description="100mA Adjustable Positive Voltage Regulator",
                stock=30000,
                price=0.25,
                attributes={"v_out_min": 1.25, "v_out_max": 37.0, "i_max": 0.1},
            ),
            ComponentSpec(
                mpn="LM337L",
                manufacturer="Texas Instruments",
                category="regulator_ldo",
                value="Adjustable",
                package="TO-92",
                symbol="Regulator_Linear:LM337L",
                footprint="Package_TO_SOT_THT:TO-92_Inline",
                description="100mA Adjustable Negative Voltage Regulator",
                stock=25000,
                price=0.30,
                attributes={"v_out_min": -37.0, "v_out_max": -1.25, "i_max": 0.1},
            ),
            # Op-amps (additional)
            ComponentSpec(
                mpn="OPA2134PA",
                manufacturer="Texas Instruments",
                category="opamp",
                value="OPA2134",
                package="DIP-8",
                symbol="Amplifier_Operational:LM358",
                footprint="Package_DIP:DIP-8_W7.62mm",
                description="Dual Low-Noise Audio Op-Amp",
                stock=8000,
                price=3.50,
                attributes={"channels": 2, "noise_nv": 8},
            ),
            # Connectors
            ComponentSpec(
                mpn="RCA-2P",
                manufacturer="CUI Devices",
                category="connector",
                value="RCA Jack",
                package="PTH",
                symbol="Connector:Conn_Coaxial",
                footprint="Connector_Coaxial:RCA_Amphenol_13-70700-1_Horizontal",
                description="RCA Phono Jack, PCB mount",
                stock=20000,
                price=0.65,
                attributes={"contacts": 2},
            ),
            ComponentSpec(
                mpn="PJ-002AH",
                manufacturer="CUI Devices",
                category="connector",
                value="DC Jack",
                package="PTH",
                symbol="Connector:Barrel_Jack",
                footprint="Connector_BarrelJack:BarrelJack_Horizontal",
                description="Barrel Power Jack 5.5/2.1mm",
                stock=15000,
                price=0.45,
                attributes={"contacts": 3},
            ),
            ComponentSpec(
                mpn="9V_CLIP",
                manufacturer="Keystone",
                category="connector",
                value="9V Battery Clip",
                package="PTH",
                symbol="Connector:Conn_01x02_Socket",
                footprint="Connector_Wire:SolderWire-0.5sqmm_1x02_P4.6mm_D1.6mm_OD3mm",
                description="9V Battery Snap Connector",
                stock=12000,
                price=0.35,
                attributes={"contacts": 2},
            ),
            # Switches
            ComponentSpec(
                mpn="GT21MCBE",
                manufacturer="C&K",
                category="switch",
                value="DPDT",
                package="PTH",
                symbol="Switch:SW_DPDT_x2",
                footprint="Button_Switch_THT:SW_DPDT_GT21MCBE",
                description="DPDT Toggle Switch, On-On",
                stock=9000,
                price=1.10,
                attributes={"positions": 2, "poles": 2},
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
        limit: int = 50,
        sort: str = "stock",
    ) -> List[ComponentSpec]:
        """
        Search for components.

        Args:
            query: Query, e.g. ``"10k 0603"``, ``"100nF 50V 0805"``,
                ``"ldo 3.3v"``, ``"esp32"``. Values are matched numerically.
            category: Category filter, e.g. ``"resistor"``, ``"regulator_ldo"``.
            package: Package filter, e.g. ``"0805"``, ``"SOT-23"``.
            min_stock: Minimum stock quantity.
            limit: Maximum results.
            sort: ``"stock"``, ``"price"`` or ``"value"``.
        """
        # Try the downloaded catalogue first if available
        if self.using_jlcparts:
            jlc_results = self._jlcparts_db.search(
                query=query,
                package=package,
                min_stock=min_stock,
                category=category,
                limit=limit,
                sort=sort,
            )
            if jlc_results:
                return [self._jlcpart_to_spec(p) for p in jlc_results]

        # Fallback to built-in catalog
        return self._search_fallback(query, category, package, min_stock, limit)

    def search_explained(
        self,
        query: str = "",
        category: Optional[str] = None,
        package: Optional[str] = None,
        min_stock: int = 0,
        limit: int = 50,
        sort: str = "stock",
    ) -> Dict[str, Any]:
        """
        Search and report how the query was interpreted.

        Returns a dictionary with ``components``, ``notes`` and ``interpretation``
        so a user interface can show why these results came back instead of
        presenting a list the user has to take on trust.
        """
        if not self.using_jlcparts:
            components = self._search_fallback(
                query, category, package, min_stock, limit
            )
            return {
                "components": [c.to_dict() for c in components],
                "notes": ["Using the built-in fallback catalog; "
                          "run 'catalog-setup' for the full catalog"],
                "interpretation": query,
                "source": self.data_source,
            }

        outcome = self._jlcparts_db.search_explained(
            query=query, package=package, min_stock=min_stock,
            category=category, limit=limit, sort=sort,
        )
        return {
            "components": [
                self._jlcpart_to_spec(p).to_dict() for p in outcome.parts
            ],
            "notes": outcome.notes,
            "interpretation": outcome.query.summary(),
            "source": self.data_source,
        }

    def find_substitutes(
        self,
        lcsc_part: str,
        limit: int = 10,
        min_stock: Optional[int] = None,
        same_package: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Find parts that can replace a given one, with the evidence for each.

        Only available with the downloaded catalogue: comparing parts requires
        their parsed specifications, which the small fallback list does not have.
        Returns dictionaries rather than ComponentSpec because the reasons and
        caveats are the point, and they have nowhere to live on a spec.

        See :meth:`JLCPartsDatabase.find_substitutes` for what is compared.
        """
        if not self.using_jlcparts:
            return []
        substitutes = self._jlcparts_db.find_substitutes(
            lcsc_part, limit=limit, min_stock=min_stock, same_package=same_package
        )
        results: List[Dict[str, Any]] = []
        for substitute in substitutes:
            entry = self._jlcpart_to_spec(substitute.part).to_dict()
            entry["reasons"] = substitute.reasons
            entry["caveats"] = substitute.caveats
            entry["verified"] = substitute.is_clean
            results.append(entry)
        return results

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

    def find_builtin(
        self,
        category: str,
        value: Optional[str] = None,
        package: Optional[str] = None,
    ) -> Optional[ComponentSpec]:
        """
        Look up a part in the curated built-in list only.

        The built-in list is small, but its parts carry symbols and pinouts the
        rest of the pipeline has been checked against. Template circuits use it
        deliberately: when a design calls for "a 10 µF 0805 capacitor", taking
        the curated one is safer than taking whichever 10 µF part the downloaded
        catalog happens to rank first.

        Returns ``None`` when nothing matches, so the caller can fall back to a
        catalog search rather than silently using a different value.
        """
        for part in self._fallback_catalog:
            if category and part.category != category:
                continue
            if value and part.value.lower() != value.lower():
                continue
            if package and part.package.lower() != package.lower():
                continue
            return part
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

        # Filter by current rating, using the parsed attribute names the
        # catalogue actually uses ("Output Current"), not invented ones. If a
        # part does not state a current rating it is kept, because dropping it
        # would silently hide usable regulators; the caller is expected to check
        # the datasheet before buying.
        filtered = []
        for part in results:
            rated = part.attributes.get("output_current") or part.attributes.get("current")
            if rated is not None and rated < i_max:
                continue
            if v_in_max is not None:
                supply = (
                    part.attributes.get("supply_voltage")
                    or part.attributes.get("voltage")
                )
                if supply is not None and supply < v_in_max:
                    continue
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
        if self.using_jlcparts:
            # Derived by classifying the downloaded file, so the list reflects
            # what is in it rather than a hard-coded guess, and includes the
            # refined categories (zener, supervisor, voltage_reference) that the
            # catalogue's own broader leaves do not distinguish.
            return sorted(self._jlcparts_db.internal_category_counts())
        return sorted({part.category for part in self._fallback_catalog})

    def internal_category_counts(self) -> Dict[str, int]:
        """Counts by this platform's categories, from the downloaded catalogue."""
        if not self.using_jlcparts:
            counts: Dict[str, int] = {}
            for part in self._fallback_catalog:
                counts[part.category] = counts.get(part.category, 0) + 1
            return counts
        return self._jlcparts_db.internal_category_counts()

    def catalog_category_counts(self, min_stock: int = 0) -> Dict[str, int]:
        """
        Counts by the catalogue's own category names.

        Separate from :meth:`get_categories` because these are the upstream
        names, useful for showing what the downloaded file contains, while
        ``get_categories`` returns the names this platform searches with.
        """
        if not self.using_jlcparts:
            return {}
        return self._jlcparts_db.category_counts(min_stock=min_stock)

    def warm(self) -> int:
        """
        Prepare the component catalog for fast parametric search.

        Parsing the catalog's values takes a few seconds; doing it at start-up
        keeps that off the first search. Returns the number of indexed parts, or
        0 when the full catalog is not installed.
        """
        if not self.using_jlcparts:
            return 0
        return self._jlcparts_db.warm()

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
        """
        Convert a catalogue row to the platform's unified ComponentSpec.

        The parsed catalogue attributes are carried through verbatim, because
        everything downstream that reasons about a part — picking a footprint,
        checking a voltage rating, finding a substitute — needs the numbers, not
        a text blob. ``value`` is the readable engineering form ("10kΩ 100mW
        ±1%") rather than the catalogue's description, which for many rows is
        empty and for others is a whitespace-separated field dump.
        """
        unit_price = 0.0
        if jlc.prices:
            unit_price = min(p["unit_price"] for p in jlc.prices)

        readable_value = jlc.specification_summary()
        if not readable_value:
            # No parsed specification: fall back to the part number, which is
            # what identifies the part in that case.
            readable_value = jlc.mfr_part or jlc.lcsc_part

        return ComponentSpec(
            mpn=jlc.mfr_part or jlc.lcsc_part,
            manufacturer=jlc.manufacturer,
            category=jlc.category,
            value=readable_value,
            package=jlc.package,
            symbol=jlc.symbol,
            footprint=jlc.footprint,
            description=jlc.description,
            stock=jlc.stock,
            price=unit_price,
            attributes=dict(jlc.parameters),
            lcsc_part=jlc.lcsc_part,
            is_basic=jlc.is_basic,
            is_preferred=jlc.is_preferred,
            datasheet_url=jlc.datasheet_url,
            product_url=jlc.product_url,
            min_order=jlc.min_order,
            attrition=dict(jlc.attrition),
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