"""
Integration tests for catalogue search and substitution.

These run against a small SQLite file with the same schema as the real catalog,
so they exercise the actual SQL and row conversion without requiring the 145 MB
download in CI.
"""

import sqlite3
from pathlib import Path

import pytest

from src.components.jlcparts import JLCPartsDatabase, Substitute


SCHEMA = """
CREATE TABLE jlc_components (
    lcsc INTEGER PRIMARY KEY,
    fetched_at INTEGER DEFAULT 0,
    present INTEGER DEFAULT 1,
    sync_seen INTEGER DEFAULT 0,
    category TEXT DEFAULT '',
    subcategory TEXT DEFAULT '',
    mfr TEXT DEFAULT '',
    package TEXT DEFAULT '',
    joints INTEGER DEFAULT 0,
    manufacturer TEXT DEFAULT '',
    library_type TEXT DEFAULT 'expand',
    preferred INTEGER DEFAULT 0,
    last_on_stock INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    datasheet TEXT DEFAULT '',
    stock INTEGER DEFAULT 0,
    price TEXT DEFAULT '',
    attributes TEXT DEFAULT '{}',
    rohs INTEGER DEFAULT 1,
    eccn TEXT DEFAULT '',
    assembly INTEGER DEFAULT 1,
    assembly_process TEXT DEFAULT '',
    assembly_mode TEXT DEFAULT '',
    website_component_id TEXT DEFAULT '',
    attrition TEXT DEFAULT '',
    basic INTEGER DEFAULT 0
)
"""

ROWS = [
    # (lcsc, category, mfr, package, description, attributes, stock, preferred,
    #  basic, price, manufacturer)
    (
        1001, "", "RC0603FR-0710KL", "0603", "",
        '{"Resistance":"10kΩ","Tolerance":"±1%","Power(Watts)":"100mW"}',
        500000, 0, 0, "1-49:0.01,5000-:0.002", "Yageo",
    ),
    (
        1002, "Resistors", "GENERIC10K5", "0603", "10kΩ chip resistor",
        '{"Resistance":"10kΩ","Tolerance":"±5%","Power(Watts)":"100mW"}',
        2000, 1, 0, "1-49:0.02", "Generic",
    ),
    (
        1003, "Resistors", "R0805-110K", "0805", "110kΩ chip resistor",
        '{"Resistance":"110kΩ","Tolerance":"±1%"}',
        50000, 0, 0, "1-49:0.03", "Generic",
    ),
    # A 10 kΩ resistor in a 0402 package with a poor stock level.
    (
        1004, "Resistors", "TINY10K", "0402", "10kΩ 0402",
        '{"Resistance":"10kΩ","Tolerance":"±1%"}',
        10, 0, 0, "1-49:0.05", "Generic",
    ),
    # Capacitors: 100 nF at two voltage ratings.
    (
        2001, "Capacitors", "C0805-100N-50V", "0805", "100nF 50V X7R",
        '{"Capacitance":"100nF","Voltage Rating":"50V","Tolerance":"±10%"}',
        8000, 1, 0, "1-49:0.03", "Generic",
    ),
    (
        2002, "Capacitors", "C0805-100N-500V", "0805", "100nF 500V X7R",
        '{"Capacitance":"100nF","Voltage Rating":"500V","Tolerance":"±10%"}',
        9000, 1, 0, "1-49:0.20", "Generic",
    ),
    (
        2003, "Capacitors", "C0805-LOW-VOLT", "0805", "100nF 16V X7R",
        '{"Capacitance":"100nF","Voltage Rating":"16V"}',
        7000, 0, 0, "1-49:0.01", "Generic",
    ),
    # An inductor with a 4.7 Ω winding: must never answer a 4.7 Ω search.
    (
        3001, "Inductors, Coils, Chokes", "L-4U7", "0603", "4.7uH inductor",
        '{"Inductance":"4.7uH","Resistance":"4.7Ω","Tolerance":"±20%"}',
        40000, 0, 0, "1-49:0.06", "Generic",
    ),
    # A 4.7 Ω resistor.
    (
        3002, "Resistors", "R-4R7", "0603", "4.7Ω resistor",
        '{"Resistance":"4.7Ω","Tolerance":"±5%"}',
        30000, 0, 0, "1-49:0.01", "Generic",
    ),
    # An LDO at 3.3 V and one at 5 V.
    (
        4001, "Power Management (PMIC)", "LDO33", "SOT-223",
        "3.3V Low Drop Out Regulator",
        '{"Output Voltage":"3.3V","Output Current":"1A","Voltage - Supply":"15V"}',
        100000, 1, 0, "1-49:0.10", "Generic",
    ),
    (
        4002, "Power Management (PMIC)", "LDO50", "SOT-223",
        "5.0V Low Drop Out Regulator",
        '{"Output Voltage":"5.0V","Output Current":"1A","Voltage - Supply":"15V"}',
        90000, 1, 0, "1-49:0.10", "Generic",
    ),
    # Named part, for the text-search path.
    (
        5001, "Embedded Processors & Controllers", "ESP32-WROOM-32E", "SMD",
        "ESP32 WiFi module", '{}', 5000, 0, 0, "1-49:2.50", "Espressif",
    ),
    # Genuinely uncategorised: no category, no recognisable description and no
    # specifications. This is 67,000 rows of the real catalogue.
    (
        6001, "", "SOME-BRACKET", "PTH", "Mounting bracket", "{}",
        100, 0, 0, "1-49:0.10", "Generic",
    ),
]


@pytest.fixture()
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    for row in ROWS:
        (lcsc, category, mfr, package, description, attributes, stock,
         preferred, basic, price, manufacturer) = row
        conn.execute(
            "INSERT INTO jlc_components "
            "(lcsc, category, mfr, package, description, attributes, stock, "
            " preferred, basic, price, manufacturer) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (lcsc, category, mfr, package, description, attributes, stock,
             preferred, basic, price, manufacturer),
        )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def db(catalog_path, monkeypatch) -> JLCPartsDatabase:
    monkeypatch.setenv("JLC_PARTS_CATALOG", str(catalog_path))
    # The index is cached per process, keyed on path and mtime; each test gets
    # a fresh temporary file, so the cache cannot leak between tests.
    return JLCPartsDatabase(catalog_path)


def mpns(parts):
    return [p.mfr_part for p in parts]


class TestSearch:
    def test_numeric_match_excludes_wrong_values(self, db):
        parts = db.search("10k 0603")
        assert "R0805-110K" not in mpns(parts)
        assert parts, "expected 10k resistors"

    def test_package_filter_is_applied(self, db):
        parts = db.search("10k", package="0402")
        assert mpns(parts) == ["TINY10K"]

    def test_package_is_relaxed_when_nothing_matches(self, db):
        """
        A package is a preference. Offering a 10 kΩ part in another package is
        more useful than offering nothing, as long as it is labelled.
        """
        outcome = db.search_explained("10k 1206")
        assert outcome.parts
        assert any("package" in note for note in outcome.notes)

    def test_voltage_is_a_minimum(self, db):
        parts = db.search("100nF 50V")
        values = {p.mfr_part for p in parts}
        # The 16 V part must not appear; the 500 V part may.
        assert "C0805-LOW-VOLT" not in values
        assert "C0805-100N-50V" in values

    def test_least_over_specified_rating_ranks_first(self, db):
        parts = db.search("100nF 50V")
        assert parts[0].mfr_part == "C0805-100N-50V"

    def test_tolerance_filter(self, db):
        parts = db.search("10k 1%")
        assert all(p.tolerance == pytest.approx(0.01) for p in parts)

    def test_resistance_search_does_not_return_an_inductor(self, db):
        parts = db.search("4R7")
        assert "L-4U7" not in mpns(parts)
        assert "R-4R7" in mpns(parts)

    def test_regulator_voltage_is_an_identity(self, db):
        parts = db.search("ldo 3.3v")
        assert "LDO50" not in mpns(parts)
        assert "LDO33" in mpns(parts)

    def test_uncovered_value_falls_back_to_text(self, db):
        """Nothing numeric matches, so the query is retried as text."""
        outcome = db.search_explained("10k 1206")
        assert outcome.parts

    def test_named_part_uses_the_text_path(self, db):
        parts = db.search("ESP32-WROOM-32E")
        assert mpns(parts) == ["ESP32-WROOM-32E"]

    def test_text_path_is_not_parametric(self, db):
        outcome = db.search_explained("ESP32")
        assert not outcome.is_parametric
        assert outcome.parts

    def test_min_stock_filter(self, db):
        parts = db.search("10k", min_stock=1000)
        assert "TINY10K" not in mpns(parts)

    def test_category_filter_uses_the_platforms_taxonomy(self, db):
        parts = db.search(category="resistor", min_stock=1)
        assert parts
        assert all(p.category == "resistor" for p in parts)

    def test_sort_by_price(self, db):
        parts = db.search("10k", sort="price")
        prices = [p.unit_price for p in parts]
        assert prices == sorted(prices)

    def test_empty_query_with_category_only(self, db):
        parts = db.search(category="resistor")
        assert parts

    def test_limit_is_respected(self, db):
        assert len(db.search("10k", limit=1)) == 1

    def test_missing_catalog_returns_nothing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JLC_PARTS_CATALOG", raising=False)
        database = JLCPartsDatabase(tmp_path / "absent.sqlite3")
        assert not database.available
        assert database.search("10k") == []
        assert database.lookup("C1001") is None
        assert database.find_substitutes("C1001") == []


class TestRowConversion:
    def test_parameters_are_parsed(self, db):
        part = db.lookup("C1001")
        assert part is not None
        assert part.parameters["resistance"] == pytest.approx(10000.0)
        assert part.parameters["tolerance"] == pytest.approx(0.01)
        assert part.parameters["power"] == pytest.approx(0.1)

    def test_category_comes_from_the_attributes_when_absent(self, db):
        """Row 1001 has no category and no description, only attributes."""
        part = db.lookup("C1001")
        assert part.category == "resistor"
        assert part.catalog_category == ""

    def test_pmic_category_is_refined_to_ldo(self, db):
        part = db.lookup("C4001")
        assert part.category == "regulator_ldo"

    def test_preferred_flag_uses_its_own_column(self, db):
        """
        `library_type` holds "base"/"expand" and is not the basic/preferred
        flag. Reading it as one makes every part look non-preferred.
        """
        assert db.lookup("C1002").is_preferred is True
        assert db.lookup("C1001").is_preferred is False

    def test_symbol_matches_the_internal_category(self, db):
        """
        The symbol is a real KiCad symbol. ``Regulator_Linear:LDO_Generic`` — what
        this used to assert — does not exist in any KiCad library, so a part that
        used it could not be drawn.
        """
        assert db.lookup("C1001").symbol == "Device:R"
        assert db.lookup("C2001").symbol == "Device:C"
        assert db.lookup("C4001").symbol.startswith("Regulator_")
        assert "_Generic" not in db.lookup("C4001").symbol

    def test_footprint_matches_the_package(self, db):
        assert db.lookup("C1001").footprint == "Resistor_SMD:R_0603_1608Metric"

    def test_specification_summary_is_readable(self, db):
        summary = db.lookup("C1001").specification_summary()
        assert "10kΩ" in summary
        assert "±1%" in summary
        assert "100mW" in summary

    def test_price_tiers_are_parsed(self, db):
        part = db.lookup("C1001")
        assert part.prices[-1]["unit_price"] == pytest.approx(0.002)
        assert part.unit_price == pytest.approx(0.002)

    def test_lookup_normalises_the_lcsc_number(self, db):
        assert db.lookup("1001").lcsc_part == "C1001"
        assert db.lookup("c1001").lcsc_part == "C1001"
        assert db.lookup("Cnotanumber") is None


class TestSubstitutes:
    def test_finds_the_same_value_from_another_manufacturer(self, db):
        substitutes = db.find_substitutes("C1002")
        assert substitutes
        assert all(s.part.mfr_part != "GENERIC10K5" for s in substitutes)
        assert all(s.part.parameters["resistance"] == pytest.approx(10000.0)
                   for s in substitutes)

    def test_reasons_and_caveats_are_reported(self, db):
        substitute = db.find_substitutes("C1002")[0]
        assert isinstance(substitute, Substitute)
        assert any("resistance" in reason for reason in substitute.reasons)
        assert any("package" in reason for reason in substitute.reasons)
        assert substitute.explain()

    def test_a_looser_tolerance_is_a_caveat(self, db):
        """
        Replacing a ±1% part with a ±5% part must be disclosed, not hidden. A
        hidden part cannot be chosen; a flagged one can.
        """
        substitutes = db.find_substitutes("C1001", limit=10)
        looser = [s for s in substitutes if s.part.mfr_part == "GENERIC10K5"]
        assert looser, "expected the ±5% part to be offered"
        assert any("looser tolerance" in caveat for caveat in looser[0].caveats)
        assert not looser[0].is_clean

    def test_a_tighter_tolerance_is_a_reason(self, db):
        substitutes = db.find_substitutes("C1002", limit=10)
        tighter = next(
            s for s in substitutes if s.part.mfr_part == "RC0603FR-0710KL"
        )
        assert any("at least as tight" in reason for reason in tighter.reasons)
        assert tighter.is_clean

    def test_a_lower_voltage_rating_is_a_caveat(self, db):
        substitutes = db.find_substitutes("C2001", same_package=False, limit=10)
        low = [s for s in substitutes if s.part.mfr_part == "C0805-LOW-VOLT"]
        assert low, "expected the 16 V part to be offered"
        assert any("voltage" in caveat for caveat in low[0].caveats)
        assert not low[0].is_clean

    def test_same_package_can_be_relaxed(self, db):
        strict = db.find_substitutes("C1001", same_package=True, limit=10)
        relaxed = db.find_substitutes("C1001", same_package=False, limit=10)
        assert set(mpns([s.part for s in relaxed])) >= set(mpns([s.part for s in strict]))

    def test_parts_without_a_value_have_no_substitutes(self, db):
        """
        A part identified only by a part number cannot be compared by value, so
        the honest answer is nothing rather than a guess.
        """
        assert db.find_substitutes("C5001") == []

    def test_unknown_part_returns_nothing(self, db):
        assert db.find_substitutes("C999999") == []


class TestCategoryTaxonomy:
    """
    The catalogue's categories are broader than this platform's. Splitting them
    is where a part can silently get the wrong symbol, so the mapping is tested
    directly.
    """

    @pytest.mark.parametrize(
        "description,expected",
        [
            ("3.3V Low Drop Out (LDO) Regulator", "regulator_ldo"),
            ("Adjustable Buck DC-DC Converter", "regulator_buck"),
            ("Boost Converter Step-Up", "regulator_boost"),
            ("Voltage Reference, 2.5V", "voltage_reference"),
            ("Voltage monitor, Watchdog timer", "supervisor"),
            ("Single Cell Battery Charger", "battery_management"),
            ("Load Switch with Quick Output Discharge", "power_switch"),
            ("Gate Driver IC", "driver"),
            ("USB Power Delivery Controller", "interface"),
        ],
    )
    def test_pmic_is_split_by_description(self, description, expected):
        """
        "Power Management (PMIC)" covers all of these. Treating the whole leaf
        as an LDO would give a TL431 voltage reference LDO pinouts — IN/OUT/GND
        — which is wrong and dangerous.
        """
        from src.components.jlcparts import JLCPartsDatabase

        assert JLCPartsDatabase._categorize(None, "Power Management (PMIC)", description, "SOT-23") == expected

    def test_an_unidentified_pmic_is_not_an_ldo(self):
        from src.components.jlcparts import JLCPartsDatabase

        assert (
            JLCPartsDatabase._categorize(
                None, "Power Management (PMIC)", "Power Management - Specialized", "TSSOP20"
            )
            == "power_management"
        )

    @pytest.mark.parametrize(
        "description,expected",
        [
            ("Zener Diode 5.1V", "zener"),
            ("Schottky Barrier Diode", "schottky"),
            ("Light Emitting Diode Green", "led"),
            ("Switching Diode 100V", "diode"),
        ],
    )
    def test_diodes_are_split(self, description, expected):
        from src.components.jlcparts import JLCPartsDatabase

        assert JLCPartsDatabase._categorize(None, "Diodes", description, "SOD-123") == expected

    def test_a_circuit_protection_part_with_a_description_is_not_refined_by_guesswork(self):
        """
        Many protection rows have no description at all. They must not be
        silently labelled as a fuse: "circuit_protection" is the honest answer.
        """
        from src.components.jlcparts import JLCPartsDatabase

        assert (
            JLCPartsDatabase._categorize(None, "Circuit Protection", "", "SMC")
            == "circuit_protection"
        )

    def test_every_refined_category_maps_to_a_catalogue_leaf(self):
        """
        A refined category that maps to no catalogue leaf produces an empty
        search. This is not hypothetical: "zener", "schottky", "tvs" and
        "varistor" were all in that state, and a category-only search for them
        returned nothing while the parts existed.
        """
        from src.components.jlcparts import _INTERNAL_TO_CATALOG, _REFINED_CATEGORIES

        missing = [
            category
            for category in _REFINED_CATEGORIES
            if not _INTERNAL_TO_CATALOG.get(category)
        ]
        assert missing == [], f"categories with no catalogue leaf: {missing}"

    def test_refined_categories_are_reachable_by_search(self, catalog_path, monkeypatch):
        """Every category in the list the API serves must actually return parts."""

        from src.components.database import ComponentDatabase

        monkeypatch.setenv("JLC_PARTS_CATALOG", str(catalog_path))
        database = ComponentDatabase(catalog_path)
        for category in database.get_categories():
            assert database.search(category=category, limit=1), category

    def test_pmic_placeholder_is_not_reported_as_an_ldo(self, db):
        """TL431 is in the PMIC leaf but is a voltage reference."""
        assert db._categorize("Power Management (PMIC)", "TL431 Voltage Reference", "SOT-23") == "voltage_reference"
