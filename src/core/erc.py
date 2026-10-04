"""
Electrical Rule Checker (ERC) for Circuit Intermediate Representation (Circuit IR).

Validates circuits deterministically before emitting KiCad schematics or PCB layouts.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType, Net


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ERCIssue:
    rule_id: str
    severity: Severity
    message: str
    component_ref: Optional[str] = None
    pin_number: Optional[str] = None
    net_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "component_ref": self.component_ref,
            "pin_number": self.pin_number,
            "net_name": self.net_name,
        }


@dataclass
class ERCReport:
    passed: bool
    issues: List[ERCIssue] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
        }


class ERCValidator:
    """
    Deterministic Electrical Rule Checker running on Circuit IR.
    """

    def __init__(self, circuit: CircuitIR):
        self.circuit = circuit

    def validate(self) -> ERCReport:
        issues: List[ERCIssue] = []

        # Run all ERC rule passes
        issues.extend(self._check_unconnected_pins())
        issues.extend(self._check_power_pins())
        issues.extend(self._check_decoupling_capacitors())
        issues.extend(self._check_led_current_limiting())
        issues.extend(self._check_empty_nets())

        errors_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        warnings_count = sum(1 for i in issues if i.severity == Severity.WARNING)
        info_count = sum(1 for i in issues if i.severity == Severity.INFO)

        summary = {
            "errors": errors_count,
            "warnings": warnings_count,
            "info": info_count,
            "total": len(issues),
        }

        # Passed if zero errors (warnings do not fail ERC by default)
        passed = (errors_count == 0)

        return ERCReport(passed=passed, issues=issues, summary=summary)

    def _check_unconnected_pins(self) -> List[ERCIssue]:
        """Check for component pins that are not connected to any net."""
        issues = []
        for ref, comp in self.circuit.components.items():
            for pin in comp.pins:
                if not pin.connected_net:
                    # Unconnected input or power pins are errors, others warnings/info
                    if pin.pin_type in (PinType.INPUT, PinType.POWER_IN):
                        issues.append(
                            ERCIssue(
                                rule_id="ERC001_UNCONNECTED_CRITICAL_PIN",
                                severity=Severity.ERROR,
                                message=f"Component {ref} pin {pin.number} ({pin.name}, {pin.pin_type.value}) is unconnected.",
                                component_ref=ref,
                                pin_number=pin.number,
                            )
                        )
                    else:
                        issues.append(
                            ERCIssue(
                                rule_id="ERC002_UNCONNECTED_PIN",
                                severity=Severity.WARNING,
                                message=f"Component {ref} pin {pin.number} ({pin.name}) is unconnected.",
                                component_ref=ref,
                                pin_number=pin.number,
                            )
                        )
        return issues

    def _check_power_pins(self) -> List[ERCIssue]:
        """Verify power input pins connect to designated power/ground nets."""
        issues = []
        for ref, comp in self.circuit.components.items():
            for pin in comp.pins:
                if pin.pin_type == PinType.POWER_IN and pin.connected_net:
                    net = self.circuit.nets.get(pin.connected_net)
                    if net and not net.is_power and net.name not in ("GND", "VCC", "+5V", "+3V3", "3.3V", "5V", "VDD", "VSS"):
                        issues.append(
                            ERCIssue(
                                rule_id="ERC003_POWER_PIN_NON_POWER_NET",
                                severity=Severity.WARNING,
                                message=f"Power input pin {ref}.{pin.number} ({pin.name}) is connected to net '{pin.connected_net}' which is not marked as power.",
                                component_ref=ref,
                                pin_number=pin.number,
                                net_name=pin.connected_net,
                            )
                        )
        return issues

    def _check_decoupling_capacitors(self) -> List[ERCIssue]:
        """Check if ICs / Microcontrollers / Regulators have at least one decoupling capacitor."""
        issues = []
        ic_types = {
            ComponentType.MICROCONTROLLER,
            ComponentType.REGULATOR_LDO,
            ComponentType.REGULATOR_BUCK,
            ComponentType.REGULATOR_BOOST,
            ComponentType.CHIP,
        }

        ic_components = [c for c in self.circuit.components.values() if c.component_type in ic_types]
        capacitors = [c for c in self.circuit.components.values() if c.component_type == ComponentType.CAPACITOR]

        if ic_components and not capacitors:
            for ic in ic_components:
                issues.append(
                    ERCIssue(
                        rule_id="ERC004_MISSING_DECOUPLING_CAPACITOR",
                        severity=Severity.WARNING,
                        message=f"Component {ic.ref} ({ic.value}) is an IC/Regulator but no decoupling capacitors were found in the circuit.",
                        component_ref=ic.ref,
                    )
                )

        return issues

    def _check_led_current_limiting(self) -> List[ERCIssue]:
        """Verify LEDs have a series current limiting resistor connected."""
        issues = []
        leds = [c for c in self.circuit.components.values() if c.component_type == ComponentType.LED]
        resistors = [c for c in self.circuit.components.values() if c.component_type == ComponentType.RESISTOR]

        for led in leds:
            led_nets = {p.connected_net for p in led.pins if p.connected_net}
            resistor_nets = {p.connected_net for r in resistors for p in r.pins if p.connected_net}
            
            # Check if LED shares at least one net with a resistor
            if not led_nets.intersection(resistor_nets):
                issues.append(
                    ERCIssue(
                        rule_id="ERC005_LED_WITHOUT_RESISTOR",
                        severity=Severity.ERROR,
                        message=f"LED {led.ref} does not appear to have a series current-limiting resistor connected.",
                        component_ref=led.ref,
                    )
                )

        return issues

    def _check_empty_nets(self) -> List[ERCIssue]:
        """Check for nets with fewer than 2 connections."""
        issues = []
        for net_name, net in self.circuit.nets.items():
            if len(net.connected_pins) < 2:
                issues.append(
                    ERCIssue(
                        rule_id="ERC006_SINGLE_PIN_NET",
                        severity=Severity.WARNING,
                        message=f"Net '{net_name}' has only {len(net.connected_pins)} connection(s).",
                        net_name=net_name,
                    )
                )
        return issues
