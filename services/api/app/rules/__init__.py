"""Governing rules for the reconciliation track.

`DEFAULT_POLICY` is the frozen constraint set for CMS-SNF-100: the output of running
`RuleExtractor` over `tests/fixtures/cms_snf.md`, checked in so the service reconciles
deterministically with no model in the loop. `PolicyRegistry` is how a freshly extracted
policy replaces it at runtime.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.rules.extract import (
    ExtractedRule,
    PolicyExtraction,
    RuleExtractionError,
    RuleExtractor,
    RulePredicate,
    validate_extraction,
)

DEFAULT_POLICY_ID = "CMS-SNF-100"

DEFAULT_POLICY = PolicyExtraction(
    policy_id=DEFAULT_POLICY_ID,
    version="2025-10-01",
    rules=[
        ExtractedRule(
            rule_id="medical_necessity",
            title="Medical necessity",
            predicate=RulePredicate(kind="require_true", fields=["medically_necessary"]),
            citation="§ 30.2",
            source_excerpt=(
                "the services are reasonable and necessary for the diagnosis or treatment of "
                "the beneficiary's condition"
            ),
            satisfied_explanation="The case documents medical necessity.",
            unsatisfied_explanation="Medical necessity is not documented.",
            relaxation=(
                "Document that the services are reasonable and necessary for the "
                "beneficiary's condition (§ 30.2)."
            ),
        ),
        ExtractedRule(
            rule_id="skilled_care_required",
            title="Skilled care requirement",
            predicate=RulePredicate(kind="require_true", fields=["skilled_care_required"]),
            citation="§ 30.3",
            source_excerpt=(
                "The beneficiary must require skilled nursing or skilled rehabilitation services "
                "that, as a practical matter, can only be provided on an inpatient basis"
            ),
            satisfied_explanation="The requested service requires skilled care.",
            unsatisfied_explanation="A skilled level of care is not established.",
            relaxation=(
                "Establish that the beneficiary requires a skilled level of inpatient care "
                "(§ 30.3)."
            ),
        ),
        ExtractedRule(
            rule_id="benefit_days_available",
            title="Benefit period limit",
            predicate=RulePredicate(
                kind="at_most",
                fields=["benefit_days_used", "requested_days"],
                limit=100,
            ),
            citation="§ 30.6",
            source_excerpt=(
                "The days already used in the benefit period, taken together with the days now "
                "requested, may not exceed that 100-day maximum"
            ),
            satisfied_explanation=(
                "{remaining} covered days remain; {requested_days} were requested."
            ),
            unsatisfied_explanation="The requested stay exceeds the 100-day benefit period.",
            relaxation=(
                "Reduce the request to at most {remaining} days, {deficit} fewer than "
                "requested (§ 30.6)."
            ),
        ),
    ],
)


class PolicyRegistry:
    """Policies available to the solver, keyed by policy id."""

    def __init__(
        self,
        policies: Iterable[PolicyExtraction] = (),
        *,
        fallback: PolicyExtraction = DEFAULT_POLICY,
    ) -> None:
        self._fallback = fallback
        self._policies: dict[str, PolicyExtraction] = {}
        for policy in policies:
            self.register(policy)

    def register(self, policy: PolicyExtraction) -> PolicyExtraction:
        self._policies[policy.policy_id] = policy
        return policy

    def get(self, policy_id: str) -> PolicyExtraction:
        """Resolve a policy, falling back to the registry default.

        An unknown id is not an error the API can surface today, so it resolves to the fallback
        and the caller reports which policy actually ran through `SolverResult.policy_version`.
        """
        return self._policies.get(policy_id, self._fallback)

    @property
    def policy_ids(self) -> list[str]:
        return sorted(self._policies)


def default_registry() -> PolicyRegistry:
    return PolicyRegistry([DEFAULT_POLICY])


__all__ = [
    "DEFAULT_POLICY",
    "DEFAULT_POLICY_ID",
    "ExtractedRule",
    "PolicyExtraction",
    "PolicyRegistry",
    "RuleExtractionError",
    "RuleExtractor",
    "RulePredicate",
    "default_registry",
    "validate_extraction",
]
