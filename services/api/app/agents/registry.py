"""The Agent Registry entry for every agent in the fleet.

This is the catalogue a second department would read before calling one of these
agents, and it is what the Agents view in the web app renders. It is generated
from live settings rather than hard-coded, so a fleet running without Vertex
credentials advertises a degraded re-adjudicator instead of claiming a model it
cannot reach. An agent card that lies is worse than no catalogue at all.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.config import Settings

AgentHealth = Literal["online", "degraded", "offline"]


class AgentCard(BaseModel):
    """One published agent. Mirrors the shape an ADK agent card exposes."""

    id: str
    name: str
    role: str
    kind: Literal["deterministic", "model", "solver", "shield", "ledger"]
    version: str = "1.0.0"
    runtime: str
    health: AgentHealth = "online"
    detail: str = ""
    capabilities: list[str] = Field(default_factory=list)


class FleetDescription(BaseModel):
    """What ``GET /api/v1/fleet`` returns."""

    app_name: str
    runtime: str
    mode: str
    orchestrator: str
    trace_exporter: str
    agents: list[AgentCard]

    @property
    def online(self) -> int:
        return sum(1 for agent in self.agents if agent.health == "online")


def describe_fleet(settings: Settings, runtime: str, trace_exporter: str) -> FleetDescription:
    hosted_armor = settings.armor_configured and settings.wants_network
    vertex = settings.vertex_configured

    agents = [
        AgentCard(
            id="intake",
            name="Intake",
            role="Normalises the inbound decision and opens the ledger",
            kind="deterministic",
            runtime=runtime,
            capabilities=["pubsub.pull", "schema.validate"],
        ),
        AgentCard(
            id="input_shield",
            name="Model Armor",
            role="Screens inbound text for injection, tool poisoning and PII",
            kind="shield",
            runtime="hosted" if hosted_armor else "local",
            health="online" if hosted_armor else "degraded",
            detail=(
                f"Template {settings.model_armor_template}"
                if hosted_armor
                else "Local pattern shield; set AEGIS_MODEL_ARMOR_TEMPLATE for the hosted service"
            ),
            capabilities=["prompt.sanitize", "response.sanitize", "pii.detect"],
        ),
        AgentCard(
            id="rules_ingestion",
            name="Rules ingestion",
            role="Loads the governing policy and compiles it to constraints",
            kind="deterministic",
            runtime=runtime,
            capabilities=["policy.load", "constraint.compile"],
        ),
        AgentCard(
            id="reconcile",
            name="Reconcile",
            role="Z3 contradiction analysis and minimal unsat core",
            kind="solver",
            runtime="z3",
            capabilities=["smt.solve", "unsat.core", "relaxation.propose"],
        ),
        AgentCard(
            id="readjudicator",
            name="Re-adjudication",
            role="Independent review of the case against the constraints",
            kind="model",
            runtime=f"{settings.model_adjudicator} (vertex)" if vertex else "deterministic",
            health="online" if vertex else "degraded",
            detail=(
                "Advisory only: the solver holds the verdict, the model may escalate but "
                "never clears a flag"
            ),
            capabilities=["case.review", "rationale.write", "concern.raise"],
        ),
        AgentCard(
            id="output_shield",
            name="Output shield",
            role="Screens generated rationale before it is stored or shown",
            kind="shield",
            runtime="hosted" if hosted_armor else "local",
            health="online" if hosted_armor else "degraded",
            capabilities=["response.sanitize", "pii.detect"],
        ),
        AgentCard(
            id="ledger",
            name="Replay ledger",
            role="Seals every hop into the hash-chained event log",
            kind="ledger",
            runtime=settings.storage_backend,
            capabilities=["event.append", "chain.verify", "timeline.fork"],
        ),
    ]

    return FleetDescription(
        app_name=settings.fleet_app_name,
        runtime=runtime,
        mode=settings.mode,
        orchestrator="adk.SequentialAgent" if runtime == "adk" else "in-process sequential",
        trace_exporter=trace_exporter,
        agents=agents,
    )
