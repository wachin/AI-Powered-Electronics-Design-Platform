"""
An electrical review of a finished design, with numbers.

Why this exists
---------------
The generator already *computed* the numbers and then refused to use them. For
the reference 5 V → 3.3 V, 1 A regulator it emitted::

    design_notes: ["LDO dropout: 1.7V", "Power dissipation: 1.70W", ...]
    warnings:     ["Check thermal dissipation for high current",
                   "Verify dropout voltage at max current"]

It knew it would dissipate 1.7 W in a SOT-223 and asked the reader to check
whether that is acceptable. It is not a small question: 1.7 W in a SOT-223 with a
junction limit of 150 °C needs a package-and-copper path better than about
60 °C/W to survive a 25 °C room. A design that heats itself past its limit works
on the bench for a minute and fails in the enclosure.

What this module does and does not do
-------------------------------------
It computes what can be computed exactly from the design and the catalogue:
power dissipation, dropout headroom, resistor dissipation, capacitor voltage
stress, and the LED operating point. Those are arithmetic on numbers that are
either in the circuit specification or in the catalogue attributes.

It does **not** invent a thermal resistance. ``θJA`` depends on the package, the
copper area, the number of layers and the airflow, and this platform controls
none of those. Publishing an invented value would be exactly the
looks-real-but-is-not failure this project keeps finding in its own parts data.
Instead the thermal check reports the dissipation, the junction limit, and the
**θJA the design requires** — the number to look up in the datasheet — and only
returns a verdict when the physics is unambiguous either way.
"""

from __future__ import annotations


from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.components.parameters import parse_conditional, parse_temperature_range

# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

PASS = "pass"
WARN = "warn"
FAIL = "fail"
UNKNOWN = "unknown"

_SEVERITY_ORDER = {FAIL: 0, WARN: 1, UNKNOWN: 2, PASS: 3}


@dataclass
class Finding:
    """
    One result of the review.

    ``detail`` carries the arithmetic. A finding without the numbers behind it is
    an opinion, and the whole point of this module is to replace opinions with
    arithmetic the reader can check.
    """

    rule_id: str
    severity: str
    subject: str
    message: str
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_problem(self) -> bool:
        return self.severity in (FAIL, WARN)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "subject": self.subject,
            "message": self.message,
            "detail": self.detail,
        }

    def render(self) -> str:
        marker = {FAIL: "FAIL", WARN: "WARN", PASS: "ok", UNKNOWN: "?"}[self.severity]
        return f"[{marker}] {self.subject}: {self.message}"


@dataclass
class DesignReview:
    """Every finding from a review, worst first."""

    findings: List[Finding] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)

    @property
    def failures(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == FAIL]

    @property
    def warnings(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == WARN]

    @property
    def unknowns(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == UNKNOWN]

    @property
    def passed(self) -> bool:
        """Whether nothing was found that should stop a build."""
        return not self.failures

    def sorted_findings(self) -> List[Finding]:
        return sorted(self.findings, key=lambda f: _SEVERITY_ORDER[f.severity])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.sorted_findings()],
            "assumptions": list(self.assumptions),
            "failures": len(self.failures),
            "warnings": len(self.warnings),
            "unknowns": len(self.unknowns),
        }

    def summary(self) -> str:
        return (
            f"{len(self.failures)} failure(s), {len(self.warnings)} warning(s), "
            f"{len(self.unknowns)} unchecked"
        )


# ---------------------------------------------------------------------------
# Known LED forward voltages
# ---------------------------------------------------------------------------

# Forward voltage by colour, as a *range*, because it is one: a green LED is
# anywhere from about 1.9 V to 2.6 V depending on the chemistry, and the current
# through it depends on that. The range is used to report a current range rather
# than a single falsely precise number.
_LED_FORWARD_VOLTAGE: Dict[str, Tuple[float, float]] = {
    "infrared": (1.1, 1.5),
    "red": (1.8, 2.2),
    "orange": (1.9, 2.2),
    "yellow": (1.9, 2.3),
    "amber": (1.9, 2.3),
    "green": (2.0, 2.6),
    "emerald": (2.6, 3.0),
    "blue": (2.8, 3.4),
    "white": (2.8, 3.4),
    "uv": (3.1, 3.6),
}

# Where the catalogue's illumination colour is a phrase rather than a word.
_COLOUR_ALIASES: Dict[str, str] = {
    "ir": "infrared",
    "wt": "white",
    "wh": "white",
    "rd": "red",
    "gn": "green",
    "bl": "blue",
    "yl": "yellow",
    "or": "orange",
    "yg": "yellow",
    "emerald green": "emerald",
    "warm white": "white",
    "cool white": "white",
    "ice blue": "blue",
}


def forward_voltage_for_colour(colour: str) -> Optional[Tuple[float, float]]:
    """
    The forward-voltage range for an LED colour, or ``None`` when unknown.

    ``None`` is the honest answer for a colour the table does not know, and the
    caller reports the check as unchecked rather than assuming 2 V.

    Matching is deliberately ordered: an exact match first, then full colour
    names, then abbreviations of three characters or more. A two-letter
    abbreviation like ``IR`` matches only as a whole word, because as a substring
    it appears inside colours that have nothing to do with infrared.
    """
    if not colour:
        return None
    text = str(colour).strip().lower()

    if text in _LED_FORWARD_VOLTAGE:
        return _LED_FORWARD_VOLTAGE[text]
    if text in _COLOUR_ALIASES:
        return _LED_FORWARD_VOLTAGE[_COLOUR_ALIASES[text]]

    # Longest first, so "emerald green" wins over "green".
    for name in sorted(_LED_FORWARD_VOLTAGE, key=len, reverse=True):
        if name in text:
            return _LED_FORWARD_VOLTAGE[name]
    for alias in sorted(_COLOUR_ALIASES, key=len, reverse=True):
        if len(alias) < 3:
            continue
        if alias in text:
            return _LED_FORWARD_VOLTAGE[_COLOUR_ALIASES[alias]]
    return None


# ---------------------------------------------------------------------------
# Thermal budget
# ---------------------------------------------------------------------------

# A package cannot beat these, whatever the copper: they are single-digit watts
# in still air with no heatsink. Used only to make a verdict when the answer does
# not depend on the unknown.
# The thresholds below are heuristics about *package classes*, deliberately not
# datasheet numbers for a specific part. They exist so the review can give a
# verdict when the physics does not depend on the unknown:
#
#   * nothing small reaches 20 °C/W without a heatsink;
#   * below about 50 °C/W no ordinary surface-mount package qualifies either —
#     a package with a soldered thermal tab is the only thing that gets close,
#     and a bare SOT-23 is far worse. A design that needs better than this is
#     reported as a problem, because "check theta_JA" would be answered "no".
#   * above 250 °C/W every package manages it.
_IMPOSSIBLE_THETA_JA = 20.0
_IMPLAUSIBLE_THETA_JA = 50.0
_TRIVIAL_THETA_JA = 250.0


def review_linear_regulator_thermal(
    subject: str,
    vin_max: float,
    vout: float,
    iout: float,
    quiescent_current: float = 0.0,
    tj_max: Optional[float] = None,
    ambient_c: float = 25.0,
) -> Finding:
    """
    Size the thermal problem of a linear regulator, and say what it demands.

    The dissipation is exact::

        P = (Vin - Vout) · Iout + Vin · Iq

    What cannot be known is the junction-to-ambient path, so the finding reports
    the **required** ``θJA`` — the figure to look up in the part's datasheet — and
    only gives a verdict when the requirement is outside the range any package
    could meet either way.

    Args:
        subject: The component reference, for the message.
        vin_max: The highest input voltage the regulator will see.
        vout: Regulated output voltage.
        iout: Output current at which the design is specified.
        quiescent_current: The regulator's own supply current, if known.
        tj_max: Junction temperature limit, in °C. When absent the check reports
            the budget without a verdict, because the limit is the constraint.
        ambient_c: The ambient the design is expected to work in.
    """
    drop = max(vin_max - vout, 0.0)
    dissipation = drop * iout + vin_max * max(quiescent_current, 0.0)
    detail: Dict[str, Any] = {
        "vin_max": vin_max,
        "vout": vout,
        "iout": iout,
        "voltage_drop": round(drop, 4),
        "power_w": round(dissipation, 4),
        "ambient_c": ambient_c,
    }

    if dissipation <= 0:
        return Finding(
            rule_id="REVIEW_THERMAL",
            severity=PASS,
            subject=subject,
            message=(
                f"No dissipation to speak of: the regulator drops "
                f"{drop:.2f} V, which with no load is {dissipation:.3f} W."
            ),
            detail=detail,
        )

    if tj_max is None:
        # State the requirement for both limits in common use, so the reader can
        # match whichever their part's datasheet quotes.
        requirements = {
            limit: (limit - ambient_c) / dissipation for limit in (125, 150)
        }
        detail["required_theta_ja_by_limit"] = {
            str(limit): round(value, 1) for limit, value in requirements.items()
        }
        detail["required_theta_ja_at_150c"] = round(requirements[150], 1)

        # An absent limit does not make an impossible design possible. If the
        # requirement is below what any surface-mount package achieves *even for
        # the most permissive common limit*, that is a problem whatever the part's
        # datasheet says — and saying so needs no invented figure.
        if requirements[150] < _IMPLAUSIBLE_THETA_JA:
            detail["limit_used_c"] = 150
            return Finding(
                rule_id="REVIEW_THERMAL",
                severity=FAIL,
                subject=subject,
                message=(
                    f"Dissipates {dissipation:.2f} W ({drop:.2f} V at {iout:g} A). "
                    f"The junction temperature limit for this part is not in the "
                    f"catalog, but it does not need to be: even for a permissive "
                    f"150 °C limit at {ambient_c:g} °C ambient this would need a "
                    f"thermal path better than {requirements[150]:.0f} °C/W, and no "
                    f"ordinary surface-mount package achieves that without a "
                    f"thermal pad or a heatsink. Reduce the input voltage, reduce "
                    f"the current, or use a switching regulator."
                ),
                detail=detail,
            )

        return Finding(
            rule_id="REVIEW_THERMAL",
            severity=UNKNOWN,
            subject=subject,
            message=(
                f"Dissipates {dissipation:.2f} W ({drop:.2f} V at {iout:g} A). The "
                f"junction temperature limit for this part is not in the catalog, "
                f"so the required thermal path cannot be judged. At "
                f"{ambient_c:g} °C ambient it must be better than "
                f"{requirements[150]:.0f} °C/W for a 150 °C limit, "
                f"or {requirements[125]:.0f} °C/W for a 125 °C one."
            ),
            detail=detail,
        )

    allowed_rise = tj_max - ambient_c
    required_theta_ja = allowed_rise / dissipation
    detail["tj_max_c"] = tj_max
    detail["allowed_rise_c"] = round(allowed_rise, 2)
    detail["required_theta_ja"] = round(required_theta_ja, 2)
    # The ambient at which this design reaches the limit, for a few thermal paths
    # spanning what small packages actually achieve.
    detail["max_ambient_c_by_theta_ja"] = {
        str(theta): round(tj_max - dissipation * theta, 1)
        for theta in (50, 100, 150, 200)
    }

    if required_theta_ja < _IMPOSSIBLE_THETA_JA:
        return Finding(
            rule_id="REVIEW_THERMAL",
            severity=FAIL,
            subject=subject,
            message=(
                f"Dissipates {dissipation:.2f} W ({drop:.2f} V at {iout:g} A). "
                f"Staying under a {tj_max:g} °C junction at {ambient_c:g} °C ambient "
                f"needs a thermal path better than {required_theta_ja:.0f} °C/W, "
                f"which no package achieves without a heatsink. Reduce the input "
                f"voltage, reduce the current, or use a switching regulator."
            ),
            detail=detail,
        )

    if required_theta_ja < _IMPLAUSIBLE_THETA_JA:
        # The junction passes its limit at the stated ambient for any thermal path
        # a surface-mount package provides. That is a design problem, not a
        # missing figure, and the arithmetic is shown so it can be checked.
        ambient_at_50 = tj_max - dissipation * _IMPLAUSIBLE_THETA_JA
        if ambient_at_50 <= 0:
            # A negative ambient is the arithmetic talking, not a temperature
            # anyone works at: it means the limit is exceeded even in a freezer.
            worst_case = (
                "at 50 °C/W, already better than most surface-mount packages, the "
                "junction would exceed its limit even at 0 °C ambient"
            )
        else:
            worst_case = (
                f"at 50 °C/W, already better than most, the junction reaches its "
                f"limit at just {ambient_at_50:.0f} °C ambient"
            )
        detail["limit_used_c"] = tj_max
        return Finding(
            rule_id="REVIEW_THERMAL",
            severity=FAIL,
            subject=subject,
            message=(
                f"Dissipates {dissipation:.2f} W ({drop:.2f} V at {iout:g} A). "
                f"Staying under a {tj_max:g} °C junction at {ambient_c:g} °C ambient "
                f"would need a thermal path better than {required_theta_ja:.0f} °C/W, "
                f"and no ordinary surface-mount package achieves that without a "
                f"thermal pad or a heatsink — {worst_case}. Reduce the input "
                f"voltage, reduce the current, or use a switching regulator."
            ),
            detail=detail,
        )

    if required_theta_ja > _TRIVIAL_THETA_JA:
        return Finding(
            rule_id="REVIEW_THERMAL",
            severity=PASS,
            subject=subject,
            message=(
                f"Dissipates {dissipation:.2f} W ({drop:.2f} V at {iout:g} A), "
                f"which any package handles: it needs only "
                f"{required_theta_ja:.0f} °C/W to stay under {tj_max:g} °C."
            ),
            detail=detail,
        )

    return Finding(
        rule_id="REVIEW_THERMAL",
        severity=WARN,
        subject=subject,
        message=(
            f"Dissipates {dissipation:.2f} W ({drop:.2f} V at {iout:g} A). Staying "
            f"under a {tj_max:g} °C junction at {ambient_c:g} °C ambient needs a "
            f"thermal path better than {required_theta_ja:.0f} °C/W. Check the "
            f"part's θJA with your copper area: at 100 °C/W the junction reaches "
            f"{tj_max - dissipation * 100:.0f} °C, which leaves "
            f"{tj_max - dissipation * 100 - ambient_c:.0f} °C of margin."
        ),
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Dropout
# ---------------------------------------------------------------------------


def review_dropout(
    subject: str,
    vin_min: float,
    vout: float,
    dropout_at_rated: Optional[float],
    rated_current: Optional[float],
    iout: float,
) -> Finding:
    """
    Check that the regulator has the input headroom it needs.

    The catalogue quotes dropout at one current, e.g. ``1.2V@(1A)``. Dropout falls
    as current falls, so the quoted figure is scaled linearly to the design
    current — an approximation, and one that is *optimistic* at very low current
    because the real curve flattens. It is labelled as an approximation rather
    than presented as the datasheet curve.
    """
    headroom = vin_min - vout
    detail: Dict[str, Any] = {
        "vin_min": vin_min,
        "vout": vout,
        "headroom_v": round(headroom, 3),
    }

    if dropout_at_rated is None:
        return Finding(
            rule_id="REVIEW_DROPOUT",
            severity=UNKNOWN,
            subject=subject,
            message=(
                f"No dropout figure is listed for this part, so the "
                f"{headroom:.2f} V of input headroom cannot be checked against "
                f"it. Look it up in the datasheet at {iout:g} A."
            ),
            detail=detail,
        )

    if rated_current and rated_current > 0 and iout < rated_current:
        dropout = dropout_at_rated * (iout / rated_current)
        approximation = (
            f"scaled from {dropout_at_rated:g} V at {rated_current:g} A"
        )
    else:
        dropout = dropout_at_rated
        approximation = f"quoted at {rated_current:g} A" if rated_current else "quoted"

    detail["dropout_v"] = round(dropout, 4)
    detail["dropout_basis"] = approximation
    margin = headroom - dropout
    detail["margin_v"] = round(margin, 4)

    if margin < 0:
        return Finding(
            rule_id="REVIEW_DROPOUT",
            severity=FAIL,
            subject=subject,
            message=(
                f"Not enough input headroom: {headroom:.2f} V available but the "
                f"regulator needs {dropout:.2f} V of dropout at {iout:g} A "
                f"({approximation}). It will not hold regulation — raise the "
                f"input voltage or lower the output."
            ),
            detail=detail,
        )

    if margin < 0.2:
        return Finding(
            rule_id="REVIEW_DROPOUT",
            severity=WARN,
            subject=subject,
            message=(
                f"Only {margin:.2f} V of dropout margin at {iout:g} A "
                f"({headroom:.2f} V available, {dropout:.2f} V needed, "
                f"{approximation}). Tolerance and temperature will eat that."
            ),
            detail=detail,
        )

    return Finding(
        rule_id="REVIEW_DROPOUT",
        severity=PASS,
        subject=subject,
        message=(
            f"{margin:.2f} V of dropout margin at {iout:g} A ({headroom:.2f} V "
            f"available, {dropout:.2f} V needed, {approximation})."
        ),
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Passives
# ---------------------------------------------------------------------------


def review_resistor_power(
    subject: str,
    resistance: Optional[float],
    current: float,
    rated_power: Optional[float],
    derating: float = 0.5,
) -> Finding:
    """
    Check a resistor's dissipation against what it is rated for.

    ``derating`` is the fraction of the rating the design is allowed to use.
    Halving it is the usual practice: a resistor run at its nominal rating
    drifts, and its value is printed on the part, not on the board.
    """
    detail: Dict[str, Any] = {"current_a": current}
    if resistance is None:
        return Finding(
            rule_id="REVIEW_RESISTOR_POWER",
            severity=UNKNOWN,
            subject=subject,
            message="The resistance is not known, so its dissipation cannot be computed.",
            detail=detail,
        )

    dissipation = current**2 * resistance
    detail["resistance_ohm"] = resistance
    detail["power_w"] = round(dissipation, 6)

    if rated_power is None:
        return Finding(
            rule_id="REVIEW_RESISTOR_POWER",
            severity=UNKNOWN,
            subject=subject,
            message=(
                f"Dissipates {_format_watts(dissipation)} (I²R with "
                f"{current * 1000:g} mA through {_format_ohms(resistance)}), but "
                f"the part's power rating is not in the catalog. Check it is at "
                f"least {_format_watts(dissipation / derating)}."
            ),
            detail=detail,
        )

    detail["rated_power_w"] = rated_power
    allowed = rated_power * derating
    detail["allowed_power_w"] = round(allowed, 6)

    if dissipation > rated_power:
        return Finding(
            rule_id="REVIEW_RESISTOR_POWER",
            severity=FAIL,
            subject=subject,
            message=(
                f"Over its rating: {_format_watts(dissipation)} in a "
                f"{_format_watts(rated_power)} resistor. Use a bigger package."
            ),
            detail=detail,
        )

    if dissipation > allowed:
        return Finding(
            rule_id="REVIEW_RESISTOR_POWER",
            severity=WARN,
            subject=subject,
            message=(
                f"Dissipates {_format_watts(dissipation)} in a "
                f"{_format_watts(rated_power)} part — more than half its rating. It "
                f"will run hot and drift; use a larger package."
            ),
            detail=detail,
        )

    return Finding(
        rule_id="REVIEW_RESISTOR_POWER",
        severity=PASS,
        subject=subject,
        message=(
            f"Dissipates {_format_watts(dissipation)} of a "
            f"{_format_watts(rated_power)} rating."
        ),
        detail=detail,
    )


def review_capacitor_voltage(
    subject: str,
    applied_voltage: float,
    rated_voltage: Optional[float],
    derating: float = 0.8,
) -> Finding:
    """
    Check a capacitor's voltage stress.

    Ceramic capacitors lose capacitance and reliability as the applied voltage
    approaches the rating, and the rating itself is quoted at 25 °C; running at
    80 % or less is standard practice.
    """
    detail: Dict[str, Any] = {
        "applied_v": applied_voltage,
        "derating": derating,
    }
    if rated_voltage is None:
        return Finding(
            rule_id="REVIEW_CAPACITOR_VOLTAGE",
            severity=UNKNOWN,
            subject=subject,
            message=(
                f"Sees {applied_voltage:g} V, but the part's voltage rating is not "
                f"in the catalog. It should be at least "
                f"{applied_voltage / derating:.1f} V."
            ),
            detail=detail,
        )

    detail["rated_v"] = rated_voltage
    allowed = rated_voltage * derating
    detail["allowed_v"] = round(allowed, 3)

    if applied_voltage > rated_voltage:
        return Finding(
            rule_id="REVIEW_CAPACITOR_VOLTAGE",
            severity=FAIL,
            subject=subject,
            message=(
                f"Over its voltage rating: {applied_voltage:g} V across a "
                f"{rated_voltage:g} V capacitor."
            ),
            detail=detail,
        )

    if applied_voltage > allowed:
        return Finding(
            rule_id="REVIEW_CAPACITOR_VOLTAGE",
            severity=WARN,
            subject=subject,
            message=(
                f"{applied_voltage:g} V across a {rated_voltage:g} V part is "
                f"{applied_voltage / rated_voltage:.0%} of its rating; keep it "
                f"under {derating:.0%}. Use the next voltage up."
            ),
            detail=detail,
        )

    return Finding(
        rule_id="REVIEW_CAPACITOR_VOLTAGE",
        severity=PASS,
        subject=subject,
        message=(
            f"{applied_voltage:g} V across a {rated_voltage:g} V part "
            f"({applied_voltage / rated_voltage:.0%} of rating)."
        ),
        detail=detail,
    )


# ---------------------------------------------------------------------------
# LEDs
# ---------------------------------------------------------------------------


def review_led_operating_point(
    subject: str,
    supply_voltage: float,
    series_resistance: Optional[float],
    colour: str,
    target_current: float = 0.01,
) -> Finding:
    """
    Compute the LED current from the series resistor, as a range.

    An LED's forward voltage is a range, not a number, so the current is a range
    too. Reporting a single figure would be false precision: a green LED that
    drops 2.0 V and one that drops 2.6 V pass very different currents through the
    same resistor, and both are "green".
    """
    detail: Dict[str, Any] = {
        "supply_v": supply_voltage,
        "colour": colour,
        "target_current_a": target_current,
    }
    forward = forward_voltage_for_colour(colour)
    if forward is None:
        return Finding(
            rule_id="REVIEW_LED_CURRENT",
            severity=UNKNOWN,
            subject=subject,
            message=(
                f"The forward voltage of a {colour!r} LED is not known, so the "
                f"current through it cannot be computed. Check the datasheet."
            ),
            detail=detail,
        )

    if not series_resistance:
        return Finding(
            rule_id="REVIEW_LED_CURRENT",
            severity=UNKNOWN,
            subject=subject,
            message="No series resistor, so the LED current cannot be computed.",
            detail=detail,
        )

    currents: List[float] = []
    for vf in forward:
        if supply_voltage <= vf:
            detail["forward_voltage_v"] = list(forward)
            return Finding(
                rule_id="REVIEW_LED_CURRENT",
                severity=FAIL,
                subject=subject,
                message=(
                    f"A {colour} LED needs {forward[0]:g}-{forward[1]:g} V but only "
                    f"{supply_voltage:g} V is available. It will not light."
                ),
                detail=detail,
            )
        currents.append((supply_voltage - vf) / series_resistance)

    low, high = min(currents), max(currents)
    detail["forward_voltage_v"] = list(forward)
    detail["resistance_ohm"] = series_resistance
    detail["current_a"] = [round(low, 5), round(high, 5)]
    detail["current_ma"] = [round(low * 1000, 2), round(high * 1000, 2)]

    if high > 0.02:
        return Finding(
            rule_id="REVIEW_LED_CURRENT",
            severity=WARN,
            subject=subject,
            message=(
                f"{low * 1000:.1f}-{high * 1000:.1f} mA through a {colour} LED "
                f"({series_resistance:g} Ω on {supply_voltage:g} V) — over the "
                f"usual 20 mA. Increase the resistor."
            ),
            detail=detail,
        )

    if high < 0.001:
        return Finding(
            rule_id="REVIEW_LED_CURRENT",
            severity=WARN,
            subject=subject,
            message=(
                f"Only {low * 1000:.2f}-{high * 1000:.2f} mA through a {colour} LED "
                f"({series_resistance:g} Ω on {supply_voltage:g} V). It will be "
                f"very dim; reduce the resistor."
            ),
            detail=detail,
        )

    return Finding(
        rule_id="REVIEW_LED_CURRENT",
        severity=PASS,
        subject=subject,
        message=(
            f"{low * 1000:.1f}-{high * 1000:.1f} mA through a {colour} LED "
            f"({series_resistance:g} Ω on {supply_voltage:g} V), against a "
            f"{target_current * 1000:g} mA target."
        ),
        detail=detail,
    )


def _format_watts(value: float) -> str:
    if value >= 1:
        return f"{value:.2f} W"
    if value >= 0.001:
        return f"{value * 1000:.1f} mW"
    return f"{value * 1e6:.0f} µW"


def _format_ohms(value: float) -> str:
    if value >= 1e6:
        return f"{value / 1e6:g} MΩ"
    if value >= 1e3:
        return f"{value / 1e3:g} kΩ"
    return f"{value:g} Ω"


# ---------------------------------------------------------------------------
# Reviewing a whole circuit
# ---------------------------------------------------------------------------


def _requirement(requirements: Any, name: str, default: float = 0.0) -> float:
    """Read a numeric requirement from a dict or an object."""
    if requirements is None:
        return default
    if isinstance(requirements, dict):
        value = requirements.get(name)
    else:
        value = getattr(requirements, name, None)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _net_name_of(circuit: Any, ref: str, pin: str) -> Optional[str]:
    """The net a given pin sits on, from the pin's own assignment."""
    component = circuit.components.get(ref)
    if component is None:
        return None
    target = component.get_pin(pin)
    if target is not None and target.connected_net:
        return target.connected_net
    # Fall back to the net's pin list, which the builder also maintains.
    for net in circuit.nets.values():
        for connection in net.connected_pins:
            if connection.get("ref") == ref and str(connection.get("pin")) == str(pin):
                return net.name
    return None


def _net_voltage(circuit: Any, net_name: Optional[str]) -> Optional[float]:
    """The voltage of a net, from the net itself or its power domain."""
    if not net_name:
        return None
    net = circuit.nets.get(net_name)
    if net is not None and isinstance(getattr(net, "voltage", None), (int, float)):
        return float(net.voltage)
    for domain in (getattr(circuit, "power_domains", None) or {}).values():
        voltage = (
            domain.get("voltage") if isinstance(domain, dict)
            else getattr(domain, "voltage", None)
        )
        if not isinstance(voltage, (int, float)):
            continue
        label = (
            domain.get("name") if isinstance(domain, dict) else getattr(domain, "name", "")
        ) or ""
        if net_name.upper() in str(label).upper() or str(label).upper() in net_name.upper():
            return float(voltage)
    return None


def _junction_limit_from_siblings(
    db: Any, mpn: str, exclude: Optional[str] = None
) -> Tuple[Optional[float], str]:
    """
    A junction temperature limit published for the same part number.

    The catalogue holds one row per manufacturer, and their datasheet summaries
    differ: one AMS1117 row says ``0℃~+150℃@(Tj)`` while another says
    ``-50℃~+140℃`` with no junction qualifier. Refusing the check because the
    first row is silent would hide a real thermal problem behind missing data.

    Returns ``(limit, description)``, or ``(None, "")`` when no row states one.
    Only an explicit ``@(Tj)`` range is accepted: an ambient range is a different
    limit and using it as a junction limit would understate the problem.
    """
    if db is None or not mpn:
        return (None, "")

    finder = getattr(db, "find_in_catalog", None)
    if finder is None:
        return (None, "")

    try:
        entries = finder(mpn) or []
    except Exception:  # pragma: no cover - defensive against DB quirks
        return (None, "")

    best, source = _best_junction_limit(entries, exclude)
    if best is not None:
        return (best, source)

    # Nothing for this exact part number. Variants of the same family often
    # publish it — the design asked for "AMS1117-3.3OE" and only "AMS1117-3.3"
    # states a junction limit — so the family is consulted and named.
    family = getattr(db, "find_family_in_catalog", None)
    if family is None:
        return (None, "")
    try:
        relatives = family(mpn) or []
    except Exception:  # pragma: no cover - defensive against DB quirks
        return (None, "")
    return _best_junction_limit(relatives, exclude, family_of=mpn)


def _best_junction_limit(
    entries: Any, exclude: Optional[str], family_of: str = ""
) -> Tuple[Optional[float], str]:
    """The lowest published junction limit among a set of catalogue entries."""
    best: Optional[float] = None
    source = ""
    for entry in entries:
        if exclude and getattr(entry, "lcsc_part", None) == exclude:
            continue
        attributes = _attributes(entry)
        parsed = parse_temperature_range(attributes.get("temperature_range"))
        if parsed is None or not parsed.is_junction or parsed.maximum is None:
            continue
        # The lowest published limit is the safe one to design against.
        if best is None or parsed.maximum < best:
            best = parsed.maximum
            label = f"{getattr(entry, 'lcsc_part', '?')} {getattr(entry, 'mpn', '')}".strip()
            if family_of and getattr(entry, "mpn", "") != family_of:
                label += f", in the same family as {family_of}"
            source = label
    return (best, source)


def _spec_for(db: Any, mpn: str) -> Any:
    """The catalogue entry for a part, or None."""
    if db is None or not mpn:
        return None
    try:
        return db.get_by_mpn(mpn)
    except Exception:  # pragma: no cover - defensive against DB quirks
        return None


def _attributes(spec: Any) -> Dict[str, Any]:
    return dict(getattr(spec, "attributes", None) or {}) if spec is not None else {}


# Attributes a check needs, so that a part missing all of them can be replaced by
# the catalogue part for the same value and package.
_RATING_KEYS = (
    "voltage",
    "power",
    "resistance",
    "dropout",
    "temperature_range",
    "quiescent_current",
    "illumination_color",
)


def _has_ratings(attributes: Dict[str, Any]) -> bool:
    return any(attributes.get(key) is not None for key in _RATING_KEYS)


def _review_attributes(
    db: Any, component: Any, spec: Any
) -> Tuple[Dict[str, Any], Optional[str], str]:
    """
    The ratings to review a component against, and where they came from.

    A design built from the component templates names parts whose ratings are
    absent — templates carry symbols and footprints, not datasheets. The part
    that will actually be built is the one the purchase list orders for the same
    value and package, so its ratings are used instead and the substitution is
    stated. Reviewing against data that does not exist would produce a page of
    "unknown" for a design that could have been checked.
    """
    attributes = _attributes(spec)
    resolved_mpn = str(getattr(spec, "mpn", "") or "")
    if _has_ratings(attributes) or db is None:
        return attributes, None, resolved_mpn

    value = str(getattr(component, "value", "") or "")
    package = str(getattr(component, "package", "") or "")
    kind = getattr(getattr(component, "component_type", None), "value", "")
    if not value:
        return attributes, None, resolved_mpn

    try:
        candidates = db.search(
            query=f"{value} {package}".strip(),
            category=kind or None,
            min_stock=1000,
            limit=3,
        )
    except Exception:  # pragma: no cover - defensive against DB quirks
        return attributes, None, resolved_mpn

    for candidate in candidates:
        if not getattr(candidate, "lcsc_part", None):
            continue
        candidate_attributes = _attributes(candidate)
        if _has_ratings(candidate_attributes):
            return (
                candidate_attributes,
                f"{candidate.lcsc_part} {candidate.mpn} "
                f"({candidate.package}) - the catalog part this value and package "
                f"resolves to",
                str(candidate.mpn or ""),
            )
    return attributes, None, resolved_mpn


def _value_number(text: Any) -> Optional[float]:
    """A resistance or capacitance parsed out of a component's value string."""
    from src.components.parameters import parse_value

    parsed = parse_value(text)
    return parsed.value if parsed else None


def review_circuit(
    circuit: Any,
    db: Any = None,
    requirements: Any = None,
    ambient_c: float = 25.0,
) -> DesignReview:
    """
    Run every applicable check over a finished circuit.

    Each check needs data that may or may not be present. Where it is missing the
    finding is ``UNKNOWN`` and says what to look up, rather than being dropped:
    a check that silently does not run is indistinguishable from a check that
    passed.
    """
    review = DesignReview()
    review.assumptions.append(
        f"The thermal budget assumes {ambient_c:g} °C ambient and still air. "
        f"Enclosed or hot environments are worse."
    )
    review.assumptions.append(
        "Junction-to-ambient thermal resistance is not assumed: each thermal "
        "finding states the value the design needs."
    )

    vin = _requirement(requirements, "input_voltage")
    vout = _requirement(requirements, "output_voltage")
    iout = _requirement(requirements, "output_current")

    for component in circuit.components.values():
        kind = getattr(getattr(component, "component_type", None), "value", "")
        spec = _spec_for(db, component.mpn or "")
        attributes, source, rating_mpn = _review_attributes(db, component, spec)
        if source:
            review.assumptions.append(
                f"{component.ref}: ratings taken from {source}."
            )
        label = f"{component.ref} ({component.mpn or component.value})"

        if kind in ("regulator_ldo", "regulator_ldo_adjustable") and vin and vout and iout:
            temperature = parse_temperature_range(attributes.get("temperature_range"))
            tj_max = None
            if temperature is not None and temperature.is_junction:
                tj_max = temperature.maximum
            else:
                # The catalogue lists the same part number several times, once per
                # manufacturer, and they do not all publish the same figures. A
                # sibling entry that states the junction limit is real data, so it
                # is used rather than declaring the check impossible.
                tj_max, limit_source = _junction_limit_from_siblings(
                    db,
                    rating_mpn or component.mpn or "",
                    exclude=getattr(spec, "lcsc_part", None),
                )
                if tj_max is not None:
                    review.assumptions.append(
                        f"{component.ref}: the rated part does not state a junction "
                        f"temperature limit; used {tj_max:g} °C from "
                        f"{limit_source}, a catalogue entry for the same part number."
                    )
            review.findings.append(
                review_linear_regulator_thermal(
                    label,
                    vin_max=vin,
                    vout=vout,
                    iout=iout,
                    quiescent_current=float(attributes.get("quiescent_current") or 0.0),
                    tj_max=tj_max,
                    ambient_c=ambient_c,
                )
            )
            dropout_raw = (attributes.get("raw") or {}).get("Voltage Dropout")
            dropout, dropout_at = parse_conditional(dropout_raw)
            if dropout is None:
                dropout = attributes.get("dropout")
            review.findings.append(
                review_dropout(
                    label,
                    vin_min=vin,
                    vout=vout,
                    dropout_at_rated=dropout,
                    rated_current=dropout_at,
                    iout=iout,
                )
            )

        elif kind == "resistor":
            resistance = _value_number(component.value) or attributes.get("resistance")
            current = _resistor_current(circuit, component.ref, attributes)
            review.findings.append(
                review_resistor_power(
                    label,
                    resistance=resistance,
                    current=current,
                    rated_power=attributes.get("power"),
                )
            )

        elif kind == "capacitor":
            net = _net_name_of(circuit, component.ref, "1") or _net_name_of(
                circuit, component.ref, "2"
            )
            applied = _net_voltage(circuit, net)
            if applied is None and net is None:
                applied = 0.0
            review.findings.append(
                review_capacitor_voltage(
                    label,
                    applied_voltage=abs(applied or 0.0),
                    rated_voltage=attributes.get("voltage"),
                )
            )

        elif kind == "led":
            colour = (
                attributes.get("illumination_color")
                or attributes.get("lens_color")
                or component.value
            )
            supply, resistance = _led_series_path(circuit, component.ref)
            review.findings.append(
                review_led_operating_point(
                    label,
                    supply_voltage=supply if supply is not None else (vout or 0.0),
                    series_resistance=resistance,
                    colour=str(colour or ""),
                )
            )

    return review


def _resistor_current(circuit: Any, ref: str, attributes: Dict[str, Any]) -> float:
    """
    The current through a resistor, when it can be worked out from the circuit.

    Only the case that can be computed is handled: a resistor in series with an
    LED, where the current follows from the supply, the LED's forward voltage and
    the resistance. A resistor that carries some other current gets zero, and the
    review reports its dissipation as unknown rather than as fine.
    """
    led = _partner_of_kind(circuit, ref, "led")
    if led is None:
        return 0.0
    supply, _resistance = _led_series_path(circuit, led.ref)
    if supply is None:
        return 0.0
    resistance = _value_number(circuit.components[ref].value)
    if not resistance:
        return 0.0
    colour = str(
        attributes.get("illumination_color")
        or circuit.components[led.ref].value
        or ""
    )
    forward = forward_voltage_for_colour(colour)
    if forward is None or supply <= forward[0]:
        return 0.0
    # The middle of the forward-voltage range, so the check is one number.
    vf = sum(forward) / 2
    return (supply - vf) / resistance


def _partner_of_kind(circuit: Any, ref: str, kind: str) -> Any:
    """A component of the given kind sharing a net with this one."""
    component = circuit.components.get(ref)
    if component is None:
        return None
    for pin in component.pins:
        net_name = pin.connected_net
        if not net_name:
            continue
        net = circuit.nets.get(net_name)
        if net is None:
            continue
        for connection in net.connected_pins:
            other = circuit.components.get(connection.get("ref"))
            if other is None or other.ref == ref:
                continue
            if getattr(getattr(other, "component_type", None), "value", "") == kind:
                return other
    return None


def _led_series_path(circuit: Any, led_ref: str) -> Tuple[Optional[float], Optional[float]]:
    """
    The supply voltage and series resistance feeding an LED.

    Walks one step: LED -> its net -> a resistor on that net -> the resistor's
    other net -> that net's voltage. Returns ``(None, None)`` when the circuit is
    not that shape, because a more complex network needs more than arithmetic to
    review.
    """
    resistor = _partner_of_kind(circuit, led_ref, "resistor")
    if resistor is None:
        return (None, None)
    resistance = _value_number(resistor.value)
    if not resistance:
        return (None, None)

    for pin in resistor.pins:
        net_name = pin.connected_net
        if not net_name:
            continue
        net = circuit.nets.get(net_name)
        if net is None:
            continue
        # The supply side is the net the LED is *not* on.
        holds_led = any(c.get("ref") == led_ref for c in net.connected_pins)
        if holds_led:
            continue
        voltage = _net_voltage(circuit, net_name)
        if voltage is not None:
            return (voltage, resistance)
    return (None, resistance)


__all__ = [
    "FAIL",
    "PASS",
    "UNKNOWN",
    "WARN",
    "DesignReview",
    "Finding",
    "forward_voltage_for_colour",
    "review_capacitor_voltage",
    "review_dropout",
    "review_led_operating_point",
    "review_circuit",
    "review_linear_regulator_thermal",
    "review_resistor_power",
]
