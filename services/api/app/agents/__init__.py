"""The Aegis agent fleet.

Public surface only. Importing this package must not pull in ADK, Vertex or
OpenTelemetry -- CI installs none of them -- so the heavy imports live behind
``build_fleet`` and are guarded there.
"""

from app.agents.adjudicator import Adjudication, AdjudicationVerdict, build_adjudicator
from app.agents.fleet import (
    ADK_AVAILABLE,
    AdkFleet,
    FleetOutcome,
    LocalFleet,
    UnsafeDecisionError,
    build_fleet,
    build_session,
)
from app.agents.registry import AgentCard, FleetDescription, describe_fleet
from app.agents.replay import ForkPlan, ForkRequest, ReplayEngine, Timeline
from app.agents.steps import DEFAULT_FORK_AFTER, PIPELINE, STEP_KEYS, FleetSession

__all__ = [
    "ADK_AVAILABLE",
    "DEFAULT_FORK_AFTER",
    "PIPELINE",
    "STEP_KEYS",
    "Adjudication",
    "AdjudicationVerdict",
    "AdkFleet",
    "AgentCard",
    "FleetDescription",
    "FleetOutcome",
    "FleetSession",
    "ForkPlan",
    "ForkRequest",
    "LocalFleet",
    "ReplayEngine",
    "Timeline",
    "UnsafeDecisionError",
    "build_adjudicator",
    "build_fleet",
    "build_session",
    "describe_fleet",
]
