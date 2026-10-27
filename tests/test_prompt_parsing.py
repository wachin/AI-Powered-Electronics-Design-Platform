"""
Tests for reading the prompt on the path that has no model.

The defect these cover: the CLI's default provider is ``mock``, and the mock
client returns *canned* requirements — 5 V in, 3.3 V out, 0.5 A — instead of
reading the prompt. So ``-p "Design a 12V to 3.3V LDO regulator"`` produced a
5 V design, and every later stage validated that wrong design without a word.
It was not a loud failure; it was a confident answer to a question nobody asked.
"""

import pytest

from src.llm.integration import (
    RequirementParser,
    create_nl_pipeline,
)
from src.llm.providers import LLMProvider, create_llm_client


@pytest.fixture()
def parser() -> RequirementParser:
    return RequirementParser(create_llm_client("mock"), deterministic=True)


class TestVoltagesAreRead:
    @pytest.mark.parametrize(
        "prompt,vin,vout",
        [
            ("Design a 12V to 3.3V LDO regulator", 12.0, 3.3),
            ("5V to 3.3V LDO with an LED indicator", 5.0, 3.3),
            ("24V to 5V buck converter at 3A", 24.0, 5.0),
            ("12 V input, 3.3 V output LDO", 12.0, 3.3),
            ("5v->3.3v regulator", 5.0, 3.3),
            ("5 V → 3.3 V regulator", 5.0, 3.3),
            # Spanish: the separator "a" is how a range is written in Spanish,
            # and this project is used in Spanish as much as in English.
            ("un regulador de 12V a 3.3V", 12.0, 3.3),
            ("regulador 9V a 5V", 9.0, 5.0),
        ],
    )
    def test_the_range_in_the_prompt_is_used(self, parser, prompt, vin, vout):
        requirement = parser._fallback_parse(prompt)
        assert requirement.input_voltage == pytest.approx(vin), prompt
        assert requirement.output_voltage == pytest.approx(vout), prompt

    def test_the_current_is_read(self, parser):
        requirement = parser._fallback_parse("12V to 3.3V LDO at 2A")
        assert requirement.output_current == pytest.approx(2.0)

    def test_milliamps_are_converted(self, parser):
        requirement = parser._fallback_parse("5V to 3.3V LDO at 500mA")
        assert requirement.output_current == pytest.approx(0.5)

    def test_the_topology_is_read(self, parser):
        assert parser._fallback_parse("an LDO").circuit_type == "ldo_regulator"
        assert parser._fallback_parse("a buck converter").circuit_type == "buck_converter"
        assert parser._fallback_parse("a boost converter").circuit_type == "boost_converter"
        assert parser._fallback_parse("an LED circuit").circuit_type == "led_driver"

    @pytest.mark.parametrize(
        "prompt,expected",
        [
            ("un regulador de 12V a 3.3V", "ldo_regulator"),
            ("regulador conmutado 12V a 5V", "buck_converter"),
            ("convertidor reductor de 24V a 5V", "buck_converter"),
            ("convertidor elevador de 3.3V a 5V", "boost_converter"),
            ("fuente lineal 9V a 5V", "ldo_regulator"),
        ],
    )
    def test_spanish_topologies_are_read(self, parser, prompt, expected):
        """
        "un regulador de 12V a 3.3V" used to come out as "generic" while the
        voltages parsed correctly — a design that ignores the topology.
        """
        assert parser._fallback_parse(prompt).circuit_type == expected

    def test_a_switching_regulator_is_not_a_linear_one(self, parser):
        """Both contain "regulator"; the direction decides."""
        assert parser._fallback_parse("a switching regulator").circuit_type == "buck_converter"
        assert parser._fallback_parse("a linear regulator").circuit_type == "ldo_regulator"


class TestAssumptionsAreStated:
    def assumptions(self, parser, prompt):
        """
        The parser reads the text; filling the gaps is `fill_defaults`' job, so
        the assumptions come from `parse`, which is the public path.
        """
        import asyncio

        requirement = asyncio.run(parser.parse(prompt))
        return (requirement.constraints or {}).get("assumptions", [])

    def test_a_missing_current_is_reported(self, parser):
        assumptions = self.assumptions(parser, "12V to 3.3V LDO")
        assert any("current" in a and "0.5" in a for a in assumptions)

    def test_a_missing_input_voltage_is_reported(self, parser):
        assumptions = self.assumptions(parser, "LDO 1A")
        assert any("input voltage" in a and "5" in a for a in assumptions)

    def test_a_single_voltage_for_a_regulator_is_taken_as_the_output(self, parser):
        assumptions = self.assumptions(parser, "LDO 3.3V 1A")
        assert any("only one voltage" in a and "output" in a for a in assumptions)

    def test_a_single_voltage_for_an_led_circuit_is_the_supply(self, parser):
        assumptions = self.assumptions(parser, "5V LED circuit")
        assert any("only one voltage" in a and "supply" in a for a in assumptions)

    def test_nothing_is_assumed_when_everything_was_stated(self, parser):
        assert self.assumptions(parser, "12V to 3.3V LDO at 2A") == []


class TestDeterministicMode:
    def test_the_mock_provider_selects_it(self):
        """
        "mock" means *no model*: the prompt is parsed with rules. It is not a stub
        that returns a canned answer while appearing to read the prompt.
        """
        pipeline = create_nl_pipeline("mock")
        assert pipeline.deterministic is True
        assert pipeline.parser.deterministic is True
        assert pipeline.spec_generator.use_llm is False

    def test_a_real_provider_does_not(self):
        pipeline = create_nl_pipeline(LLMProvider.OLLAMA)
        assert pipeline.deterministic is False
        assert pipeline.parser.deterministic is False
        assert pipeline.spec_generator.use_llm is True

    def test_the_mock_client_alone_would_discard_the_prompt(self):
        """
        The behaviour that caused the bug, pinned so it cannot come back
        unnoticed: asking the mock client returns the same canned requirements
        whatever you ask it.
        """
        asking = RequirementParser(create_llm_client("mock"), deterministic=False)
        assert asking.deterministic is False
        # Its canned answer is 5 V / 3.3 V / 0.5 A regardless of the prompt, which
        # is exactly why the deterministic parser must be used instead.
        import asyncio

        parsed = asyncio.run(asking.parse("Design a 12V to 3.3V LDO regulator"))
        assert parsed.input_voltage == 5.0
        assert parsed.output_voltage == 3.3


class TestEndToEnd:
    def test_a_twelve_volt_prompt_produces_a_twelve_volt_design(self):
        """
        The whole point: 12 V in means 8.7 V dropped across a linear regulator,
        which is a 4.4 W thermal problem, not the 0.87 W a 5 V design has.
        """
        import asyncio

        pipeline = create_nl_pipeline("mock", component_db=None)
        result = asyncio.run(
            pipeline.process("Design a 12V to 3.3V LDO regulator at 0.5A", "t")
        )
        requirements = result["requirements"]
        assert requirements.input_voltage == pytest.approx(12.0)
        assert requirements.output_voltage == pytest.approx(3.3)

        spec = result["specification"]
        assert any("8.7V" in note for note in spec.design_notes), spec.design_notes

    def test_the_pipeline_carries_the_assumptions(self):
        import asyncio

        pipeline = create_nl_pipeline("mock")
        result = asyncio.run(pipeline.process("an LDO", "t"))
        assumptions = (result["requirements"].constraints or {}).get("assumptions", [])
        assert assumptions, "an under-specified prompt must say what was assumed"


class TestReviewSeesTheRealInput:
    """
    The review is only as good as the requirements it is handed. This is the
    check that showed the bug: a 12 V design dissipates 4.4 W, needs a thermal
    path better than about 23 °C/W, and cannot be built in a SOT-223.
    """

    @pytest.fixture()
    def real_db(self):
        import os
        from pathlib import Path

        from src.components.database import ComponentDatabase

        path = os.environ.get("JLC_PARTS_CATALOG")
        if not path or not Path(path).exists():
            pytest.skip("JLC_PARTS_CATALOG is not set to a real catalog")
        return ComponentDatabase(Path(path))

    def circuit(self):
        from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType

        circuit = CircuitIR(name="ldo", description="")
        u1 = Component(
            ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
            footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
            symbol="Regulator_Linear:AMS1117-3.3", mpn="", package="SOT-223",
        )
        for number, name in (("1", "GND"), ("2", "VO"), ("3", "VI")):
            u1.add_pin(number, name, PinType.POWER_IN)
        circuit.add_component(u1)
        return circuit

    def test_five_volts_passes_and_twelve_volts_fails(self, real_db):
        from src.core.design_review import review_circuit

        def thermal(vin):
            review = review_circuit(
                self.circuit(), real_db,
                {"input_voltage": vin, "output_voltage": 3.3, "output_current": 0.5},
            )
            return next(f for f in review.findings if f.rule_id == "REVIEW_THERMAL")

        low = thermal(5.0)
        high = thermal(12.0)
        assert low.severity != "fail", low.message
        assert high.severity == "fail", high.message
        assert high.detail["power_w"] == pytest.approx(4.4, abs=0.1)
        assert "switching regulator" in high.message

    def test_the_junction_limit_is_taken_from_the_part_family(self, real_db):
        """
        The part the design resolves to states no junction limit; a variant of the
        same part number does. Using it is real data, and the review says where it
        came from.
        """
        from src.core.design_review import review_circuit

        review = review_circuit(
            self.circuit(), real_db,
            {"input_voltage": 12.0, "output_voltage": 3.3, "output_current": 0.5},
        )
        assert any("same family" in a for a in review.assumptions), review.assumptions
