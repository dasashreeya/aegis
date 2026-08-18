from dataclasses import dataclass

from z3 import And, Bool, BoolVal, Not, Solver, unsat

from app.models import DecisionInput, RuleFinding


@dataclass(frozen=True)
class SolverResult:
    eligible: bool
    conflicts_with_original: bool
    unsat_core: list[str]
    findings: list[RuleFinding]


class EligibilitySolver:
    def evaluate(self, decision: DecisionInput) -> SolverResult:
        facts = decision.facts
        checks = {
            "medical_necessity": facts.medically_necessary,
            "skilled_care_required": facts.skilled_care_required,
            "benefit_days_available": facts.benefit_days_used + facts.requested_days <= 100,
        }
        findings = [
            RuleFinding(
                rule_id="medical_necessity",
                title="Medical necessity",
                satisfied=checks["medical_necessity"],
                explanation=(
                    "The case documents medical necessity."
                    if checks["medical_necessity"]
                    else "Medical necessity is not documented."
                ),
            ),
            RuleFinding(
                rule_id="skilled_care_required",
                title="Skilled care requirement",
                satisfied=checks["skilled_care_required"],
                explanation=(
                    "The requested service requires skilled care."
                    if checks["skilled_care_required"]
                    else "A skilled level of care is not established."
                ),
            ),
            RuleFinding(
                rule_id="benefit_days_available",
                title="Benefit period limit",
                satisfied=checks["benefit_days_available"],
                explanation=(
                    f"{100 - facts.benefit_days_used} covered days remain; "
                    f"{facts.requested_days} were requested."
                    if checks["benefit_days_available"]
                    else "The requested stay exceeds the 100-day benefit period."
                ),
            ),
        ]

        eligible = all(checks.values())
        expected_approval = decision.original_decision == "approved"
        conflicts = eligible != expected_approval
        core: list[str] = []

        if conflicts:
            solver = Solver()
            eligibility_terms = []
            for rule_id, satisfied in checks.items():
                rule_value = Bool(f"value_{rule_id}")
                solver.assert_and_track(rule_value == BoolVal(satisfied), Bool(rule_id))
                eligibility_terms.append(rule_value)

            decision_label = Bool(f"original_{decision.original_decision}")
            original_assertion = (
                And(*eligibility_terms)
                if decision.original_decision == "approved"
                else Not(And(*eligibility_terms))
            )
            solver.assert_and_track(original_assertion, decision_label)
            if solver.check() == unsat:
                core = [str(item) for item in solver.unsat_core()]

        return SolverResult(
            eligible=eligible,
            conflicts_with_original=conflicts,
            unsat_core=core,
            findings=findings,
        )
