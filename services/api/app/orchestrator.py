"""The orchestrator: one decision in, one sealed record and ledger out.

It owns the objects a request needs -- fleet, solver, stores, replay engine --
and it owns the two operations the API exposes: run a decision, and fork a
recorded one. Everything about *how* the seven steps execute lives in
:mod:`app.agents`; what lives here is the transaction around them, which is the
part that must not vary between runtimes.

The order matters. The ledger is sealed before the record is written, including
when a shield stops the run, so there is no state in which Aegis holds a verdict
it cannot show the derivation of.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from app.agents.fleet import FleetOutcome, build_fleet, build_session
from app.agents.registry import FleetDescription, describe_fleet
from app.agents.replay import ForkPlan, ForkRequest, ReplayEngine, Timeline
from app.agents.steps import UnsafeDecisionError
from app.config import Settings
from app.contracts import Solver
from app.models import AuditEvent, DecisionInput, DecisionRecord
from app.solver import EligibilitySolver
from app.store import DecisionStore, EventLedger, LedgerEntry
from app.telemetry import telemetry

logger = logging.getLogger(__name__)

__all__ = ["DecisionOrchestrator", "UnsafeDecisionError"]


class DecisionOrchestrator:
    def __init__(
        self,
        store: DecisionStore,
        ledger: EventLedger,
        settings: Settings,
        solver: Solver | None = None,
    ) -> None:
        self.store = store
        self.ledger = ledger
        self.settings = settings
        self.solver: Solver = solver or EligibilitySolver()
        self.fleet = build_fleet(settings)
        self.replay = ReplayEngine(ledger)

    # -- introspection -------------------------------------------------------
    def describe(self) -> FleetDescription:
        return describe_fleet(self.settings, self.fleet.runtime, telemetry.exporter)

    def timeline(self, decision_id: str) -> Timeline:
        return self.replay.timeline(decision_id)

    def recent_events(self, limit: int = 200) -> list[LedgerEntry]:
        return self.ledger.recent(limit)

    # -- run -----------------------------------------------------------------
    async def arun(
        self,
        decision: DecisionInput,
        *,
        replay_of: str | None = None,
        plan: ForkPlan | None = None,
    ) -> DecisionRecord:
        record = DecisionRecord(
            source=decision.source,
            subject=decision.subject,
            requested_service=decision.requested_service,
            original_decision=decision.original_decision,
            status="pending",
            policy_id=decision.policy_id,
            facts=decision.facts,
            rationale="",
            replay_of=replay_of,
        )
        replayed = (
            self.replay.replayable_entries(plan.replay_of, plan.forked_after) if plan else {}
        )
        session = build_session(
            decision,
            self.settings,
            self.solver,
            replay_of=replay_of,
            forked_after=plan.forked_after if plan else None,
            replayed=replayed,
        )
        try:
            outcome = await self.fleet.arun(session, record.id)
        except UnsafeDecisionError:
            # Seal what did happen. The block is evidence, not an error to discard.
            self.ledger.seal(record.id, session.entries)
            raise
        sealed = self.ledger.seal(record.id, outcome.entries)
        return self.store.put(self._finalise(record, outcome, sealed, plan))

    def run(
        self,
        decision: DecisionInput,
        *,
        replay_of: str | None = None,
        plan: ForkPlan | None = None,
    ) -> DecisionRecord:
        """Synchronous entry point, for scripts and non-async callers."""
        return asyncio.run(self.arun(decision, replay_of=replay_of, plan=plan))

    # -- fork ----------------------------------------------------------------
    async def afork(self, decision_id: str, request: ForkRequest) -> DecisionRecord | None:
        original = self.store.get(decision_id)
        if original is None:
            return None
        plan = self.replay.plan(original, request)
        return await self.arun(plan.decision, replay_of=original.id, plan=plan)

    def run_fork(self, decision_id: str, request: ForkRequest) -> DecisionRecord | None:
        """Synchronous fork, for scripts and the demo harness."""
        return asyncio.run(self.afork(decision_id, request))

    # -- assembly ------------------------------------------------------------
    def _finalise(
        self,
        record: DecisionRecord,
        outcome: FleetOutcome,
        sealed: list[LedgerEntry],
        plan: ForkPlan | None,
    ) -> DecisionRecord:
        session = outcome.session
        solver_result = session.require_solver_result()
        adjudication = session.require_adjudication()
        events = [_as_audit_event(entry) for entry in sealed]
        if plan is not None:
            events.insert(0, _fork_event(plan, sealed))

        rationale = adjudication.rationale
        if adjudication.posture == "escalate":
            rationale += (
                " The re-adjudication agent raised concerns beyond the constraint set; "
                "the decision stays flagged for human review."
            )
        elif adjudication.posture == "dissent":
            rationale += (
                " The re-adjudication agent proposed a more permissive outcome than the "
                "constraints support; that view is recorded but does not clear the finding."
            )

        return record.model_copy(
            update={
                "status": outcome.status,
                "rationale": rationale,
                "unsat_core": list(solver_result.unsat_core),
                "relaxations": _relaxations(solver_result, adjudication),
                "policy_version": solver_result.policy_version,
                "findings": list(solver_result.findings),
                "events": events,
            }
        )


def _relaxations(solver_result, adjudication) -> list[str]:
    """Solver relaxations first, then anything only the model noticed."""
    seen = list(solver_result.relaxations)
    for concern in adjudication.concerns:
        if concern not in seen:
            seen.append(concern)
    return seen


def _as_audit_event(entry: LedgerEntry) -> AuditEvent:
    return AuditEvent(
        id=entry.entry_hash[:32] or str(uuid4()),
        kind=entry.kind,
        agent=entry.agent,
        message=entry.message,
        created_at=entry.recorded_at,
        trace_id=entry.trace_id,
        span_id=entry.span_id,
        payload=entry.payload,
    )


def _fork_event(plan: ForkPlan, entries: list[LedgerEntry]) -> AuditEvent:
    substitutions = ", ".join(f"{key}={value}" for key, value in plan.substitutions.items())
    detail = f" Substituted {substitutions}." if substitutions else ""
    return AuditEvent(
        kind="replay.forked",
        agent="Replay",
        message=(
            f"Forked deterministic event log from {plan.replay_of} after "
            f"{plan.forked_after}; replayed {len(plan.replayed_steps)} of "
            f"{len(entries)} steps.{detail}"
        ),
        trace_id=entries[0].trace_id if entries else None,
        payload={
            "replay_of": plan.replay_of,
            "forked_after": plan.forked_after,
            "replayed_steps": plan.replayed_steps,
            "substitutions": plan.substitutions,
        },
    )
