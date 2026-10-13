"""
Tests for the KiCad symbol and footprint names the platform hands out.

The defect these cover: KiCad ships **no generic IC symbols**. There is no
``Regulator_Linear:LDO_Generic`` and no ``MCU_Microcontroller:MCU_Generic``, but
the catalogue path invented 26 names of that shape and 5 of the component
templates pointed at names that do not exist either. A design that resolved a
part from the catalogue therefore could not be drawn at all — "symbol library not
found" — while a design that happened to match one of the 36 templates worked.

These tests read the installed KiCad libraries, so they are the only thing that
can tell a real name from a plausible one.
"""

import pytest

from src.components.database import ComponentDatabase
from src.components.jlcparts import JLCPart
from src.core.component_resolver import resolve_pins
from src.core.circuit_ir import ComponentType
from src.generators.kicad_footprints import load_footprint
from src.generators.kicad_symbols import load_symbol

# Every category the catalogue can produce, exercised through the same entry
# point the design pipeline uses.
CATEGORIES = (
    "resistor", "capacitor", "inductor", "diode", "zener", "schottky", "led",
    "transistor", "mosfet", "regulator_ldo", "regulator_buck",
    "regulator_boost", "regulator_switching", "power_management",
    "voltage_reference", "supervisor", "battery_management", "power_switch",
    "microcontroller", "opamp", "comparator", "crystal", "oscillator",
    "connector", "switch", "fuse", "tvs", "varistor", "circuit_protection",
    "sensor", "rf_module", "memory", "logic", "driver", "isolation",
    "interface", "data_acquisition", "display", "filter", "relay", "audio",
    "hardware", "module", "power_module", "analog",
)


# The component type a role in this category resolves to, which is what decides
# whether the passive pin template or the IC pinout table is consulted.
CATEGORY_TO_TYPE = {
    "resistor": ComponentType.RESISTOR,
    "capacitor": ComponentType.CAPACITOR,
    "inductor": ComponentType.INDUCTOR,
    "diode": ComponentType.DIODE,
    "zener": ComponentType.DIODE,
    "schottky": ComponentType.DIODE,
    "led": ComponentType.LED,
    "transistor": ComponentType.TRANSISTOR,
    "mosfet": ComponentType.MOSFET,
    "crystal": ComponentType.CRYSTAL,
    "connector": ComponentType.CONNECTOR,
    "switch": ComponentType.SWITCH,
    "microcontroller": ComponentType.MICROCONTROLLER,
    "opamp": ComponentType.OPAMP,
    "voltage_reference": ComponentType.CHIP,
}


def part_in(category: str) -> JLCPart:
    return JLCPart(
        lcsc_part="C1", mfr_part="", manufacturer="", description="",
        category=category, package="0603", package_type="SMD", stock=1,
        min_order=1,
    )


class TestCategorySymbols:
    """
    Every symbol the catalogue path hands out must exist in the installed KiCad
    libraries.
    """

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_the_symbol_exists(self, category):
        symbol = part_in(category).symbol
        assert symbol, f"no symbol for {category}"
        assert load_symbol(symbol) is not None, (
            f"{category} maps to {symbol}, which is not a KiCad symbol"
        )

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_no_category_gets_a_made_up_generic_name(self, category):
        """
        The shape of the old bug: a *symbol* name that reads like a generic.

        Only the part after the library counts. ``Connector_Generic`` is a real
        KiCad library, so ``Connector_Generic:Conn_01x02`` is a real symbol; the
        fabricated ones were ``Regulator_Linear:LDO_Generic`` and friends, where
        the invented part is the symbol name.
        """
        symbol_name = part_in(category).symbol.split(":")[-1]
        assert "_Generic" not in symbol_name, symbol_name
        assert not symbol_name.endswith("Generic"), symbol_name

    def test_an_unknown_category_gets_no_symbol(self):
        """
        "Device:R" used to be the fallback, which drew a resistor for a part the
        platform did not understand. Nothing is the honest answer.
        """
        assert part_in("something_unheard_of").symbol == ""

    def test_a_longer_category_name_wins_over_a_shorter_one(self):
        """
        "power_module" contains "module"; a power module must not come out as an
        RF module.
        """
        assert part_in("power_module").symbol == "Converter_DCDC:IH0505S"
        assert part_in("rf_module").symbol == "RF_Module:ESP32-WROOM-32"


class TestDeclaredPinsMatchTheSymbol:
    """
    A symbol and a pin list that disagree produce a schematic whose pins do not
    exist on the part — a netlist error that looks like a working design.
    """

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_declared_pins_exist_on_the_symbol(self, category):
        symbol = part_in(category).symbol
        if not symbol:
            pytest.skip(f"no symbol for {category}")
        definition = load_symbol(symbol)
        assert definition is not None

        # The pipeline resolves pins for the component type; a passive gets its
        # two-terminal template, an IC gets the pinout for its symbol family.
        pins = resolve_pins(ComponentType.CUSTOM, symbol=symbol)
        real = {pin.number for pin in definition.pins}
        declared = {number for number, _, _ in pins}
        assert declared <= real, (
            f"{category}: {symbol} declares pins {sorted(declared - real)} "
            f"but has {sorted(real)}"
        )

    @pytest.mark.parametrize(
        "category,expected",
        [
            ("regulator_ldo", 3),
            ("regulator_buck", 5),
            ("regulator_boost", 6),
            ("supervisor", 3),
            ("opamp", 8),
            ("comparator", 8),
            ("isolation", 4),
            ("memory", 8),
        ],
    )
    def test_the_archetypes_have_the_pins_a_design_needs(self, category, expected):
        """
        These are the categories a generated design actually connects to by role
        name, so they must resolve a pinout rather than nothing.
        """
        symbol = part_in(category).symbol
        pins = resolve_pins(ComponentType.CUSTOM, symbol=symbol)
        assert len(pins) == expected, (category, symbol, pins)


class TestTemplateSymbols:
    def test_every_template_symbol_exists(self):
        bad = []
        for template in ComponentDatabase(prefer_jlcparts=False)._component_templates:
            if load_symbol(template.symbol) is None:
                bad.append((template.value, template.symbol))
        assert bad == [], f"templates pointing at symbols KiCad does not have: {bad}"

    def test_every_template_footprint_exists(self):
        bad = []
        checked = 0
        for template in ComponentDatabase(prefer_jlcparts=False)._component_templates:
            definition = load_footprint(template.footprint)
            if definition is None:
                bad.append((template.value, template.footprint))
                continue
            checked += 1
            assert definition.pads, (template.value, template.footprint)
        if checked == 0:
            pytest.skip("KiCad footprint libraries are not installed")
        assert bad == [], f"templates pointing at footprints KiCad does not have: {bad}"

    # The only templates with no pinout, and the reason: a microcontroller has
    # tens of pins and the platform does not know their assignment. It says "no
    # known pinout" rather than inventing one, so the gap is documented here
    # rather than allowed to grow quietly.
    KNOWN_WITHOUT_PINOUT = {
        ("microcontroller", "ESP32"),
        ("microcontroller", "STM32F103"),
        ("microcontroller", "RP2040"),
    }

    def test_only_the_known_templates_lack_a_pinout(self):
        """
        The templates are what a design without a catalogue uses, so their
        pinouts have to resolve — except where the platform honestly does not
        know them.
        """
        without = set()
        for template in ComponentDatabase(prefer_jlcparts=False)._component_templates:
            component_type = CATEGORY_TO_TYPE.get(template.category, ComponentType.CUSTOM)
            pins = resolve_pins(
                component_type, symbol=template.symbol, value=template.value
            )
            if not pins:
                without.add((template.category, template.value))
        assert without == self.KNOWN_WITHOUT_PINOUT, (
            f"templates without a pinout changed: {sorted(without)}"
        )


class TestTheDesignPipelineDrawsCatalogueParts:
    """
    The end-to-end consequence: a part resolved from the catalogue has to produce
    a schematic KiCad can read, with a symbol that exists.
    """

    def test_a_catalogue_part_gets_a_real_symbol_and_footprint(self):
        from src.components.database import ComponentDatabase as Db

        db = Db()
        if not db.using_jlcparts:
            pytest.skip("no catalogue installed")
        for category in ("regulator_ldo", "capacitor", "resistor", "diode"):
            part = db.search(category=category, min_stock=1000, limit=1)[0]
            assert part.symbol, f"{category}: no symbol"
            assert load_symbol(part.symbol) is not None, (
                f"{category}: {part.symbol} is not a KiCad symbol"
            )
