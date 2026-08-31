"""The seven hops every decision takes, independent of which runtime runs them.

Both fleet runtimes -- the ADK ``SequentialAgent`` and the in-process fallback --
execute exactly these steps in exactly this order. Keeping the semantics here
rather than in either runtime is what makes the two interchangeable: a decision
processed without ADK installed produces the same ledger, the same spans and the
same record as one processed with it.

A step is replayable. When a fork supplies a recorded entry for a step, the
runtime restores that step from the log instead of executing it, which is what
lets Replay resume from the point of denial rather than from the beginning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Protocol

from app.agents.adjudicator import Adjudication, Adjudicator
from app.armor import ArmorResult, Shield
from app.contracts import Solver, SolverResult
from app.models import DecisionInput
from app.store import LedgerEntry

# z3-solver's Python bindings share one global context, and that context is not
# thread safe: concurrent calls fault inside the native library rather than
# raising. Both fleet runtimes hand steps to worker threads, so two overlapping
# requests are enough to reach it. Every call into the solver is serialised
# here. Evaluation is sub-millisecond, so the contention costs nothing
# measurable, and the alternative -- a Z3 context per thread -- would have to
# live in the rules track's code rather than in the fleet.
_SOLVER_LOCK = Lock()


class UnsafeDecisionError(ValueError):
    """Raised when a shield blocks the decision. The run stops; the block is logged."""

    def __init__(self, message: str, result: ArmorResult | None = None) -> None:
        super().__init__(message)
        self.result = result


@dataclass
class FleetSession:
    """Everything one decision needs, and everything it accumulates."""

    decision: DecisionInput
    solver: Solver
    shield: Shield
    adjudicator: Adjudicator
    replay_of: str | None = None
    forked_after: str | None = None
    replayed: dict[str, LedgerEntry] = field(default_factory=dict)

    # Ledger entries accumulate here so a run that is stopped by a shield still
    # hands the orchestrator the block to seal.
    entries: list[LedgerEntry] = field(default_factory=list)

    solver_result: SolverResult | None = None
    adjudication: Adjudication | None = None
    input_armor: ArmorResult | None = None
    output_armor: ArmorResult | None = None
    notes: list[str] = field(default_factory=list)
    # Set by the ADK runtime when it dispatches the LlmAgent, so the commit step
    # can report how long the model leg actually took.
    llm_dispatched_at: float | None = None

    def require_solver_result(self) -> SolverResult:
        if self.solver_result is None:
            raise RuntimeError("Solver step has not run for this decision")
        return self.solver_result

    def require_adjudication(self) -> Adjudication:
        if self.adjudication is None:
            raise RuntimeError("Re-adjudication step has not run for this decision")
        return self.adjudication


@dataclass(frozen=True)
class StepOutput:
    message: str
    payload: dict[str, Any] = field(default_factory=dict)


class Step(Protocol):
    key: str
    kind: str
    agent: str

    def run(self, session: FleetSession) -> StepOutput: ...

    def restore(self, session: FleetSession, payload: dict[str, Any]) -> None: ...


class _BaseStep:
    key = ""
    kind = ""
    agent = ""

    def restore(self, session: FleetSession, payload: dict[str, Any]) -> None:
        """Rehydrate whatever this step contributed, without re-running it."""
        return


class IntakeStep(_BaseStep):
    key = "intake"
    kind = "decision.received"
    agent = "Intake"

    def run(self, session: FleetSession) -> StepOutput:
        decision = session.decision
        origin = f"forked from {session.replay_of}" if session.replay_of else "source system"
        return StepOutput(
            message=f"Accepted {decision.original_decision} decision from {decision.source}.",
            payload={
                "source": decision.source,
                "subject": decision.subject,
                "requested_service": decision.requested_service,
                "original_decision": decision.original_decision,
                "policy_id": decision.policy_id,
                "facts": decision.facts.model_dump(),
                "origin": origin,
            },
        )


class InputShieldStep(_BaseStep):
    key = "input_shield"
    kind = "shield.input"
    agent = "Model Armor"

    def run(self, session: FleetSession) -> StepOutput:
        result = session.shield.inspect(session.decision)
        session.input_armor = result
        if not result.safe:
            raise UnsafeDecisionError(
                "Input shield rejected potentially unsafe decision content", result
            )
        return StepOutput(
            message=result.summary,
            payload={
                "engine": result.engine,
                "degraded": result.degraded,
                "categories": sorted({item.category for item in result.detections}),
            },
        )

    def restore(self, session: FleetSession, payload: dict[str, Any]) -> None:
        session.input_armor = ArmorResult(
            safe=True, findings=(), engine=str(payload.get("engine", "replayed"))
        )


class RulesIngestionStep(_BaseStep):
    key = "rules"
    kind = "rules.loaded"
    agent = "Rules ingestion"

    def run(self, session: FleetSession) -> StepOutput:
        policy_id = session.decision.policy_id
        describe = getattr(session.solver, "describe_policy", None)
        summary: dict[str, Any] = {"policy_id": policy_id}
        if callable(describe):
            # Optional extension point for the rules track; absent on the base solver.
            # Held under the solver lock because compiling a policy builds Z3 terms.
            with _SOLVER_LOCK:
                summary.update(describe(policy_id) or {})
        return StepOutput(
            message=f"Loaded governing constraints for {policy_id}.",
            payload=summary,
        )


class ReconcileStep(_BaseStep):
    key = "solve"
    kind = "solver.completed"
    agent = "Reconcile"

    def run(self, session: FleetSession) -> StepOutput:
        with _SOLVER_LOCK:
            result = session.solver.evaluate(session.decision)
        session.solver_result = result
        message = (
            "Formal solver found a contradiction in the original decision."
            if result.conflicts_with_original
            else "Formal solver verified the original decision."
        )
        return StepOutput(
            message=message,
            payload={
                "eligible": result.eligible,
                "conflicts_with_original": result.conflicts_with_original,
                "unsat_core": list(result.unsat_core),
                "relaxations": list(result.relaxations),
                "policy_version": result.policy_version,
                "findings": [finding.model_dump() for finding in result.findings],
            },
        )

    def restore(self, session: FleetSession, payload: dict[str, Any]) -> None:
        from app.models import RuleFinding

        session.solver_result = SolverResult(
            eligible=bool(payload.get("eligible")),
            conflicts_with_original=bool(payload.get("conflicts_with_original")),
            unsat_core=list(payload.get("unsat_core", [])),
            findings=[RuleFinding.model_validate(item) for item in payload.get("findings", [])],
            relaxations=list(payload.get("relaxations", [])),
            policy_version=payload.get("policy_version"),
        )


class ReadjudicationStep(_BaseStep):
    key = "adjudicate"
    kind = "adjudication.completed"
    agent = "Re-adjudication"

    def run(self, session: FleetSession) -> StepOutput:
        solver_result = session.require_solver_result()
        adjudication = session.adjudicator.adjudicate(session.decision, solver_result)
        session.adjudication = adjudication
        return StepOutput(
            message=adjudication.message,
            payload=adjudication.model_dump(),
        )

    def restore(self, session: FleetSession, payload: dict[str, Any]) -> None:
        session.adjudication = Adjudication.model_validate(payload)


class OutputShieldStep(_BaseStep):
    key = "output_shield"
    kind = "shield.output"
    agent = "Output shield"

    def run(self, session: FleetSession) -> StepOutput:
        adjudication = session.require_adjudication()
        result = session.shield.inspect_response(adjudication.rationale)
        session.output_armor = result
        if not result.safe:
            # Never surface unscreened model text. Fall back to the solver rationale.
            session.notes.append("Generated rationale withheld by the output shield.")
            session.adjudication = adjudication.model_copy(
                update={
                    "rationale": (
                        "The generated explanation was withheld by the output shield. "
                        "The formal constraint evaluation stands unchanged."
                    ),
                    "degraded": True,
                }
            )
        return StepOutput(
            message=result.summary,
            payload={
                "engine": result.engine,
                "safe": result.safe,
                "degraded": result.degraded,
                "categories": sorted({item.category for item in result.detections}),
            },
        )


class SealStep(_BaseStep):
    key = "seal"
    kind = "verdict.sealed"
    agent = "Replay ledger"

    def run(self, session: FleetSession) -> StepOutput:
        solver_result = session.require_solver_result()
        adjudication = session.require_adjudication()
        status = "flagged" if solver_result.conflicts_with_original else "upheld"
        if adjudication.posture == "escalate":
            status = "flagged"
        return StepOutput(
            message=f"Decision sealed as {status}; ledger committed.",
            payload={
                "status": status,
                "solver_verdict": "approve" if solver_result.eligible else "deny",
                "model_verdict": adjudication.verdict,
                "posture": adjudication.posture,
            },
        )


PIPELINE: tuple[Step, ...] = (
    IntakeStep(),
    InputShieldStep(),
    RulesIngestionStep(),
    ReconcileStep(),
    ReadjudicationStep(),
    OutputShieldStep(),
    SealStep(),
)

STEP_KEYS: tuple[str, ...] = tuple(step.key for step in PIPELINE)
DEFAULT_FORK_AFTER = InputShieldStep.key


def steps_through(fork_after: str | None) -> tuple[str, ...]:
    """Step keys replayed from the log when forking after ``fork_after``."""
    if fork_after is None:
        return ()
    if fork_after not in STEP_KEYS:
        raise ValueError(f"Unknown fork point {fork_after!r}; expected one of {STEP_KEYS}")
    return STEP_KEYS[: STEP_KEYS.index(fork_after) + 1]
