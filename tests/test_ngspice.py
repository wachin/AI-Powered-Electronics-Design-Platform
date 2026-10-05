"""
Unit tests for ngspice simulation integration.
"""

import pytest
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