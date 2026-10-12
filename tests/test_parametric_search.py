"""
Tests for query parsing and parametric matching.

The behaviour under test is the reason this subsystem exists: ``"10k 0603"``
must not return a 110 kΩ part, and ``"4.7Ω"`` must not return an inductor whose
DC resistance happens to measure 4.7 Ω.
"""

import sqlite3

import pytest

from src.components.parametric import (
    IndexedPart,
    ParametricIndex,
    ParsedQuery,
    ValueConstraint,
    is_package_token,
    lowest_unit_price,
    parse_query,
)


class TestPackageTokens:
    @pytest.mark.parametrize(
        "token", ["0402", "0603", "0805", "1206", "2512", "sot-23", "SOT-23-5",
                  "soic-8", "QFN-32", "lqfp-48", "dip-8", "to-220", "DO-214",
                  "SMD", "THT", "usb-c"]
    )
    def test_recognised_packages(self, token):
        assert is_package_token(token), token

    @pytest.mark.parametrize(
        "token",
        [
            "1000", "1200", "10k", "100nF", "3.3V", "esp32", "1n4148",
            "resist", "toroid", "ldo", "3.3v",
        ],
    )
    def test_values_and_words_are_not_packages(self, token):
        """
        "1206" is a package but "1200" is a value; "to-220" is a package but
        "toroid" is a word. The distinction has to be explicit.
        """
        assert not is_package_token(token), token


class TestParseQuery:
    def test_value_and_package(self):
        parsed = parse_query("10k 0603")
        assert parsed.is_parametric
        assert len(parsed.values) == 1
        assert parsed.values[0].value == pytest.approx(10000.0)
        assert parsed.packages == ["0603"]
        assert parsed.text_terms == []

    def test_explicit_unit_gives_the_family(self):
        parsed = parse_query("10kΩ 0603")
        assert parsed.values[0].family == "resistance"
        assert parsed.packages == ["0603"]

    def test_bare_prefix_is_not_given_a_family(self):
        """10k is almost always a resistance, but 100n could be F or H."""
        assert parse_query("10k").values[0].family is None
        assert parse_query("100n").values[0].family is None
        assert parse_query("100nF").values[0].family == "capacitance"

    def test_voltage_rating_is_a_minimum(self):
        parsed = parse_query("50V 100nF")
        by_unit = {v.unit: v for v in parsed.values}
        assert by_unit["V"].mode == "at_least"
        assert by_unit["F"].mode == "exact"

    def test_tolerance_is_read_separately(self):
        parsed = parse_query("10k 1% 0603")
        assert parsed.tolerance == pytest.approx(0.01)
        assert parsed.values[0].value == pytest.approx(10000.0)

    def test_plus_minus_tolerance(self):
        assert parse_query("10k ±0.1%").tolerance == pytest.approx(0.001)

    def test_category_words(self):
        assert parse_query("resistor 4R7").category == "resistor"
        assert parse_query("ldo 3.3v").category == "regulator_ldo"
        assert parse_query("capacitor 100n").category == "capacitor"

    @pytest.mark.parametrize("query", ["esp32", "AMS1117", "1n4148", "stm32f103"])
    def test_part_numbers_stay_text(self, query):
        """A part number must not turn into a numeric constraint."""
        parsed = parse_query(query)
        assert not parsed.is_parametric, query
        assert parsed.text_terms == [query]

    def test_r_notation_is_a_value_not_a_part_number(self):
        parsed = parse_query("4R7")
        assert parsed.is_parametric
        assert parsed.values[0].value == pytest.approx(4.7)
        assert parsed.values[0].family == "resistance"

    def test_prefixed_trailing_digit_is_a_value(self):
        parsed = parse_query("4k7")
        assert parsed.is_parametric
        assert parsed.values[0].value == pytest.approx(4700.0)

    def test_package_argument_is_added(self):
        parsed = parse_query("10k", package="0603")
        assert parsed.packages == ["0603"]

    def test_explicit_category_argument_wins(self):
        parsed = parse_query("100nF", category="capacitor")
        assert parsed.category == "capacitor"

    def test_extra_words_become_text_terms(self):
        parsed = parse_query("10k thick film")
        assert parsed.text_terms == ["thick", "film"]

    def test_empty_query(self):
        parsed = parse_query("")
        assert not parsed.is_parametric
        assert parsed.text_terms == []
        assert parsed.summary() == "(empty query)"

    def test_summary_is_human_readable(self):
        summary = parse_query("10k 1% 0603").summary()
        assert "10k" in summary
        assert "±1%" in summary
        assert "0603" in summary


def make_part(lcsc, category, package="0603", stock=1000, **params):
    return IndexedPart(
        lcsc=lcsc,
        category=category,
        catalog_category=category,
        package=package.lower(),
        stock=stock,
        preferred=False,
        basic=False,
        unit_price=0.01,
        text=f"part{lcsc}",
        params=params,
    )


class TestParametricIndexMatching:
    def build(self, *parts) -> ParametricIndex:
        index = ParametricIndex()
        index._parts = list(parts)
        index._by_lcsc = {p.lcsc: p for p in parts}
        return index

    def test_exact_resistance_match(self):
        index = self.build(
            make_part(1, "resistor", resistance=10000.0, primary_field="resistance", primary=10000.0),
            make_part(2, "resistor", resistance=110000.0, primary_field="resistance", primary=110000.0),
            make_part(3, "resistor", resistance=910000.0, primary_field="resistance", primary=910000.0),
        )
        hits = index.find(parse_query("10k"))
        assert [h.lcsc for h in hits] == [1]

    def test_package_filter(self):
        index = self.build(
            make_part(1, "resistor", package="0603", resistance=10000.0,
                      primary_field="resistance", primary=10000.0),
            make_part(2, "resistor", package="0805", resistance=10000.0,
                      primary_field="resistance", primary=10000.0),
        )
        hits = index.find(parse_query("10k 0603"))
        assert [h.lcsc for h in hits] == [1]

    def test_a_resistance_query_does_not_match_an_inductors_dc_resistance(self):
        """
        An inductor has a "Resistance" attribute — its winding resistance. It
        must not answer a search for a resistor of that value.
        """
        index = self.build(
            make_part(1, "resistor", resistance=4.7, primary_field="resistance", primary=4.7),
            make_part(2, "inductor", resistance=4.7, inductance=4.7e-6,
                      primary_field="inductance", primary=4.7e-6),
        )
        hits = index.find(parse_query("4R7"))
        assert [h.lcsc for h in hits] == [1]

    def test_voltage_rating_is_matched_as_a_minimum(self):
        index = self.build(
            make_part(1, "capacitor", capacitance=100e-9, voltage=50.0,
                      primary_field="capacitance", primary=100e-9),
            make_part(2, "capacitor", capacitance=100e-9, voltage=16.0,
                      primary_field="capacitance", primary=100e-9),
        )
        hits = index.find(parse_query("100nF 50V"))
        assert [h.lcsc for h in hits] == [1]

    def test_the_least_over_specified_part_ranks_first(self):
        """Both 50 V and 500 V satisfy "50 V"; the 50 V part is the better answer."""
        index = self.build(
            make_part(1, "capacitor", capacitance=100e-9, voltage=500.0,
                      primary_field="capacitance", primary=100e-9),
            make_part(2, "capacitor", capacitance=100e-9, voltage=50.0,
                      primary_field="capacitance", primary=100e-9),
        )
        hits = index.find(parse_query("100nF 50V"))
        assert [h.lcsc for h in hits] == [2, 1]

    def test_regulator_output_voltage_is_an_identity_not_a_rating(self):
        """A 5 V regulator must not satisfy a search for 3.3 V."""
        index = self.build(
            make_part(1, "regulator_ldo", output_voltage=3.3, supply_voltage=15.0,
                      primary_field="output_voltage", primary=3.3),
            make_part(2, "regulator_ldo", output_voltage=5.0, supply_voltage=15.0,
                      primary_field="output_voltage", primary=5.0),
        )
        hits = index.find(parse_query("3.3v", category="regulator_ldo"))
        assert [h.lcsc for h in hits] == [1]

    def test_tolerance_filter_excludes_looser_parts(self):
        index = self.build(
            make_part(1, "resistor", resistance=10000.0, tolerance=0.01,
                      primary_field="resistance", primary=10000.0),
            make_part(2, "resistor", resistance=10000.0, tolerance=0.05,
                      primary_field="resistance", primary=10000.0),
            make_part(3, "resistor", resistance=10000.0,
                      primary_field="resistance", primary=10000.0),
        )
        hits = index.find(parse_query("10k 1%"))
        # The part with no stated tolerance is excluded: it cannot be shown to
        # meet the requirement.
        assert [h.lcsc for h in hits] == [1]

    def test_min_stock_filter(self):
        index = self.build(
            make_part(1, "resistor", stock=100, resistance=10000.0,
                      primary_field="resistance", primary=10000.0),
            make_part(2, "resistor", stock=5000, resistance=10000.0,
                      primary_field="resistance", primary=10000.0),
        )
        hits = index.find(parse_query("10k", min_stock=1000))
        assert [h.lcsc for h in hits] == [2]

    def test_category_filter(self):
        index = self.build(
            make_part(1, "resistor", resistance=10000.0,
                      primary_field="resistance", primary=10000.0),
            make_part(2, "inductor", inductance=10000.0, resistance=10000.0,
                      primary_field="inductance", primary=10000.0),
        )
        hits = index.find(parse_query("10k", category="resistor"))
        assert [h.lcsc for h in hits] == [1]

    def test_text_terms_narrow_the_results(self):
        index = self.build(
            IndexedPart(
                lcsc=1, category="resistor", catalog_category="Resistors",
                package="0603", stock=10, preferred=False, basic=False,
                unit_price=0.01, text="thick film resistor",
                params={"resistance": 10000.0, "primary_field": "resistance",
                        "primary": 10000.0},
            ),
            IndexedPart(
                lcsc=2, category="resistor", catalog_category="Resistors",
                package="0603", stock=10, preferred=False, basic=False,
                unit_price=0.01, text="thin film resistor",
                params={"resistance": 10000.0, "primary_field": "resistance",
                        "primary": 10000.0},
            ),
        )
        hits = index.find(parse_query("10k thick"))
        assert [h.lcsc for h in hits] == [1]

    def test_preferred_parts_rank_first(self):
        index = self.build(
            make_part(1, "resistor", stock=100000, resistance=10000.0,
                      primary_field="resistance", primary=10000.0),
            IndexedPart(
                lcsc=2, category="resistor", catalog_category="Resistors",
                package="0603", stock=10, preferred=True, basic=False,
                unit_price=0.01, text="x",
                params={"resistance": 10000.0, "primary_field": "resistance",
                        "primary": 10000.0},
            ),
        )
        hits = index.find(parse_query("10k"))
        assert [h.lcsc for h in hits] == [2, 1]

    def test_limit_is_respected(self):
        index = self.build(
            *[
                make_part(i, "resistor", resistance=10000.0,
                          primary_field="resistance", primary=10000.0)
                for i in range(1, 11)
            ]
        )
        assert len(index.find(parse_query("10k", limit=3))) == 3


class TestLowestUnitPrice:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("1-49:0.0887,50-149:0.0707,6000-:0.0451", 0.0451),
            ("1-49:0.5", 0.5),
            ("", 0.0),
            (None, 0.0),
            (0.25, 0.25),
            ("garbage", 0.0),
        ],
    )
    def test_parses_tiers(self, text, expected):
        assert lowest_unit_price(text) == pytest.approx(expected)

    def test_falls_back_to_a_scan_when_the_last_tier_is_broken(self):
        assert lowest_unit_price("1-49:0.5,50-:oops") == pytest.approx(0.5)


class TestIndexBuildFromSqlite:
    """The index is built from a real SQLite table, so test against one."""

    @pytest.fixture()
    def catalog(self, tmp_path):
        path = tmp_path / "mini.sqlite3"
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE jlc_components (
                lcsc INTEGER PRIMARY KEY,
                category TEXT, package TEXT, stock INTEGER,
                preferred INTEGER, basic INTEGER, mfr TEXT, description TEXT,
                attributes TEXT, price TEXT
            )
            """
        )
        rows = [
            # A resistor with no category and no description: the attributes are
            # the only thing that identifies it.
            (1, "", "0603", 500000, 0, 0, "RC0603FR-0710KL", "",
             '{"Resistance":"10kΩ","Tolerance":"±1%","Power(Watts)":"100mW"}',
             "1-49:0.01,5000-:0.002"),
            (2, "Resistors", "0603", 1000, 1, 0, "OTHER10K", "10kΩ resistor",
             '{"Resistance":"10kΩ","Tolerance":"±5%"}', "1-49:0.02"),
            (3, "Resistors", "0805", 10000, 0, 0, "R0805-110K", "110kΩ resistor",
             '{"Resistance":"110kΩ","Tolerance":"±1%"}', "1-49:0.03"),
            # Not indexed: no quantitative attribute.
            (4, "Capacitors", "0805", 100, 0, 0, "SOMECAP", "a capacitor", "{}", ""),
            (5, "Capacitors", "0603", 9000, 0, 0, "CAP100N", "100nF 50V",
             '{"Capacitance":"100nF","Voltage Rating":"50V","Tolerance":"±10%"}',
             "1-49:0.05"),
        ]
        conn.executemany(
            "INSERT INTO jlc_components VALUES (?,?,?,?,?,?,?,?,?,?)", rows
        )
        conn.commit()
        conn.close()
        return path

    def categorize(self, catalog_category, description, package):
        if catalog_category == "Resistors":
            return "resistor"
        if catalog_category == "Capacitors":
            return "capacitor"
        from src.components.parameters import category_from_parameters

        return "unknown"

    def build(self, catalog):
        conn = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True)
        def categorize(cat, desc, pkg):
            result = self.categorize(cat, desc, pkg)
            return result
        return ParametricIndex.build(conn, categorize, source=str(catalog))

    def test_only_rows_with_specifications_are_indexed(self, catalog):
        index = self.build(catalog)
        assert len(index) == 4  # the bare capacitor is excluded
        assert index.get(4) is None

    def test_uncategorised_row_is_classified_from_its_attributes(self, catalog):
        index = self.build(catalog)
        part = index.get(1)
        assert part is not None
        assert part.category == "resistor"
        assert part.params["primary"] == pytest.approx(10000.0)
        assert part.params["primary_field"] == "resistance"

    def test_search_over_the_built_index(self, catalog):
        index = self.build(catalog)
        hits = index.find(parse_query("10k 0603"))
        assert sorted(h.lcsc for h in hits) == [1, 2]

    def test_the_wrong_value_is_not_returned(self, catalog):
        """The whole point: 110k must not appear in a search for 10k."""
        index = self.build(catalog)
        hits = index.find(parse_query("10k"))
        assert 3 not in [h.lcsc for h in hits]

    def test_price_is_read_from_the_tier_string(self, catalog):
        index = self.build(catalog)
        assert index.get(1).unit_price == pytest.approx(0.002)

    def test_preferred_flag_is_read_from_its_own_column(self, catalog):
        """
        The catalogue's `preferred` column carries the flag. It must not be
        inferred from `library_type`, which holds "base"/"expand".
        """
        index = self.build(catalog)
        assert index.get(2).preferred is True
        assert index.get(1).preferred is False
