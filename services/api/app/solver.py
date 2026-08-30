"""Implements the `Solver` protocol over extracted policy constraints."""

from __future__ import annotations

from app.contracts import SolverResult
from app.models import DecisionInput
from app.rules import PolicyRegistry, default_registry
from app.rules.compile import evaluate_policy


class EligibilitySolver:
    """Reconciles a decision against the constraints extracted from its governing policy.

    The default registry carries the frozen CMS-SNF-100 set, so the service runs with no model
    in the loop; pass a registry populated by `RuleExtractor` to reconcile against live prose.
    """

    def __init__(self, registry: PolicyRegistry | None = None) -> None:
        self._registry = registry or default_registry()

    @property
    def registry(self) -> PolicyRegistry:
        return self._registry

    def evaluate(self, decision: DecisionInput) -> SolverResult:
        return evaluate_policy(self._registry.get(decision.policy_id), decision)
