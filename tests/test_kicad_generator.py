"""
Unit tests for KiCad Generator.
"""

import tempfile
from pathlib import Path
from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
from src.generators.kicad_generator import KiCadGenerator


def test_kicad_generator_export():
    circuit = CircuitIR(name="Test KiCad Gen")

    r1 = Component(
        ref="R1",
        value="10k",
        component_type=ComponentType.RESISTOR,
        footprint="Resistor_SMD:R_0805_2012Metric",
        symbol="Device:R",
    )
    r1.add_pin("1", "1", PinType.PASSIVE)
    r1.add_pin("2", "2", PinType.PASSIVE)
    circuit.add_component(r1)

    circuit.connect("R1", "1", "VCC")
    circuit.connect("R1", "2", "GND")

    generator = KiCadGenerator(circuit)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        files = generator.export_project(out_dir, "my_board")

        assert files["sch"].exists()
        assert files["pcb"].exists()
        assert files["pro"].exists()

        sch_content = files["sch"].read_text()
        pcb_content = files["pcb"].read_text()

        assert "(kicad_sch" in sch_content
        assert "Device:R" in sch_content
        assert "R1" in sch_content

        assert "(kicad_pcb" in pcb_content
        assert "Resistor_SMD:R_0805_2012Metric" in pcb_content
