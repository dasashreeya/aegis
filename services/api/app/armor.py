import re
from dataclasses import dataclass

from app.models import DecisionInput


@dataclass(frozen=True)
class ArmorResult:
    safe: bool
    findings: tuple[str, ...]


class InputShield:
    """Local shield used for development; replace through this boundary in cloud deployments."""

    _patterns = (
        re.compile(r"ignore (all|any|the) previous instructions", re.IGNORECASE),
        re.compile(r"reveal (the )?(system|developer) prompt", re.IGNORECASE),
        re.compile(r"bypass (the )?(policy|rules|controls)", re.IGNORECASE),
    )

    def inspect(self, decision: DecisionInput) -> ArmorResult:
        content = (
            f"{decision.source} {decision.subject} "
            f"{decision.requested_service} {decision.policy_id}"
        )
        findings = tuple(pattern.pattern for pattern in self._patterns if pattern.search(content))
        return ArmorResult(safe=not findings, findings=findings)
