"""
Unit tests for Circuit IR models.
"""

from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType


def test_circuit_ir_creation():
    ir = CircuitIR(name="Test Regulator")
    assert ir.name == "Test Regulator"

    # Add regulator
    reg = Component(
        ref="U1",
        value="AMS1117-3.3",
        component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:AMS1117-3.3"
    )
    reg.add_pin("1", "GND", PinType.POWER_IN)
    reg.add_pin("2", "VO", PinType.POWER_OUT)
    reg.add_pin("3", "VI", PinType.POWER_IN)

    ir.add_component(reg)

    # Connections
    ir.connect("U1", "VI", "5V")
    ir.connect("U1", "VO", "3.3V")
    ir.connect("U1", "GND", "GND")

    data = ir.to_dict()
    assert "U1" in data["components"]
    assert "5V" in data["nets"]
    assert "3.3V" in data["nets"]
    assert "GND" in data["nets"]

    cj_elements = ir.to_circuit_json_compatible()
    assert len(cj_elements) >= 4  # Metadata + 1 component + 3 nets


if __name__ == "__main__":
    test_circuit_ir_creation()
    print("✅ Circuit IR models test PASSED")
