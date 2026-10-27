"""
Tests for turning a design into an order.

These cover the gap between "the design is correct" and "the parts can be
bought": an orderable part number, a real price at the quantity being ordered,
and quantities that respect what the distributor actually sells. Getting any of
these wrong produces a plausible-looking list that fails at the order form or,
worse, produces boards that cannot be assembled.
"""

import re
import sqlite3
from pathlib import Path

import pytest

from src.components.database import ComponentDatabase
from src.components.ordering import (
    PRICE_CATALOG,
    PRICE_UNKNOWN,
    build_purchase_list,
    minimum_order_quantity,
    order_quantity_for,
    package_from_footprint,
    unit_price_at,
)
from src.core.circuit_ir import CircuitIR, Component, ComponentType


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestPackageFromFootprint:
    @pytest.mark.parametrize(
        "footprint,expected",
        [
            ("Resistor_SMD:R_0805_2012Metric", "0805"),
            ("Capacitor_SMD:C_0603_1608Metric", "0603"),
            ("LED_SMD:LED_0402_1005Metric", "0402"),
            ("Package_TO_SOT_SMD:SOT-223-3_TabPin2", "SOT-223"),
            ("Package_TO_SOT_SMD:SOT-23-3", "SOT-23"),
            ("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "SOIC-8"),
            ("Package_QFN:QFN-32_5x5mm_P0.5mm", "QFN-32"),
            ("Package_DIP:DIP-8_W7.62mm", "DIP-8"),
            (":R_1206_3216Metric", "1206"),
        ],
    )
    def test_reads_the_package(self, footprint, expected):
        assert package_from_footprint(footprint) == expected

    @pytest.mark.parametrize(
        "footprint", ["", "Connector:Conn_01x04_Pin", "SomethingUnknown"]
    )
    def test_unknown_returns_nothing_rather_than_a_guess(self, footprint):
        """A wrong package would find a wrong part, so nothing is the safe answer."""
        assert package_from_footprint(footprint) == ""


class TestUnitPriceAt:
    TIERS = [
        {"quantity": 1, "unit_price": 0.10},
        {"quantity": 200, "unit_price": 0.05},
        {"quantity": 2000, "unit_price": 0.02},
    ]

    @pytest.mark.parametrize(
        "quantity,expected",
        [
            (1, 0.10),
            (10, 0.10),
            (199, 0.10),
            (200, 0.05),
            (1999, 0.05),
            (2000, 0.02),
            (100000, 0.02),
        ],
    )
    def test_picks_the_applicable_tier(self, quantity, expected):
        assert unit_price_at(self.TIERS, quantity) == pytest.approx(expected)

    def test_below_the_first_tier_uses_the_first_tier(self):
        """That is the smallest quantity the distributor will sell."""
        assert unit_price_at([{"quantity": 100, "unit_price": 0.5}], 1) == pytest.approx(0.5)

    def test_tiers_are_sorted_not_assumed_ordered(self):
        shuffled = [
            {"quantity": 2000, "unit_price": 0.02},
            {"quantity": 1, "unit_price": 0.10},
            {"quantity": 200, "unit_price": 0.05},
        ]
        assert unit_price_at(shuffled, 500) == pytest.approx(0.05)

    @pytest.mark.parametrize(
        "tiers",
        [
            [],
            None,
            [{}],
            [{"quantity": 1, "unit_price": 0}],
            [{"quantity": "x", "unit_price": "y"}],
        ],
    )
    def test_unusable_tables_return_none(self, tiers):
        """None means "unknown price", which is not the same as free."""
        assert unit_price_at(tiers, 10) is None


class TestMinimumOrderQuantity:
    def test_takes_the_largest_of_the_published_minimums(self):
        """
        JLCPCB publishes several minimums; the order form applies the largest.
        Reading only one of them produces a quantity the form then rejects.
        """
        assert minimum_order_quantity({"minPurchaseNum": 1, "leastNumber": 20}) == 20
        assert minimum_order_quantity({"minPurchaseNum": 50, "leastNumber": 20}) == 50

    @pytest.mark.parametrize("attrition", [None, {}, {"leastNumber": 0}])
    def test_falls_back_to_one(self, attrition):
        assert minimum_order_quantity(attrition) == 1

    def test_junk_is_ignored(self):
        assert minimum_order_quantity({"leastNumber": "twenty"}) == 1


class TestOrderQuantity:
    def test_one_board_needs_no_rounding(self):
        assert order_quantity_for(1, boards=1) == 1

    def test_scales_with_the_board_count(self):
        assert order_quantity_for(2, boards=5) == 10

    def test_never_below_the_distributors_minimum(self):
        assert order_quantity_for(1, attrition={"leastNumber": 20}, boards=1) == 20

    def test_adds_the_attrition_allowance_per_board(self):
        """Running short on the last board costs a second order."""
        assert order_quantity_for(1, attrition={"lossNumber": 6}, boards=5) == 35

    def test_least_number_is_a_minimum_not_a_spare_count(self):
        """
        A regression: leastNumber was read as spare parts per board, which asked
        for 105 resistors to build 5 boards.
        """
        quantity = order_quantity_for(
            1, attrition={"leastNumber": 20, "lossNumber": 6}, boards=5
        )
        assert quantity == 35, quantity

    def test_spare_fraction_applies_on_top(self):
        assert order_quantity_for(1, boards=10, spare_fraction=0.5) == 15

    def test_never_zero(self):
        assert order_quantity_for(0, boards=0) == 1


# ---------------------------------------------------------------------------
# Building the list against a real (small) catalog
# ---------------------------------------------------------------------------

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

# lcsc, category, mfr, package, description, attributes, stock, price, attrition
ROWS = [
    # The design's own part number is in the catalogue: the happy path.
    (
        1001, "Resistors", "RC0603FR-0710KL", "0603", "10kΩ 1%",
        '{"Resistance":"10kΩ","Tolerance":"±1%"}', 500000,
        "1-199:0.01,200-1999:0.005,2000-:0.002",
        '{"leastNumber":20,"lossNumber":6,"minPurchaseNum":1}',
    ),
    # A second 10k 0603 resistor under a different part number.
    (
        1002, "Resistors", "OTHER-10K-0603", "0603", "10kΩ 5%",
        '{"Resistance":"10kΩ","Tolerance":"±5%"}', 2000,
        "1-99:0.02,100-:0.01",
        '{"leastNumber":20,"lossNumber":6,"minPurchaseNum":1}',
    ),
    # The design's part number is NOT in the catalogue, but the value is: the
    # ordering equivalent has to be found by value and package.
    (
        2001, "Capacitors", "REAL-10UF-0805", "0805", "10uF 25V",
        '{"Capacitance":"10uF","Voltage Rating":"25V"}', 300000,
        "1-99:0.05,100-:0.03",
        '{"leastNumber":20,"lossNumber":6,"minPurchaseNum":1}',
    ),
    # Scarce: not enough stock for a large order.
    (
        2002, "Capacitors", "SCARCE-22UF-0805", "0805", "22uF 10V",
        '{"Capacitance":"22uF","Voltage Rating":"10V"}', 3,
        "1-:0.09",
        '{"leastNumber":1,"lossNumber":0,"minPurchaseNum":1}',
    ),
    # A regulator, for the pinout caveat.
    (
        3001, "Power Management (PMIC)", "LDO-33-ALT", "SOT-223",
        "3.3V Low Drop Out Regulator",
        '{"Output Voltage":"3.3V","Output Current":"1A"}', 90000,
        "1-99:0.10,100-:0.06",
        '{"leastNumber":2,"lossNumber":0,"minPurchaseNum":1}',
    ),
    # A different 3.3 V regulator in another package: must not be preferred when
    # the design asks for SOT-223.
    (
        3002, "Power Management (PMIC)", "LDO-33-WRONG-PKG", "SOT-23-5",
        "3.3V Low Drop Out Regulator",
        '{"Output Voltage":"3.3V","Output Current":"0.5A"}', 90000,
        "1-:0.08",
        '{"leastNumber":2,"lossNumber":0,"minPurchaseNum":1}',
    ),
    # A near-miss: LM317L is a *positive* adjustable regulator and LM337L is a
    # negative one. One character apart, and the value "Adjustable" cannot tell
    # them apart.
    (
        3003, "Power Management (PMIC)", "LM317L", "TO-92",
        "Adjustable Linear Regulator Positive",
        '{"Output Voltage":"1.25V","Output Current":"100mA"}', 8000,
        "1-99:0.05,100-:0.03",
        '{"leastNumber":1,"lossNumber":0,"minPurchaseNum":1}',
    ),
    # An LED, matched by colour.
    (
        4001, "Optoelectronics", "LED-GREEN-0805-REAL", "0805", "Green LED 0805",
        '{"Illumination Color":"Green"}', 50000,
        "1-99:0.03,100-:0.02",
        '{"leastNumber":5,"lossNumber":4,"minPurchaseNum":1}',
    ),
]


@pytest.fixture()
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    for row in ROWS:
        conn.execute(
            "INSERT INTO jlc_components "
            "(lcsc, category, mfr, package, description, attributes, stock, "
            " price, attrition) VALUES (?,?,?,?,?,?,?,?,?)",
            row,
        )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def db(catalog_path, monkeypatch) -> ComponentDatabase:
    monkeypatch.setenv("JLC_PARTS_CATALOG", str(catalog_path))
    return ComponentDatabase(catalog_path)


def make_circuit(*components) -> CircuitIR:
    circuit = CircuitIR(name="test", description="test")
    for component in components:
        circuit.add_component(component)
    return circuit


def resistor(ref="R1", mpn="RC0603FR-0710KL", value="10k"):
    return Component(
        ref=ref, value=value, component_type=ComponentType.RESISTOR,
        footprint="Resistor_SMD:R_0603_1608Metric", symbol="Device:R",
        mpn=mpn, package="0603",
    )


def capacitor(ref="C1", mpn="PLACEHOLDER-10UF", value="10uF"):
    return Component(
        ref=ref, value=value, component_type=ComponentType.CAPACITOR,
        footprint="Capacitor_SMD:C_0805_2012Metric", symbol="Device:C",
        mpn=mpn, package="0805",
    )


class TestExactCatalogMatch:
    def test_design_part_found_by_its_own_mpn(self, db):
        """When the catalogue has the design's part, the order agrees exactly."""
        purchase = build_purchase_list(make_circuit(resistor()), db)
        line = purchase.lines[0]
        assert line.lcsc_part == "C1001"
        assert line.order_mpn == "RC0603FR-0710KL"
        assert line.price_source == PRICE_CATALOG
        # No part-number caveat: it is the same part.
        assert not any("Different" in note for note in line.notes)
        assert not line.pinout_check_required

    def test_price_comes_from_the_tier_table(self, db):
        purchase = build_purchase_list(make_circuit(resistor()), db, boards=1)
        line = purchase.lines[0]
        # 1 x 1 board + attrition 6 = 7, raised to the 20 minimum, so the 1-199
        # tier applies.
        assert line.order_quantity == 20
        assert line.unit_price == pytest.approx(0.01)
        assert line.line_total == pytest.approx(0.20)

    def test_a_larger_order_reaches_a_cheaper_tier(self, db):
        small = build_purchase_list(make_circuit(resistor()), db, boards=1).lines[0]
        large = build_purchase_list(make_circuit(resistor()), db, boards=500).lines[0]
        assert small.unit_price > large.unit_price
        assert large.unit_price == pytest.approx(0.002)


class TestValueMatchedPart:
    def test_finds_an_orderable_part_by_value_when_the_mpn_is_absent(self, db):
        """
        The built-in catalogue's part numbers do not exist at any distributor, so
        this is the common case, not the exception.
        """
        purchase = build_purchase_list(make_circuit(capacitor()), db)
        line = purchase.lines[0]
        assert line.lcsc_part == "C2001"
        assert line.order_mpn == "REAL-10UF-0805"
        assert line.order_mpn != line.mpn

    def test_a_passive_gets_no_pinout_warning(self, db):
        """A 10 kΩ resistor has no pinout to get wrong; saying otherwise is noise."""
        line = build_purchase_list(make_circuit(capacitor()), db).lines[0]
        assert any("no pinout to check" in note for note in line.notes)
        assert not line.pinout_check_required

    def test_an_ic_does_get_a_pinout_warning(self, db):
        regulator = Component(
            ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
            footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2", symbol="LDO",
            mpn="PRETEND-LDO-3.3", package="SOT-223",
        )
        line = build_purchase_list(make_circuit(regulator), db).lines[0]
        assert line.pinout_check_required
        assert any("verify the pinout" in note for note in line.notes)
        assert any(line.mpn in warning for warning in build_purchase_list(
            make_circuit(regulator), db
        ).warnings())

    def test_prefers_the_requested_package(self, db):
        """Two 3.3 V regulators are in the catalogue; the SOT-223 one must win."""
        regulator = Component(
            ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
            footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2", symbol="LDO",
            mpn="PRETEND-LDO-3.3", package="SOT-223",
        )
        line = build_purchase_list(make_circuit(regulator), db).lines[0]
        assert line.package == "SOT-223"
        assert line.lcsc_part == "C3001"

    def test_led_matched_by_colour(self, db):
        led = Component(
            ref="D1", value="Green", component_type=ComponentType.LED,
            footprint="LED_SMD:LED_0805_2012Metric", symbol="Device:LED",
            mpn="PLACEHOLDER-LED", package="0805",
        )
        line = build_purchase_list(make_circuit(led), db).lines[0]
        assert line.lcsc_part == "C4001"

    def test_package_derived_from_the_footprint_when_absent(self, db):
        """A design that only knows footprints still has to be orderable."""
        part = resistor()
        part.package = ""
        line = build_purchase_list(make_circuit(part), db).lines[0]
        assert line.package == "0603"
        assert line.lcsc_part == "C1001"


class TestGrouping:
    def test_identical_parts_are_one_line(self, db):
        circuit = make_circuit(resistor("R1"), resistor("R2"), resistor("R3"))
        purchase = build_purchase_list(circuit, db, boards=2)
        assert len(purchase.lines) == 1
        line = purchase.lines[0]
        assert sorted(line.designators) == ["R1", "R2", "R3"]
        assert line.quantity == 3
        # 3 x 2 boards + 6 attrition x 2 boards = 18, raised to the 20 minimum.
        assert line.order_quantity == 20

    def test_different_values_are_separate_lines(self, db):
        circuit = make_circuit(resistor("R1"), capacitor("C1"))
        assert len(build_purchase_list(circuit, db).lines) == 2


class TestShortfallsAndHonesty:
    def test_reports_insufficient_stock(self, db):
        scarce = Component(
            ref="C9", value="22uF", component_type=ComponentType.CAPACITOR,
            footprint="Capacitor_SMD:C_0805_2012Metric", symbol="Device:C",
            mpn="SCARCE-22UF-0805", package="0805",
        )
        purchase = build_purchase_list(make_circuit(scarce), db, boards=5)
        line = purchase.lines[0]
        assert line.stock == 3
        assert line.in_stock is False
        assert any("enough stock" in warning for warning in purchase.warnings())

    def test_a_template_only_match_is_reported_as_not_orderable(self, db):
        """
        47 uH in 1210 has a component template — symbol, footprint, value — and
        no part number, so it cannot be ordered. The line must say so rather than
        look like an order.
        """
        template_only = Component(
            ref="X1", value="47uH", component_type=ComponentType.INDUCTOR,
            footprint="Inductor_SMD:L_1210_3225Metric", symbol="Device:L",
            mpn="", package="1210",
        )
        purchase = build_purchase_list(make_circuit(template_only), db)
        line = purchase.lines[0]
        assert line.orderable is False
        assert line.lcsc_part is None
        assert line.price_source == PRICE_UNKNOWN
        assert any("component template" in note for note in line.notes)
        assert any("cannot be ordered" in warning for warning in purchase.warnings())

    def test_reports_a_part_with_no_match_at_all(self, db):
        """Nothing in either catalogue: no parts, and no price to show."""
        unknown = Component(
            ref="X2", value="470uH", component_type=ComponentType.INDUCTOR,
            footprint="Inductor_SMD:L_1812_4532Metric", symbol="Device:L",
            mpn="NOT-IN-CATALOG", package="1812",
        )
        purchase = build_purchase_list(make_circuit(unknown), db)
        line = purchase.lines[0]
        assert line.orderable is False
        assert line.lcsc_part is None
        assert line.price_source == PRICE_UNKNOWN
        assert line.line_total == 0.0
        assert any("cannot be ordered" in warning for warning in purchase.warnings())

    def test_still_reports_how_many_pieces_the_boards_need(self, db):
        """An unorderable line is still a fact about the board."""
        unknown = Component(
            ref="X1", value="47uH", component_type=ComponentType.INDUCTOR,
            footprint="Inductor_SMD:L_1210_3225Metric", symbol="Device:L",
            mpn="NOT-IN-CATALOG", package="1210",
        )
        purchase = build_purchase_list(make_circuit(unknown), db, boards=4)
        assert purchase.lines[0].order_quantity == 4

    def test_no_catalogue_means_no_prices_at_all(self, tmp_path, monkeypatch):
        """
        Without the catalogue there are no part numbers, prices or stock — the
        templates carry none of them. An invented price is as misleading as an
        invented part number, and this project shipped both.
        """
        monkeypatch.delenv("JLC_PARTS_CATALOG", raising=False)
        no_catalog = ComponentDatabase(tmp_path / "absent.sqlite3")
        purchase = build_purchase_list(make_circuit(resistor()), no_catalog)
        line = purchase.lines[0]
        assert line.price_source == PRICE_UNKNOWN
        assert line.unit_price == 0.0
        assert line.orderable is False
        assert purchase.lines_without_prices
        warnings = purchase.warnings()
        assert any("no price" in warning for warning in warnings)
        assert any("catalog-setup" in warning for warning in warnings)

    def test_empty_circuit_produces_an_empty_list(self, db):
        purchase = build_purchase_list(make_circuit(), db)
        assert purchase.lines == []
        assert purchase.total_cost == 0.0
        assert purchase.warnings() == []


class TestOutput:
    def test_jlcpcb_csv_has_the_expected_columns(self, db):
        purchase = build_purchase_list(
            make_circuit(resistor("R1"), resistor("R2"), capacitor("C1")), db
        )
        csv_text = purchase.to_jlcpcb_csv()
        header, *rows = csv_text.strip().split("\n")
        assert header == "Comment,Designator,Footprint,LCSC Part #"
        assert len(rows) == 2

    def test_jlcpcb_csv_puts_designators_of_one_part_on_one_row(self, db):
        """The uploader rejects a part spread over several rows."""
        purchase = build_purchase_list(
            make_circuit(resistor("R1"), resistor("R2")), db
        )
        rows = purchase.to_jlcpcb_csv().strip().split("\n")[1:]
        assert len(rows) == 1
        assert "R1,R2" in rows[0]

    def test_jlcpcb_csv_omits_lines_that_cannot_be_ordered(self, db):
        unknown = Component(
            ref="X1", value="47uH", component_type=ComponentType.INDUCTOR,
            footprint="Inductor_SMD:L_1210_3225Metric", symbol="Device:L",
            mpn="NOT-IN-CATALOG", package="1210",
        )
        purchase = build_purchase_list(make_circuit(resistor(), unknown), db)
        csv_text = purchase.to_jlcpcb_csv()
        assert "C1001" in csv_text
        assert "NOT-IN-CATALOG" not in csv_text

    def test_markdown_states_the_board_count_and_total(self, db):
        purchase = build_purchase_list(make_circuit(resistor()), db, boards=3)
        markdown = purchase.to_markdown()
        assert "3 boards" in markdown
        assert "Estimated total" in markdown
        assert "C1001" in markdown

    def test_markdown_includes_the_quantity_arithmetic(self, db):
        purchase = build_purchase_list(make_circuit(resistor()), db, boards=5)
        markdown = purchase.to_markdown()
        assert "Quantity" in markdown
        assert "minimum order" in markdown or "attrition" in markdown

    def test_dict_is_serialisable_and_complete(self, db):
        import json

        purchase = build_purchase_list(make_circuit(resistor()), db, boards=2)
        payload = purchase.to_dict()
        json.dumps(payload)  # must not raise
        assert payload["boards"] == 2
        assert payload["orderable_lines"] == 1
        assert payload["total_parts"] == 20
        assert payload["lines"][0]["lcsc_part"] == "C1001"


class TestOrderIsAlwaysReal:
    """
    The property that matters for buying parts: nothing reaches the order form
    unless it is a real catalogue part with stock.

    An earlier version of this project emitted manufacturer part numbers that do
    not exist at any distributor. They looked exactly like real ones, which is
    what made them dangerous.
    """

    ALL_LCSC = re.compile(r"^C\d+$")

    def test_every_csv_line_has_a_wellformed_lcsc_number(self, db):
        purchase = build_purchase_list(
            make_circuit(
                resistor(), capacitor(), resistor("R2", "RC0805FR-0710KL", "10k")
            ),
            db,
        )
        rows = purchase.to_jlcpcb_csv().strip().split("\n")[1:]
        assert rows
        for row in rows:
            lcsc = row.split(",")[-1]
            assert self.ALL_LCSC.match(lcsc), f"bad LCSC number in the order: {lcsc}"

    def test_a_line_with_no_catalogue_part_never_reaches_the_csv(self, db):
        unknown = Component(
            ref="X1", value="470uH", component_type=ComponentType.INDUCTOR,
            footprint="Inductor_SMD:L_1812_4532Metric", symbol="Device:L",
            mpn="NOT-IN-CATALOG", package="1812",
        )
        purchase = build_purchase_list(make_circuit(unknown), db)
        assert purchase.to_jlcpcb_csv().strip().split("\n")[1:] == []

    def test_near_identical_part_numbers_are_called_out(self, db):
        """
        LM337L and LM317L are one character apart: a negative adjustable
        regulator and a positive one. A value of "Adjustable" cannot distinguish
        them, so the difference has to be stated in words.

        The design's own part number is set explicitly here: templates carry no
        part number, so this hazard shows up when a design *does* name one and
        the catalogue has to find a different part.
        """
        negative = Component(
            ref="U1", value="Adjustable", component_type=ComponentType.REGULATOR_LDO,
            footprint="Package_TO_SOT_THT:TO-92_Inline", symbol="Regulator_Linear:LM337L",
            mpn="LM337L", package="TO-92",
        )
        line = build_purchase_list(make_circuit(negative), db).lines[0]
        assert line.order_mpn and line.order_mpn != "LM337L", line.order_mpn
        assert any("nearly identical" in note for note in line.notes)

    def test_a_non_numeric_value_is_flagged_as_not_identifying_a_part(self, db):
        led = Component(
            ref="D1", value="Green", component_type=ComponentType.LED,
            footprint="LED_SMD:LED_0805_2012Metric", symbol="Device:LED",
            mpn="", package="0805",
        )
        line = build_purchase_list(make_circuit(led), db).lines[0]
        assert any("does not contain a number" in note for note in line.notes)

    def test_a_real_part_number_produces_no_part_number_noise(self, db):
        line = build_purchase_list(make_circuit(resistor()), db).lines[0]
        assert not any("nearly identical" in note for note in line.notes)
        assert not any("does not contain a number" in note for note in line.notes)


class TestAgainstTheRealCatalog:
    """
    The same logic against the downloaded catalogue.

    Skipped unless ``JLC_PARTS_CATALOG`` points at a real one, because the
    interesting property — that the built-in list's part numbers are absent from
    the catalogue while the values are present — can only be checked there.
    """

    @pytest.fixture()
    def real_db(self):
        from conftest import real_catalog_path

        catalog = real_catalog_path()
        if catalog is None:
            pytest.skip("no component catalog found (run: make catalog)")
        from src.components.database import ComponentDatabase

        return ComponentDatabase(catalog)

    def test_builtin_part_numbers_are_not_orderable(self, real_db):
        """
        CC0805KRX7R9BB106 and friends look like real Yageo part numbers but are
        not in JLCPCB's catalogue, so a BOM naming them cannot be ordered.
        """
        assert real_db.find_in_catalog("CC0805KRX7R9BB106") == []

    def test_the_value_is_orderable_under_a_real_part_number(self, real_db):
        purchase = build_purchase_list(make_circuit(capacitor()), real_db)
        line = purchase.lines[0]
        assert line.lcsc_part and line.lcsc_part.startswith("C")
        assert line.stock and line.stock > 0
        assert line.price_source == PRICE_CATALOG
        assert line.unit_price > 0

    def test_a_real_design_gets_a_real_part_number(self, real_db):
        purchase = build_purchase_list(make_circuit(resistor()), real_db)
        line = purchase.lines[0]
        assert line.lcsc_part is not None
        assert line.price_source == PRICE_CATALOG

    def test_every_lcsc_in_the_order_exists_with_stock(self, real_db):
        """
        The end-to-end guarantee: every part number that reaches the order form
        resolves in the catalogue and is in stock. This is the check that would
        have caught the invented part numbers.
        """
        circuit = make_circuit(
            resistor(), capacitor(), resistor("R2", "RC0805FR-0710KL", "10k")
        )
        purchase = build_purchase_list(circuit, real_db, boards=3)
        rows = purchase.to_jlcpcb_csv().strip().split("\n")[1:]
        assert rows, "expected at least one orderable line"
        for row in rows:
            lcsc = row.split(",")[-1]
            part = real_db.get_by_lcsc(lcsc)
            assert part is not None, f"{lcsc} is not in the catalogue"
            assert part.stock > 0, f"{lcsc} has no stock"
            assert part.price > 0, f"{lcsc} has no price"

    def test_the_templates_claim_no_lcsc_number(self, real_db):
        """A template must not pretend to be orderable."""
        from src.components.database import ComponentDatabase as _Db

        templates = _Db(prefer_jlcparts=False)._component_templates
        assert templates
        assert all(p.lcsc_part is None for p in templates)

    def test_the_templates_carry_no_parts_data_at_all(self, real_db):
        """
        The property that replaces the old verified/placeholder allowlist: there
        is no part number, manufacturer, price or stock anywhere in the
        templates, so there is nothing left to be wrong about. The catalogue is
        the only source of parts data.
        """
        from src.components.database import ComponentDatabase as _Db

        templates = _Db(prefer_jlcparts=False)._component_templates
        assert len(templates) == 36
        for part in templates:
            assert part.mpn == "", part.mpn
            assert part.manufacturer == "", part.manufacturer
            assert part.price == 0.0, part.price
            assert part.stock == 0, part.stock
            assert part.lcsc_part is None
            # What they do carry: everything needed to place the part.
            assert part.value and part.package
            assert part.symbol and part.footprint
            assert part.category

    def test_every_template_footprint_exists_in_kicad(self):
        """
        The templates' real value is a checked symbol and footprint, so a template
        pointing at a footprint KiCad does not have would be worse than nothing.
        """
        import pytest

        from src.generators.kicad_footprints import load_footprint
        from src.components.database import ComponentDatabase as _Db

        templates = _Db(prefer_jlcparts=False)._component_templates
        missing = []
        checked = 0
        for part in templates:
            definition = load_footprint(part.footprint)
            if definition is None:
                missing.append((part.value, part.footprint))
                continue
            checked += 1
            # A footprint with no pads cannot be placed or netlisted.
            assert definition.pads, (part.value, part.footprint)

        if checked == 0:
            pytest.skip("KiCad footprint libraries are not installed")
        assert missing == [], f"footprints KiCad does not have: {missing}"
