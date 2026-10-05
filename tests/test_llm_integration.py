"""
Tests for LLM Integration module.
"""

import pytest
from src.llm.integration import (
    MockLLMClient,
    LLMProvider,
    CircuitRequirement,
    CircuitSpecification,
    ComponentSelection,
    parse_requirements,
    generate_specification,
    nl_to_circuit_spec,
    REQUIREMENT_SCHEMA,
    SPECIFICATION_SCHEMA,
)


def test_mock_llm_client_available():
    """Test mock client is always available."""
    client = MockLLMClient()
    assert client.is_available() is True


def test_mock_ldo_parsing():
    """Test LDO regulator parsing from natural language."""
    client = MockLLMClient()
    
    prompt = "Design a 5V to 3.3V LDO regulator with LED indicator"
    result = client.complete(prompt, REQUIREMENT_SCHEMA, "")
    
    assert result["circuit_type"] == "ldo_regulator"
    assert result["input_voltage"] == 5.0
    assert result["output_voltage"] == 3.3
    assert "led" in str(result.get("features", [])).lower() or "led_indicator" in str(result.get("features", []))


def test_mock_buck_parsing():
    """Test buck converter parsing."""
    client = MockLLMClient()
    
    prompt = "Create a 12V to 5V buck converter 3A output"
    result = client.complete(prompt, REQUIREMENT_SCHEMA, "")
    
    assert result["circuit_type"] == "buck_converter"
    assert result["input_voltage"] == 12.0
    assert result["output_voltage"] == 5.0
    assert result["output_current"] == 3.0


def test_mock_boost_parsing():
    """Test boost converter parsing."""
    client = MockLLMClient()
    
    prompt = "Design a 3.3V to 5V boost converter"
    result = client.complete(prompt, REQUIREMENT_SCHEMA, "")
    
    assert result["circuit_type"] == "boost_converter"
    assert result["input_voltage"] == 3.3
    assert result["output_voltage"] == 5.0


def test_mock_led_parsing():
    """Test LED driver parsing."""
    client = MockLLMClient()
    
    prompt = "Simple LED circuit with current limiting resistor"
    result = client.complete(prompt, REQUIREMENT_SCHEMA, "")
    
    assert result["circuit_type"] == "led_driver"


def test_parse_requirements():
    """Test parse_requirements function."""
    req = parse_requirements("Design a 5V to 3.3V LDO regulator with LED")
    
    assert isinstance(req, CircuitRequirement)
    assert req.circuit_type == "ldo_regulator"
    assert req.input_voltage == 5.0
    assert req.output_voltage == 3.3


def test_generate_specification():
    """Test generate_specification function."""
    req = CircuitRequirement(
        circuit_type="ldo_regulator",
        description="5V to 3.3V LDO",
        input_voltage=5.0,
        output_voltage=3.3,
        output_current=0.5,
        features=["led_indicator"]
    )
    
    spec = generate_specification(req)
    
    assert isinstance(spec, CircuitSpecification)
    assert spec.topology == "linear_ldo"
    assert len(spec.components) >= 3  # regulator + caps + LED
    
    # Check regulator component
    reg = next((c for c in spec.components if c.role == "regulator"), None)
    assert reg is not None
    assert reg.mpn == "AMS1117-3.3"
    
    # Check caps
    caps = [c for c in spec.components if "capacitor" in c.role]
    assert len(caps) >= 2


def test_nl_to_circuit_spec():
    """Test end-to-end natural language to specification."""
    spec = nl_to_circuit_spec("Design a 5V to 3.3V LDO regulator with LED indicator")
    
    assert isinstance(spec, CircuitSpecification)
    assert spec.requirements.circuit_type == "ldo_regulator"
    assert spec.topology == "linear_ldo"
    assert spec.requirements.input_voltage == 5.0
    assert spec.requirements.output_voltage == 3.3


def test_buck_specification():
    """Test buck converter specification generation."""
    req = CircuitRequirement(
        circuit_type="buck_converter",
        description="12V to 5V buck",
        input_voltage=12.0,
        output_voltage=5.0,
        output_current=3.0
    )
    
    spec = generate_specification(req)
    
    assert spec.topology == "buck_async"
    assert len(spec.components) >= 5  # controller, inductor, caps, diode
    
    # Check key components
    roles = {c.role for c in spec.components}
    assert "controller" in roles
    assert "inductor" in roles
    assert "freewheel_diode" in roles


def test_boost_specification():
    """Test boost converter specification."""
    req = CircuitRequirement(
        circuit_type="boost_converter",
        description="3.3V to 5V boost",
        input_voltage=3.3,
        output_voltage=5.0,
        output_current=1.0
    )
    
    spec = generate_specification(req)
    
    assert spec.topology == "boost"
    roles = {c.role for c in spec.components}
    assert "controller" in roles
    assert "inductor" in roles


def test_schema_validity():
    """Test that schemas are valid JSON Schema."""
    import jsonschema
    
    # Test requirement schema
    sample_req = {
        "circuit_type": "ldo_regulator",
        "description": "Test",
        "input_voltage": 5.0,
        "output_voltage": 3.3,
        "output_current": 0.5,
        "features": ["led"]
    }
    jsonschema.validate(sample_req, REQUIREMENT_SCHEMA)
    
    # Test specification schema
    sample_spec = {
        "circuit_type": "ldo_regulator",
        "description": "Test",
        "topology": "linear_ldo",
        "components": [{
            "role": "regulator",
            "mpn": "AMS1117-3.3",
            "manufacturer": "AMS",
            "value": "3.3V",
            "package": "SOT-223",
            "reasoning": "Test"
        }]
    }
    jsonschema.validate(sample_spec, SPECIFICATION_SCHEMA)


def test_component_selection_dataclass():
    """Test ComponentSelection dataclass."""
    comp = ComponentSelection(
        role="regulator",
        mpn="AMS1117-3.3",
        manufacturer="AMS",
        value="3.3V",
        package="SOT-223",
        reasoning="LDO for 5V to 3.3V",
        alternatives=["LM2940"],
        estimated_cost=0.15
    )
    
    assert comp.role == "regulator"
    assert comp.estimated_cost == 0.15
    assert "LM2940" in comp.alternatives


if __name__ == "__main__":
    pytest.main([__file__, "-v"])