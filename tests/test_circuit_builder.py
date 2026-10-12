"""
Tests for component resolution and specification -> Circuit IR building.

These cover the handoff that previously did not exist: an LLM's component list
and connection list becoming a real, ERC-clean Circuit IR with catalog part
numbers, real pins, and deterministic reference designators.
"""

import pytest

from src.components.database import ComponentDatabase
from src.core.circuit_builder import CircuitIRBuilder
from src.core.circuit_ir import CircuitIR, ComponentType, PinType
from src.core.component_resolver import (
    DesignatorAssigner,
    canonicalize_pin_name,
    infer_component_type,
    is_power_net,
    normalize_package,
    resolve_mpn,
    resolve_pins,
    role_to_component_type,
    synthesize_passive_passport,
)
from src.core.erc import ERCValidator
from src.llm.validation import DesignValidator, validate_spec_shape


@pytest.fixture(scope="module")
def db():
    return ComponentDatabase()


# ---------------------------------------------------------------------------
# Role -> ComponentType
# ---------------------------------------------------------------------------

class TestRoleMapping:
    @pytest.mark.parametrize(
        "role,expected",
        [
            ("regulator", ComponentType.REGULATOR_LDO),
            ("ldo_regulator", ComponentType.REGULATOR_LDO),
            ("buck_converter", ComponentType.REGULATOR_BUCK),
            ("boost_converter", ComponentType.REGULATOR_BOOST),
            ("input_capacitor", ComponentType.CAPACITOR),
            ("output_capacitor", ComponentType.CAPACITOR),
            ("freewheel_diode", ComponentType.DIODE),
            ("led_indicator", ComponentType.LED),
            # The governing noun must win over the modifier.
            ("led_resistor", ComponentType.RESISTOR),
            ("current_limit_resistor", ComponentType.RESISTOR),
            ("riaa_r1_left", ComponentType.RESISTOR),
            ("riaa_c2_right", ComponentType.CAPACITOR),
            ("gain_rf_left", ComponentType.RESISTOR),
            ("input_jack_left", ComponentType.CONNECTOR),
            ("opamp_left_1", ComponentType.OPAMP),
            ("vref_diode", ComponentType.CHIP),
            ("microcontroller", ComponentType.MICROCONTROLLER),
            ("8mhz_crystal", ComponentType.CRYSTAL),
        ],
    )
    def test_role_maps_to_type(self, role, expected):
        assert role_to_component_type(role) == expected

    def test_unknown_role_falls_back(self):
        assert role_to_component_type("mystery_part") == ComponentType.CUSTOM
        assert role_to_component_type("") == ComponentType.CUSTOM

    @pytest.mark.parametrize(
        "role,mpn,value,expected",
        [
            ("controller", "LM2596S-5.0", "5V", ComponentType.REGULATOR_BUCK),
            ("controller", "MT3608", "Adjustable", ComponentType.REGULATOR_BOOST),
            ("controller", "AMS1117-3.3", "3.3V", ComponentType.REGULATOR_LDO),
            ("regulator", "LM2596S-5.0", "5V", ComponentType.REGULATOR_BUCK),
            ("resistor", "RC0805FR-0710KL", "10k", ComponentType.RESISTOR),
        ],
    )
    def test_infer_from_mpn(self, role, mpn, value, expected):
        base = role_to_component_type(role)
        assert infer_component_type(role, base, mpn=mpn, value=value) == expected


# ---------------------------------------------------------------------------
# Designators, packages, pins
# ---------------------------------------------------------------------------

class TestResolvers:
    def test_designators_are_sequential_per_prefix(self):
        assigner = DesignatorAssigner()
        assert assigner.assign(ComponentType.RESISTOR) == "R1"
        assert assigner.assign(ComponentType.RESISTOR) == "R2"
        assert assigner.assign(ComponentType.CAPACITOR) == "C1"
        assert assigner.assign(ComponentType.REGULATOR_LDO) == "U1"

    def test_designators_avoid_reserved_refs(self):
        assigner = DesignatorAssigner()
        assigner.reserve("R5")
        assert assigner.assign(ComponentType.RESISTOR) == "R6"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("0805", "0805"),
            ("0603", "0603"),
            ("SOIC8", "SOIC-8"),
            ("SOT23", "SOT-23"),
            ("0805 (2012 Metric)", "0805"),
            ("HC-49S", "HC-49S"),
        ],
    )
    def test_normalize_package(self, raw, expected):
        assert normalize_package(raw) == expected

    def test_passive_passport_has_footprint(self):
        symbol, footprint = synthesize_passive_passport(ComponentType.RESISTOR, "0603")
        assert symbol == "Device:R"
        assert footprint == "Resistor_SMD:R_0603_1608Metric"

    def test_passive_passport_unknown_package_defaults(self):
        _, footprint = synthesize_passive_passport(ComponentType.CAPACITOR, "weird")
        assert footprint == "Capacitor_SMD:C_0805_2012Metric"

    def test_resolve_pins_led_uses_anode_cathode(self):
        pins = resolve_pins(ComponentType.LED)
        assert [p[1] for p in pins] == ["K", "A"]

    def test_resolve_pins_known_regulator(self):
        """Pin names must match the real KiCad symbol (VI/VO, not VIN/VOUT)."""
        pins = resolve_pins(
            ComponentType.REGULATOR_LDO, "AMS1117-3.3", "Regulator_Linear:AMS1117-3.3"
        )
        by_name = {p[1]: p[0] for p in pins}
        assert by_name["VI"] == "3"
        assert by_name["VO"] == "2"
        assert by_name["GND"] == "1"

    @pytest.mark.parametrize(
        "written,expected_number",
        [
            ("VIN", "3"),
            ("VI", "3"),
            ("VOUT", "2"),
            ("VO", "2"),
            ("OUT", "2"),
            ("GND", "1"),
            ("VSS", "1"),
        ],
    )
    def test_pin_aliases_resolve_to_real_pins(self, written, expected_number):
        """A model may write familiar names; they must hit the real KiCad pin."""
        from src.core.component_resolver import find_pin_in

        pins = resolve_pins(
            ComponentType.REGULATOR_LDO, "AMS1117-3.3", "Regulator_Linear:AMS1117-3.3"
        )
        match = find_pin_in(pins, written)
        assert match is not None, f"{written} should resolve"
        assert match[0] == expected_number

    def test_led_number_refs_do_not_collide_with_names(self):
        """D1.A must not silently land on pin 1 (K) just because 'A' is absent."""
        from src.core.component_resolver import find_pin_in

        pins = resolve_pins(ComponentType.LED)
        assert find_pin_in(pins, "A")[0] == "2"
        assert find_pin_in(pins, "K")[0] == "1"
        assert find_pin_in(pins, "2")[0] == "2"

    def test_resolve_pins_opamp(self):
        pins = resolve_pins(ComponentType.OPAMP, "LM358", "Amplifier_Operational:LM358")
        assert len(pins) == 8
        power = {p[1] for p in pins if p[2] == PinType.POWER_IN}
        assert power == {"V+", "V-"}

    @pytest.mark.parametrize(
        "raw,expected",
        [("IN+", "IN+"), ("IN -", "IN-"), ("IN1-", "IN1-"), ("OUT", "OUT")],
    )
    def test_canonicalize_pin_name(self, raw, expected):
        assert canonicalize_pin_name(raw) == expected

    @pytest.mark.parametrize(
        "net,power",
        [("GND", True), ("VIN", True), ("+3V3", True), ("D1_A", False), ("SW", False)],
    )
    def test_is_power_net(self, net, power):
        assert is_power_net(net) is power


class TestMPNResolution:
    def test_exact_catalog_hit(self, db):
        result = resolve_mpn(ComponentType.REGULATOR_LDO, "AMS1117-3.3", db)
        assert result.resolved is not None
        assert result.resolved.mpn == "AMS1117-3.3"
        assert result.substituted is False

    def test_fake_mpn_is_substituted_with_real_part(self, db):
        result = resolve_mpn(
            ComponentType.CAPACITOR, "C-10uF-0805", db, package="0805", value="10uF"
        )
        assert result.resolved is not None
        assert result.resolved.category == "capacitor"
        assert result.substituted is True
        assert "not in catalog" in result.note

    def test_value_matched_substitution_prefers_right_variant(self, db):
        result = resolve_mpn(
            ComponentType.LED, "LED-GREEN-0805", db, package="0805", value="Green"
        )
        assert result.resolved is not None
        assert result.resolved.value == "Green"

    def test_unknown_category_recorded(self, db):
        result = resolve_mpn(ComponentType.CUSTOM, "NOT-A-REAL-PART", db)
        assert result.resolved is None
        assert "not in catalog" in result.note


# ---------------------------------------------------------------------------
# Spec -> Circuit IR
# ---------------------------------------------------------------------------

LDO_SPEC = {
    "topology": "Linear LDO Regulator",
    "components": [
        {
            "role": "regulator",
            "mpn": "AMS1117-3.3",
            "value": "3.3V",
            "package": "SOT-223",
            "reasoning": "5V to 3.3V LDO",
        },
        {
            "role": "input_capacitor",
            "mpn": "C-10uF-0805",
            "value": "10uF",
            "package": "0805",
            "reasoning": "input decoupling",
        },
        {
            "role": "output_capacitor",
            "mpn": "CC0805KRX5R7BB226",
            "value": "22uF",
            "package": "0805",
            "reasoning": "output stability",
        },
        {
            "role": "led_indicator",
            "mpn": "LTST-C190KGKT",
            "value": "Green",
            "package": "0805",
            "reasoning": "power indicator",
        },
        {
            "role": "led_resistor",
            "mpn": "RC0805FR-07330RL",
            "value": "330",
            "package": "0805",
            "reasoning": "LED current limit",
        },
    ],
    "connections": [
        {"from": "U1.VIN", "to": "C1.1", "net": "VIN"},
        {"from": "U1.VOUT", "to": "C2.1", "net": "VOUT"},
        {"from": "U1.VOUT", "to": "R1.1", "net": "VOUT"},
        {"from": "R1.2", "to": "D1.A", "net": "LED_A"},
        {"from": "D1.K", "to": "C1.2", "net": "GND"},
        {"from": "U1.GND", "to": "C2.2", "net": "GND"},
    ],
}

REQUIREMENTS = {
    "circuit_type": "ldo_regulator",
    "description": "5V to 3.3V LDO with indicator",
    "input_voltage": 5.0,
    "output_voltage": 3.3,
    "output_current": 0.5,
}


class TestCircuitIRBuilder:
    def test_builds_expected_components_and_designators(self, db):
        circuit, report = CircuitIRBuilder(db).build(LDO_SPEC, REQUIREMENTS)

        assert set(circuit.components) == {"U1", "C1", "C2", "D1", "R1"}
        assert report.total_components == 5
        # The fake MPN must have been replaced by a real catalog part.
        assert circuit.components["C1"].mpn == "CC0805KRX7R9BB106"
        assert report.substituted_mpns

    def test_uses_llm_connections_and_marks_power_nets(self, db):
        circuit, _ = CircuitIRBuilder(db).build(LDO_SPEC, REQUIREMENTS)

        vout = circuit.nets["VOUT"]
        assert vout.is_power is True
        connected = {(p["ref"], p["pin"]) for p in vout.connected_pins}
        assert ("U1", "2") in connected
        assert ("R1", "1") in connected

        # The LED anode connects to the resistor, not to GND.
        led_nets = {p.connected_net for p in circuit.components["D1"].pins}
        assert "LED_A" in led_nets

    def test_result_passes_erc(self, db):
        circuit, _ = CircuitIRBuilder(db).build(LDO_SPEC, REQUIREMENTS)
        report = ERCValidator(circuit).validate()
        assert report.passed is True
        assert report.summary["errors"] == 0

    def test_carries_reasoning_as_description(self, db):
        circuit, _ = CircuitIRBuilder(db).build(LDO_SPEC, REQUIREMENTS)
        assert circuit.components["U1"].description == "5V to 3.3V LDO"

    def test_resolves_role_names_in_connections(self, db):
        spec = dict(LDO_SPEC)
        spec["connections"] = [
            {"from": "regulator.VIN", "to": "input_capacitor.1", "net": "VIN"},
            {"from": "regulator.VOUT", "to": "output_capacitor.1", "net": "VOUT"},
            {"from": "regulator.VOUT", "to": "led_resistor.1", "net": "VOUT"},
            {"from": "led_resistor.2", "to": "led_indicator.A", "net": "LED_A"},
            {"from": "led_indicator.K", "to": "input_capacitor.2", "net": "GND"},
            {"from": "regulator.GND", "to": "output_capacitor.2", "net": "GND"},
        ]
        circuit, report = CircuitIRBuilder(db).build(spec, REQUIREMENTS)

        assert report.skipped_connections == []
        assert ERCValidator(circuit).validate().passed is True

    def test_invalid_pin_is_reported_not_ignored(self, db):
        spec = dict(LDO_SPEC)
        spec["connections"] = [
            {"from": "U1.NOPE", "to": "C1.1", "net": "VIN"},
        ]
        _, report = CircuitIRBuilder(db).build(spec, REQUIREMENTS)
        assert any("NOPE" in entry for entry in report.skipped_connections)

    def test_unknown_component_reference_is_reported(self, db):
        spec = dict(LDO_SPEC)
        spec["connections"] = [{"from": "U9.VIN", "to": "C1.1", "net": "VIN"}]
        _, report = CircuitIRBuilder(db).build(spec, REQUIREMENTS)
        assert any("U9" in entry for entry in report.skipped_connections)

    def test_signal_net_without_pin_is_not_guessed(self, db):
        """Guessing a signal pin would silently corrupt the netlist."""
        spec = dict(LDO_SPEC)
        spec["connections"] = [{"from": "U1", "to": "C2.1", "net": "SOME_SIGNAL"}]
        _, report = CircuitIRBuilder(db).build(spec, REQUIREMENTS)
        assert any("no pin given" in entry for entry in report.skipped_connections)

    def test_power_net_without_pin_is_inferred_and_noted(self, db):
        spec = dict(LDO_SPEC)
        spec["connections"] = [{"from": "U1", "to": "C2.2", "net": "GND"}]
        _, report = CircuitIRBuilder(db).build(spec, REQUIREMENTS)
        assert any("inferred pin" in note for note in report.notes)

    def test_empty_spec_produces_empty_but_usable_report(self, db):
        circuit, report = CircuitIRBuilder(db).build({"components": []}, REQUIREMENTS)
        assert isinstance(circuit, CircuitIR)
        assert report.total_components == 0

    def test_connections_as_dict_shape(self, db):
        spec = dict(LDO_SPEC)
        spec["connections"] = {
            "VIN": ["U1.VIN", "C1.1"],
            "GND": ["U1.GND", "C1.2", "C2.2"],
            "VOUT": ["U1.VOUT", "C2.1"],
        }
        circuit, _ = CircuitIRBuilder(db).build(spec, REQUIREMENTS)
        assert ("U1", "3") in {(p["ref"], p["pin"]) for p in circuit.nets["VIN"].connected_pins}


class TestDesignValidator:
    def test_valid_spec_passes(self, db):
        report = DesignValidator(db).validate(LDO_SPEC, REQUIREMENTS, "LDO")
        assert report.valid is True
        assert report.errors == []
        assert report.circuit is not None

    def test_missing_topology_is_error(self, db):
        spec = dict(LDO_SPEC)
        spec["topology"] = ""
        report = DesignValidator(db).validate(spec, REQUIREMENTS)
        assert report.valid is False
        assert any(i.code == "SPEC_MISSING_TOPOLOGY" for i in report.errors)

    def test_no_components_is_error(self, db):
        report = DesignValidator(db).validate({"topology": "x", "components": []}, REQUIREMENTS)
        assert report.valid is False
        assert any(i.code == "SPEC_NO_COMPONENTS" for i in report.errors)

    def test_missing_component_fields_is_error(self, db):
        spec = {
            "topology": "x",
            "components": [{"role": "regulator", "mpn": "AMS1117-3.3"}],
        }
        report = DesignValidator(db).validate(spec, REQUIREMENTS)
        assert any(i.code == "SPEC_COMPONENT_MISSING_FIELDS" for i in report.errors)

    def test_unknown_mpn_is_error_and_drives_repair_text(self, db):
        spec = {
            "topology": "x",
            "components": [
                {
                    "role": "mystery",
                    "mpn": "TOTALLY-FAKE-999",
                    "value": "1",
                    "package": "0805",
                }
            ],
        }
        report = DesignValidator(db).validate(spec, REQUIREMENTS)
        assert any(i.code == "MPN_UNKNOWN" for i in report.errors)
        feedback = report.feedback()
        assert "TOTALLY-FAKE-999" in feedback
        assert "ERROR" in feedback

    def test_feedback_is_bounded(self, db):
        spec = {
            "topology": "x",
            "components": [
                {"role": "mystery", "mpn": f"FAKE-{i}", "value": "1", "package": "0805"}
                for i in range(40)
            ],
        }
        report = DesignValidator(db).validate(spec, REQUIREMENTS)
        assert len(report.feedback(max_issues=5).splitlines()) <= 5

    def test_erc_errors_surface_as_validation_errors(self, db):
        """An LED with no resistor must be reported, not silently accepted."""
        spec = {
            "topology": "led",
            "components": [
                {
                    "role": "led",
                    "mpn": "LTST-C190KGKT",
                    "value": "Green",
                    "package": "0805",
                },
                {
                    "role": "resistor",
                    "mpn": "RC0805FR-07330RL",
                    "value": "330",
                    "package": "0805",
                },
            ],
            "connections": [
                {"from": "D1.A", "to": "D1.K", "net": "SHORT"},
                {"from": "R1.1", "to": "R1.2", "net": "OPEN"},
            ],
        }
        report = DesignValidator(db).validate(spec, REQUIREMENTS)
        assert report.valid is False
        assert any(i.code == "ERC005_LED_WITHOUT_RESISTOR" for i in report.errors)


class TestSpecShape:
    def test_accepts_mapping_like_components(self):
        """ComponentSpec objects are mapping-like and must validate."""

        class Fake:
            def __init__(self, **kw):
                self.__dict__.update(kw)

            def keys(self):
                return list(self.__dict__)

            def __getitem__(self, key):
                return self.__dict__[key]

            def get(self, key, default=None):
                return self.__dict__.get(key, default)

        spec = {
            "topology": "ldo",
            "components": [
                Fake(role="regulator", mpn="AMS1117-3.3", value="3.3V", package="SOT-223")
            ],
        }
        assert validate_spec_shape(spec) == []

    def test_rejects_non_mapping_spec(self):
        issues = validate_spec_shape("just a string")
        assert any(i.code == "SPEC_NOT_OBJECT" for i in issues)

class TestConnectionInference:
    """Pin inference must be safe, recorded, and never guess polarity."""

    def _build(self, db, connections):
        spec = dict(LDO_SPEC)
        spec["connections"] = connections
        return CircuitIRBuilder(db).build(spec, REQUIREMENTS)

    def test_remaining_free_pin_is_used(self, db):
        """If pin 1 of a resistor is on VOUT, a pinless link must mean pin 2."""
        _, report = self._build(db, [
            {"from": "U1.VOUT", "to": "R1.1", "net": "VOUT"},
            {"from": "R1", "to": "D1.A", "net": "LED_A"},
        ])
        # R1 pin 2 (not pin 1) should be on LED_A.
        assert ("R1", "2") in [
            (p["ref"], p["pin"]) for p in _.nets["LED_A"].connected_pins
        ]
        assert any("remaining free pin" in n for n in report.notes)

    def test_polarised_part_is_never_guessed(self, db):
        """An LED without a pin must be reported, not silently wired."""
        _, report = self._build(db, [{"from": "R1.2", "to": "D1", "net": "X"}])
        assert any("D1" in entry for entry in report.skipped_connections)

    def test_two_terminal_passive_is_inferred_and_noted(self, db):
        _, report = self._build(db, [
            {"from": "U1.VIN", "to": "C1", "net": "VIN"},
        ])
        assert any("C1" in n and "assumed pin" in n for n in report.notes)

    def test_unknown_component_is_still_an_error(self, db):
        _, report = self._build(db, [{"from": "D9.A", "to": "C1.1", "net": "X"}])
        assert any("D9" in entry for entry in report.skipped_connections)
