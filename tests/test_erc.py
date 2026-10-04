"""
Unit tests for Electrical Rule Checker (ERC).
"""

from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
from src.core.erc import ERCValidator, Severity


def test_erc_clean_circuit():
    circuit = CircuitIR(name="Clean Circuit")

    # Resistor + LED
    r1 = Component(
        ref="R1",
        value="330",
        component_type=ComponentType.RESISTOR,
        footprint="Resistor_SMD:R_0805_2012Metric",
        symbol="Device:R",
    )
    r1.add_pin("1", "1", PinType.PASSIVE)
    r1.add_pin("2", "2", PinType.PASSIVE)

    d1 = Component(
        ref="D1",
        value="Green",
        component_type=ComponentType.LED,
        footprint="LED_SMD:LED_0805_2012Metric",
        symbol="Device:LED",
    )
    d1.add_pin("1", "K", PinType.PASSIVE)
    d1.add_pin("2", "A", PinType.PASSIVE)

    circuit.add_component(r1)
    circuit.add_component(d1)

    circuit.connect("R1", "1", "VCC")
    circuit.connect("R1", "2", "NET_A")
    circuit.connect("D1", "2", "NET_A")
    circuit.connect("D1", "1", "GND")

    validator = ERCValidator(circuit)
    report = validator.validate()

    assert report.passed is True
    assert report.summary["errors"] == 0


def test_erc_unconnected_critical_pin():
    circuit = CircuitIR(name="Unconnected Pin Circuit")

    u1 = Component(
        ref="U1",
        value="MCU",
        component_type=ComponentType.MICROCONTROLLER,
        footprint="QFP",
        symbol="MCU",
    )
    u1.add_pin("1", "VDD", PinType.POWER_IN)  # Unconnected!
    circuit.add_component(u1)

    validator = ERCValidator(circuit)
    report = validator.validate()

    assert report.passed is False
    assert report.summary["errors"] >= 1
    assert any(i.rule_id == "ERC001_UNCONNECTED_CRITICAL_PIN" for i in report.issues)


def test_erc_led_missing_resistor():
    circuit = CircuitIR(name="Unprotected LED")

    d1 = Component(
        ref="D1",
        value="Red",
        component_type=ComponentType.LED,
        footprint="LED_SMD:LED_0805",
        symbol="Device:LED",
    )
    d1.add_pin("1", "K", PinType.PASSIVE)
    d1.add_pin("2", "A", PinType.PASSIVE)
    circuit.add_component(d1)

    circuit.connect("D1", "2", "5V")
    circuit.connect("D1", "1", "GND")

    validator = ERCValidator(circuit)
    report = validator.validate()

    assert report.passed is False
    assert any(i.rule_id == "ERC005_LED_WITHOUT_RESISTOR" for i in report.issues)
