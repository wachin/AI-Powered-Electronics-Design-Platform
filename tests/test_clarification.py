"""
Tests for asking the user what the request did not say.

The behaviour these cover: the parser used to fill in every gap silently — no
input voltage became 5 V — and then report the assumption *after* the design was
finished. Now it asks first, when there is someone to ask.
"""

import pytest

from src.llm.clarification import (
    THERMAL_ATTENTION_W,
    UNUSABLE_TOPOLOGIES,
    WORKING_TOPOLOGIES,
    Clarification,
    apply_answers,
    clarifications_for,
    clarify,
    coerce_answer,
    fill_defaults,
)
from src.llm.integration import CircuitRequirement


def requirement(**kwargs) -> CircuitRequirement:
    base = {"circuit_type": "ldo_regulator", "description": "test"}
    base.update(kwargs)
    return CircuitRequirement(**base)


def scripted(*answers):
    """An ``ask`` callable that returns pre-written answers, in order."""
    queue = list(answers)

    def ask(question):
        return queue.pop(0) if queue else ""

    return ask


class TestWhatIsAsked:
    def test_nothing_is_asked_when_everything_was_stated(self):
        complete = requirement(
            input_voltage=5.0, output_voltage=3.3, output_current=0.5
        )
        assert clarifications_for(complete).questions == []

    @pytest.mark.parametrize(
        "missing,field",
        [
            ("input_voltage", "input_voltage"),
            ("output_voltage", "output_voltage"),
            ("output_current", "output_current"),
        ],
    )
    def test_a_missing_value_is_asked_about(self, missing, field):
        values = {"input_voltage": 5.0, "output_voltage": 3.3, "output_current": 0.5}
        values[missing] = None
        questions = clarifications_for(requirement(**values)).questions
        assert [q.field for q in questions] == [field]

    def test_an_unknown_topology_is_asked_about(self):
        """ "generic" means the platform did not understand the request."""
        questions = clarifications_for(
            requirement(circuit_type="generic")
        ).questions
        assert [q.field for q in questions] == ["circuit_type"]
        assert questions[0].choices

    def test_the_question_offers_only_topologies_that_work(self):
        """
        A clarification must not offer an answer that leads to a broken design.
        The switched-mode controller currently resolves with no pins.
        """
        question = clarifications_for(requirement(circuit_type="generic")).questions[0]
        for choice in question.choices:
            assert choice in WORKING_TOPOLOGIES
        assert set(question.choices).isdisjoint(UNUSABLE_TOPOLOGIES)
        # And the ones that cannot be offered are named, with the reason.
        for blocked in UNUSABLE_TOPOLOGIES:
            assert blocked in question.why

    def test_an_led_circuit_is_not_asked_for_a_voltage_drop(self):
        """The thermal question is about linear regulators."""
        questions = clarifications_for(
            requirement(
                circuit_type="led_driver",
                input_voltage=5.0, output_voltage=None, output_current=None,
            )
        ).questions
        assert all("dissipate" not in q.question for q in questions)

    def test_every_question_says_why_it_is_asked(self):
        questions = clarifications_for(requirement()).questions
        assert questions
        for question in questions:
            assert question.why
            assert question.question.endswith("?")


class TestTheThermalQuestion:
    def test_a_hot_linear_design_is_questioned(self):
        """
        12 V to 3.3 V at 1 A is 8.7 W in the regulator. That is a design
        decision, not a missing number, so it is worth asking about.
        """
        questions = clarifications_for(
            requirement(input_voltage=12.0, output_voltage=3.3, output_current=1.0)
        ).questions
        assert len(questions) == 1
        assert "dissipate" in questions[0].question
        assert "8.70 W" in questions[0].question

    def test_a_cool_linear_design_is_not_questioned(self):
        questions = clarifications_for(
            requirement(input_voltage=5.0, output_voltage=3.3, output_current=0.1)
        ).questions
        assert questions == []

    def test_the_threshold_is_the_documented_rule_of_thumb(self):
        below = clarifications_for(
            requirement(input_voltage=5.0, output_voltage=3.3, output_current=0.5)
        ).questions
        above = clarifications_for(
            requirement(input_voltage=5.0, output_voltage=3.3, output_current=2.0)
        ).questions
        # 0.5 A x 1.7 V = 0.85 W, under the 1 W rule of thumb; 2 A is 3.4 W.
        assert THERMAL_ATTENTION_W == pytest.approx(1.0)
        assert below == []
        assert above

    def test_it_says_what_current_would_be_feasible(self):
        question = clarifications_for(
            requirement(input_voltage=12.0, output_voltage=3.3, output_current=1.0)
        ).questions[0]
        # 1 W over an 8.7 V drop is about 0.11 A.
        assert "0.11 A" in question.why

    def test_it_is_not_asked_twice(self):
        """Answering with the same current must move on, not ask again."""
        hot = requirement(input_voltage=12.0, output_voltage=3.3, output_current=1.0)
        assert clarifications_for(hot, exclude=["output_current"]).questions == []


class TestAnswering:
    def test_enter_takes_the_default(self):
        question = Clarification("input_voltage", "?", "why", default=5.0)
        assert coerce_answer(question, "") == 5.0
        assert coerce_answer(question, "   ") == 5.0

    def test_a_plain_number(self):
        question = Clarification("input_voltage", "?", "why", default=5.0)
        assert coerce_answer(question, "12") == 12.0
        assert coerce_answer(question, "3.3") == 3.3

    def test_a_number_with_a_unit(self):
        question = Clarification("input_voltage", "?", "why", default=5.0, unit=" V")
        assert coerce_answer(question, "12V") == 12.0
        assert coerce_answer(question, "12 v") == 12.0

    def test_milliamps(self):
        question = Clarification("output_current", "?", "why", default=0.5)
        assert coerce_answer(question, "500mA") == pytest.approx(0.5)

    def test_an_unreadable_answer_falls_back_to_the_default(self):
        """
        A typo must not end the run or produce a nonsense value; pressing Enter is
        the documented way to accept the default, and so is anything unreadable.
        """
        question = Clarification("input_voltage", "?", "why", default=5.0)
        assert coerce_answer(question, "banana") == 5.0

    def test_a_choice_can_be_named_or_numbered(self):
        question = Clarification(
            "circuit_type", "?", "why", default="ldo_regulator",
            choices=("ldo_regulator", "led_driver"),
        )
        assert coerce_answer(question, "led_driver") == "led_driver"
        assert coerce_answer(question, "led driver") == "led_driver"
        assert coerce_answer(question, "2") == "led_driver"
        assert coerce_answer(question, "") == "ldo_regulator"

    def test_answers_are_applied(self):
        req = requirement()
        apply_answers(req, {"input_voltage": 12.0, "output_voltage": 5.0})
        assert req.input_voltage == 12.0
        assert req.output_voltage == 5.0

    def test_an_unusable_topology_answer_is_ignored(self):
        """The question does not offer it, so an answer naming it must not stick."""
        req = requirement(circuit_type="generic")
        apply_answers(req, {"circuit_type": "buck_converter"})
        assert req.circuit_type == "generic"

    def test_a_stray_key_is_ignored(self):
        req = requirement()
        apply_answers(req, {"nonsense": 3, "input_voltage": "12"})
        assert req.input_voltage == 12.0


class TestTheLoop:
    def test_it_asks_until_nothing_is_left(self):
        req = requirement()
        answers = iter(["12", "5", "0.1"])
        result = clarify(req, lambda q: next(answers, ""))
        assert result.input_voltage == 12.0
        assert result.output_voltage == 5.0
        assert result.output_current == 0.1

    def test_it_terminates_when_every_answer_is_the_default(self):
        """
        A loop that re-asks after a default answer never ends. Each field is asked
        at most once, so this is bounded by the number of fields.
        """
        req = requirement(input_voltage=12.0, output_voltage=3.3, output_current=1.0)
        asked = []

        def always_default(question):
            asked.append(question.field)
            return ""

        clarify(req, always_default, max_rounds=10)
        assert len(asked) == len(set(asked)), asked
        assert len(asked) <= 1

    def test_an_unknown_topology_is_asked_about_first(self):
        """
        Once the topology is answered the voltages become worth asking about, in
        that order: the topology decides which questions matter.
        """
        req = requirement(circuit_type="generic")
        asked = []

        def record(question):
            asked.append(question.field)
            return ""

        clarify(req, record)
        assert asked[0] == "circuit_type"
        assert set(asked) <= {"circuit_type", "input_voltage", "output_voltage", "output_current"}


class TestFallbackWhenNobodyAnswers:
    def test_the_defaults_are_filled_and_recorded(self):
        req = fill_defaults(requirement())
        assert req.input_voltage == 5.0
        assert req.output_voltage == 3.3
        assert req.output_current == 0.5
        assumptions = req.constraints.get("assumptions", [])
        assert any("input voltage" in a for a in assumptions)
        assert any("current" in a for a in assumptions)

    def test_a_stated_value_is_not_an_assumption(self):
        req = fill_defaults(
            requirement(input_voltage=12.0, output_voltage=5.0, output_current=1.0)
        )
        assert req.constraints.get("assumptions") in (None, [])

    def test_an_answered_value_is_not_an_assumption(self):
        """
        The point of the whole flow: what the user said is a fact, and what nobody
        answered is an assumption.
        """
        req = requirement(input_voltage=12.0, output_voltage=5.0, output_current=None)
        clarify(req, scripted("2"))
        fill_defaults(req)
        assumptions = req.constraints.get("assumptions", [])
        assert assumptions == []
        assert req.output_current == 2.0

    def test_a_partly_answered_request_records_only_the_gap(self):
        req = requirement(input_voltage=None, output_voltage=5.0, output_current=1.0)
        clarify(req, scripted("12"))
        fill_defaults(req)
        assumptions = req.constraints.get("assumptions", [])
        assert assumptions == []
        assert req.input_voltage == 12.0


class TestThePipelineHonoursIt:
    def test_no_clarifier_means_defaults_and_assumptions(self):
        import asyncio

        from src.llm.integration import create_nl_pipeline

        pipeline = create_nl_pipeline("mock")
        result = asyncio.run(pipeline.process("an LDO regulator", "t"))
        req = result["requirements"]
        assert (req.input_voltage, req.output_voltage) == (5.0, 3.3)
        assert (req.constraints or {}).get("assumptions")

    def test_a_clarifier_is_asked_and_its_answers_used(self):
        import asyncio

        from src.llm.integration import create_nl_pipeline

        answers = iter(["12", "5", "0.1"])
        pipeline = create_nl_pipeline("mock", clarifier=lambda q: next(answers, ""))
        result = asyncio.run(pipeline.process("an LDO regulator", "t"))
        req = result["requirements"]
        assert req.input_voltage == 12.0
        assert req.output_voltage == 5.0
        assert req.output_current == 0.1
        # Nothing was left to assume.
        assert (req.constraints or {}).get("assumptions") in (None, [])

    def test_the_questions_asked_are_recorded(self):
        import asyncio

        from src.llm.integration import create_nl_pipeline

        pipeline = create_nl_pipeline("mock", clarifier=lambda q: "")
        asyncio.run(pipeline.process("an LDO regulator", "t"))
        assert [q.field for q in pipeline.last_clarifications] == [
            "input_voltage", "output_voltage", "output_current",
        ]

    def test_the_design_uses_the_answered_voltages(self):
        """
        The whole point, end to end: answering 12 V must produce a 12 V design and
        therefore a 7 V drop, not the 1.7 V of a 5 V one.
        """
        import asyncio

        from src.llm.integration import create_nl_pipeline

        answers = iter(["12", "5", "1"])
        pipeline = create_nl_pipeline("mock", clarifier=lambda q: next(answers, ""))
        result = asyncio.run(pipeline.process("an LDO regulator", "t"))
        notes = " ".join(result["specification"].design_notes)
        assert "7.0V" in notes, notes
