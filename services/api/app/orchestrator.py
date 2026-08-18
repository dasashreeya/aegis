from app.armor import InputShield
from app.contracts import Solver
from app.models import AuditEvent, DecisionInput, DecisionRecord
from app.solver import EligibilitySolver
from app.store import DecisionStore


class UnsafeDecisionError(ValueError):
    pass


class DecisionOrchestrator:
    def __init__(self, store: DecisionStore) -> None:
        self.store = store
        self.shield = InputShield()
        self.solver: Solver = EligibilitySolver()

    def run(self, decision: DecisionInput, replay_of: str | None = None) -> DecisionRecord:
        events: list[AuditEvent] = []
        shield_result = self.shield.inspect(decision)
        events.append(
            AuditEvent(
                kind="shield.completed",
                agent="Model Armor",
                message="Input screened; no prompt injection or policy bypass detected.",
            )
        )
        if not shield_result.safe:
            raise UnsafeDecisionError("Input shield rejected potentially unsafe decision content")

        events.append(
            AuditEvent(
                kind="rules.loaded",
                agent="Rules ingestion",
                message=f"Loaded governing constraints for {decision.policy_id}.",
            )
        )
        solver_result = self.solver.evaluate(decision)
        events.append(
            AuditEvent(
                kind="solver.completed",
                agent="Reconcile",
                message=(
                    "Formal solver found a contradiction in the original decision."
                    if solver_result.conflicts_with_original
                    else "Formal solver verified the original decision."
                ),
            )
        )
        events.append(
            AuditEvent(
                kind="adjudication.completed",
                agent="Re-adjudication",
                message=f"Independent outcome: {'approve' if solver_result.eligible else 'deny'}.",
            )
        )
        if replay_of:
            events.insert(
                0,
                AuditEvent(
                    kind="replay.forked",
                    agent="Replay",
                    message=f"Forked deterministic event log from {replay_of}.",
                ),
            )

        if solver_result.conflicts_with_original:
            rationale = (
                "The governing eligibility constraints are satisfied, but the source decision was denied."
                if solver_result.eligible
                else "The governing eligibility constraints are not satisfied, but the source decision was approved."
            )
            status = "flagged"
        else:
            rationale = "The source decision is consistent with the governing eligibility constraints."
            status = "upheld"

        record = DecisionRecord(
            source=decision.source,
            subject=decision.subject,
            requested_service=decision.requested_service,
            original_decision=decision.original_decision,
            status=status,
            policy_id=decision.policy_id,
            facts=decision.facts,
            rationale=rationale,
            unsat_core=solver_result.unsat_core,
            relaxations=solver_result.relaxations,
            policy_version=solver_result.policy_version,
            findings=solver_result.findings,
            events=events,
            replay_of=replay_of,
        )
        return self.store.put(record)
