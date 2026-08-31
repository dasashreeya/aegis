"""The governed fleet, in two interchangeable runtimes.

``AdkFleet``    a real ADK ``SequentialAgent``. The deterministic hops are
                ``BaseAgent`` subclasses; re-adjudication is an ``LlmAgent``
                bound to Gemini on Vertex with a response schema, so the model
                leg runs through ADK rather than beside it.
``LocalFleet``  the same seven steps executed in process. No ADK, no network,
                no credentials. This is what CI and ``mock`` mode run.

Both share :mod:`app.agents.steps`, so they produce the same ledger, the same
spans and the same record. ``build_fleet`` picks one; ``AEGIS_FLEET_RUNTIME``
forces either.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from app.agents.adjudicator import (
    Adjudication,
    AdjudicationVerdict,
    DeterministicAdjudicator,
    build_adjudicator,
    build_case_prompt,
    from_verdict,
)
from app.agents.steps import (
    PIPELINE,
    FleetSession,
    Step,
    UnsafeDecisionError,
)
from app.armor import build_shield
from app.config import Settings
from app.contracts import Solver
from app.store import LedgerEntry
from app.telemetry import NO_SPAN, SpanContext, telemetry

logger = logging.getLogger(__name__)

STATE_CASE_PROMPT = "aegis_case_prompt"
STATE_VERDICT = "aegis_verdict"

try:  # pragma: no cover - depends on the optional agents extra
    import google.adk  # noqa: F401

    ADK_AVAILABLE = True
except ImportError:  # pragma: no cover
    ADK_AVAILABLE = False


@dataclass
class FleetOutcome:
    """What one pass of the fleet produced."""

    session: FleetSession
    entries: list[LedgerEntry] = field(default_factory=list)
    runtime: str = "local"

    @property
    def status(self) -> str:
        seal = next((entry for entry in self.entries if entry.kind == "verdict.sealed"), None)
        return str(seal.payload.get("status", "pending")) if seal else "pending"


class StepRecorder:
    """Runs a step inside a span and turns the result into a ledger entry.

    Both runtimes go through this, which is why replay, tracing and the ledger
    behave identically whether or not ADK is installed.
    """

    def __init__(self, decision_id: str, entries: list[LedgerEntry] | None = None) -> None:
        self.decision_id = decision_id
        self.entries: list[LedgerEntry] = [] if entries is None else entries

    def record(
        self,
        kind: str,
        agent: str,
        message: str,
        payload: dict[str, Any],
        span: SpanContext = NO_SPAN,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            decision_id=self.decision_id,
            sequence=len(self.entries),
            kind=kind,
            agent=agent,
            message=message,
            payload=payload,
            trace_id=span.trace_id,
            span_id=span.span_id,
        )
        self.entries.append(entry)
        return entry

    def execute(self, step: Step, session: FleetSession) -> LedgerEntry:
        recorded = session.replayed.get(step.key)
        if recorded is not None:
            step.restore(session, recorded.payload)
            return self.record(
                kind=f"{step.kind}.replayed",
                agent=step.agent,
                message=f"Replayed from ledger entry {recorded.sequence} of {recorded.decision_id}.",
                payload={
                    **recorded.payload,
                    "replayed_from": recorded.decision_id,
                    "replayed_sequence": recorded.sequence,
                    "replayed_hash": recorded.entry_hash,
                },
            )
        with telemetry.span(
            f"aegis.{step.key}",
            step=step.key,
            agent=step.agent,
            decision_id=self.decision_id,
        ) as span:
            try:
                output = step.run(session)
            except UnsafeDecisionError as error:
                self.record(
                    kind="shield.blocked",
                    agent=step.agent,
                    message=str(error),
                    payload={
                        "engine": error.result.engine if error.result else "unknown",
                        "categories": sorted(
                            {item.category for item in (error.result.detections if error.result else ())}
                        ),
                    },
                    span=span,
                )
                raise
        return self.record(step.kind, step.agent, output.message, output.payload, span)


class LocalFleet:
    """Seven steps, in process. The reference implementation of the semantics."""

    runtime = "local"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def arun(self, session: FleetSession, decision_id: str) -> FleetOutcome:
        return await asyncio.to_thread(self.run, session, decision_id)

    def run(self, session: FleetSession, decision_id: str) -> FleetOutcome:
        recorder = StepRecorder(decision_id, session.entries)
        outcome = FleetOutcome(session=session, entries=recorder.entries, runtime=self.runtime)
        with telemetry.span("aegis.fleet", runtime=self.runtime, decision_id=decision_id):
            for step in PIPELINE:
                recorder.execute(step, session)
        return outcome


_CURRENT_SESSION: ContextVar[FleetSession] = ContextVar("aegis_fleet_session")
_CURRENT_RECORDER: ContextVar[StepRecorder] = ContextVar("aegis_fleet_recorder")


def _build_adk_fleet(settings: Settings):
    """Compose the ``SequentialAgent``. Built once and reused across requests."""
    from google.adk.agents import BaseAgent, LlmAgent, SequentialAgent
    from google.adk.agents.readonly_context import ReadonlyContext
    from google.adk.events import Event, EventActions
    from google.genai import types

    step_by_key = {step.key: step for step in PIPELINE}

    class StepAgent(BaseAgent):
        """Wraps one deterministic hop as an ADK agent."""

        step_key: str = ""

        async def _run_async_impl(self, ctx):
            session = _CURRENT_SESSION.get()
            recorder = _CURRENT_RECORDER.get()
            step = step_by_key[self.step_key]
            entry = await asyncio.to_thread(recorder.execute, step, session)
            delta: dict[str, Any] = {f"aegis_{step.key}": entry.payload}
            if step.key == "solve" and session.solver_result is not None:
                delta[STATE_CASE_PROMPT] = build_case_prompt(
                    session.decision, session.solver_result
                )
                session.llm_dispatched_at = time.perf_counter()
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(role="model", parts=[types.Part(text=entry.message)]),
                actions=EventActions(state_delta=delta),
            )

    class CommitAdjudicationAgent(BaseAgent):
        """Turns the LlmAgent output into the governed Adjudication record.

        The model is advisory: this is where its verdict is measured against the
        binding solver result and classified as concur, escalate or dissent.
        """

        async def _run_async_impl(self, ctx):
            session = _CURRENT_SESSION.get()
            recorder = _CURRENT_RECORDER.get()
            step = step_by_key["adjudicate"]
            solver_result = session.require_solver_result()
            raw = ctx.session.state.get(STATE_VERDICT)
            dispatched = session.llm_dispatched_at or time.perf_counter()
            latency = round((time.perf_counter() - dispatched) * 1000, 2)
            engine = f"{settings.model_adjudicator} (adk/vertex)"
            with telemetry.span(
                "aegis.adjudicate", step="adjudicate", agent=step.agent, decision_id=recorder.decision_id
            ) as span:
                if raw is None:
                    logger.warning("LlmAgent produced no verdict; falling back to the solver")
                    fallback = DeterministicAdjudicator().adjudicate(session.decision, solver_result)
                    adjudication = fallback.model_copy(
                        update={
                            "engine": f"{engine} -> deterministic",
                            "degraded": True,
                            "latency_ms": latency,
                            "concerns": [
                                *fallback.concerns,
                                "Re-adjudication model returned no parsable verdict.",
                            ],
                        }
                    )
                else:
                    parsed = AdjudicationVerdict.model_validate(raw)
                    adjudication = from_verdict(parsed, solver_result, engine, latency)
                session.adjudication = adjudication
                entry = recorder.record(
                    step.kind, step.agent, adjudication.message, adjudication.model_dump(), span
                )
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                content=types.Content(role="model", parts=[types.Part(text=entry.message)]),
                actions=EventActions(state_delta={"aegis_adjudicate": entry.payload}),
            )

    def adjudication_instruction(ctx: ReadonlyContext) -> str:
        return str(ctx.state.get(STATE_CASE_PROMPT, "No case was supplied."))

    def node(key: str, description: str) -> BaseAgent:
        return StepAgent(name=f"aegis_{key}", description=description, step_key=key)

    sub_agents: list[BaseAgent] = [
        node("intake", "Normalises the inbound decision"),
        node("input_shield", "Model Armor screening of inbound text"),
        node("rules", "Loads the governing policy constraints"),
        node("solve", "Z3 contradiction analysis"),
    ]

    if settings.vertex_configured:
        from app.agents.adjudicator import SYSTEM_INSTRUCTION

        sub_agents.append(
            LlmAgent(
                name="aegis_readjudicator",
                description="Independent review of the case against the constraints",
                model=settings.model_adjudicator,
                instruction=adjudication_instruction,
                static_instruction=types.Content(
                    role="user", parts=[types.Part(text=SYSTEM_INSTRUCTION)]
                ),
                output_schema=AdjudicationVerdict,
                output_key=STATE_VERDICT,
                include_contents="none",
                generate_content_config=types.GenerateContentConfig(
                    temperature=settings.adjudicator_temperature,
                    max_output_tokens=settings.adjudicator_max_output_tokens,
                ),
            )
        )
        sub_agents.append(
            CommitAdjudicationAgent(
                name="aegis_commit_adjudication",
                description="Applies the governance rule that the solver holds the verdict",
            )
        )
    else:
        sub_agents.append(node("adjudicate", "Deterministic review; no model configured"))

    sub_agents.append(node("output_shield", "Screens the generated rationale"))
    sub_agents.append(node("seal", "Seals the verdict into the hash-chained ledger"))

    return SequentialAgent(
        name="aegis_oversight_fleet",
        description="Audits an automated decision against the rules that govern it",
        sub_agents=sub_agents,
    )


class AdkFleet:
    """The ADK runtime. Falls back to :class:`LocalFleet` if a run fails."""

    runtime = "adk"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._fallback = LocalFleet(settings)
        self._agent = _build_adk_fleet(settings)
        from google.adk.sessions import InMemorySessionService

        self._sessions = InMemorySessionService()

    def run(self, session: FleetSession, decision_id: str) -> FleetOutcome:
        return asyncio.run(self.arun(session, decision_id))

    async def arun(self, session: FleetSession, decision_id: str) -> FleetOutcome:
        from google.adk.runners import Runner
        from google.genai import types

        recorder = StepRecorder(decision_id, session.entries)
        outcome = FleetOutcome(session=session, entries=recorder.entries, runtime=self.runtime)
        _CURRENT_SESSION.set(session)
        _CURRENT_RECORDER.set(recorder)

        runner = Runner(
            app_name=self.settings.fleet_app_name,
            agent=self._agent,
            session_service=self._sessions,
        )
        adk_session = await self._sessions.create_session(
            app_name=self.settings.fleet_app_name, user_id="aegis", state={}
        )
        try:
            with telemetry.span("aegis.fleet", runtime=self.runtime, decision_id=decision_id):
                async for _ in runner.run_async(
                    user_id="aegis",
                    session_id=adk_session.id,
                    new_message=types.Content(
                        role="user",
                        parts=[types.Part(text=f"Audit decision {decision_id}")],
                    ),
                ):
                    pass
        except UnsafeDecisionError:
            raise
        except Exception as error:
            logger.exception("ADK fleet run failed, retrying in process")
            session.notes.append(f"ADK runtime failed, executed in process: {str(error)[:160]}")
            return await self._fallback.arun(_reset(session), decision_id)
        finally:
            await self._sessions.delete_session(
                app_name=self.settings.fleet_app_name, user_id="aegis", session_id=adk_session.id
            )
        return outcome


def _reset(session: FleetSession) -> FleetSession:
    """Clear partial results so a fallback run starts from a clean session."""
    session.solver_result = None
    session.adjudication = None
    session.input_armor = None
    session.output_armor = None
    session.entries.clear()
    return session


def build_fleet(settings: Settings) -> LocalFleet | AdkFleet:
    if settings.fleet_runtime == "local":
        return LocalFleet(settings)
    if not ADK_AVAILABLE:
        if settings.fleet_runtime == "adk":
            raise RuntimeError(
                "AEGIS_FLEET_RUNTIME=adk but google-adk is not installed; "
                "install the 'agents' dependency group"
            )
        return LocalFleet(settings)
    _export_genai_environment(settings)
    try:
        return AdkFleet(settings)
    except Exception as error:  # pragma: no cover - construction is exercised in tests
        if settings.fleet_runtime == "adk":
            raise
        logger.warning("Could not construct the ADK fleet, using the local runtime: %s", error)
        return LocalFleet(settings)


def _export_genai_environment(settings: Settings) -> None:
    """ADK reads the Vertex target from the process environment, not from us."""
    if not settings.vertex_configured:
        return
    flag = str(settings.use_vertexai).lower()
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", flag)
    # google-genai is renaming the flag; set both so neither version warns.
    os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", flag)
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.google_cloud_project or "")
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.google_cloud_location)


def build_session(
    decision,
    settings: Settings,
    solver: Solver,
    *,
    replay_of: str | None = None,
    forked_after: str | None = None,
    replayed: dict[str, LedgerEntry] | None = None,
) -> FleetSession:
    return FleetSession(
        decision=decision,
        solver=solver,
        shield=build_shield(settings),
        adjudicator=build_adjudicator(settings),
        replay_of=replay_of,
        forked_after=forked_after,
        replayed=replayed or {},
    )


__all__ = [
    "ADK_AVAILABLE",
    "Adjudication",
    "AdkFleet",
    "FleetOutcome",
    "LocalFleet",
    "StepRecorder",
    "UnsafeDecisionError",
    "build_fleet",
    "build_session",
]
