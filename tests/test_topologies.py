"""
Every topology the platform offers must produce a design that passes.

The defect these cover: ``buck`` and ``boost`` were advertised as supported and
generated a specification with a controller that resolved to a generic IC — no
category, therefore no symbol, therefore no pins — so every connection to it was
dropped and the ERC failed with ten to twelve errors. The pipeline emitted a
board whose controller was not connected to anything.

The cause was one word. The role ``"controller"`` is ambiguous, and the resolver
leaves it as a generic chip; ``"buck_controller"`` names the topology and
resolves. A test that builds each topology is the only thing that keeps an
advertised feature from being an unbuildable one.
"""

import asyncio

import pytest

from src.core.circuit_ir import ComponentType
from src.core.component_resolver import infer_component_type, role_to_component_type
from src.llm.clarification import WORKING_TOPOLOGIES
from src.llm.integration import create_nl_pipeline


def build(prompt: str):
    pipeline = create_nl_pipeline("mock")
    return asyncio.run(pipeline.process(prompt, "test"))


PROMPTS = {
    "ldo_regulator": "5V to 3.3V LDO regulator at 0.5A",
    "buck_converter": "24V to 5V buck converter at 3A",
    "boost_converter": "5V to 12V boost converter at 1A",
    "led_driver": "5V LED circuit",
}


@pytest.mark.parametrize("circuit_type", sorted(PROMPTS))
class TestEveryTopologyBuilds:
    def test_it_produces_a_design(self, circuit_type):
        result = build(PROMPTS[circuit_type])
        assert result["circuit_ir"] is not None
        assert result["circuit_ir"].components

    def test_it_passes_the_electrical_rules(self, circuit_type):
        result = build(PROMPTS[circuit_type])
        report = result["validation"]
        assert report.valid is True, [i.message for i in report.errors[:4]]

    def test_no_component_is_left_without_pins(self, circuit_type):
        """
        A component with no pins cannot be connected to anything: every
        connection naming it is discarded, and the board is quietly unbuildable.
        """
        result = build(PROMPTS[circuit_type])
        orphaned = {
            ref: component.component_type.value
            for ref, component in result["circuit_ir"].components.items()
            if not component.pins
        }
        assert orphaned == {}, f"components with no pins: {orphaned}"

    def test_every_component_has_a_symbol(self, circuit_type):
        result = build(PROMPTS[circuit_type])
        missing = [
            ref
            for ref, component in result["circuit_ir"].components.items()
            if not component.symbol
        ]
        assert missing == [], f"components with no symbol: {missing}"

    def test_every_net_connects_something(self, circuit_type):
        result = build(PROMPTS[circuit_type])
        lonely = [
            net.name
            for net in result["circuit_ir"].nets.values()
            if len(net.connected_pins) < 2
        ]
        assert lonely == [], f"nets with fewer than two pins: {lonely}"


class TestOfferedTopologiesAreReal:
    def test_the_clarification_only_offers_what_builds(self):
        """
        The question must not offer a topology that produces a broken design.
        """
        for topology in WORKING_TOPOLOGIES:
            assert topology in PROMPTS, (
                f"{topology} is offered but not covered by a build test"
            )

    def test_every_offered_topology_is_actually_covered(self):
        for topology, prompt in PROMPTS.items():
            result = build(prompt)
            assert result["validation"].valid is True, topology


class TestControllerRoles:
    """
    The one-word cause, pinned so it cannot come back.
    """

    @pytest.mark.parametrize(
        "role,expected",
        [
            ("buck_controller", ComponentType.REGULATOR_BUCK),
            ("boost_controller", ComponentType.REGULATOR_BOOST),
            ("regulator", ComponentType.REGULATOR_LDO),
        ],
    )
    def test_a_topology_in_the_role_resolves(self, role, expected):
        assert role_to_component_type(role) is expected
        assert infer_component_type(role, expected) is expected

    def test_a_bare_controller_role_does_not(self):
        """
        "controller" on its own is genuinely ambiguous, and the platform says so
        rather than guessing a topology.
        """
        resolved = infer_component_type(
            "controller", role_to_component_type("controller"),
            value="5V", package="TO-220-5",
        )
        assert resolved not in (
            ComponentType.REGULATOR_BUCK, ComponentType.REGULATOR_BOOST
        )

    def test_the_generated_specs_name_the_topology_in_the_role(self):
        """Which is what makes the resolution above possible."""
        for prompt in ("24V to 5V buck converter at 3A", "5V to 12V boost converter at 1A"):
            spec = build(prompt)["specification"]
            roles = [component.role for component in spec.components]
            assert any("controller" in role for role in roles), roles
            assert not any(role == "controller" for role in roles), roles
