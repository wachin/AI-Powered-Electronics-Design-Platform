"""
Tests for generated PCB output.

The original `generate_pcb()` emitted footprints with no pads and wrote track
endpoints as designator references (`(start D1.2)`), which KiCad cannot parse —
`kicad-cli pcb drc` reported "Failed to load board", so DRC, Gerber export and
routing were all impossible on a generated design.

These tests require the board to load, to contain real pads from the installed
KiCad footprint libraries, and to have every connected pad assigned to its net.
"""

import re
import subprocess


from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
from src.generators.kicad_footprints import load_footprint, place_pads
from src.generators.kicad_generator import KiCadGenerator
from conftest import requires_kicad

AMS = "Regulator_Linear:AMS1117-3.3"
AMS_FP = "Package_TO_SOT_SMD:SOT-223-3_TabPin2"
R_FP = "Resistor_SMD:R_0805_2012Metric"
C_FP = "Capacitor_SMD:C_0805_2012Metric"
LED_FP = "LED_SMD:LED_0805_2012Metric"


def build_circuit() -> CircuitIR:
    circuit = CircuitIR(name="pcb_test", description="LDO with indicator")

    specs = [
        ("U1", "3.3V", AMS, AMS_FP,
         [("1", "GND", PinType.POWER_IN), ("2", "VO", PinType.POWER_OUT),
          ("3", "VI", PinType.POWER_IN)]),
        ("C1", "10uF", "Device:C", C_FP,
         [("1", "1", PinType.PASSIVE), ("2", "2", PinType.PASSIVE)]),
        ("C2", "22uF", "Device:C", C_FP,
         [("1", "1", PinType.PASSIVE), ("2", "2", PinType.PASSIVE)]),
        ("D1", "Green", "Device:LED", LED_FP,
         [("1", "K", PinType.PASSIVE), ("2", "A", PinType.PASSIVE)]),
        ("R1", "330", "Device:R", R_FP,
         [("1", "1", PinType.PASSIVE), ("2", "2", PinType.PASSIVE)]),
    ]
    for ref, value, symbol, footprint, pins in specs:
        component = Component(
            ref=ref, value=value, component_type=ComponentType.CUSTOM,
            footprint=footprint, symbol=symbol, mpn=value,
        )
        for number, name, pin_type in pins:
            component.add_pin(number, name, pin_type)
        circuit.add_component(component)

    for ref, pin, net in (
        ("U1", "3", "VIN"), ("U1", "2", "VOUT"), ("U1", "1", "GND"),
        ("C1", "1", "VIN"), ("C1", "2", "GND"),
        ("C2", "1", "VOUT"), ("C2", "2", "GND"),
        ("R1", "1", "VOUT"), ("R1", "2", "LED_A"),
        ("D1", "2", "LED_A"), ("D1", "1", "GND"),
    ):
        circuit.connect(ref, pin, net)
    return circuit


class TestFootprintLibrary:
    def test_reads_resistor_pads_with_geometry(self):
        footprint = load_footprint(R_FP)
        assert footprint is not None
        assert [p.number for p in footprint.pads] == ["1", "2"]
        # Pads must have real offsets, not sit on top of each other.
        assert footprint.pads[0].x != footprint.pads[1].x

    def test_sot223_tab_shares_a_pad_number(self):
        """The SOT-223 tab is pad 2, so pad 2 legitimately appears twice."""
        footprint = load_footprint(AMS_FP)
        assert footprint is not None
        numbers = [p.number for p in footprint.pads]
        assert numbers.count("2") == 2
        assert set(numbers) == {"1", "2", "3"}

    def test_missing_footprint_returns_none(self):
        assert load_footprint("NoSuchLibrary:NoSuchPart") is None
        assert load_footprint("") is None

    def test_place_pads_applies_rotation(self):
        footprint = load_footprint(R_FP)
        unrotated = place_pads(footprint, 100.0, 100.0, 0.0)
        rotated = place_pads(footprint, 100.0, 100.0, 90.0)
        assert unrotated[0].x != rotated[0].x
        assert abs(rotated[0].x - 100.0) < 1e-6


class TestPcbGeneration:
    def test_board_contains_real_pads(self):
        text = KiCadGenerator(build_circuit()).generate_pcb()
        # 4 pads on the SOT-223 (its tab is pad 2, so pad 2 appears twice)
        # plus 2 each on four 2-pin parts.
        assert text.count("(pad ") == 12

    def test_pads_carry_their_net(self):
        text = KiCadGenerator(build_circuit()).generate_pcb()
        for net in ("VIN", "VOUT", "GND", "LED_A"):
            assert re.search(rf"\(net \d+ {net}\)", text), f"no pad assigned to {net}"

    def test_net_declarations_are_present(self):
        text = KiCadGenerator(build_circuit()).generate_pcb()
        assert '(net 0 "")' in text
        for net in ("VIN", "VOUT", "GND", "LED_A"):
            assert f'"{net}"' in text

    def test_no_designator_references_in_tracks(self):
        """`(start D1.2)` is not valid geometry and made boards unloadable."""
        text = KiCadGenerator(build_circuit()).generate_pcb()
        assert not re.search(r"\(start [A-Z]+\d+\.", text)
        assert not re.search(r"\(end [A-Z]+\d+\.", text)

    def test_board_outline_is_present(self):
        text = KiCadGenerator(build_circuit()).generate_pcb()
        assert text.count("Edge.Cuts") >= 4

    def test_stub_routing_is_opt_in(self):
        default = KiCadGenerator(build_circuit()).generate_pcb()
        routed = KiCadGenerator(build_circuit(), route_pcb=True).generate_pcb()
        assert "(segment " not in default
        assert "(segment " in routed

    def test_board_is_parenthesis_balanced(self):
        text = KiCadGenerator(build_circuit()).generate_pcb()
        assert text.count("(") == text.count(")")

    def test_missing_footprint_is_reported_not_fatal(self):
        circuit = build_circuit()
        circuit.components["R1"].footprint = "NoSuchLibrary:Nothing"
        text = KiCadGenerator(circuit).generate_pcb()
        # The other four parts are still emitted.
        assert text.count("(footprint ") == 4


@requires_kicad
class TestKiCadAcceptsBoard:
    """The real gate: KiCad must load the board and see connected pads."""

    def test_drc_loads_board_and_finds_no_shorts(self, tmp_path):
        files = KiCadGenerator(build_circuit()).export_project(tmp_path, "pcb_test")
        report = tmp_path / "drc.rpt"
        result = subprocess.run(
            ["kicad-cli", "pcb", "drc", "--output", str(report), str(files["pcb"])],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (result.stderr or result.stdout)
        assert report.exists(), "board did not load (no DRC report produced)"

        content = report.read_text()
        assert "Failed to load" not in content
        # No shorts: an unrouted board has unconnected pads, not shorted nets.
        assert "shorting_items" not in content
        assert "tracks_crossing" not in content
        assert "lib_footprint_issues" in content  # only the known library warning

    def test_gerbers_and_drill_can_be_exported(self, tmp_path):
        files = KiCadGenerator(build_circuit()).export_project(tmp_path, "pcb_test")
        out = tmp_path / "gerbers"
        out.mkdir()

        result = subprocess.run(
            ["kicad-cli", "pcb", "export", "gerbers", "--output", str(out), str(files["pcb"])],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (result.stderr or result.stdout)
        assert (out / "pcb_test-F_Cu.gtl").exists()
        assert (out / "pcb_test-Edge_Cuts.gm1").exists()

        drill = subprocess.run(
            ["kicad-cli", "pcb", "export", "drill", "--output", str(out) + "/", str(files["pcb"])],
            capture_output=True,
            text=True,
        )
        assert drill.returncode == 0, (drill.stderr or drill.stdout)
        assert list(out.glob("*.drl")), "no drill file produced"
