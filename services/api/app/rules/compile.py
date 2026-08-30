"""Extracted rules -> Z3 constraints -> minimal unsat core -> plain-English relaxations.

Rule satisfaction is decided by Z3 against the case facts rather than by Python `if`s, so the
clause set that gets explained is exactly the clause set that was solved.
"""

from __future__ import annotations

from typing import Any

from z3 import And, Bool, BoolVal, Implies, Int, Not, Solver, is_true, unsat

from app.contracts import SolverResult
from app.models import DecisionFacts, DecisionInput, RuleFinding
from app.rules.extract import BOOLEAN_FACTS, ExtractedRule, PolicyExtraction, RulePredicate


class _SafeDict(dict):
    """Leaves an unknown placeholder visible instead of raising mid-render."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render(template: str, context: dict[str, Any]) -> str:
    try:
        return template.format_map(_SafeDict(context))
    except (IndexError, ValueError):
        return template


def _fact_terms() -> dict[str, Any]:
    return {
        name: (Bool(name) if name in BOOLEAN_FACTS else Int(name))
        for name in DecisionFacts.model_fields
    }


def _predicate_expr(predicate: RulePredicate, terms: dict[str, Any]) -> Any:
    if predicate.kind == "require_true":
        return terms[predicate.fields[0]]
    total = terms[predicate.fields[0]]
    for name in predicate.fields[1:]:
        total = total + terms[name]
    if predicate.kind == "at_most":
        return total <= predicate.limit
    return total >= predicate.limit


def _solve_satisfaction(
    rules: list[ExtractedRule],
    facts: DecisionFacts,
) -> dict[str, bool]:
    """Ask Z3 which clauses hold under these facts."""
    terms = _fact_terms()
    environment = Solver()
    for name, term in terms.items():
        environment.add(term == getattr(facts, name))
    environment.check()
    model = environment.model()
    return {
        rule.rule_id: is_true(model.eval(_predicate_expr(rule.predicate, terms), True))
        for rule in rules
    }


def _format_context(predicate: RulePredicate, facts: DecisionFacts) -> dict[str, Any]:
    context: dict[str, Any] = facts.model_dump()
    if predicate.kind == "require_true" or predicate.limit is None:
        return context
    values = [getattr(facts, name) for name in predicate.fields]
    total = sum(values)
    context.update(
        limit=predicate.limit,
        total=total,
        slack=predicate.limit - total,
        deficit=total - predicate.limit,
        remaining=predicate.limit - sum(values[:-1]),
    )
    return context


def _minimal_core(solver: Solver, candidates: list[str]) -> list[str]:
    """Z3's core is small but not guaranteed minimal; drop one label at a time until it is."""
    core = list(candidates)
    index = 0
    while index < len(core):
        trial = core[:index] + core[index + 1 :]
        if trial and solver.check(*[Bool(name) for name in trial]) == unsat:
            core = trial
        else:
            index += 1
    return core


def _relaxations(
    core_rules: list[ExtractedRule],
    eligible: bool,
    original_decision: str,
    facts: DecisionFacts,
) -> list[str]:
    if eligible and original_decision == "denied":
        lines = ["Approve the request; no clause in the minimal conflict set supports a denial."]
        lines.extend(
            f"A denial would hold only if {rule.title.lower()} failed ({rule.citation})."
            for rule in core_rules
        )
        return lines
    return [
        _render(rule.relaxation, _format_context(rule.predicate, facts))
        for rule in core_rules
    ]


def evaluate_policy(extraction: PolicyExtraction, decision: DecisionInput) -> SolverResult:
    """Reconcile one decision against one extracted policy."""
    facts = decision.facts
    rules = extraction.rules
    satisfied = _solve_satisfaction(rules, facts)

    findings = [
        RuleFinding(
            rule_id=rule.rule_id,
            title=rule.title,
            satisfied=satisfied[rule.rule_id],
            explanation=_render(
                rule.satisfied_explanation
                if satisfied[rule.rule_id]
                else rule.unsatisfied_explanation,
                _format_context(rule.predicate, facts),
            ),
            citation=rule.citation,
            source_excerpt=rule.source_excerpt,
        )
        for rule in rules
    ]

    eligible = all(satisfied.values())
    expected_approval = decision.original_decision == "approved"
    conflicts = eligible != expected_approval
    if not conflicts:
        return SolverResult(
            eligible=eligible,
            conflicts_with_original=False,
            unsat_core=[],
            findings=findings,
            relaxations=[],
            policy_version=extraction.version_label,
        )

    solver = Solver()
    claims = []
    for rule in rules:
        claim = Bool(f"value_{rule.rule_id}")
        claims.append(claim)
        solver.add(Implies(Bool(rule.rule_id), claim == BoolVal(satisfied[rule.rule_id])))

    decision_label = f"original_{decision.original_decision}"
    conjunction = And(*claims) if claims else BoolVal(True)
    solver.add(
        Implies(
            Bool(decision_label),
            conjunction if expected_approval else Not(conjunction),
        )
    )

    assumptions = [rule.rule_id for rule in rules] + [decision_label]
    core: list[str] = []
    if solver.check(*[Bool(name) for name in assumptions]) == unsat:
        reported = {str(item) for item in solver.unsat_core()}
        core = _minimal_core(solver, [name for name in assumptions if name in reported])

    core_rules = [rule for rule in rules if rule.rule_id in core]
    return SolverResult(
        eligible=eligible,
        conflicts_with_original=True,
        unsat_core=core,
        findings=findings,
        relaxations=_relaxations(core_rules, eligible, decision.original_decision, facts),
        policy_version=extraction.version_label,
    )
