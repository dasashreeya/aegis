"""The recorded incident corpus.

Real automated-decision failures, reconstructed from the public record with
citations, and replayed through the fleet. The claim Aegis makes is narrow and
testable: *given the facts of record, this decision contradicts the rules that
govern it.* The corpus is how that claim is checked against cases where the
contradiction was later established by a court, a regulator or a news
investigation rather than by us.

Each file in ``incidents/`` carries the sources it was built from, the governing
rules with their citations, and the outcome each decision is expected to reach.
The regression test asserts those outcomes in mock mode, so a change to the
fleet that would have let one of these denials through fails CI.

Two shapes of case:

``decisions``   named decisions reconstructed from a specific claimant's record.
``cohort``      a population reconstructed from a published *rate*, expanded
                deterministically so the same file always produces the same
                cases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.config import REPO_ROOT
from app.models import DecisionFacts, DecisionInput

INCIDENT_DIR = REPO_ROOT / "incidents"

ExpectedStatus = Literal["flagged", "upheld"]


class IncidentSource(BaseModel):
    """A citation. Every factual claim in an incident file traces to one."""

    title: str
    publisher: str
    date: str
    url: str


class GoverningRule(BaseModel):
    """The rule the original decision is alleged to have contradicted."""

    rule_id: str
    citation: str
    requirement: str


class RecordedDecision(BaseModel):
    label: str
    expected_status: ExpectedStatus
    requested_service: str
    original_decision: Literal["approved", "denied"]
    facts: DecisionFacts
    note: str | None = None


class CohortProfile(BaseModel):
    """A group of like cases within a population reconstructed from a rate."""

    count: int = Field(ge=1, le=500)
    label: str
    expected_status: ExpectedStatus
    requested_service: str
    original_decision: Literal["approved", "denied"]
    facts: DecisionFacts
    note: str | None = None


class Cohort(BaseModel):
    basis: str
    profiles: list[CohortProfile]

    @property
    def size(self) -> int:
        return sum(profile.count for profile in self.profiles)

    @property
    def denial_rate(self) -> float:
        denied = sum(p.count for p in self.profiles if p.original_decision == "denied")
        return denied / self.size if self.size else 0.0


class Incident(BaseModel):
    """One recorded failure, with everything needed to re-audit it."""

    id: str
    title: str
    system: str
    operator: str
    period: str
    policy_id: str
    summary: str
    harm: str
    # False only for cases traced to a named claimant in a filed complaint.
    # True where the *mechanism* is documented but the individual case is a
    # reconstruction. Never blur the two.
    reconstructed: bool
    caveat: str
    governing_rules: list[GoverningRule]
    sources: list[IncidentSource]
    decisions: list[RecordedDecision] = Field(default_factory=list)
    cohort: Cohort | None = None

    def cases(self) -> list[tuple[str, ExpectedStatus, DecisionInput]]:
        """Every decision to replay, as (label, expected status, input)."""
        results: list[tuple[str, ExpectedStatus, DecisionInput]] = []
        for recorded in self.decisions:
            results.append(
                (
                    recorded.label,
                    recorded.expected_status,
                    self._as_input(recorded.label, recorded),
                )
            )
        if self.cohort is not None:
            index = 0
            for profile in self.cohort.profiles:
                for _ in range(profile.count):
                    index += 1
                    label = f"{profile.label} #{index:02d}"
                    results.append((label, profile.expected_status, self._as_input(label, profile)))
        return results

    def _as_input(self, label: str, source: RecordedDecision | CohortProfile) -> DecisionInput:
        return DecisionInput(
            source=_bounded(self.system, 120),
            subject=_bounded(label, 120),
            requested_service=_bounded(source.requested_service, 240),
            original_decision=source.original_decision,
            policy_id=self.policy_id,
            facts=source.facts,
        )

    @property
    def case_count(self) -> int:
        return len(self.decisions) + (self.cohort.size if self.cohort else 0)


def _bounded(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1]}…"


def load_incidents(directory: Path | None = None) -> list[Incident]:
    """Read every incident file, in a stable order."""
    root = directory or INCIDENT_DIR
    if not root.is_dir():
        raise FileNotFoundError(f"No incident corpus at {root}")
    incidents = [
        Incident.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("*.json"))
    ]
    if not incidents:
        raise FileNotFoundError(f"Incident corpus at {root} is empty")
    return incidents


def load_incident(incident_id: str, directory: Path | None = None) -> Incident:
    for incident in load_incidents(directory):
        if incident.id == incident_id:
            return incident
    raise KeyError(f"No incident with id {incident_id!r}")
