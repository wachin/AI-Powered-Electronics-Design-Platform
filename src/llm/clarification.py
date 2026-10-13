"""
Asking for what the request did not say.

Why this exists
---------------
The requirement parser used to fill in every missing value silently: no input
voltage became 5 V, no current became 0.5 A. It now *reports* what it assumed,
which is better, but the user still finds out after the design is finished. This
module asks first.

What is worth asking about
--------------------------
Only values that change the design, and only when the answer cannot be inferred:

* **the topology**, when the request did not name one — "generic" means the
  platform did not understand the request, which is exactly when to ask;
* **the input voltage**, because it sets the voltage dropped across a linear
  regulator, and therefore the heat;
* **the output voltage**, because everything downstream depends on it;
* **the output current**, for the same thermal reason;
* **a linear design that will get hot**, because that is a design decision, not
  a missing number: 12 V to 3.3 V at 1 A burns 8.7 W in the regulator.

What is not asked about
-----------------------
Anything the design does not depend on: features, cost targets, board size. A
clarification round that asks about things it could have inferred is a worse
experience than one that fills them in, so the default is always offered and
pressing Enter accepts it.

Where it is not asked at all
----------------------------
When there is no one to ask. A piped invocation, a test or an API call has no
terminal, and blocking on input there would hang. Those paths keep the defaults
and say so, which is what the assumptions list is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

# A linear regulator shedding more than this in a surface-mount package needs a
# deliberate thermal decision. It is a rule of thumb, stated as one: the exact
# requirement is computed later against the real part, and this number exists
# only to decide whether to ask.
THERMAL_ATTENTION_W = 1.0

# The topologies this platform can generate a design for, checked by
# `tests/test_topologies.py`, which builds each one and requires it to pass the
# electrical rules. A clarification must never offer an answer that leads to a
# broken design, so this list is not a wish list.
WORKING_TOPOLOGIES: Dict[str, str] = {
    "ldo_regulator": "linear regulator (LDO)",
    "buck_converter": "switching step-down (buck)",
    "boost_converter": "switching step-up (boost)",
    "led_driver": "LED with a series resistor",
}

# Understood by the pipeline but deliberately not offered, with the reason.
# Empty today; the structure stays because a topology that stops working has to
# be withdrawn from the question rather than silently offered.
UNUSABLE_TOPOLOGIES: Dict[str, str] = {}


@dataclass
class Clarification:
    """One question, with the answer it proposes and why it is being asked."""

    field: str
    question: str
    why: str
    default: Any = None
    choices: Sequence[str] = ()
    unit: str = ""

    def describe_default(self) -> str:
        """The answer that pressing Enter accepts."""
        if self.default in (None, ""):
            return "none"
        return f"{self.default}{self.unit}"

    def render(self, index: int = 1, total: int = 1) -> str:
        lines = [f"({index}/{total}) {self.question}"]
        lines.append(f"        why: {self.why}")
        if self.choices:
            lines.append(f"        options: {', '.join(self.choices)}")
        elif self.default not in (None, ""):
            lines.append(f"        default: {self.default}{self.unit} (press Enter)")
        return "\n".join(lines)


@dataclass
class ClarificationSet:
    """The questions worth asking about one requirement."""

    questions: List[Clarification] = field(default_factory=list)
    # What the platform would fill in if nobody answers. Kept so a
    # non-interactive run can report exactly what it assumed.
    fallbacks: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.questions)

    def __len__(self) -> int:
        return len(self.questions)

    def render(self) -> str:
        return "\n".join(
            question.render(index, len(self.questions))
            for index, question in enumerate(self.questions, start=1)
        )


def clarifications_for(
    requirement: Any, exclude: Sequence[str] = ()
) -> ClarificationSet:
    """
    The questions worth asking about a parsed requirement.

    Args:
        exclude: Fields already asked about in this conversation. A field is asked
            at most once: asking the current and then immediately interrogating
            the answer is an interrogation, not a clarification, and it does not
            terminate if the answer is the default.

    Returns an empty set when the request said everything that matters, so the
    common case asks nothing at all.
    """
    result = ClarificationSet()
    skip = set(exclude)

    circuit_type = str(getattr(requirement, "circuit_type", "") or "")
    vin = getattr(requirement, "input_voltage", None)
    vout = getattr(requirement, "output_voltage", None)
    iout = getattr(requirement, "output_current", None)

    if circuit_type == "generic":
        if "circuit_type" in skip:
            return result
        offered = ", ".join(WORKING_TOPOLOGIES)
        blocked = "; ".join(
            f"{name}: {reason}" for name, reason in UNUSABLE_TOPOLOGIES.items()
        )
        result.questions.append(
            Clarification(
                field="circuit_type",
                question="What kind of circuit is this?",
                why=(
                    "the request did not name a topology, so the design would be "
                    f"a guess. Available: {offered}. Not yet usable: {blocked}"
                ),
                default="ldo_regulator",
                choices=tuple(WORKING_TOPOLOGIES),
            )
        )
        result.fallbacks.append("circuit type assumed to be a linear regulator")
        return result

    if circuit_type in ("ldo_regulator", "buck_converter", "boost_converter"):
        if vin is None and "input_voltage" not in skip:
            result.questions.append(
                Clarification(
                    field="input_voltage",
                    question="What is the input voltage?",
                    why=(
                        "a linear regulator drops the difference between input and "
                        "output, and that difference becomes heat"
                    ),
                    default=5.0,
                    unit=" V",
                )
            )
            result.fallbacks.append("input voltage assumed to be 5 V")

        if vout is None and "output_voltage" not in skip:
            default_out = 3.3 if circuit_type == "ldo_regulator" else 5.0
            result.questions.append(
                Clarification(
                    field="output_voltage",
                    question="What is the output voltage?",
                    why="every component in the design depends on it",
                    default=default_out,
                    unit=" V",
                )
            )
            result.fallbacks.append(f"output voltage assumed to be {default_out:g} V")

        if iout is None and "output_current" not in skip:
            # A current is asked for even when it could be defaulted, because for
            # a linear regulator it decides whether the design is buildable.
            result.questions.append(
                Clarification(
                    field="output_current",
                    question="How much current does the load draw?",
                    why=(
                        "with the voltage drop it sets the heat: at 5 V in and "
                        "3.3 V out, 0.5 A is 0.85 W and 2 A is 3.4 W"
                    ),
                    default=0.5,
                    unit=" A",
                )
            )
            result.fallbacks.append("output current assumed to be 0.5 A")

    # The design decision that follows from the numbers, when they are known.
    # Only worth asking when the current came from the request rather than from
    # this conversation: having just asked for it, pressing Enter must move on.
    if (
        circuit_type == "ldo_regulator"
        and None not in (vin, vout, iout)
        and "output_current" not in skip
    ):
        drop = float(vin) - float(vout)
        dissipation = drop * float(iout)
        if drop > 0 and dissipation > THERMAL_ATTENTION_W:
            result.questions.append(
                Clarification(
                    field="output_current",
                    question=(
                        f"This linear regulator would dissipate {dissipation:.2f} W "
                        f"({drop:.2f} V dropped at {iout:g} A). What current do you "
                        f"actually need?"
                    ),
                    why=(
                        f"more than about {THERMAL_ATTENTION_W:g} W in a "
                        f"surface-mount package needs a thermal path most packages "
                        f"do not provide; about "
                        f"{THERMAL_ATTENTION_W / drop:.2f} A would stay under that. "
                        f"A smaller current, or a lower input voltage, may be the "
                        f"design you actually want. Enter the same number to keep "
                        f"it — the electrical review will then report exactly what "
                        f"it demands"
                    ),
                    default=iout,
                    unit=" A",
                )
            )

    return result


def apply_answers(requirement: Any, answers: Dict[str, Any]) -> Any:
    """
    Apply the answers to a requirement, returning the same object updated.

    Unknown fields are ignored rather than raising: the answers come from a
    person typing, and a stray key should not end the run.
    """
    for key, value in answers.items():
        if value is None or value == "":
            continue
        if key == "circuit_type":
            if str(value) in WORKING_TOPOLOGIES:
                requirement.circuit_type = str(value)
            continue
        if key not in ("input_voltage", "output_voltage", "output_current"):
            continue
        try:
            setattr(requirement, key, float(value))
        except (TypeError, ValueError):
            continue

    # Nothing was filled in before the questions were asked, so whatever is still
    # missing afterwards is exactly what nobody answered, and `fill_defaults`
    # records it.
    return requirement


def coerce_answer(question: Clarification, text: str) -> Any:
    """
    Turn typed text into an answer for a question.

    Empty input, or an unreadable one, means "take the default" — pressing Enter
    is the documented way to accept what the platform proposed, and it must never
    be an error.
    """
    text = (text or "").strip()
    if not text:
        return question.default

    if question.choices:
        lowered = text.lower()
        for choice in question.choices:
            if lowered == choice.lower() or lowered == choice.lower().replace("_", " "):
                return choice
        # A number selects by position, which is how people answer a list.
        if text.isdigit():
            index = int(text) - 1
            if 0 <= index < len(question.choices):
                return question.choices[index]
        return question.default

    # A numeric field: accept "3.3", "3.3V", "500mA".
    import re

    milliamps = re.match(r"^(\d+(?:\.\d+)?)\s*ma$", text, re.IGNORECASE)
    if milliamps:
        return float(milliamps.group(1)) / 1000.0
    match = re.match(r"^(\d+(?:\.\d+)?)\s*[a-z]*$", text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return question.default
    return question.default


def fill_defaults(requirement: Any) -> Any:
    """
    Fill anything the request left unstated, recording each value as an assumption.

    This is what happens when nobody answers: refusing to design would be worse,
    and a design that says which values it invented is more useful than no design
    at all. Each value is appended to ``requirement.constraints["assumptions"]``
    so the caller can report it.
    """
    circuit_type = str(getattr(requirement, "circuit_type", "") or "")
    constraints = getattr(requirement, "constraints", None)
    if not isinstance(constraints, dict):
        constraints = {}
        requirement.constraints = constraints
    assumptions = list(constraints.get("assumptions", []) or [])

    if circuit_type in ("ldo_regulator", "buck_converter", "boost_converter"):
        if getattr(requirement, "input_voltage", None) is None:
            requirement.input_voltage = 5.0
            assumptions.append("no input voltage was stated; assumed 5 V")
        if getattr(requirement, "output_voltage", None) is None:
            default_out = 3.3 if circuit_type == "ldo_regulator" else 5.0
            requirement.output_voltage = default_out
            assumptions.append(
                f"no output voltage was stated; assumed {default_out:g} V"
            )
        if getattr(requirement, "output_current", None) is None:
            requirement.output_current = 0.5
            assumptions.append("no current was stated; assumed 0.5 A")

    if assumptions:
        constraints["assumptions"] = assumptions
    return requirement


def clarify(
    requirement: Any,
    ask: Callable[[Clarification], str],
    max_rounds: int = 6,
) -> Any:
    """
    Ask until there is nothing left worth asking.

    One question per round, because an answer changes what is worth asking next.
    Each field is asked at most once, which bounds the loop by the number of
    fields and makes the conversation terminate even when every answer is the
    default.

    ``ask`` receives a question and returns the raw text of the answer. It is a
    callable rather than a terminal prompt so the caller owns the terminal, and so
    this can be tested without one.
    """
    asked: List[str] = []
    for _ in range(max(1, max_rounds)):
        outstanding = clarifications_for(requirement, exclude=asked)
        if not outstanding:
            break
        question = outstanding.questions[0]
        asked.append(question.field)
        answer = coerce_answer(question, ask(question))
        requirement = apply_answers(requirement, {question.field: answer})
    return requirement


__all__ = [
    "THERMAL_ATTENTION_W",
    "UNUSABLE_TOPOLOGIES",
    "WORKING_TOPOLOGIES",
    "Clarification",
    "ClarificationSet",
    "apply_answers",
    "clarifications_for",
    "clarify",
    "fill_defaults",
    "coerce_answer",
]
