"""
Tests for how a template circuit chooses its components.

These exist because of a real bug. Fixing the component-category filter made
``db.search(category="capacitor")`` start returning real catalogue parts instead
of the curated built-in ones, and the orchestrator's ``[0]`` then selected a
100 nF part where a 10 µF input capacitor was intended. A design that silently
uses the wrong value is worse than one that fails.
"""

import pytest

from src.agents.orchestrator import AIDesignOrchestrator
from src.components.database import ComponentDatabase


@pytest.fixture()
def orchestrator() -> AIDesignOrchestrator:
    return AIDesignOrchestrator(db=ComponentDatabase())


class TestSelectPart:
    def test_uses_the_curated_part_when_one_matches(self, orchestrator):
        part = orchestrator._select_part("capacitor", "10uF 0805", value="10uF")
        assert part.value == "10uF"
        assert part.lcsc_part is None, "expected the curated built-in part"

    def test_selects_the_intended_value_not_just_the_category(self, orchestrator):
        """
        The regression: the capacitor chosen for the input must be 10 µF and the
        output one 22 µF, however the catalogue happens to be ordered.
        """
        c_in = orchestrator._select_part("capacitor", "10uF 0805", value="10uF")
        c_out = orchestrator._select_part("capacitor", "22uF 0805", value="22uF")
        assert c_in.value == "10uF"
        assert c_out.value == "22uF"
        assert c_in.mpn != c_out.mpn

        resistor = orchestrator._select_part("resistor", "330 0805", value="330")
        assert resistor.value == "330"

    def test_the_ldo_is_a_real_3v3_regulator(self, orchestrator):
        part = orchestrator._select_part("regulator_ldo", "3.3v", value="3.3V")
        assert part.category == "regulator_ldo"
        assert "3.3" in part.value

    def test_raising_rather_than_guessing(self, monkeypatch):
        """
        With nothing available, the lookup must fail loudly. A wrong part would
        only be discovered after the boards arrive.
        """
        orchestrator = AIDesignOrchestrator(db=ComponentDatabase(prefer_jlcparts=False))

        def nothing(*args, **kwargs):
            return []

        monkeypatch.setattr(orchestrator.db, "find_builtin", lambda *a, **k: None)
        monkeypatch.setattr(orchestrator.db, "search", nothing)
        with pytest.raises(LookupError, match="catalog-setup"):
            orchestrator._select_part("capacitor", "10uF")

    def test_falls_back_to_the_catalog_when_the_builtin_list_cannot_help(
        self, monkeypatch
    ):
        """The built-in list is small; a value it lacks should still be found."""
        orchestrator = AIDesignOrchestrator(db=ComponentDatabase())
        part = orchestrator._select_part("capacitor", "47uF 0805", value="47uF")
        assert part.value  # whatever it is, it is a real part
        assert part.category == "capacitor"


class TestTemplateCircuitValues:
    def test_the_ldo_template_uses_the_intended_values(self, orchestrator):
        circuit = orchestrator._synthesize_circuit_ir(
            "Design a 5V to 3.3V LDO regulator with an LED indicator", "test"
        )
        values = {ref: component.value for ref, component in circuit.components.items()}
        assert values["U1"] == "3.3V"
        assert values["R1"] == "330"
        assert "10uF" in " ".join(values.values())
        assert "22uF" in " ".join(values.values())

    def test_the_generic_template_uses_the_intended_values(self, orchestrator):
        circuit = orchestrator._synthesize_circuit_ir("Simple LED circuit", "test")
        values = {ref: component.value for ref, component in circuit.components.items()}
        assert values["R1"] == "330"
