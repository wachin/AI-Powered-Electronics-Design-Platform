"""
Tests for per-net trace widths and the KiCad net classes that carry them.

The defect these cover: the generated project had no net classes at all, so
KiCad fell back to its built-in 0.2 mm Default class and FreeRouting routed a 1 A
regulator output at 0.2 mm — about 0.74 A of capacity. The project file *looked*
like it set a width, which is what made it hard to notice.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core.circuit_ir import CircuitIR, Component, ComponentType, Net, Point2D
from src.generators.kicad_generator import KiCadGenerator
from src.pcb.netclasses import (
    DEFAULT_CLASS,
    HIGH_POWER_CLASS,
    HIGH_POWER_THRESHOLD_A,
    MIN_TRACE_WIDTH_MM,
    POWER_CLASS,
    SIGNAL_CLASS,
    build_net_settings,
    class_for_current,
    current_capacity_a,
    describe_netclasses,
    netclass_assignments,
    trace_width_mm,
    width_shortfalls,
)


class TestIPC2221:
    """
    The formula is the reason a width is what it is, so it is checked against
    published values rather than against itself.
    """

    @pytest.mark.parametrize(
        "current_a,expected_mm",
        [
            (1.0, 0.300),
            (2.0, 0.781),
            (3.0, 1.367),
        ],
    )
    def test_matches_published_external_widths(self, current_a, expected_mm):
        """1 oz copper, 10 °C rise, outer layer."""
        assert trace_width_mm(current_a) == pytest.approx(expected_mm, abs=0.005)

    @pytest.mark.parametrize(
        "current_a,expected_mm",
        [
            (1.0, 0.781),
            (2.0, 2.033),
        ],
    )
    def test_matches_published_internal_widths(self, current_a, expected_mm):
        """
        An inner trace cannot dissipate heat into air, so it needs about twice
        the copper. Using the external width on a four-layer board is the
        mistake this guards against.
        """
        assert trace_width_mm(current_a, external=False) == pytest.approx(
            expected_mm, abs=0.005
        )

    def test_capacity_is_the_inverse_of_the_width(self):
        """
        Checked only above the minimum width. Below it the width is clamped,
        which deliberately gives more capacity than asked for — see the next test.
        """
        for current in (1.0, 1.5, 2.5):
            width = trace_width_mm(current)
            assert current_capacity_a(width) == pytest.approx(current, rel=1e-3)

    def test_small_currents_get_more_capacity_than_they_need(self):
        """
        The clamp is one-sided on purpose: asking for 0.5 A must not produce a
        0.15 mm trace that no cheap board house will etch reliably.
        """
        width = trace_width_mm(0.5)
        assert width == MIN_TRACE_WIDTH_MM
        assert current_capacity_a(width) > 0.5

    def test_heavier_copper_needs_less_width(self):
        assert trace_width_mm(2.0, copper_oz=2.0) < trace_width_mm(2.0, copper_oz=1.0)

    def test_a_larger_temperature_rise_allows_a_narrower_trace(self):
        assert trace_width_mm(2.0, temperature_rise_c=20) < trace_width_mm(2.0)

    def test_zero_current_returns_the_minimum_not_zero(self):
        """A trace is still a trace."""
        assert trace_width_mm(0.0) == MIN_TRACE_WIDTH_MM

    @pytest.mark.parametrize(
        "kwargs",
        [{"copper_oz": 0}, {"temperature_rise_c": 0}, {"copper_oz": -1}],
    )
    def test_nonsense_inputs_are_rejected(self, kwargs):
        with pytest.raises(ValueError):
            trace_width_mm(1.0, **kwargs)


class TestClassChoice:
    def test_the_power_class_covers_the_platforms_rails(self):
        """
        This platform's designs regulate up to about 1 A. 0.6 mm carries 1.65 A
        on outer copper, so there is margin without wasting board area.
        """
        assert POWER_CLASS.capacity_a() > 1.5
        assert trace_width_mm(1.0) <= POWER_CLASS.track_width

    def test_the_signal_class_is_not_thinner_than_the_platform_minimum(self):
        assert SIGNAL_CLASS.track_width >= MIN_TRACE_WIDTH_MM
        assert DEFAULT_CLASS.track_width >= MIN_TRACE_WIDTH_MM

    def test_a_large_current_gets_the_high_power_class(self):
        assert class_for_current(HIGH_POWER_THRESHOLD_A + 0.1).name == "PWR_HI"

    def test_a_small_current_gets_the_power_class(self):
        assert class_for_current(0.5).name == "PWR"

    def test_zero_current_gets_the_signal_class(self):
        assert class_for_current(0.0).name == "SIG"

    def test_a_multilayer_board_always_uses_the_wider_class(self):
        """
        The same net may route on an inner layer, where the width carries half
        the current. A single width per class means sizing for the worse case.
        """
        assert class_for_current(0.2, layers=4).name == "PWR_HI"


class TestNetclassAssignments:
    def net(self, name, is_power=False, voltage=None):
        return Net(name=name, is_power=is_power, voltage=voltage)

    def test_ground_is_a_power_net_even_when_not_flagged(self):
        """
        The templates mark GND as a power net, but an LLM-authored spec may not.
        Ground carries the return current of every rail, so it is the last net
        that should get a thin trace.
        """
        assignments = netclass_assignments([self.net("GND")])
        assert assignments["GND"] == "PWR"

    @pytest.mark.parametrize("name", ["GND", "Ground", "VSS", "0V"])
    def test_ground_spellings_are_recognised(self, name):
        assert netclass_assignments([self.net(name)])[name] == "PWR"

    def test_a_flagged_power_net_with_no_declared_current_is_still_power(self):
        """
        Falling back to the signal class here would give a rail a 0.25 mm trace
        — the exact failure this module exists to prevent.
        """
        assignments = netclass_assignments([self.net("VIN", is_power=True)])
        assert assignments["VIN"] == "PWR"

    def test_signal_nets_get_the_signal_class(self):
        assignments = netclass_assignments([self.net("LED_A")])
        assert assignments["LED_A"] == "SIG"

    def test_a_declared_current_above_the_threshold_widens_the_class(self):
        net = self.net("VBUS", is_power=True)
        domains = {"VBUS": {"max_current_ma": 3000}}
        assert netclass_assignments([net], domains)["VBUS"] == "PWR_HI"

    def test_a_domain_is_matched_by_voltage_when_the_names_differ(self):
        """
        A design rarely names a rail and its power domain the same thing: the
        templates call the 5 V domain "5V_Domain" while the net is "VIN".
        """
        net = self.net("VIN", is_power=True, voltage=5.0)
        domains = {"5V_Domain": {"voltage": 5.0, "max_current_ma": 2000}}
        assert netclass_assignments([net], domains)["VIN"] == "PWR_HI"

    def test_an_unmatched_domain_does_not_widen_the_class(self):
        net = self.net("VIN", is_power=True, voltage=5.0)
        domains = {"12V_Domain": {"voltage": 12.0, "max_current_ma": 5000}}
        assert netclass_assignments([net], domains)["VIN"] == "PWR"

    def test_unnamed_nets_are_skipped_rather_than_guessed(self):
        assert netclass_assignments([self.net("")]) == {}

    def test_plain_strings_are_accepted(self):
        assert netclass_assignments(["GND", "OUT"]) == {"GND": "PWR", "OUT": "SIG"}


class TestNetSettingsBlock:
    def test_default_is_first_with_the_highest_priority(self):
        """KiCad expects the Default class first, and gives it the top priority."""
        settings = build_net_settings({"GND": "PWR"})
        assert settings["classes"][0]["name"] == "Default"
        assert settings["classes"][0]["priority"] == 2147483647

    def test_only_the_classes_in_use_are_declared(self):
        settings = build_net_settings({"GND": "PWR", "OUT": "SIG"})
        names = {c["name"] for c in settings["classes"]}
        assert names == {"Default", "PWR", "SIG"}
        assert "PWR_HI" not in names

    def test_every_class_carries_the_fields_kicad_writes(self):
        settings = build_net_settings({"GND": "PWR"})
        for cls in settings["classes"]:
            for field_name in (
                "name", "priority", "track_width", "clearance",
                "via_diameter", "via_drill", "diff_pair_width",
            ):
                assert field_name in cls, field_name

    def test_meta_version_is_the_one_kicad_9_expects(self):
        assert build_net_settings({"GND": "PWR"})["meta"] == {"version": 4}

    def test_nets_in_the_default_class_are_not_listed_as_assignments(self):
        settings = build_net_settings({"GND": "PWR", "OUT": "Default"})
        assert settings["netclass_assignments"] == {"GND": "PWR"}

    def test_an_undeclared_class_is_not_assigned(self):
        """A reference to a class that does not exist would be a broken project."""
        settings = build_net_settings({"GND": "NOT_A_CLASS"})
        assert settings["netclass_assignments"] is None

    def test_assignments_are_explicit_rather_than_regex_patterns(self):
        """
        Net names are not regex-safe: "+5V" and "Net-(D1-K)" would have to be
        escaped, and an escaping mistake silently classifies the wrong net.
        """
        settings = build_net_settings({"+5V": "PWR", "Net-(D1-K)": "SIG"})
        assert settings["netclass_patterns"] == []
        assert settings["netclass_assignments"]["+5V"] == "PWR"


class TestDescribe:
    def test_states_the_width_and_what_it_carries(self):
        lines = describe_netclasses({"GND": "PWR", "OUT": "SIG"})
        power = next(line for line in lines if line.startswith("PWR"))
        assert "0.6 mm" in power
        assert "1.65 A" in power

    def test_omits_classes_that_are_not_used(self):
        lines = describe_netclasses({"OUT": "SIG"})
        assert all(not line.startswith("PWR") for line in lines)


class TestWidthShortfalls:
    def test_a_narrow_routed_net_is_reported(self):
        """
        FreeRouting was observed narrowing two segments of a 0.6 mm power net to
        0.45 mm. That still carries about 1.2 A, but it is not what the design
        was checked against, so it is reported.
        """
        warnings = width_shortfalls({"VOUT": 0.45, "LED_A": 0.25}, {"VOUT": "PWR", "LED_A": "SIG"})
        assert len(warnings) == 1
        assert "VOUT" in warnings[0]
        assert "0.45" in warnings[0]

    def test_a_compliant_board_produces_no_warnings(self):
        assert width_shortfalls({"VOUT": 0.6, "LED_A": 0.25}, {"VOUT": "PWR", "LED_A": "SIG"}) == []

    def test_an_unrouted_net_is_not_a_warning(self):
        """No tracks is a routing failure, reported elsewhere."""
        assert width_shortfalls({}, {"VOUT": "PWR"}) == []

    def test_a_wider_trace_is_fine(self):
        assert width_shortfalls({"VOUT": 0.8}, {"VOUT": "PWR"}) == []


def make_circuit(with_components: bool = False) -> CircuitIR:
    """
    A 5 V to 3.3 V regulator with an indicator LED, as the template builds it.

    ``with_components`` adds real components with pins on the nets. It matters
    for the DSN check: a net class whose nets have no pads on the board is
    dropped from the exported DSN, so a circuit of bare nets proves nothing about
    what reaches the router.
    """
    circuit = CircuitIR(name="ldo", description="test")
    for net_name, voltage, is_power in (
        ("VIN", 5.0, True),
        ("VOUT", 3.3, True),
        ("GND", 0.0, True),
        ("LED_A", None, False),
    ):
        circuit.get_or_create_net(net_name, is_power=is_power, voltage=voltage)
    circuit.power_domains["5V_Domain"] = type(
        "D", (), {"voltage": 5.0, "max_current_ma": 1000}
    )()
    circuit.power_domains["3V3_Domain"] = type(
        "D", (), {"voltage": 3.3, "max_current_ma": 1000}
    )()

    if not with_components:
        return circuit

    u1 = Component(
        ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:AMS1117-3.3", mpn="AMS1117-3.3", package="SOT-223",
    )
    u1.add_pin("1", "GND")
    u1.add_pin("2", "VO")
    u1.add_pin("3", "VI")
    circuit.add_component(u1)

    r1 = Component(
        ref="R1", value="330", component_type=ComponentType.RESISTOR,
        footprint="Resistor_SMD:R_0805_2012Metric", symbol="Device:R",
        mpn="", package="0805",
    )
    r1.add_pin("1", "1")
    r1.add_pin("2", "2")
    circuit.add_component(r1)

    d1 = Component(
        ref="D1", value="Green", component_type=ComponentType.LED,
        footprint="LED_SMD:LED_0805_2012Metric", symbol="Device:LED",
        mpn="", package="0805",
    )
    d1.add_pin("1", "K")
    d1.add_pin("2", "A")
    circuit.add_component(d1)

    # Both representations have to be set: the PCB generator reads the net name
    # off each pin (`Pin.connected_net`), while ERC and the netlist read the pin
    # list on each net (`Net.connected_pins`).
    for ref, pin, net_name in (
        ("U1", "3", "VIN"),
        ("U1", "2", "VOUT"),
        ("R1", "1", "VOUT"),
        ("R1", "2", "LED_A"),
        ("D1", "2", "LED_A"),
        ("U1", "1", "GND"),
        ("D1", "1", "GND"),
    ):
        circuit.components[ref].get_pin(pin).connected_net = net_name
        circuit.nets[net_name].connect(ref, pin)
    return circuit


class TestGeneratedProjectFile:
    def project(self, circuit=None) -> dict:
        generator = KiCadGenerator(circuit or make_circuit())
        return json.loads(generator.generate_project_config("design"))

    def test_the_project_declares_net_classes(self):
        """
        Without this block KiCad falls back to its built-in 0.2 mm Default class
        and the router never sees the widths.
        """
        project = self.project()
        assert "net_settings" in project
        assert project["net_settings"]["classes"]

    def test_power_and_signal_nets_are_separated(self):
        assignments = self.project()["net_settings"]["netclass_assignments"]
        assert assignments["GND"] == "PWR"
        assert assignments["VIN"] == "PWR"
        assert assignments["VOUT"] == "PWR"
        assert assignments["LED_A"] == "SIG"

    def test_a_power_class_wider_than_the_default_exists(self):
        classes = {c["name"]: c for c in self.project()["net_settings"]["classes"]}
        assert classes["PWR"]["track_width"] > classes["Default"]["track_width"]

    def test_the_rationale_is_recorded(self):
        """A width with no stated capacity is a number the reader has to trust."""
        project = self.project()
        rationale = project["ai_electronics_design"]["netclass_rationale"]
        assert any("A on 1 oz copper" in line for line in rationale)

    def test_the_interactive_default_matches_the_default_class(self):
        project = self.project()
        defaults = project["board"]["design_settings"]["defaults"]
        assert defaults["track_width"] == DEFAULT_CLASS.track_width

    def test_a_circuit_with_no_nets_still_produces_a_valid_project(self):
        project = self.project(CircuitIR(name="empty", description=""))
        assert project["net_settings"]["classes"][0]["name"] == "Default"


# ---------------------------------------------------------------------------
# Verification against KiCad itself
# ---------------------------------------------------------------------------


def _pcbnew_python() -> str | None:
    """An interpreter with KiCad's pcbnew bindings, if there is one."""
    from src.agents.mcp_registry import find_pcbnew_python

    try:
        return find_pcbnew_python()
    except Exception:  # pragma: no cover - defensive
        return None


needs_pcbnew = pytest.mark.skipif(
    _pcbnew_python() is None,
    reason="KiCad's pcbnew Python bindings are not available",
)


@needs_pcbnew
class TestKiCadReadsTheNetClasses:
    """
    The end-to-end check: KiCad itself must read the classes out of the project
    file and put the widths into the Specctra DSN the router reads.
    """

    def _generate_and_export(self, tmp_path: Path):
        circuit = make_circuit(with_components=True)
        generator = KiCadGenerator(circuit)
        files = generator.export_project(tmp_path, "netclass_test")

        script = f"""
import json, pcbnew
board = pcbnew.LoadBoard({str(files['pcb'])!r})
settings = board.GetDesignSettings()
effective = {{}}
for net in ("GND", "VIN", "VOUT", "LED_A"):
    cls = settings.m_NetSettings.GetEffectiveNetClass(net)
    if cls is not None:
        effective[net] = {{"class": cls.GetName(), "width": cls.GetTrackWidth() / 1e6}}
dsn = {str(tmp_path / 'out.dsn')!r}
ok = pcbnew.ExportSpecctraDSN(board, dsn)
print("RESULT " + json.dumps({{"ok": bool(ok), "effective": effective}}))
"""
        result = subprocess.run(
            [_pcbnew_python(), "-c", script],
            capture_output=True, text=True, timeout=180,
        )
        payload = None
        for line in (result.stdout or "").splitlines():
            if line.startswith("RESULT "):
                payload = json.loads(line[len("RESULT "):])
        assert payload is not None, f"pcbnew produced no result: {result.stderr[:400]}"
        return files, payload

    def test_effective_classes_come_from_the_project_file(self, tmp_path):
        _files, payload = self._generate_and_export(tmp_path)
        effective = payload["effective"]
        assert effective["GND"]["class"] == "PWR"
        assert effective["VIN"]["class"] == "PWR"
        assert effective["VOUT"]["class"] == "PWR"
        assert effective["LED_A"]["class"] == "SIG"
        assert effective["VOUT"]["width"] == pytest.approx(0.6)
        assert effective["LED_A"]["width"] == pytest.approx(0.25)

    def test_the_dsn_carries_the_widths_to_the_router(self, tmp_path):
        """
        This is the file FreeRouting routes from. If the widths are not here,
        they are not used, however correct the project file looks.
        """
        files, payload = self._generate_and_export(tmp_path)
        if not payload["ok"]:
            pytest.skip("this KiCad build declined to export a DSN")
        dsn = (tmp_path / "out.dsn").read_text(errors="replace")
        assert "(class PWR" in dsn
        assert "(class SIG" in dsn
        assert "(width 600)" in dsn
        assert "(width 250)" in dsn
        # The power class must list the power nets, or the rule applies to none.
        power_line = next(line for line in dsn.splitlines() if "(class PWR" in line)
        for net in ("GND", "VIN", "VOUT"):
            assert net in power_line
