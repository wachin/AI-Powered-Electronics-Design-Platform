"""
Tests for LLM Integration module.
"""

import json
import pytest
from src.llm.integration import (
    MockLLMClient,
    LLMProvider,
    CircuitRequirement,
    CircuitSpecification,
    RequirementParser,
    CircuitSpecificationGenerator,
    NLToCircuitPipeline,
    create_nl_pipeline,
    REQUIREMENT_SCHEMA,
    SPECIFICATION_SCHEMA,
)
from src.llm.providers import MockLLMClient, LLMProvider, create_llm_client


class TestMockLLMClient:
    """Tests for MockLLMClient."""

    def test_mock_llm_client_available(self):
        """Test mock client is always available."""
        client = MockLLMClient()
        assert client.is_available() is True

    @pytest.mark.asyncio
    async def test_mock_ldo_parsing(self):
        """Test LDO regulator parsing from natural language."""
        client = MockLLMClient()
        client.responses["Design a 5V to 3.3V LDO regulator with LED indicator"] = {
            "circuit_type": "ldo_regulator",
            "description": "5V to 3.3V LDO regulator with LED indicator",
            "input_voltage": 5.0,
            "output_voltage": 3.3,
            "output_current": 0.5,
            "features": ["led_indicator"],
        }

        prompt = "Design a 5V to 3.3V LDO regulator with LED indicator"
        result = await client.complete(prompt)
        data = json.loads(result.content)

        assert data["circuit_type"] == "ldo_regulator"
        assert data["input_voltage"] == 5.0
        assert data["output_voltage"] == 3.3
        assert "led" in str(data.get("features", [])).lower() or "led_indicator" in str(data.get("features", []))

    @pytest.mark.asyncio
    async def test_mock_buck_parsing(self):
        """Test buck converter parsing."""
        client = MockLLMClient()
        client.responses["Create a 12V to 5V buck converter 3A output"] = {
            "circuit_type": "buck_converter",
            "description": "12V to 5V buck converter 3A",
            "input_voltage": 12.0,
            "output_voltage": 5.0,
            "output_current": 3.0,
        }

        prompt = "Create a 12V to 5V buck converter 3A output"
        result = await client.complete(prompt)
        data = json.loads(result.content)

        assert data["circuit_type"] == "buck_converter"
        assert data["input_voltage"] == 12.0
        assert data["output_voltage"] == 5.0
        assert data["output_current"] == 3.0

    @pytest.mark.asyncio
    async def test_mock_boost_parsing(self):
        """Test boost converter parsing."""
        client = MockLLMClient()
        client.responses["Design a 3.3V to 5V boost converter"] = {
            "circuit_type": "boost_converter",
            "description": "3.3V to 5V boost converter",
            "input_voltage": 3.3,
            "output_voltage": 5.0,
        }

        prompt = "Design a 3.3V to 5V boost converter"
        result = await client.complete(prompt)
        data = json.loads(result.content)

        assert data["circuit_type"] == "boost_converter"
        assert data["input_voltage"] == 3.3
        assert data["output_voltage"] == 5.0

    @pytest.mark.asyncio
    async def test_mock_led_parsing(self):
        """Test LED driver parsing."""
        client = MockLLMClient()
        client.responses["Simple LED circuit with current limiting resistor"] = {
            "circuit_type": "led_driver",
            "description": "Simple LED circuit with current limiting resistor",
        }

        prompt = "Simple LED circuit with current limiting resistor"
        result = await client.complete(prompt)
        data = json.loads(result.content)

        assert data["circuit_type"] == "led_driver"


class TestRequirementParser:
    """Tests for RequirementParser."""

    @pytest.mark.asyncio
    async def test_parse_requirements(self):
        """Test parse_requirements function."""
        # Use the actual parser
        llm_client = create_llm_client(LLMProvider.MOCK)
        parser = RequirementParser(llm_client)

        req = await parser.parse("Design a 5V to 3.3V LDO regulator with LED")

        assert isinstance(req, CircuitRequirement)
        assert req.circuit_type == "ldo_regulator"
        assert req.input_voltage == 5.0
        assert req.output_voltage == 3.3


class TestCircuitSpecificationGenerator:
    """Tests for CircuitSpecificationGenerator."""

    @pytest.mark.asyncio
    async def test_generate_specification(self):
        """Test generate_specification function."""
        # Create a mock LLM client that returns appropriate responses
        client = MockLLMClient()

        # Set up mock responses for the LDO design
        client.responses["default"] = {
            "topology": "linear_ldo",
            "components": [
                {
                    "role": "regulator",
                    "mpn": "AMS1117-3.3",
                    "manufacturer": "AMS",
                    "value": "3.3V",
                    "package": "SOT-223",
                    "reasoning": "LDO regulator 5V to 3.3V, 1A"
                },
                {
                    "role": "input_capacitor",
                    "mpn": "CC0805KRX7R9BB106",
                    "manufacturer": "Yageo",
                    "value": "10uF",
                    "package": "0805",
                    "reasoning": "Input decoupling capacitor"
                },
                {
                    "role": "output_capacitor",
                    "mpn": "CC0805KRX7R9BB106",
                    "manufacturer": "Yageo",
                    "value": "10uF",
                    "package": "0805",
                    "reasoning": "Output stability capacitor"
                },
                {
                    "role": "led_indicator",
                    "mpn": "LTST-C190KGKT",
                    "manufacturer": "Lite-On",
                    "value": "Green",
                    "package": "0805",
                    "reasoning": "Power-on indicator LED"
                },
                {
                    "role": "led_resistor",
                    "mpn": "RC0805FR-0710KL",
                    "manufacturer": "Yageo",
                    "value": "10k",
                    "package": "0805",
                    "reasoning": "LED current limiting resistor"
                },
            ],
            "design_notes": [
                "LDO dropout: 1.7V",
                "Power dissipation: 0.85W",
                "Ensure adequate thermal relief"
            ],
            "warnings": [
                "Check thermal dissipation for high current",
                "Verify dropout voltage at max current"
            ]
        }

        client = MockLLMClient()
        db = None
        generator = CircuitSpecificationGenerator(client, db)

        req = CircuitRequirement(
            circuit_type="ldo_regulator",
            description="5V to 3.3V LDO",
            input_voltage=5.0,
            output_voltage=3.3,
            output_current=0.5,
            features=["led_indicator"]
        )

        spec = await generator.generate(req)

        assert spec.topology == "linear_ldo"
        assert len(spec.components) >= 4

        reg = next((c for c in spec.components if c.role == "regulator"), None)
        assert reg is not None
        assert reg.mpn == "AMS1117-3.3"

    @pytest.mark.asyncio
    async def test_buck_specification(self):
        """Test buck converter specification generation."""
        client = MockLLMClient()
        db = None
        generator = CircuitSpecificationGenerator(client, db)

        req = CircuitRequirement(
            circuit_type="buck_converter",
            description="12V to 5V buck",
            input_voltage=12.0,
            output_voltage=5.0,
            output_current=3.0
        )

        spec = await generator.generate(req)

        assert spec.topology == "buck_async"
        assert len(spec.components) >= 5

        roles = {c.role for c in spec.components}
        assert "controller" in roles
        assert "inductor" in roles
        assert "input_capacitor" in roles
        assert "output_capacitor" in roles
        assert "freewheel_diode" in roles

    @pytest.mark.asyncio
    async def test_boost_specification(self):
        """Test boost converter specification generation."""
        client = MockLLMClient()
        db = None
        generator = CircuitSpecificationGenerator(client, db)

        req = CircuitRequirement(
            circuit_type="boost_converter",
            description="3.3V to 5V boost",
            input_voltage=3.3,
            output_voltage=5.0,
            output_current=1.0
        )

        spec = await generator.generate(req)

        assert spec.topology == "boost"
        roles = {c.role for c in spec.components}
        assert "controller" in roles
        assert "inductor" in roles

    @pytest.mark.asyncio
    async def test_led_specification(self):
        """Test LED driver specification generation."""
        client = MockLLMClient()
        db = None
        generator = CircuitSpecificationGenerator(client, db)

        req = CircuitRequirement(
            circuit_type="led_driver",
            description="Simple LED circuit",
            input_voltage=5.0,
            output_current=0.02
        )

        spec = await generator.generate(req)

        assert spec.topology == "series_resistor"
        roles = {c.role for c in spec.components}
        assert "led" in roles
        assert "current_limit_resistor" in roles


class TestNLToCircuitPipeline:
    """Tests for the end-to-end NL to Circuit pipeline."""

    @pytest.mark.asyncio
    async def test_nl_to_circuit_spec(self):
        """Test end-to-end natural language to circuit specification."""
        # This tests the full pipeline with mock LLM
        client = MockLLMClient()

        # Set up mock responses for the full pipeline
        client.responses["default"] = {
            "circuit_type": "ldo_regulator",
            "description": "5V to 3.3V LDO regulator with LED",
            "input_voltage": 5.0,
            "output_voltage": 3.3,
            "output_current": 0.5,
            "features": ["led_indicator"],
        }

        pipeline = create_nl_pipeline(LLMProvider.MOCK)

        spec = await pipeline.nl_to_circuit_spec(
            "Design a 5V to 3.3V LDO regulator with LED indicator"
        )

        assert spec.requirements.circuit_type == "ldo_regulator"
        assert spec.requirements.input_voltage == 5.0
        assert spec.requirements.output_voltage == 3.3
        assert spec.requirements.output_current == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
