"""
Design validation that produces actionable, LLM-readable feedback.

The purpose of this module is *not* to grade a design. It is to turn every
physical problem in a generated circuit into a sentence specific enough that
an LLM can fix it on the next attempt:

    "Component R1 uses MPN 'R-330-0805', which is not in the catalog."
    "Connection U1.NOPE references pin 'NOPE', but U1 only has pins 1, 2, 3."
    "ERC005_LED_WITHOUT_RESISTOR: LED D1 has no series current-limiting resistor."

Format validation alone cannot catch any of these; they are semantic and
electrical, which is why the repair loop runs against the built Circuit IR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.circuit_builder import BuildReport, CircuitIRBuilder
from src.core.circuit_ir import CircuitIR
from src.core.erc import ERCReport, ERCValidator, Severity


@dataclass
class ValidationIssue:
    """A single problem found in a generated design."""

    code: str
    severity: str  # "error" | "warning"
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"code": self.code, "severity": self.severity, "message": self.message}


@dataclass
class DesignValidationReport:
    """Result of validating a specification and its built Circuit IR."""

    valid: bool
    circuit: Optional[CircuitIR] = None
    build_report: Optional[BuildReport] = None
    erc: Optional[ERCReport] = None
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [i.to_dict() for i in self.issues],
            "erc": self.erc.to_dict() if self.erc else None,
            "build_report": self.build_report.to_dict() if self.build_report else None,
        }

    def feedback(self, max_issues: int = 12) -> str:
        """
        Render the problems as instructions an LLM can act on.

        Only errors and the most important warnings are included: dumping 40
        unconnected-pin warnings on a small model makes repair worse, not
        better.
        """
        lines: List[str] = []

        for issue in self.errors[:max_issues]:
            lines.append(f"- ERROR [{issue.code}] {issue.message}")

        remaining = max_issues - len(lines)
        if remaining > 0:
            for issue in self.warnings[:remaining]:
                lines.append(f"- WARNING [{issue.code}] {issue.message}")

        return "\n".join(lines)


def _is_mapping_like(value: Any) -> bool:
    """True for dicts and dict-like spec objects (e.g. ComponentSpec)."""
    return isinstance(value, dict) or (
        hasattr(value, "keys") and hasattr(value, "__getitem__")
    )


def _get(component: Any, key: str, default: Any = "") -> Any:
    if isinstance(component, dict):
        return component.get(key, default)
    getter = getattr(component, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(component, key, default)


def validate_spec_shape(spec: Any) -> List[ValidationIssue]:
    """Structural checks on the raw specification before anything is built."""
    issues: List[ValidationIssue] = []

    if not _is_mapping_like(spec):
        return [
            ValidationIssue(
                code="SPEC_NOT_OBJECT",
                severity="error",
                message="The specification must be a JSON object.",
            )
        ]

    topology = _get(spec, "topology")
    if not topology or not str(topology).strip():
        issues.append(
            ValidationIssue(
                code="SPEC_MISSING_TOPOLOGY",
                severity="error",
                message="The specification is missing the required 'topology' field.",
            )
        )

    components = _get(spec, "components", None)
    if not isinstance(components, (list, tuple)) or not components:
        issues.append(
            ValidationIssue(
                code="SPEC_NO_COMPONENTS",
                severity="error",
                message=(
                    "The specification must contain a non-empty 'components' array, "
                    "each entry with at least role, mpn, value and package."
                ),
            )
        )
        return issues

    for index, component in enumerate(components):
        if not _is_mapping_like(component):
            issues.append(
                ValidationIssue(
                    code="SPEC_COMPONENT_NOT_OBJECT",
                    severity="error",
                    message=f"Component at index {index} is not a JSON object.",
                )
            )
            continue
        missing = [
            key
            for key in ("role", "mpn", "value", "package")
            if not str(_get(component, key) or "").strip()
        ]
        if missing:
            issues.append(
                ValidationIssue(
                    code="SPEC_COMPONENT_MISSING_FIELDS",
                    severity="error",
                    message=(
                        f"Component at index {index} (role="
                        f"'{_get(component, 'role', '?')}') is missing required "
                        f"field(s): {', '.join(missing)}."
                    ),
                )
            )

    return issues


class DesignValidator:
    """Validates specifications, builds Circuit IR, and runs ERC."""

    def __init__(self, component_db: Any = None) -> None:
        self.db = component_db
        self.builder = CircuitIRBuilder(component_db)

    def validate(
        self,
        spec: Any,
        requirements: Any = None,
        description: str = "",
    ) -> DesignValidationReport:
        issues = validate_spec_shape(spec)
        if any(issue.severity == "error" for issue in issues):
            return DesignValidationReport(valid=False, issues=issues)

        circuit, build_report = self.builder.build(
            spec, requirements=requirements, description=description
        )

        issues.extend(self._issues_from_build_report(build_report))
        erc = ERCValidator(circuit).validate()
        issues.extend(self._issues_from_erc(erc))

        # ERC warnings are advisory; ERC errors and structural problems are not.
        valid = not any(issue.severity == "error" for issue in issues)
        return DesignValidationReport(
            valid=valid,
            circuit=circuit,
            build_report=build_report,
            erc=erc,
            issues=issues,
        )

    @staticmethod
    def _issues_from_build_report(report: BuildReport) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        for note in report.substituted_mpns:
            issues.append(
                ValidationIssue(
                    code="MPN_SUBSTITUTED",
                    severity="warning",
                    message=(
                        f"{note}. Prefer a part number that exists in the catalog, "
                        f"or keep the substitution if the rating is equivalent."
                    ),
                )
            )

        for mpn in report.unverified_mpns:
            issues.append(
                ValidationIssue(
                    code="MPN_UNKNOWN",
                    severity="error",
                    message=(
                        f"Component MPN '{mpn}' is not in the component catalog and "
                        f"no substitute with a matching rating could be found. Use a "
                        f"real, purchasable manufacturer part number."
                    ),
                )
            )

        for entry in report.skipped_connections:
            issues.append(
                ValidationIssue(
                    code="CONNECTION_INVALID",
                    severity="error",
                    message=(
                        f"Connection ignored: {entry}. Every connection must name an "
                        f"existing component and one of its real pins."
                    ),
                )
            )

        for entry in report.missing_footprints:
            issues.append(
                ValidationIssue(
                    code="FOOTPRINT_MISSING",
                    severity="warning",
                    message=(
                        f"Component '{entry}' has no footprint, so it cannot be "
                        f"placed on the PCB. Specify a standard package."
                    ),
                )
            )

        return issues

    @staticmethod
    def _issues_from_erc(erc: ERCReport) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for issue in erc.issues:
            severity = "error" if issue.severity == Severity.ERROR else "warning"
            issues.append(
                ValidationIssue(
                    code=issue.rule_id,
                    severity=severity,
                    message=issue.message,
                )
            )
        return issues


__all__ = [
    "DesignValidationReport",
    "DesignValidator",
    "ValidationIssue",
    "validate_spec_shape",
]
