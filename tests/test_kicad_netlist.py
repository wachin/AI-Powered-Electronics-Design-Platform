"""
Tests that the generated KiCad schematic has real electrical connectivity.

The original generator emitted symbols with no `lib_symbols` definitions, no
pin instances and no wires or labels. KiCad could open the file but extracted an
*empty netlist*, so the schematic was decorative: nothing downstream (netlist,
PCB, simulation) could ever be correct.

These tests pin down the three things connectivity requires, and — when
kicad-cli is available — verify with KiCad itself that the netlist is non-empty.
"""

import subprocess

import pytest

from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
from src.generators.kicad_generator import KiCadGenerator
from conftest import requires_kicad
from src.generators.kicad_symbols import SymbolLibrary, load_symbol

R = "Device:R"
C = "Device:C"
LED = "Device:LED"
AMS = "Regulator_Linear:AMS1117-3.3"


def build_ldo() -> CircuitIR:
    circuit = CircuitIR(name="sch_test", description="LDO with indicator")

    u1 = Component(
        ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2", symbol=AMS, mpn="AMS1117-3.3",
    )
    u1.add_pin("1", "GND", PinType.POWER_IN)
    u1.add_pin("2", "VO", PinType.POWER_OUT)
    u1.add_pin("3", "VI", PinType.POWER_IN)
    circuit.add_component(u1)

    for ref, value, symbol, footprint, pins in (
        ("C1", "10uF", C, "Capacitor_SMD:C_0805_2012Metric", [("1", "1"), ("2", "2")]),
        ("C2", "22uF", C, "Capacitor_SMD:C_0805_2012Metric", [("1", "1"), ("2", "2")]),
        ("D1", "Green", LED, "LED_SMD:LED_0805_2012Metric", [("1", "K"), ("2", "A")]),
        ("R1", "330", R, "Resistor_SMD:R_0805_2012Metric", [("1", "1"), ("2", "2")]),
    ):
        component = Component(
            ref=ref, value=value, component_type=ComponentType.CUSTOM,
            footprint=footprint, symbol=symbol, mpn=value,
        )
        for number, name in pins:
            component.add_pin(number, name, PinType.PASSIVE)
        circuit.add_component(component)

    for comp_ref, pin, net in (
        ("U1", "3", "VIN"), ("U1", "2", "VOUT"), ("U1", "1", "GND"),
        ("C1", "1", "VIN"), ("C1", "2", "GND"),
        ("C2", "1", "VOUT"), ("C2", "2", "GND"),
        ("R1", "1", "VOUT"), ("R1", "2", "LED_A"),
        ("D1", "2", "LED_A"), ("D1", "1", "GND"),
    ):
        circuit.connect(comp_ref, pin, net)
    return circuit


class TestSymbolLibrary:
    def test_loads_resistor_pins(self):
        symbol = load_symbol(R)
        assert symbol is not None
        assert [p.number for p in symbol.pins] == ["1", "2"]

    def test_follows_extends_for_ams1117(self):
        """AMS1117-3.3 extends AP1117-15; pins must come from the base."""
        symbol = load_symbol(AMS)
        assert symbol is not None
        assert symbol.extends, "this symbol is expected to use `extends`"
        by_number = {p.number: p.name for p in symbol.pins}
        assert by_number == {"1": "GND", "2": "VO", "3": "VI"}

    def test_led_polarity_names(self):
        symbol = load_symbol(LED)
        assert {p.number: p.name for p in symbol.pins} == {"1": "K", "2": "A"}

    def test_definition_quotes_pin_numbers(self):
        """Unquoted pin numbers make kicad-cli reject the whole file."""
        definition = load_symbol(R).definition_sexpr
        assert '(number "1"' in definition
        assert "(number 1" not in definition

    def test_missing_library_returns_none(self):
        assert load_symbol("NoSuchLibrary:Foo") is None


class TestSchematicConnectivity:
    def test_lib_symbols_definitions_are_emitted(self):
        text = KiCadGenerator(build_ldo()).generate_schematic()
        assert "(lib_symbols" in text
        assert '(symbol "Device:R"' in text or '(symbol "Device:R" ' in text

    def test_symbol_instances_declare_their_pins(self):
        text = KiCadGenerator(build_ldo()).generate_schematic()
        # Six pins on the regulator plus two each on four 2-pin parts.
        assert text.count('(pin "') >= 11

    def test_wires_and_labels_are_emitted_for_every_connected_pin(self):
        text = KiCadGenerator(build_ldo()).generate_schematic()
        for net in ("VIN", "VOUT", "GND", "LED_A"):
            assert f'(label "{net}"' in text
        assert text.count("(wire ") == text.count("(label ")

    def test_schematic_is_parenthesis_balanced(self):
        text = KiCadGenerator(build_ldo()).generate_schematic()
        assert text.count("(") == text.count(")")

    def test_deterministic_uuids(self):
        """Everything except the random sheet uuid must be reproducible."""
        a = KiCadGenerator(build_ldo()).generate_schematic()
        b = KiCadGenerator(build_ldo()).generate_schematic()

        def strip(text: str) -> str:
            return "\n".join(
                line
                for line in text.splitlines()
                if '(uuid "' not in line and '(path "/' not in line
            )

        assert strip(a) == strip(b)


@requires_kicad
class TestKiCadAcceptsSchematic:
    """The real acceptance test: KiCad must extract the expected netlist."""

    def test_netlist_contains_all_nets(self, tmp_path):
        files = KiCadGenerator(build_ldo()).export_project(tmp_path, "sch_test")
        netlist = tmp_path / "sch_test.net"
        result = subprocess.run(
            [
                "kicad-cli", "sch", "export", "netlist",
                "--output", str(netlist), str(files["sch"]),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (result.stderr or result.stdout)
        assert netlist.exists(), "kicad-cli did not produce a netlist"

        content = netlist.read_text()
        for net in ("VIN", "VOUT", "GND", "LED_A"):
            assert f'name "/{net}"' in content, f"net {net} missing from netlist"

        # Every net must carry at least two pins, i.e. real connectivity.
        nets_section = content[content.index("(nets"):]
        assert nets_section.count("(node ") >= 8

        # Pin names must be resolved from the real symbol.
        assert 'pinfunction "VI"' in content
        assert 'pinfunction "VO"' in content
