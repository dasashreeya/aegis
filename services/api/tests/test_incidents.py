"""The recorded incident corpus, replayed as a regression suite.

These are decisions that a court, a regulator or a newsroom later established
were wrong, plus a control set of denials that were right. If a change to the
fleet would let one of the wrong ones through, or start flagging one of the
right ones, this fails.

It runs in mock mode, so the assertions are on the formal layer -- the shield,
the solver and the ledger -- which is the layer that holds the verdict. The
model is exercised against the same corpus by ``scripts/incidents.py --live``.
"""

from __future__ import annotations

import pytest

from app.corpus import Incident, load_incidents
from app.orchestrator import DecisionOrchestrator
from app.solver import EligibilitySolver
from app.store import MemoryDecisionStore, MemoryEventLedger
from tests.test_fleet import settings

CORPUS = load_incidents()
CASES = [
    pytest.param(incident, label, expected, decision, id=f"{incident.id}::{label}")
    for incident in CORPUS
    for label, expected, decision in incident.cases()
]


@pytest.fixture(scope="module")
def fleet() -> DecisionOrchestrator:
    return DecisionOrchestrator(
        MemoryDecisionStore(),
        MemoryEventLedger(),
        settings(fleet_runtime="local"),
        EligibilitySolver(),
    )


def test_corpus_is_not_empty() -> None:
    assert len(CORPUS) >= 5
    assert sum(incident.case_count for incident in CORPUS) >= 40


@pytest.mark.parametrize("incident", CORPUS, ids=lambda item: item.id)
def test_every_incident_carries_its_evidence(incident: Incident) -> None:
    """An incident without a citation is an anecdote."""
    assert incident.sources, f"{incident.id} has no sources"
    for source in incident.sources:
        assert source.url.startswith("https://"), f"{incident.id}: {source.url}"
        assert source.publisher and source.date
    assert incident.governing_rules, f"{incident.id} names no governing rule"
    for rule in incident.governing_rules:
        assert rule.citation, f"{incident.id}: {rule.rule_id} has no citation"
    # Every file must say what in it is reconstructed and what is on the record.
    assert len(incident.caveat) > 40, f"{incident.id} has no meaningful caveat"


def test_named_claimant_cases_are_not_marked_reconstructed() -> None:
    """The two cases traced to a filed complaint must not be labelled otherwise."""
    by_id = {incident.id: incident for incident in CORPUS}
    assert by_id["lokken-nh-predict"].reconstructed is False
    assert by_id["tetzloff-nh-predict"].reconstructed is False
    # Everything else is a population or a pattern, and must say so.
    for incident in CORPUS:
        if incident.id not in {"lokken-nh-predict", "tetzloff-nh-predict"}:
            assert incident.reconstructed is True, incident.id


@pytest.mark.parametrize(("incident", "label", "expected", "decision"), CASES)
def test_incident_reaches_the_recorded_outcome(
    fleet: DecisionOrchestrator,
    incident: Incident,
    label: str,
    expected: str,
    decision,
) -> None:
    record = fleet.run(decision)
    assert record.status == expected, (
        f"{incident.id} / {label}: expected {expected}, got {record.status}. "
        f"Core: {record.unsat_core}"
    )
    assert fleet.ledger.verify(record.id).intact


def test_control_incident_upholds_every_correct_denial(fleet: DecisionOrchestrator) -> None:
    """A layer that flags everything has told you nothing.

    This is the assertion that makes the flag rate on the real incidents mean
    something.
    """
    control = next(incident for incident in CORPUS if incident.id == "control-correct-denials")
    for _, expected, decision in control.cases():
        assert expected == "upheld"
        assert fleet.run(decision).status == "upheld"


def test_lokken_finding_survives_the_unknown_parameter() -> None:
    """The public record does not say how many further days were ordered.

    So the finding must not depend on the value we picked. Sweep the whole
    range that fits inside the benefit period.
    """
    incident = next(item for item in CORPUS if item.id == "lokken-nh-predict")
    _, _, decision = incident.cases()[0]
    solver = EligibilitySolver()
    remaining = 100 - decision.facts.benefit_days_used
    for days in range(1, remaining + 1):
        candidate = decision.model_copy(
            update={"facts": decision.facts.model_copy(update={"requested_days": days})}
        )
        assert solver.evaluate(candidate).conflicts_with_original, (
            f"the contradiction disappears at requested_days={days}"
        )


def test_psi_cohort_reproduces_the_published_denial_rate() -> None:
    """The cohort is built from a rate, so the rate must actually come out."""
    incident = next(item for item in CORPUS if item.id == "psi-refusal-of-recovery")
    assert incident.cohort is not None
    assert incident.cohort.size == 22
    assert round(incident.cohort.denial_rate * 100, 1) == 22.7
