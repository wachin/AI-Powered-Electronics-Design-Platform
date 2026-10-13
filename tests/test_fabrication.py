"""
Tests for the manufacturing output.

The defect these cover: the pipeline produced a ``.kicad_pcb`` — which no board
house accepts — and nothing else. The ROADMAP recorded that Gerber export had
been verified with ``kicad-cli`` by hand, and there was no code that produced
them, no drill files, and no position file without which an assembly service
cannot place anything.

The checks matter as much as the export: ``kicad-cli`` can exit zero having
written nothing, and a part in the BOM that the position file does not place
comes back as a hole on the board.
"""

import shutil
import zipfile
from pathlib import Path

import pytest

from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
from src.generators.fabrication import (
    REQUIRED_GERBER_SUFFIXES,
    export_fabrication,
    read_position_designators,
)
from src.generators.kicad_generator import KiCadGenerator

needs_kicad = pytest.mark.skipif(
    shutil.which("kicad-cli") is None,
    reason="kicad-cli is not installed",
)

DESIGNATORS = ("U1", "C1", "R1")


def board(tmp_path: Path) -> Path:
    """
    A small board with real footprints at real positions.

    A 3.3 V regulator with an input capacitor and a series resistor, wired so the
    pads carry nets. The pads must have nets: a board whose pads are unconnected
    still plots, but it is not the board this platform produces.
    """
    circuit = CircuitIR(name="fab", description="test")

    u1 = Component(
        ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:AMS1117-3.3", package="SOT-223",
    )
    for number, name in (("1", "GND"), ("2", "VO"), ("3", "VI")):
        u1.add_pin(number, name, PinType.POWER_IN)
    circuit.add_component(u1)

    c1 = Component(
        ref="C1", value="10uF", component_type=ComponentType.CAPACITOR,
        footprint="Capacitor_SMD:C_0805_2012Metric", symbol="Device:C",
        package="0805",
    )
    c1.add_pin("1", "1")
    c1.add_pin("2", "2")
    circuit.add_component(c1)

    r1 = Component(
        ref="R1", value="330", component_type=ComponentType.RESISTOR,
        footprint="Resistor_SMD:R_0805_2012Metric", symbol="Device:R",
        package="0805",
    )
    r1.add_pin("1", "1")
    r1.add_pin("2", "2")
    circuit.add_component(r1)

    for ref, pin, net_name in (
        ("U1", "3", "VIN"),
        ("C1", "1", "VIN"),
        ("U1", "2", "VOUT"),
        ("R1", "1", "VOUT"),
        ("U1", "1", "GND"),
        ("C1", "2", "GND"),
        ("R1", "2", "GND"),
    ):
        circuit.components[ref].get_pin(pin).connected_net = net_name
        circuit.get_or_create_net(net_name).connect(ref, pin)

    circuit.get_or_create_net("VIN", is_power=True, voltage=5.0)
    circuit.get_or_create_net("VOUT", is_power=True, voltage=3.3)
    circuit.get_or_create_net("GND", is_power=True, voltage=0.0)

    files = KiCadGenerator(circuit).export_project(tmp_path, "fab")
    return files["pcb"]


@needs_kicad
class TestExport:
    @pytest.fixture()
    def output(self, tmp_path):
        pcb = board(tmp_path)
        return export_fabrication(
            pcb, tmp_path / "out", "fab", expected_designators=DESIGNATORS
        )

    def test_it_produces_gerbers_and_drills(self, output):
        assert output.errors == [], output.errors
        assert output.gerber_files
        assert output.drill_files
        assert output.usable

    def test_the_layers_an_order_needs_are_all_there(self, output):
        names = [p.name for p in output.gerber_files]
        for suffix in REQUIRED_GERBER_SUFFIXES:
            assert any(name.endswith(suffix) for name in names), (suffix, names)

    def test_the_gerbers_are_actually_gerbers(self, output):
        """
        An empty file, or an error message written to the output path, would both
        be counted as "a file was produced".
        """
        for path in output.gerber_files:
            text = path.read_text(errors="replace")[:64]
            assert any(m in text for m in ("%FS", "%MO", "G04", "%TF")), path.name
            assert path.stat().st_size > 0, path.name

    def test_the_drill_files_are_excellon(self, output):
        for path in output.drill_files:
            assert "M48" in path.read_text(errors="replace")[:64], path.name

    def test_it_writes_a_position_file(self, output):
        assert output.position_file is not None
        assert output.position_file.exists()

    def test_the_archive_holds_the_gerbers_and_drills(self, output):
        assert output.archive is not None
        with zipfile.ZipFile(output.archive) as bundle:
            names = set(bundle.namelist())
        for path in output.gerber_files + output.drill_files:
            assert path.name in names, path.name

    def test_it_reports_what_it_produced(self, output):
        payload = output.to_dict()
        assert payload["usable"] is True
        assert payload["gerber_files"]
        assert payload["drill_files"]
        assert payload["position_file"]
        assert "Gerber" in output.summary()


@needs_kicad
class TestThePositionFileMatchesTheBom:
    def test_the_designators_are_read_back(self, tmp_path):
        pcb = board(tmp_path)
        output = export_fabrication(
            pcb, tmp_path / "out", "fab", expected_designators=DESIGNATORS
        )
        listed = set(read_position_designators(output.position_file))
        assert listed == set(DESIGNATORS)

    def test_a_part_the_position_file_does_not_place_is_reported(self, tmp_path):
        """
        A component in the BOM that the position file omits would not be fitted,
        and the board comes back with a hole where it should be.
        """
        pcb = board(tmp_path)
        output = export_fabrication(
            pcb, tmp_path / "out", "fab",
            expected_designators=list(DESIGNATORS) + ["R99"],
        )
        assert any("R99" in warning for warning in output.warnings), output.warnings
        # It is a warning, not an error: the rest of the order is placeable.
        assert output.usable

    def test_a_part_the_board_has_but_the_bom_does_not_is_reported(self, tmp_path):
        pcb = board(tmp_path)
        output = export_fabrication(
            pcb, tmp_path / "out", "fab", expected_designators=["U1"],
        )
        assert any(
            "does not list" in warning for warning in output.warnings
        ), output.warnings

    def test_no_expected_designators_means_no_comparison(self, tmp_path):
        pcb = board(tmp_path)
        output = export_fabrication(pcb, tmp_path / "out", "fab")
        assert output.warnings == []
        assert output.usable


@needs_kicad
class TestFailureModes:
    def test_a_missing_board_is_an_error_not_a_traceback(self, tmp_path):
        output = export_fabrication(tmp_path / "nope.kicad_pcb", tmp_path / "out", "x")
        assert output.usable is False
        assert any("board not found" in e for e in output.errors)

    def test_the_output_directory_is_created(self, tmp_path):
        pcb = board(tmp_path)
        target = tmp_path / "deep" / "nested" / "out"
        output = export_fabrication(pcb, target, "fab")
        assert target.exists()
        assert output.usable


class TestReadPositionDesignators:
    def test_it_reads_kicads_csv(self, tmp_path):
        """KiCad quotes the Ref column, which has to be stripped."""
        path = tmp_path / "cpl.csv"
        path.write_text(
            'Ref,Val,Package,PosX,PosY,Rot,Side\n'
            '"C1","10uF","C_0805_2012Metric",31.0,-30.6,0.0,top\n'
            '"U1","3.3V","SOT-223",31.0,-23.5,0.0,top\n'
        )
        assert read_position_designators(path) == ["C1", "U1"]

    def test_a_missing_file_is_empty_not_an_error(self, tmp_path):
        assert read_position_designators(tmp_path / "nope.csv") == []

    def test_a_file_with_no_ref_column_is_empty(self, tmp_path):
        path = tmp_path / "other.csv"
        path.write_text("A,B\n1,2\n")
        assert read_position_designators(path) == []


class TestThePipelineProducesIt:
    """
    The end-to-end consequence: a finished design comes with files that can be
    ordered, not just a KiCad project.
    """

    def test_a_design_run_writes_gerbers_and_a_position_file(self, tmp_path):
        import asyncio

        from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest
        from src.components.database import ComponentDatabase

        if shutil.which("kicad-cli") is None:
            pytest.skip("kicad-cli is not installed")

        orchestrator = AIDesignOrchestrator(db=ComponentDatabase())
        summary = asyncio.run(orchestrator.process_request(
            DesignRequest(
                prompt="5V to 3.3V LDO with an LED",
                project_name="fabrun",
                run_spice=False,
                run_routing=False,
            ),
            tmp_path,
        ))

        assert summary.fabrication is not None
        assert summary.fabrication.usable, summary.fabrication.errors
        assert summary.fabrication.archive is not None
        assert summary.fabrication.archive.exists()

        # Every part the BOM lists must be placed, or it would not be fitted.
        bom_designators = {
            designator
            for line in summary.bom
            for designator in line["designators"]
        }
        placed = set(read_position_designators(summary.fabrication.position_file))
        assert bom_designators <= placed, bom_designators - placed

        assert "gerber_archive" in summary.generated_files
        assert summary.to_dict()["fabrication"]["usable"] is True


class TestWhichBoardIsPlotted:
    """
    The routed board, and the reason is not aesthetic.

    Measured on the reference design: the routed board's copper Gerber holds 25
    draw operations (the tracks) and the unrouted board's holds none. Plotting the
    wrong one produces a Gerber set that passes every file-level check and yields
    a board with pads and no connections.
    """

    def test_the_routed_board_wins(self, tmp_path):
        from src.agents.orchestrator import board_to_manufacture

        class Result:
            success = True
            routed_pcb_path = tmp_path / "routed.kicad_pcb"

        chosen = board_to_manufacture(Result(), {"pcb": tmp_path / "plain.kicad_pcb"})
        assert chosen == tmp_path / "routed.kicad_pcb"

    @pytest.mark.parametrize(
        "success,routed", [(False, Path("/r")), (True, None), (False, None)]
    )
    def test_the_plain_board_is_the_fallback(self, tmp_path, success, routed):
        from src.agents.orchestrator import board_to_manufacture

        class Result:
            pass

        Result.success = success
        Result.routed_pcb_path = routed
        chosen = board_to_manufacture(Result(), {"pcb": tmp_path / "plain.kicad_pcb"})
        assert chosen == tmp_path / "plain.kicad_pcb"

    def test_no_routing_result_at_all(self, tmp_path):
        from src.agents.orchestrator import board_to_manufacture

        assert board_to_manufacture(None, {"pcb": tmp_path / "p.kicad_pcb"}) == (
            tmp_path / "p.kicad_pcb"
        )

    @needs_kicad
    def test_an_unrouted_board_plots_no_tracks(self, tmp_path):
        """
        The property that makes the choice matter, measured directly.
        """
        from src.generators.fabrication import export_fabrication
        import re

        pcb = board(tmp_path)
        output = export_fabrication(pcb, tmp_path / "out", "fab", archive=False)
        copper = next(
            p for p in output.gerber_files if p.name.endswith(".gtl")
        )
        # D01 is a draw (a track); D03 is a flash (a pad). An unrouted board has
        # pads and no draws.
        draws = len(re.findall(r"D0?1\*", copper.read_text(errors="replace")))
        flashes = len(re.findall(r"D0?3\*", copper.read_text(errors="replace")))
        assert flashes > 0, "expected the pads to be plotted"
        assert draws == 0, "this board has no tracks, so none should be plotted"
