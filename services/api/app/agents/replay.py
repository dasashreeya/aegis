"""Deterministic replay and counterfactual forking.

A decision is not a row, it is a chain: the ordered, hash-linked entries the
fleet wrote as it ran. That makes two things possible that a status column
cannot support.

**Replay.** Re-read the chain and verify it. If a single byte of a payload was
edited after the fact, the recomputed hash no longer matches and the ledger says
where the break is.

**Fork.** Resume from any entry, substitute a fact or an outcome, and re-execute
only the steps after that point. The steps before it are not re-run: they are
replayed out of the log, carrying the original hashes forward as provenance. So
"replay to the point of denial, correct the rule, re-execute" produces a record
that is honest about which parts were observed and which were recomputed.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.steps import DEFAULT_FORK_AFTER, PIPELINE, STEP_KEYS, steps_through
from app.models import DecisionInput, DecisionRecord
from app.store import EventLedger, LedgerEntry, LedgerVerification

_KIND_TO_KEY = {step.kind: step.key for step in PIPELINE}


class ForkRequest(BaseModel):
    """The counterfactual to run against a recorded decision."""

    fork_after: str = Field(
        default=DEFAULT_FORK_AFTER,
        description=f"Replay through this step, re-execute the rest. One of {list(STEP_KEYS)}.",
    )
    fact_overrides: dict[str, bool | int] = Field(default_factory=dict)
    original_decision: Literal["approved", "denied"] | None = None
    note: str | None = Field(default=None, max_length=280)


class Timeline(BaseModel):
    """What ``GET /api/v1/decisions/{id}/timeline`` returns."""

    decision_id: str
    verification: LedgerVerification
    entries: list[LedgerEntry]
    fork_points: list[str] = Field(default_factory=lambda: list(STEP_KEYS))


class ForkPlan(BaseModel):
    """The inputs a fork run needs, resolved before anything executes."""

    decision: DecisionInput
    replay_of: str
    forked_after: str
    replayed_steps: list[str]
    substitutions: dict[str, bool | int | str] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class ReplayEngine:
    """Reads the ledger and turns a fork request into a runnable plan."""

    def __init__(self, ledger: EventLedger) -> None:
        self._ledger = ledger

    def timeline(self, decision_id: str) -> Timeline:
        return Timeline(
            decision_id=decision_id,
            verification=self._ledger.verify(decision_id),
            entries=self._ledger.entries(decision_id),
        )

    def replayable_entries(self, decision_id: str, fork_after: str) -> dict[str, LedgerEntry]:
        """Ledger entries for the steps that are replayed rather than re-run."""
        wanted = set(steps_through(fork_after))
        found: dict[str, LedgerEntry] = {}
        for entry in self._ledger.entries(decision_id):
            key = _KIND_TO_KEY.get(entry.kind.removesuffix(".replayed"))
            if key in wanted and key not in found:
                found[key] = entry
        return found

    def plan(self, original: DecisionRecord, request: ForkRequest) -> ForkPlan:
        steps_through(request.fork_after)  # validates the fork point
        facts = original.facts.model_copy(update=request.fact_overrides)
        substitutions: dict[str, bool | int | str] = dict(request.fact_overrides)
        if request.original_decision and request.original_decision != original.original_decision:
            substitutions["original_decision"] = request.original_decision
        suffix = f" / replay {request.note}" if request.note else " / replay"
        decision = DecisionInput(
            source=original.source,
            subject=_bounded(f"{original.subject}{suffix}"),
            requested_service=original.requested_service,
            original_decision=request.original_decision or original.original_decision,
            policy_id=original.policy_id,
            facts=facts,
        )
        replayed = self.replayable_entries(original.id, request.fork_after)
        return ForkPlan(
            decision=decision,
            replay_of=original.id,
            forked_after=request.fork_after,
            replayed_steps=sorted(replayed, key=STEP_KEYS.index),
            substitutions=substitutions,
        )


def _bounded(value: str, limit: int = 120) -> str:
    """DecisionInput.subject is capped at 120 characters; forks can nest."""
    return value if len(value) <= limit else f"{value[: limit - 1]}…"
