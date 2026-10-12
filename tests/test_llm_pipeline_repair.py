"""
Tests for the validated specification -> Circuit IR -> repair loop.

The original pipeline computed an LLM specification and then threw it away,
building a hardcoded circuit instead. It also swallowed every LLM failure and
silently substituted the rule-based template. These tests pin down the fixed
behaviour:

* the LLM's own components and connections reach the Circuit IR
* a physically invalid design is sent back to the model with specific errors
* the best attempt is kept, not the last one
* an empty LLM response is a failure, not a silent template substitution
"""

import json

import pytest

from src.components.database import ComponentDatabase
from src.llm.integration import (
    CircuitRequirement,
    CircuitSpecificationGenerator,
    NLToCircuitPipeline,
)
from src.llm.providers import LLMClient, LLMMessage, LLMResponse, LLMResponseError


class ScriptedLLMClient(LLMClient):
    """Returns a queue of structured responses, recording every request."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []
        self.call_count = 0

    async def complete(self, messages, temperature=0.1, max_tokens=4096, response_format=None):
        return LLMResponse(content=json.dumps(self._responses[-1] if self._responses else {}))

    async def complete_structured(
        self, messages, response_schema, temperature=0.1, max_tokens=2048
    ):
        self.call_count += 1
        self.requests.append(messages)
        if not self._responses:
            raise LLMResponseError("no more scripted responses")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def health_check(self):
        return True


def _requirements(circuit_type="ldo_regulator"):
    return CircuitRequirement(
        circuit_type=circuit_type,
        description="5V to 3.3V LDO regulator with 500mA and LED indicator",
        input_voltage=5.0,
        output_voltage=3.3,
        output_current=0.5,
        features=["led_indicator"],
    )


VALID_LDO_SPEC = {
    "topology": "LDO Linear Regulator",
    "components": [
        {"role": "regulator", "mpn": "AMS1117-3.3", "value": "3.3V", "package": "SOT-223"},
        {"role": "input_capacitor", "mpn": "CC0805KRX7R9BB106", "value": "10uF", "package": "0805"},
        {"role": "output_capacitor", "mpn": "CC0805KRX5R7BB226", "value": "22uF", "package": "0805"},
        {"role": "led_indicator", "mpn": "LTST-C190KGKT", "value": "Green", "package": "0805"},
        {"role": "led_resistor", "mpn": "RC0805FR-07330RL", "value": "330", "package": "0805"},
    ],
    "connections": [
        {"from": "U1.VIN", "to": "C1.1", "net": "VIN"},
        {"from": "U1.VOUT", "to": "C2.1", "net": "VOUT"},
        {"from": "U1.VOUT", "to": "R1.1", "net": "VOUT"},
        {"from": "R1.2", "to": "D1.A", "net": "LED_A"},
        {"from": "D1.K", "to": "C1.2", "net": "GND"},
        {"from": "U1.GND", "to": "C2.2", "net": "GND"},
    ],
}

# Same circuit, but wired with a pin that does not exist and an LED with no resistor.
BROKEN_LDO_SPEC = {
    "topology": "LDO Linear Regulator",
    "components": [
        {"role": "regulator", "mpn": "AMS1117-3.3", "value": "3.3V", "package": "SOT-223"},
        {"role": "input_capacitor", "mpn": "CC0805KRX7R9BB106", "value": "10uF", "package": "0805"},
        {"role": "output_capacitor", "mpn": "CC0805KRX5R7BB226", "value": "22uF", "package": "0805"},
        {"role": "led_indicator", "mpn": "LTST-C190KGKT", "value": "Green", "package": "0805"},
    ],
    "connections": [
        {"from": "U1.VIN", "to": "C1.1", "net": "VIN"},
        {"from": "U1.MADE_UP_PIN", "to": "C2.1", "net": "VOUT"},
        {"from": "D1.A", "to": "C1.2", "net": "GND"},
    ],
}


@pytest.fixture(scope="module")
def db():
    return ComponentDatabase()


class TestValidatedGeneration:
    @pytest.mark.asyncio
    async def test_llm_components_reach_the_circuit(self, db):
        client = ScriptedLLMClient([VALID_LDO_SPEC])
        generator = CircuitSpecificationGenerator(client, db, use_llm=True)

        spec, circuit, report = await generator.generate_validated(
            _requirements(), max_repairs=0
        )

        assert report.valid is True
        assert spec.used_llm is True
        assert set(circuit.components) == {"U1", "C1", "C2", "D1", "R1"}
        # The LLM's own part choices survived, unlike the old hardcoded path.
        assert circuit.components["U1"].mpn == "AMS1117-3.3"
        assert circuit.components["R1"].mpn == "RC0805FR-07330RL"

    @pytest.mark.asyncio
    async def test_repair_loop_recovers_from_broken_design(self, db):
        client = ScriptedLLMClient([BROKEN_LDO_SPEC, VALID_LDO_SPEC])
        generator = CircuitSpecificationGenerator(client, db, use_llm=True)

        spec, circuit, report = await generator.generate_validated(
            _requirements(), max_repairs=2
        )

        assert client.call_count == 2, "the invalid design should trigger one repair"
        assert report.valid is True
        assert spec.repair_attempts == 1

    @pytest.mark.asyncio
    async def test_repair_prompt_contains_specific_errors(self, db):
        client = ScriptedLLMClient([BROKEN_LDO_SPEC, VALID_LDO_SPEC])
        generator = CircuitSpecificationGenerator(client, db, use_llm=True)

        await generator.generate_validated(_requirements(), max_repairs=2)

        repair_messages = client.requests[1]
        repair_text = "\n".join(m.content for m in repair_messages)
        assert "MADE_UP_PIN" in repair_text or "CONNECTION_INVALID" in repair_text
        assert "ERROR" in repair_text

    @pytest.mark.asyncio
    async def test_keeps_best_attempt_when_repair_gets_worse(self, db):
        """
        A repair that introduces *more* errors must not replace a better attempt.

        BROKEN_LDO_SPEC has 4 errors across 4 components; the "worse" reply has
        1 error but only 1 component. Fewest errors wins, so the 4-component
        attempt is still the one that gets returned.
        """
        worse = {
            "topology": "x",
            "components": [
                {"role": "mystery", "mpn": "FAKE-1", "value": "1", "package": "0805"}
            ],
        }
        client = ScriptedLLMClient([BROKEN_LDO_SPEC, worse])
        generator = CircuitSpecificationGenerator(client, db, use_llm=True)

        spec, circuit, report = await generator.generate_validated(
            _requirements(), max_repairs=1
        )

        assert circuit is not None
        assert len(circuit.components) == 1
        assert len(report.errors) == 1

    @pytest.mark.asyncio
    async def test_never_regresses_from_valid_to_invalid(self, db):
        """A garbage repair must not discard an already-valid design."""
        client = ScriptedLLMClient([VALID_LDO_SPEC, LLMResponseError("garbage")])
        generator = CircuitSpecificationGenerator(client, db, use_llm=True)

        spec, circuit, report = await generator.generate_validated(
            _requirements(), max_repairs=1
        )

        assert report.valid is True
        assert set(circuit.components) == {"U1", "C1", "C2", "D1", "R1"}

    @pytest.mark.asyncio
    async def test_repair_failure_keeps_previous_spec(self, db):
        client = ScriptedLLMClient(
            [BROKEN_LDO_SPEC, LLMResponseError("provider went away")]
        )
        generator = CircuitSpecificationGenerator(client, db, use_llm=True)

        spec, circuit, report = await generator.generate_validated(
            _requirements(), max_repairs=1
        )

        assert circuit is not None
        assert len(circuit.components) == 4

    @pytest.mark.asyncio
    async def test_empty_llm_response_is_not_silently_templated(self, db):
        """When fallback is forbidden, an empty response must raise."""
        client = ScriptedLLMClient([{"topology": "", "components": []}])
        generator = CircuitSpecificationGenerator(
            client, db, use_llm=True, allow_fallback=False
        )

        with pytest.raises(LLMResponseError):
            await generator.generate_validated(_requirements(), max_repairs=0)

    @pytest.mark.asyncio
    async def test_fallback_is_recorded_when_allowed(self, db):
        client = ScriptedLLMClient([LLMResponseError("boom")])
        generator = CircuitSpecificationGenerator(
            client, db, use_llm=True, allow_fallback=True
        )

        spec, circuit, report = await generator.generate_validated(
            _requirements(), max_repairs=0
        )

        # The fallback still produces a *valid* circuit, but must say so.
        assert spec.used_llm is False
        assert report.valid is True
        assert len(circuit.components) >= 4

    @pytest.mark.asyncio
    async def test_validation_payload_attached_to_spec(self, db):
        client = ScriptedLLMClient([VALID_LDO_SPEC])
        generator = CircuitSpecificationGenerator(client, db, use_llm=True)

        spec, _, _ = await generator.generate_validated(_requirements(), max_repairs=0)

        assert spec.validation is not None
        assert spec.validation["valid"] is True
        assert spec.validation["erc"]["passed"] is True


class TestPipelineEndToEnd:
    @pytest.mark.asyncio
    async def test_pipeline_returns_circuit_ir_from_llm_output(self, db):
        # First response parses the requirement, second generates the circuit.
        parse_response = {
            "circuit_type": "ldo_regulator",
            "description": "5V to 3.3V LDO with LED",
            "input_voltage": 5.0,
            "output_voltage": 3.3,
            "output_current": 0.5,
            "features": ["led_indicator"],
        }
        client = ScriptedLLMClient([parse_response, VALID_LDO_SPEC])
        pipeline = NLToCircuitPipeline(
            llm_client=client, component_db=db, allow_fallback=False, max_repairs=0
        )

        circuit = await pipeline.nl_to_circuit_ir(
            "Design a 5V to 3.3V LDO regulator with an LED indicator"
        )

        assert set(circuit.components) == {"U1", "C1", "C2", "D1", "R1"}
        assert pipeline.last_validation is not None
        assert pipeline.last_validation.valid is True

    @pytest.mark.asyncio
    async def test_pipeline_process_reports_validation_and_files(self, db, tmp_path):
        parse_response = {
            "circuit_type": "ldo_regulator",
            "description": "5V to 3.3V LDO",
            "input_voltage": 5.0,
            "output_voltage": 3.3,
            "output_current": 0.5,
        }
        client = ScriptedLLMClient([parse_response, VALID_LDO_SPEC])
        pipeline = NLToCircuitPipeline(
            llm_client=client, component_db=db, allow_fallback=False, max_repairs=0
        )

        result = await pipeline.process(
            "Design a 5V to 3.3V LDO regulator",
            project_name="t",
            output_dir=tmp_path,
        )

        assert result["valid"] is True
        assert result["circuit_ir"].components
        assert result["files"]["sch"].exists()

    @pytest.mark.asyncio
    async def test_pipeline_raises_when_design_cannot_be_built(self, db):
        parse_response = {
            "circuit_type": "ldo_regulator",
            "description": "bad",
            "input_voltage": 5.0,
            "output_voltage": 3.3,
            "output_current": 0.5,
        }
        broken = {
            "topology": "x",
            "components": [
                {"role": "mystery", "mpn": "FAKE-1", "value": "1", "package": "0805"}
            ],
        }
        client = ScriptedLLMClient([parse_response, broken])
        pipeline = NLToCircuitPipeline(
            llm_client=client, component_db=db, allow_fallback=False, max_repairs=0
        )

        with pytest.raises(RuntimeError):
            await pipeline.nl_to_circuit_ir("bad request")
