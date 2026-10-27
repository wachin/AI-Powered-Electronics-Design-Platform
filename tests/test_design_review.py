"""
Tests for the electrical design review.

The defect these cover: the generator computed "Power dissipation: 1.70W" and
then emitted "Check thermal dissipation for high current" — it knew the number
and refused to use it. 1.7 W in a SOT-223 needs a thermal path better than about
73 °C/W, which is a real constraint, not a footnote.
"""

import json

import pytest

from src.core.design_review import (
    FAIL,
    PASS,
    UNKNOWN,
    WARN,
    DesignReview,
    Finding,
    forward_voltage_for_colour,
    review_capacitor_voltage,
    review_circuit,
    review_dropout,
    review_led_operating_point,
    review_linear_regulator_thermal,
    review_resistor_power,
)
from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType


class TestFinding:
    def test_a_finding_renders_its_severity(self):
        finding = Finding("R", FAIL, "U1", "message")
        assert finding.render().startswith("[FAIL] U1")

    def test_a_finding_is_a_problem_when_it_is_a_failure_or_a_warning(self):
        assert Finding("R", FAIL, "s", "m").is_problem
        assert Finding("R", WARN, "s", "m").is_problem
        assert not Finding("R", PASS, "s", "m").is_problem

    def test_the_detail_is_serialisable(self):
        finding = Finding("R", PASS, "s", "m", {"a": 1, "b": [1.0, 2.0]})
        json.dumps(finding.to_dict())

    def test_a_review_sorts_worst_first(self):
        review = DesignReview(
            findings=[
                Finding("A", PASS, "a", ""),
                Finding("B", FAIL, "b", ""),
                Finding("C", WARN, "c", ""),
                Finding("D", UNKNOWN, "d", ""),
            ]
        )
        assert [f.severity for f in review.sorted_findings()] == [
            FAIL, WARN, UNKNOWN, PASS
        ]

    def test_a_review_passes_when_nothing_failed(self):
        assert DesignReview(findings=[Finding("A", WARN, "a", "")]).passed
        assert not DesignReview(findings=[Finding("A", FAIL, "a", "")]).passed

    def test_the_summary_counts_each_severity(self):
        review = DesignReview(
            findings=[
                Finding("A", FAIL, "a", ""),
                Finding("B", WARN, "b", ""),
                Finding("C", UNKNOWN, "c", ""),
            ]
        )
        assert review.summary() == "1 failure(s), 1 warning(s), 1 unchecked"
        payload = review.to_dict()
        assert payload["failures"] == 1
        assert payload["passed"] is False


class TestLinearRegulatorThermal:
    """
    The dissipation is exact, so it is asserted exactly. The thermal resistance
    is not knowable, so it is asserted as an *answer*, never as an input.
    """

    def test_the_reference_design_dissipation(self):
        """5 V to 3.3 V at 1 A: 1.7 V dropped, 1.7 W burned."""
        finding = review_linear_regulator_thermal(
            "U1", vin_max=5.0, vout=3.3, iout=1.0, tj_max=150.0
        )
        assert finding.detail["voltage_drop"] == pytest.approx(1.7)
        assert finding.detail["power_w"] == pytest.approx(1.7)

    def test_the_required_thermal_path_is_reported(self):
        finding = review_linear_regulator_thermal(
            "U1", vin_max=5.0, vout=3.3, iout=1.0, tj_max=150.0, ambient_c=25.0
        )
        # (150 - 25) / 1.7 W
        assert finding.detail["required_theta_ja"] == pytest.approx(73.5, abs=0.5)
        assert finding.severity == WARN
        assert "°C/W" in finding.message

    def test_the_quiescent_current_is_included(self):
        with_iq = review_linear_regulator_thermal(
            "U1", vin_max=5.0, vout=3.3, iout=1.0, quiescent_current=0.005, tj_max=150.0
        )
        assert with_iq.detail["power_w"] == pytest.approx(1.725)

    def test_a_low_dissipation_passes_confidently(self):
        finding = review_linear_regulator_thermal(
            "U1", vin_max=5.0, vout=3.3, iout=0.05, tj_max=150.0
        )
        assert finding.severity == PASS

    def test_an_impossible_thermal_requirement_fails(self):
        """No package sheds 5 W without a heatsink."""
        finding = review_linear_regulator_thermal(
            "U1", vin_max=12.0, vout=3.3, iout=1.0, tj_max=125.0
        )
        assert finding.severity == FAIL
        assert "switching regulator" in finding.message

    def test_a_missing_junction_limit_is_reported_not_assumed(self):
        """
        Publishing an invented theta_JA would be the looks-real-but-is-not
        failure this project keeps finding in its own data.
        """
        finding = review_linear_regulator_thermal(
            "U1", vin_max=5.0, vout=3.3, iout=1.0, tj_max=None
        )
        assert finding.severity == UNKNOWN
        assert "not in the catalog" in finding.message
        assert "required_theta_ja" not in finding.detail
        assert finding.detail["required_theta_ja_by_limit"]["150"] == pytest.approx(73.5, abs=0.5)
        assert finding.detail["required_theta_ja_by_limit"]["125"] == pytest.approx(58.8, abs=0.5)

    def test_the_ambient_limit_is_reported_for_several_thermal_paths(self):
        finding = review_linear_regulator_thermal(
            "U1", vin_max=5.0, vout=3.3, iout=1.0, tj_max=150.0, ambient_c=25.0
        )
        limits = finding.detail["max_ambient_c_by_theta_ja"]
        # At 100 °C/W the junction would pass 150 °C well below room temperature.
        assert limits["100"] == pytest.approx(150.0 - 1.7 * 100, abs=0.1)
        assert limits["50"] > 25

    def test_no_dropout_means_no_dissipation(self):
        finding = review_linear_regulator_thermal(
            "U1", vin_max=3.3, vout=3.3, iout=1.0, tj_max=150.0
        )
        assert finding.severity == PASS
        assert finding.detail["power_w"] == pytest.approx(0.0)

    def test_a_hotter_ambient_worsens_the_requirement(self):
        cool = review_linear_regulator_thermal(
            "U1", vin_max=5.0, vout=3.3, iout=1.0, tj_max=125.0, ambient_c=25.0
        )
        hot = review_linear_regulator_thermal(
            "U1", vin_max=5.0, vout=3.3, iout=1.0, tj_max=125.0, ambient_c=60.0
        )
        assert hot.detail["required_theta_ja"] < cool.detail["required_theta_ja"]


class TestDropout:
    def test_scales_the_catalogue_figure_to_the_design_current(self):
        finding = review_dropout(
            "U1", vin_min=5.0, vout=3.3, dropout_at_rated=1.3, rated_current=1.0, iout=0.5
        )
        assert finding.detail["dropout_v"] == pytest.approx(0.65)
        assert finding.detail["margin_v"] == pytest.approx(1.05)
        assert finding.severity == PASS
        assert "scaled from" in finding.detail["dropout_basis"]

    def test_insufficient_headroom_fails(self):
        """3.3 V out from a 4.0 V input with a 1.3 V dropout cannot regulate."""
        finding = review_dropout(
            "U1", vin_min=4.0, vout=3.3, dropout_at_rated=1.3, rated_current=1.0, iout=1.0
        )
        assert finding.severity == FAIL
        assert finding.detail["margin_v"] == pytest.approx(-0.6)

    def test_a_thin_margin_warns(self):
        # 1.70 V of headroom, 1.55 V needed: 0.15 V is inside the tolerance of
        # most regulators, let alone their temperature drift.
        finding = review_dropout(
            "U1", vin_min=5.0, vout=3.3, dropout_at_rated=1.55, rated_current=1.0, iout=1.0
        )
        assert finding.severity == WARN
        assert finding.detail["margin_v"] == pytest.approx(0.15)

    def test_exactly_the_warn_threshold_still_passes(self):
        finding = review_dropout(
            "U1", vin_min=5.0, vout=3.3, dropout_at_rated=1.5, rated_current=1.0, iout=1.0
        )
        assert finding.severity == PASS
        assert finding.detail["margin_v"] == pytest.approx(0.2)

    def test_no_dropout_figure_is_unchecked_not_fine(self):
        finding = review_dropout(
            "U1", vin_min=5.0, vout=3.3, dropout_at_rated=None, rated_current=None, iout=1.0
        )
        assert finding.severity == UNKNOWN
        assert "datasheet" in finding.message

    def test_an_unscaled_figure_is_labelled_as_quoted(self):
        finding = review_dropout(
            "U1", vin_min=5.0, vout=3.3, dropout_at_rated=1.2, rated_current=None, iout=1.0
        )
        assert finding.detail["dropout_basis"] == "quoted"
        assert finding.detail["dropout_v"] == pytest.approx(1.2)


class TestResistorPower:
    def test_computes_i_squared_r(self):
        finding = review_resistor_power(
            "R1", resistance=330.0, current=0.0030303, rated_power=0.125
        )
        assert finding.detail["power_w"] == pytest.approx(0.00303, abs=1e-5)
        assert finding.severity == PASS

    def test_over_half_its_rating_warns(self):
        finding = review_resistor_power(
            "R1", resistance=100.0, current=0.03, rated_power=0.1
        )
        # 0.03^2 * 100 = 0.09 W in a 0.1 W part
        assert finding.severity == WARN
        assert "more than half" in finding.message

    def test_over_its_rating_fails(self):
        finding = review_resistor_power(
            "R1", resistance=100.0, current=0.05, rated_power=0.1
        )
        # 0.25 W in a 0.1 W part
        assert finding.severity == FAIL

    def test_a_missing_rating_states_what_to_check(self):
        finding = review_resistor_power(
            "R1", resistance=330.0, current=0.01, rated_power=None
        )
        assert finding.severity == UNKNOWN
        # 0.033 W dissipated, so at least 0.066 W rated
        assert "0.066" in finding.message or "66" in finding.message

    def test_a_missing_resistance_is_unchecked(self):
        finding = review_resistor_power(
            "R1", resistance=None, current=0.01, rated_power=0.125
        )
        assert finding.severity == UNKNOWN


class TestCapacitorVoltage:
    def test_comfortable_derating_passes(self):
        finding = review_capacitor_voltage("C1", applied_voltage=5.0, rated_voltage=25.0)
        assert finding.severity == PASS
        assert "20%" in finding.message

    def test_over_80_percent_warns(self):
        finding = review_capacitor_voltage("C1", applied_voltage=21.0, rated_voltage=25.0)
        assert finding.severity == WARN

    def test_exactly_80_percent_is_within_the_derating_rule(self):
        finding = review_capacitor_voltage("C1", applied_voltage=20.0, rated_voltage=25.0)
        assert finding.severity == PASS
        assert "80%" in finding.message

    def test_over_the_rating_fails(self):
        finding = review_capacitor_voltage("C1", applied_voltage=30.0, rated_voltage=25.0)
        assert finding.severity == FAIL

    def test_an_exact_rating_is_a_warning_not_a_pass(self):
        finding = review_capacitor_voltage("C1", applied_voltage=25.0, rated_voltage=25.0)
        assert finding.severity == WARN

    def test_a_missing_rating_states_the_minimum(self):
        finding = review_capacitor_voltage("C1", applied_voltage=5.0, rated_voltage=None)
        assert finding.severity == UNKNOWN
        assert "6.2" in finding.message


class TestLedOperatingPoint:
    def test_the_current_is_a_range_because_vf_is_a_range(self):
        """
        A green LED that drops 2.0 V and one that drops 2.6 V pass very
        different currents through the same resistor, and both are "green".
        """
        finding = review_led_operating_point(
            "D1", supply_voltage=3.3, series_resistance=330.0, colour="Green"
        )
        low, high = finding.detail["current_ma"]
        assert low == pytest.approx((3.3 - 2.6) / 330 * 1000, abs=0.1)
        assert high == pytest.approx((3.3 - 2.0) / 330 * 1000, abs=0.1)
        assert finding.severity == PASS

    def test_a_dim_led_warns(self):
        finding = review_led_operating_point(
            "D1", supply_voltage=3.3, series_resistance=100000.0, colour="Red"
        )
        assert finding.severity == WARN
        assert "dim" in finding.message

    def test_an_overdriven_led_warns(self):
        finding = review_led_operating_point(
            "D1", supply_voltage=5.0, series_resistance=47.0, colour="Red"
        )
        assert finding.severity == WARN
        assert "20 mA" in finding.message

    def test_a_supply_below_the_forward_voltage_fails(self):
        finding = review_led_operating_point(
            "D1", supply_voltage=1.5, series_resistance=330.0, colour="Blue"
        )
        assert finding.severity == FAIL
        assert "will not light" in finding.message

    def test_an_unknown_colour_is_unchecked(self):
        finding = review_led_operating_point(
            "D1", supply_voltage=3.3, series_resistance=330.0, colour="chartreuse"
        )
        assert finding.severity == UNKNOWN

    def test_no_resistor_is_unchecked(self):
        finding = review_led_operating_point(
            "D1", supply_voltage=3.3, series_resistance=None, colour="Green"
        )
        assert finding.severity == UNKNOWN

    @pytest.mark.parametrize(
        "colour,low,high",
        [
            ("red", 1.8, 2.2),
            ("green", 2.0, 2.6),
            ("blue", 2.8, 3.4),
            ("white", 2.8, 3.4),
            ("IR", 1.1, 1.5),
        ],
    )
    def test_forward_voltage_by_colour(self, colour, low, high):
        assert forward_voltage_for_colour(colour) == (low, high)

    def test_colour_phrases_are_recognised(self):
        assert forward_voltage_for_colour("Yellow Green") is not None
        assert forward_voltage_for_colour("Emerald Green") == (2.6, 3.0)
        assert forward_voltage_for_colour("") is None


# ---------------------------------------------------------------------------
# Reviewing a whole circuit
# ---------------------------------------------------------------------------


def ldo_circuit() -> CircuitIR:
    """
    A 5 V to 3.3 V regulator with an LED indicator, wired as the template does.

    Note that the pins must carry their net names: the PCB generator and this
    review both read ``Pin.connected_net``, while ERC reads the net's pin list.
    """
    circuit = CircuitIR(name="ldo", description="test")

    u1 = Component(
        ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:AMS1117-3.3", mpn="AMS1117-3.3", package="SOT-223",
    )
    for number, name in (("1", "GND"), ("2", "VO"), ("3", "VI")):
        u1.add_pin(number, name, PinType.POWER_IN)
    circuit.add_component(u1)

    c1 = Component(
        ref="C1", value="10uF", component_type=ComponentType.CAPACITOR,
        footprint="Capacitor_SMD:C_0805_2012Metric", symbol="Device:C", package="0805",
    )
    c1.add_pin("1", "1")
    c1.add_pin("2", "2")
    circuit.add_component(c1)

    r1 = Component(
        ref="R1", value="330", component_type=ComponentType.RESISTOR,
        footprint="Resistor_SMD:R_0805_2012Metric", symbol="Device:R", package="0805",
    )
    r1.add_pin("1", "1")
    r1.add_pin("2", "2")
    circuit.add_component(r1)

    d1 = Component(
        ref="D1", value="Green", component_type=ComponentType.LED,
        footprint="LED_SMD:LED_0805_2012Metric", symbol="Device:LED", package="0805",
    )
    d1.add_pin("1", "K")
    d1.add_pin("2", "A")
    circuit.add_component(d1)

    for ref, pin, net_name in (
        ("U1", "3", "VIN"),
        ("C1", "1", "VIN"),
        ("U1", "2", "VOUT"),
        ("R1", "1", "VOUT"),
        ("R1", "2", "LED_A"),
        ("D1", "2", "LED_A"),
        ("U1", "1", "GND"),
        ("C1", "2", "GND"),
        ("D1", "1", "GND"),
    ):
        circuit.components[ref].get_pin(pin).connected_net = net_name
        circuit.nets.setdefault(net_name, __import__("src.core.circuit_ir", fromlist=["Net"]).Net(name=net_name))
        circuit.nets[net_name].connect(ref, pin)

    circuit.get_or_create_net("VIN", is_power=True, voltage=5.0)
    circuit.get_or_create_net("VOUT", is_power=True, voltage=3.3)
    circuit.get_or_create_net("GND", is_power=True, voltage=0.0)
    return circuit


REQUIREMENTS = {"input_voltage": 5.0, "output_voltage": 3.3, "output_current": 1.0}


class TestReviewCircuit:
    def test_reviews_every_kind_of_component(self):
        review = review_circuit(ldo_circuit(), None, REQUIREMENTS)
        rules = {f.rule_id for f in review.findings}
        assert "REVIEW_THERMAL" in rules
        assert "REVIEW_DROPOUT" in rules
        assert "REVIEW_CAPACITOR_VOLTAGE" in rules
        assert "REVIEW_RESISTOR_POWER" in rules
        assert "REVIEW_LED_CURRENT" in rules

    def test_works_with_no_catalogue_at_all(self):
        """Every check must degrade to UNKNOWN, not crash."""
        review = review_circuit(ldo_circuit(), None, REQUIREMENTS)
        assert review.findings
        assert all(f.severity in (PASS, WARN, FAIL, UNKNOWN) for f in review.findings)
        json.dumps(review.to_dict())

    def test_the_led_current_follows_the_wired_series_resistor(self):
        review = review_circuit(ldo_circuit(), None, REQUIREMENTS)
        led = next(f for f in review.findings if f.rule_id == "REVIEW_LED_CURRENT")
        assert led.detail["supply_v"] == pytest.approx(3.3)
        assert led.detail["resistance_ohm"] == pytest.approx(330.0)

    def test_the_capacitor_sees_the_voltage_of_its_own_net(self):
        review = review_circuit(ldo_circuit(), None, REQUIREMENTS)
        cap = next(f for f in review.findings if f.rule_id == "REVIEW_CAPACITOR_VOLTAGE")
        assert cap.detail["applied_v"] == pytest.approx(5.0)

    def test_the_assumptions_are_stated(self):
        review = review_circuit(ldo_circuit(), None, REQUIREMENTS, ambient_c=40.0)
        text = " ".join(review.assumptions)
        assert "40" in text
        assert "thermal resistance is not assumed" in text

    def test_an_empty_circuit_reviews_to_nothing(self):
        review = review_circuit(CircuitIR(name="empty", description=""), None, REQUIREMENTS)
        assert review.findings == []
        assert review.passed

    def test_a_circuit_without_requirements_does_not_review_the_regulator(self):
        """Without an input voltage there is nothing to compute the dissipation from."""
        review = review_circuit(ldo_circuit(), None, {})
        assert not any(f.rule_id == "REVIEW_THERMAL" for f in review.findings)


class TestReviewAgainstTheRealCatalog:
    """
    Against the downloaded catalogue, the review has real ratings to work with.
    """

    @pytest.fixture()
    def real_db(self):

        from conftest import real_catalog_path

        catalog = real_catalog_path()
        if catalog is None:
            pytest.skip("no component catalog found (run: make catalog)")
        from src.components.database import ComponentDatabase

        return ComponentDatabase(catalog)

    def test_the_reference_design_produces_real_numbers(self, real_db):
        """
        5 V to 3.3 V at 1 A: the dropout and the capacitor and resistor ratings
        all come from the catalogue, so most findings are pass or warn rather
        than unchecked.
        """
        review = review_circuit(ldo_circuit(), real_db, REQUIREMENTS)
        checked = [f for f in review.findings if f.severity != UNKNOWN]
        assert len(checked) >= 4, [f.render() for f in review.findings]

    def test_the_dropout_comes_from_the_catalogue(self, real_db):
        review = review_circuit(ldo_circuit(), real_db, REQUIREMENTS)
        dropout = next(f for f in review.findings if f.rule_id == "REVIEW_DROPOUT")
        assert dropout.detail["dropout_v"] > 0
        assert dropout.detail["margin_v"] > 0

    def test_ratings_taken_from_another_part_are_disclosed(self, real_db):
        """
        The built-in list's parts have no datasheet data, so the review uses the
        catalogue part the purchase list would order. That substitution must be
        visible, or the reader cannot tell what was checked.
        """
        review = review_circuit(ldo_circuit(), real_db, REQUIREMENTS)
        substitutions = [a for a in review.assumptions if "ratings taken from" in a]
        assert substitutions, review.assumptions
        assert any("C1" in a for a in substitutions)
