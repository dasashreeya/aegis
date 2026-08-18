"""Interfaces shared across agents. Frozen — changes require a PR to main."""

from dataclasses import dataclass, field
from typing import Protocol

from app.models import DecisionInput, RuleFinding


@dataclass(frozen=True)
class SolverResult:
    eligible: bool
    conflicts_with_original: bool
    unsat_core: list[str]
    findings: list[RuleFinding]
    relaxations: list[str] = field(default_factory=list)
    policy_version: str | None = None


class Solver(Protocol):
    """Implemented by the rules track, consumed by the orchestrator."""

    def evaluate(self, decision: DecisionInput) -> SolverResult: ...
