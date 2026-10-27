"""
Tests for value parsing and attribute extraction.

These are the tests that matter most for part selection: a wrong number here
silently puts the wrong component in a bill of materials, and that is only
discovered after the boards arrive.
"""

import pytest

from src.components.parameters import (
    category_from_parameters,
    extract_parameters,
    format_value,
    parse_tolerance,
    parse_value,
    set_primary,
    values_match,
)


class TestParseValue:
    @pytest.mark.parametrize(
        "text,expected,unit",
        [
            ("10k", 10000.0, ""),
            ("10kΩ", 10000.0, "ohm"),
            ("4.7k", 4700.0, ""),
            ("13kΩ", 13000.0, "ohm"),
            ("220kΩ", 220000.0, "ohm"),
            ("6.2Ω", 6.2, "ohm"),
            ("0.1Ω", 0.1, "ohm"),
            ("47uF", 47e-6, "F"),
            ("1uF", 1e-6, "F"),
            ("100nF", 100e-9, "F"),
            ("27pF", 27e-12, "F"),
            ("62pF", 62e-12, "F"),
            ("2.2u", 2.2e-6, ""),
            ("10uH", 10e-6, "H"),
            ("100mW", 0.1, "W"),
            ("40V", 40.0, "V"),
            ("1.2A", 1.2, "A"),
            ("8MHz", 8e6, "Hz"),
            ("32.768kHz", 32768.0, "Hz"),
            ("0", 0.0, ""),
        ],
    )
    def test_parses_common_forms(self, text, expected, unit):
        parsed = parse_value(text)
        assert parsed is not None, text
        assert parsed.value == pytest.approx(expected), text
        assert parsed.unit == unit, text

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("4R7", 4.7),
            ("1R0", 1.0),
            ("0R05", 0.05),
            ("10R", 10.0),
        ],
    )
    def test_r_notation_means_ohms(self, text, expected):
        """4R7 is 4.7 Ω. Reading it as 4 with an unknown unit would be wrong."""
        parsed = parse_value(text)
        assert parsed is not None
        assert parsed.unit == "ohm"
        assert parsed.value == pytest.approx(expected)

    def test_milli_symbol_trailing_digit(self):
        """"1M0" is 1 MΩ, not 1 and not 1 milli."""
        parsed = parse_value("1M0")
        assert parsed is not None
        assert parsed.value == pytest.approx(1e6)

    def test_case_distinguishes_milli_from_mega(self):
        assert parse_value("1m").value == pytest.approx(1e-3)
        assert parse_value("1M").value == pytest.approx(1e6)

    def test_greek_mu_is_accepted(self):
        assert parse_value("47µF").value == pytest.approx(47e-6)
        assert parse_value("47μF").value == pytest.approx(47e-6)

    def test_tolerance_sign_is_ignored(self):
        """±1% and +/-1% must compare equal."""
        assert parse_tolerance("±1%") == pytest.approx(0.01)
        assert parse_tolerance("+/-1%") == pytest.approx(0.01)
        assert parse_tolerance("±0.1%") == pytest.approx(0.001)
        assert parse_tolerance("5%") == pytest.approx(0.05)

    def test_ppm_is_read_as_a_magnitude_not_a_tolerance(self):
        """A temperature coefficient is not a tolerance; only the number is read."""
        parsed = parse_value("±200ppm/℃")
        assert parsed is not None
        assert parsed.value == pytest.approx(200)

    @pytest.mark.parametrize("text", [None, "", "-", "N/A", "abc", "—"])
    def test_unparseable_returns_none(self, text):
        """A failed parse must be None, never 0: zero is a real component value."""
        assert parse_value(text) is None

    def test_strict_mode_rejects_part_numbers(self):
        """A query for esp32 must not be read as the number 32."""
        assert parse_value("esp32", strict=True) is None
        assert parse_value("1n4148", strict=True) is None
        # Forgiving mode is for catalogue cells, which may embed a number.
        assert parse_value("esp32") is not None

    def test_family_is_derived_from_unit(self):
        assert parse_value("10kΩ").family == "resistance"
        assert parse_value("100nF").family == "capacitance"
        assert parse_value("10uH").family == "inductance"
        assert parse_value("8MHz").family == "frequency"
        assert parse_value("40V").family is None

    def test_numbers_pass_through(self):
        assert parse_value(10000).value == 10000.0
        # bool is an int subclass; it is not a value.
        assert parse_value(True) is None


class TestValuesMatch:
    def test_exact_by_default(self):
        assert values_match(10000.0, 10000.0)
        assert not values_match(10000.0, 110000.0)
        assert not values_match(10000.0, 910000.0)

    def test_relative_tolerance(self):
        assert values_match(52.0, 50.0, tolerance=0.05)
        assert not values_match(60.0, 50.0, tolerance=0.05)

    def test_none_never_matches(self):
        assert not values_match(None, 10.0)
        assert not values_match(10.0, None)
        assert not values_match(None, None)


class TestExtractParameters:
    RESISTOR = {
        "Resistance": "10kΩ",
        "Tolerance": "±1%",
        "Power(Watts)": "100mW",
        "Temperature Coefficient": "±100ppm/℃",
        "Operating Temperature": "-55℃~+155℃",
        "Type": "Thick Film Resistor",
    }

    def test_resistor_parameters(self):
        params = extract_parameters(self.RESISTOR, "resistor")
        assert params["resistance"] == pytest.approx(10000.0)
        assert params["tolerance"] == pytest.approx(0.01)
        assert params["power"] == pytest.approx(0.1)
        assert params["type"] == "Thick Film Resistor"
        # The temperature coefficient is a string here, not a tolerance.
        assert params["temperature_coefficient"] == "±100ppm/℃"

    def test_primary_value_is_set_for_a_known_category(self):
        params = extract_parameters(self.RESISTOR, "resistor")
        assert params["primary_field"] == "resistance"
        assert params["primary"] == pytest.approx(10000.0)

    def test_primary_is_absent_without_a_category(self):
        params = extract_parameters(self.RESISTOR, "")
        assert "primary" not in params

    def test_raw_attributes_are_kept(self):
        params = extract_parameters(self.RESISTOR, "resistor")
        assert params["raw"] == self.RESISTOR

    def test_accepts_a_json_string(self):
        import json

        params = extract_parameters(json.dumps(self.RESISTOR), "resistor")
        assert params["resistance"] == pytest.approx(10000.0)

    @pytest.mark.parametrize("attributes", [None, "", "not json", {}, [], 42])
    def test_junk_attributes_yield_no_parameters(self, attributes):
        assert extract_parameters(attributes, "resistor") == {}

    def test_empty_attributes_are_not_guessed(self):
        """A row with no specifications must report nothing, not zero."""
        params = extract_parameters({"Operating Temperature": "-40℃"}, "resistor")
        assert "resistance" not in params
        assert "tolerance" not in params

    def test_capacitor_voltage_rating(self):
        params = extract_parameters(
            {"Capacitance": "100nF", "Voltage Rating": "50V", "Tolerance": "±5%"},
            "capacitor",
        )
        assert params["capacitance"] == pytest.approx(100e-9)
        assert params["voltage"] == pytest.approx(50.0)

    def test_regulator_output_voltage(self):
        params = extract_parameters(
            {"Output Voltage": "3.3V", "Output Current": "1A"}, "regulator_ldo"
        )
        assert params["output_voltage"] == pytest.approx(3.3)
        assert params["primary_field"] == "output_voltage"


class TestSetPrimary:
    def test_fills_in_a_missing_primary(self):
        params = {"resistance": 4700.0}
        set_primary(params, "resistor")
        assert params["primary"] == 4700.0

    def test_does_not_overwrite(self):
        params = {"resistance": 4700.0, "primary": 1.0, "primary_field": "x"}
        set_primary(params, "resistor")
        assert params["primary"] == 1.0

    def test_noop_for_an_unknown_category(self):
        params = {"resistance": 4700.0}
        set_primary(params, "unknown")
        assert "primary" not in params


class TestCategoryFromParameters:
    def test_uses_the_attribute_when_there_is_no_category(self):
        """67,000 catalogue rows have no category and no description."""
        assert category_from_parameters({"resistance": 1.0}) == "resistor"
        assert category_from_parameters({"capacitance": 1.0}) == "capacitor"
        assert category_from_parameters({"inductance": 1.0}) == "inductor"
        assert category_from_parameters({"zener_voltage": 5.1}) == "zener"

    def test_an_output_voltage_alone_does_not_prove_an_ldo(self):
        """
        A supervisor, a charger and a switching converter all state an output
        voltage too. Claiming "regulator_ldo" from that alone would assert
        IN/OUT/GND pins the part may not have, so the honest answer is the
        generic power-management bucket.
        """
        assert category_from_parameters({"output_voltage": 3.3}) == "power_management"

    def test_keeps_an_existing_category(self):
        assert category_from_parameters({"resistance": 1.0}, "diode") == "diode"

    def test_frequency_alone_is_not_enough_for_a_crystal(self):
        """
        An RF module also reports a frequency. Calling it a crystal would give
        it the wrong symbol, so a resonator package is required.
        """
        assert category_from_parameters({"frequency": 2.4e9}) == "unknown"
        assert (
            category_from_parameters({"frequency": 8e6}, package="HC-49S")
            == "crystal"
        )
        assert (
            category_from_parameters({"frequency": 8e6}, package="SMD3225-4P")
            == "crystal"
        )


class TestFormatValue:
    @pytest.mark.parametrize(
        "value,unit,expected",
        [
            (10000.0, "Ω", "10kΩ"),
            (100e-9, "F", "100nF"),
            (0.1, "W", "100mW"),
            (8e6, "Hz", "8MHz"),
            (4.7, "Ω", "4.7Ω"),
            (1e6, "Hz", "1MHz"),
            (0.0625, "W", "62.5mW"),
            (1e9, "Hz", "1GHz"),
            (2.2e-12, "F", "2.2pF"),
        ],
    )
    def test_engineering_notation(self, value, unit, expected):
        assert format_value(value, unit) == expected

    def test_none_is_empty(self):
        assert format_value(None) == ""
