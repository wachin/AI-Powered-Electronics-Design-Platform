"""
Component Database and Parts Registry for AI-Powered Electronics Design Platform.

Provides component search, parametric matching, symbol/footprint resolution,
substitute finding, and distributor inventory data.

Priority:
1. The downloaded JLCPCB/LCSC catalog (~180,000 in-stock parts)
2. Component templates - symbol, footprint and package for common values,
   used when the catalogue is not installed. Not parts: no part numbers.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from src.components.jlcparts import JLCPartsDatabase, JLCPart, download_catalog


@dataclass
class ComponentSpec:
    """
    Unified component specification for the design platform.

    ``manufacturer``, ``stock`` and ``price`` default to empty because a
    component *template* has none of them: those are parts data, and the
    catalogue is the only source of them. A caller that needs to be sure it is
    looking at a real part should check ``lcsc_part``, which only a catalogue
    part has.
    """
    mpn: str
    category: str
    value: str
    package: str
    symbol: str
    footprint: str
    description: str
    manufacturer: str = ""
    stock: int = 0
    price: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)
    lcsc_part: Optional[str] = None
    is_basic: bool = False
    is_preferred: bool = False
    datasheet_url: str = ""
    product_url: str = ""
    # Quantity price breaks, ascending: [{"quantity": n, "unit_price": p}].
    # Needed to price an order correctly: the unit price at 10 pieces is not the
    # unit price at 10,000.
    prices: List[Dict[str, Any]] = field(default_factory=list)
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
            "prices": self.prices,
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
    Unified component database: the downloaded JLCPCB/LCSC catalogue, plus a set
    of component templates for when it is not installed.

    One source of *parts* data — the catalogue — and one source of *template*
    data: the symbol, footprint and package to use for common component values.
    Keeping a second copy of part numbers, prices and stock here is how this
    project once came to ship 28 invented part numbers.
    """

    def __init__(self, db_path: Optional[Path] = None, prefer_jlcparts: bool = True):
        self.prefer_jlcparts = prefer_jlcparts
        self._jlcparts_db: Optional[JLCPartsDatabase] = None
        self._component_templates: List[ComponentSpec] = []

        if prefer_jlcparts:
            self._jlcparts_db = JLCPartsDatabase(db_path)

        self._load_component_templates()

    def _load_component_templates(self):
        """
        Loads the component templates used when no catalogue is installed.

        These are **templates, not parts**. Each carries a category, a value, a
        package and the KiCad symbol and footprint to use — the knowledge the
        pipeline has been verified against, and the one thing the catalogue does
        not supply: a real catalogue part comes back with a generic symbol
        (``Regulator_Linear:LDO_Generic``) and a footprint derived from its
        package name.

        They deliberately carry **no part number, manufacturer, price or stock**.
        Those are parts data, they are the catalogue's job, and keeping a second
        copy here is how this project ended up with 28 invented part numbers —
        numbers that looked exactly like orderable parts
        (``CC0805KRX7R9BB106``, ``RC0805FR-07330RL``) and were not. The prices
        were as invented as the numbers: an AMS1117 was quoted here at $0.15
        against a catalogue price of $0.0187.

        A design built from these templates therefore names no part number. It has
        a correct symbol, footprint and value, and
        :mod:`src.components.ordering` resolves each one to a real, in-stock
        catalogue part, records the LCSC number, and states on the line when the
        part number it found is not the one the design implied.

        Do not add a part number, a price or a stock figure here. If a value is
        missing, add a template with a value and a package, and let the catalogue
        say what it costs.
        """
        self._component_templates = [
            ComponentSpec(
                mpn="",
                category='regulator_ldo',
                value='3.3V',
                package='SOT-223',
                symbol='Regulator_Linear:AMS1117-3.3',
                footprint='Package_TO_SOT_SMD:SOT-223-3_TabPin2',
                description='1A Low Dropout Voltage Regulator 3.3V',
            ),
            ComponentSpec(
                mpn="",
                category='regulator_ldo',
                value='5V',
                package='TO-220',
                symbol='Regulator_Linear:LM7805',
                footprint='Package_TO_SOT_THT:TO-220-3_Vertical',
                description='1.5A Positive Voltage Regulator 5V',
            ),
            ComponentSpec(
                mpn="",
                category='regulator_buck',
                value='5V',
                package='TO-220-5',
                symbol='Regulator_Switching:LM2596',
                footprint='Package_TO_SOT_THT:TO-220-5_Vertical',
                description='3A Step-Down Switching Regulator 5V',
            ),
            ComponentSpec(
                mpn="",
                category='regulator_boost',
                value='Adjustable',
                package='SOT-23-6',
                symbol='Regulator_Switching:MT3608',
                footprint='Package_TO_SOT_SMD:SOT-23-6',
                description='2A Boost Converter, up to 28V output',
            ),
            ComponentSpec(
                mpn="",
                category='resistor',
                value='10k',
                package='0805',
                symbol='Device:R',
                footprint='Resistor_SMD:R_0805_2012Metric',
                description='Resistor 10k Ohm 1% 1/8W 0805',
            ),
            ComponentSpec(
                mpn="",
                category='resistor',
                value='330',
                package='0805',
                symbol='Device:R',
                footprint='Resistor_SMD:R_0805_2012Metric',
                description='Resistor 330 Ohm 1% 1/8W 0805',
            ),
            ComponentSpec(
                mpn="",
                category='resistor',
                value='10k',
                package='0603',
                symbol='Device:R',
                footprint='Resistor_SMD:R_0603_1608Metric',
                description='Resistor 10k Ohm 1% 1/10W 0603',
            ),
            ComponentSpec(
                mpn="",
                category='resistor',
                value='240',
                package='0603',
                symbol='Device:R',
                footprint='Resistor_SMD:R_0603_1608Metric',
                description='Resistor 240 Ohm 1% 1/10W 0603',
            ),
            ComponentSpec(
                mpn="",
                category='resistor',
                value='1k',
                package='0603',
                symbol='Device:R',
                footprint='Resistor_SMD:R_0603_1608Metric',
                description='Resistor 1k Ohm 1% 1/10W 0603',
            ),
            ComponentSpec(
                mpn="",
                category='resistor',
                value='10k',
                package='0402',
                symbol='Device:R',
                footprint='Resistor_SMD:R_0402_1005Metric',
                description='Resistor 10k Ohm 1% 1/16W 0402',
            ),
            ComponentSpec(
                mpn="",
                category='capacitor',
                value='10uF',
                package='0805',
                symbol='Device:C',
                footprint='Capacitor_SMD:C_0805_2012Metric',
                description='Capacitor MLCC 10uF 25V X7R 0805',
            ),
            ComponentSpec(
                mpn="",
                category='capacitor',
                value='22uF',
                package='0805',
                symbol='Device:C',
                footprint='Capacitor_SMD:C_0805_2012Metric',
                description='Capacitor MLCC 22uF 16V X5R 0805',
            ),
            ComponentSpec(
                mpn="",
                category='capacitor',
                value='100nF',
                package='0603',
                symbol='Device:C',
                footprint='Capacitor_SMD:C_0603_1608Metric',
                description='Capacitor MLCC 100nF 50V X7R 0603',
            ),
            ComponentSpec(
                mpn="",
                category='capacitor',
                value='100nF',
                package='0402',
                symbol='Device:C',
                footprint='Capacitor_SMD:C_0402_1005Metric',
                description='Capacitor MLCC 100nF 25V X7R 0402',
            ),
            ComponentSpec(
                mpn="",
                category='led',
                value='Green',
                package='0805',
                symbol='Device:LED',
                footprint='LED_SMD:LED_0805_2012Metric',
                description='LED Green Clear 0805 SMD',
            ),
            ComponentSpec(
                mpn="",
                category='led',
                value='Red',
                package='0805',
                symbol='Device:LED',
                footprint='LED_SMD:LED_0805_2012Metric',
                description='LED Red Clear 0805 SMD',
            ),
            ComponentSpec(
                mpn="",
                category='led',
                value='Blue',
                package='0805',
                symbol='Device:LED',
                footprint='LED_SMD:LED_0805_2012Metric',
                description='LED Blue Clear 0805 SMD',
            ),
            ComponentSpec(
                mpn="",
                category='microcontroller',
                value='ESP32',
                package='Module',
                symbol='RF_Module:ESP32-WROOM-32',
                footprint='RF_Module:ESP32-WROOM-32',
                description='Wi-Fi & Bluetooth MCU Module',
            ),
            ComponentSpec(
                mpn="",
                category='microcontroller',
                value='STM32F103',
                package='LQFP-48',
                symbol='MCU_ST_STM32F1:STM32F103C8T6',
                footprint='Package_QFP:LQFP-48_7x7mm_P0.5mm',
                description='ARM Cortex-M3 MCU 72MHz 64KB Flash',
            ),
            ComponentSpec(
                mpn="",
                category='microcontroller',
                value='RP2040',
                package='QFN-56',
                symbol='MCU_RaspberryPi:RP2040',
                footprint='Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm',
                description='Dual ARM Cortex-M0+ MCU',
            ),
            ComponentSpec(
                mpn="",
                category='inductor',
                value='47uH',
                package='1210',
                symbol='Device:L',
                footprint='Inductor_SMD:L_1210_3225Metric',
                description='47uH 1.6A Shielded Power Inductor',
            ),
            ComponentSpec(
                mpn="",
                category='inductor',
                value='10uH',
                package='0805',
                symbol='Device:L',
                footprint='Inductor_SMD:L_0805_2012Metric',
                description='10uH 1.1A Shielded Power Inductor',
            ),
            ComponentSpec(
                mpn="",
                category='diode',
                value='1N4148',
                package='SOD-123',
                symbol='Device:D',
                footprint='Diode_SMD:D_SOD-123',
                description='Fast Switching Diode 100V 300mA',
            ),
            ComponentSpec(
                mpn="",
                category='diode',
                value='SS14',
                package='SMA',
                symbol='Device:D',
                footprint='Diode_SMD:D_SMA',
                description='Schottky Rectifier 40V 1A',
            ),
            ComponentSpec(
                mpn="",
                category='mosfet',
                value='2N7002',
                package='SOT-23',
                symbol='Transistor_FET:Q_NMOS_GSD',
                footprint='Package_TO_SOT_SMD:SOT-23-3',
                description='N-Channel MOSFET 60V 115mA',
            ),
            ComponentSpec(
                mpn="",
                category='mosfet',
                value='SI2302',
                package='SOT-23',
                symbol='Transistor_FET:Q_NMOS_GSD',
                footprint='Package_TO_SOT_SMD:SOT-23-3',
                description='N-Channel MOSFET 20V 2.3A',
            ),
            ComponentSpec(
                mpn="",
                category='opamp',
                value='LM358',
                package='SOIC-8',
                symbol='Amplifier_Operational:LM358',
                footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
                description='Dual Operational Amplifier',
            ),
            ComponentSpec(
                mpn="",
                category='opamp',
                value='TL072',
                package='SOIC-8',
                symbol='Amplifier_Operational:TL072',
                footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
                description='Dual JFET-Input OpAmp Low Noise',
            ),
            ComponentSpec(
                mpn="",
                category='voltage_reference',
                value='TL431',
                package='SOT-23',
                symbol='Reference_Voltage:TL431DBZ',
                footprint='Package_TO_SOT_SMD:SOT-23-3',
                description='Programmable Precision Reference 2.5V',
            ),
            ComponentSpec(
                mpn="",
                category='crystal',
                value='8MHz',
                package='HC-49S',
                symbol='Device:Crystal',
                footprint='Crystal:Crystal_SMD_HC49-SD',
                description='8MHz Crystal 20pF',
            ),
            ComponentSpec(
                mpn="",
                category='crystal',
                value='16MHz',
                package='HC-49S',
                symbol='Device:Crystal',
                footprint='Crystal:Crystal_SMD_HC49-SD',
                description='16MHz Crystal 20pF',
            ),
            ComponentSpec(
                mpn="",
                category='regulator_ldo',
                value='Adjustable',
                package='TO-92',
                symbol='Regulator_Linear:LM317L',
                footprint='Package_TO_SOT_THT:TO-92_Inline',
                description='100mA Adjustable Positive Voltage Regulator',
            ),
            ComponentSpec(
                mpn="",
                category='regulator_ldo',
                value='Adjustable',
                package='TO-92',
                symbol='Regulator_Linear:LM337L',
                footprint='Package_TO_SOT_THT:TO-92_Inline',
                description='100mA Adjustable Negative Voltage Regulator',
            ),
            ComponentSpec(
                mpn="",
                category='opamp',
                value='OPA2134',
                package='DIP-8',
                symbol='Amplifier_Operational:LM358',
                footprint='Package_DIP:DIP-8_W7.62mm',
                description='Dual Low-Noise Audio Op-Amp',
            ),
            ComponentSpec(
                mpn="",
                category='connector',
                value='DC Jack',
                package='PTH',
                symbol='Connector:Barrel_Jack',
                footprint='Connector_BarrelJack:BarrelJack_Horizontal',
                description='Barrel Power Jack 5.5/2.1mm',
            ),
            ComponentSpec(
                mpn="",
                category='switch',
                value='DPDT',
                package='PTH',
                symbol='Switch:SW_DPDT_x2',
                footprint='Button_Switch_SMD:SW_DPDT_CK_JS202011JCQN',
                description='DPDT Toggle Switch, On-On',
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
        return len(self._component_templates)

    @property
    def data_source(self) -> str:
        """
        Description of the active data source.

        Without the catalogue this says "templates", not "catalog": there are no
        part numbers, prices or stock figures to offer, and describing them as a
        catalog would be the same overstatement in a different place.
        """
        if self.using_jlcparts:
            return f"JLCPCB/LCSC offline catalog ({self.catalog_size:,} parts)"
        return (
            f"{len(self._component_templates)} component templates — no part "
            f"numbers, prices or stock; run 'catalog-setup'"
        )

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

        # Fall back to the templates
        return self._search_templates(query, category, package, min_stock, limit)

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
            components = self._search_templates(
                query, category, package, min_stock, limit
            )
            return {
                "components": [c.to_dict() for c in components],
                "notes": [
                    "These are component templates: symbol, footprint and value, "
                    "with no part number, price or stock. Run 'catalog-setup' to "
                    "search real, orderable parts."
                ],
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
        """
        Find an exact component by Manufacturer Part Number or LCSC number.

        The catalogue is consulted first and matches on the part number itself,
        not on a text search that happens to rank the right part first. The
        templates are the fallback, and they carry no part number at all, so a
        caller that needs an orderable part must check
        ``ComponentSpec.lcsc_part`` before treating the result as one.
        """
        if self.using_jlcparts:
            if mpn.upper().startswith("C") and mpn[1:].isdigit():
                jlc_part = self._jlcparts_db.lookup(mpn)
                if jlc_part:
                    return self._jlcpart_to_spec(jlc_part)

            exact = self._jlcparts_db.lookup_mpn(mpn)
            if exact:
                return self._jlcpart_to_spec(exact[0])

        for part in self._component_templates:
            if part.mpn.lower() == mpn.lower():
                return part
        return None

    def find_in_catalog(self, mpn: str) -> List[ComponentSpec]:
        """
        Every catalogue entry with this exact MPN, best stock first.

        Consults the catalogue only, so a caller that must not accept a template
        can ask this question. Templates carry no part numbers in any case.
        """
        if not self.using_jlcparts:
            return []
        return [self._jlcpart_to_spec(p) for p in self._jlcparts_db.lookup_mpn(mpn)]

    def get_by_lcsc(self, lcsc_part: str) -> Optional[ComponentSpec]:
        """Find component by LCSC part number (e.g., 'C123456')."""
        if self.using_jlcparts:
            jlc_part = self._jlcparts_db.lookup(lcsc_part)
            if jlc_part:
                return self._jlcpart_to_spec(jlc_part)
        return None

    def find_template(
        self,
        category: str,
        value: Optional[str] = None,
        package: Optional[str] = None,
    ) -> Optional[ComponentSpec]:
        """
        Look up a component template by category, value and package.

        Templates carry the symbol and footprint the pipeline has been checked
        against, so a design that asks for "a 10 µF 0805 capacitor" gets a correct
        land pattern whether or not a catalogue is installed.

        Returns ``None`` when nothing matches, so the caller can fall back to a
        catalogue search rather than silently using a different value.
        """
        for part in self._component_templates:
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
        return sorted({part.category for part in self._component_templates})

    def internal_category_counts(self) -> Dict[str, int]:
        """Counts by this platform's categories, from the downloaded catalogue."""
        if not self.using_jlcparts:
            counts: Dict[str, int] = {}
            for part in self._component_templates:
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
            prices=[dict(tier) for tier in jlc.prices],
        )

    def _search_templates(
        self,
        query: str,
        category: Optional[str],
        package: Optional[str],
        min_stock: int,
        limit: int
    ) -> List[ComponentSpec]:
        """
        Search the component templates.

        There is no part number, manufacturer or stock to match on or filter by,
        because templates do not have any. ``min_stock`` is accepted and ignored
        for the same reason: filtering on a stock figure that does not exist
        would silently return nothing.
        """
        results = []
        q = query.lower().strip()

        for part in self._component_templates:
            if category and part.category != category:
                continue
            if package and part.package.lower() != package.lower():
                continue

            if not q or (
                q in part.value.lower()
                or q in part.description.lower()
                or q in part.category.lower()
                or q in part.package.lower()
            ):
                results.append(part)

        return results[:limit]


# Convenience function
def get_database(db_path: Optional[Path] = None) -> ComponentDatabase:
    """Get a component database instance (singleton-like)."""
    return ComponentDatabase(db_path)