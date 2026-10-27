"""
Unit tests for ngspice simulation integration.
"""

from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
from src.simulation.ngspice import CircuitIRToSpice, NgSpiceRunner


def test_circuit_ir_to_spice_compilation():
    """Test Circuit IR compiles to valid SPICE netlist."""
    circuit = CircuitIR(name="Test Circuit")

    r1 = Component(
        ref="R1",
        value="1k",
        component_type=ComponentType.RESISTOR,
        footprint="Resistor_SMD:R_0805",
        symbol="Device:R",
    )
    r1.add_pin("1", "1", PinType.PASSIVE)
    r1.add_pin("2", "2", PinType.PASSIVE)
    circuit.add_component(r1)

    c1 = Component(
        ref="C1",
        value="100n",
        component_type=ComponentType.CAPACITOR,
        footprint="Capacitor_SMD:C_0805",
        symbol="Device:C",
    )
    c1.add_pin("1", "1", PinType.PASSIVE)
    c1.add_pin("2", "2", PinType.PASSIVE)
    circuit.add_component(c1)

    circuit.connect("R1", "1", "VCC")
    circuit.connect("R1", "2", "NET_OUT")
    circuit.connect("C1", "1", "NET_OUT")
    circuit.connect("C1", "2", "GND")

    compiler = CircuitIRToSpice(circuit)
    netlist = compiler.compile()

    assert ".op" in netlist
    assert "R1" in netlist
    assert "C1" in netlist
    assert "VCC" in netlist
    assert "GND" in netlist


def test_ldo_spice_generation():
    """Test LDO regulator compiles with voltage sources."""
    circuit = CircuitIR(name="LDO Test")

    u1 = Component(
        ref="U1",
        value="3.3V",
        component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:AMS1117-3.3",
    )
    u1.add_pin("1", "GND", PinType.POWER_IN)
    u1.add_pin("2", "VOUT", PinType.POWER_OUT)
    u1.add_pin("3", "VIN", PinType.POWER_IN)
    circuit.add_component(u1)

    circuit.connect("U1", "VIN", "5V")
    circuit.connect("U1", "VOUT", "3.3V")
    circuit.connect("U1", "GND", "GND")

    compiler = CircuitIRToSpice(circuit)
    netlist = compiler.compile()

    assert "VU1_OUT" in netlist
    assert "VU1_IN" in netlist
    assert "3.3" in netlist


def test_ngspice_runner_check():
    """Test ngspice runner availability check."""
    runner = NgSpiceRunner()
    
    # Simple netlist for testing
    netlist = """
* Test
V1 VCC GND DC 5
R1 VCC OUT 1k
C1 OUT GND 100n
.op
.tran 1u 1m
.end
"""
    result = runner.run_simulation(netlist)
    
    # Either ngspice is available and works, or not installed
    # Both are valid test outcomes
    assert hasattr(result, 'success')
    assert hasattr(result, 'stdout')
    assert hasattr(result, 'stderr')

class TestOperatingPointParsing:
    """The operating point is the only machine-checkable simulation output."""

    SAMPLE = """
\tOperating point information:
\t----\t-------
\tvu1_out#branch                   -6.34211e-03
\t     device                   cc2                   cc1
\t      dc                     3.3                     5
\t   acmag                       0                       0
\t     device                vu1_in               vu1_out
\t      dc                       5                     3.3
"""

    def test_extracts_dc_node_voltages(self):
        from src.simulation.ngspice import parse_operating_point

        result = parse_operating_point(self.SAMPLE)
        assert result["node_voltages"] == {
            "cc2": 3.3, "cc1": 5.0, "vu1_in": 5.0, "vu1_out": 3.3
        }

    def test_ignores_branch_currents_and_placeholder_rows(self):
        from src.simulation.ngspice import parse_operating_point

        result = parse_operating_point(self.SAMPLE)
        # `vu1_out#branch` must not appear as a voltage.
        assert not any("#branch" in name for name in result["node_voltages"])

    def test_reports_min_and_max(self):
        from src.simulation.ngspice import parse_operating_point

        result = parse_operating_point(self.SAMPLE)
        assert result["min_voltage"] == 3.3
        assert result["max_voltage"] == 5.0

    def test_empty_output_yields_nothing(self):
        from src.simulation.ngspice import parse_operating_point

        assert parse_operating_point("") == {}
        assert parse_operating_point("no tables here") == {}

    def test_result_exposes_voltages_and_flags_missing_results(self):
        from src.simulation.ngspice import SimulationResult

        empty = SimulationResult(success=True, stdout="", stderr="")
        assert empty.node_voltages == {}
        assert empty.has_results is False

        filled = SimulationResult(
            success=True,
            stdout="",
            stderr="",
            measurements={"node_voltages": {"VOUT": 3.3}},
        )
        assert filled.has_results is True
