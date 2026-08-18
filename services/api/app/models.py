from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class DecisionFacts(BaseModel):
    medically_necessary: bool
    skilled_care_required: bool
    benefit_days_used: int = Field(ge=0, le=100)
    requested_days: int = Field(gt=0, le=100)


class DecisionInput(BaseModel):
    source: str = Field(min_length=1, max_length=120)
    subject: str = Field(min_length=1, max_length=120)
    requested_service: str = Field(min_length=1, max_length=240)
    original_decision: Literal["approved", "denied"]
    policy_id: str = Field(min_length=1, max_length=80)
    facts: DecisionFacts


class RuleFinding(BaseModel):
    rule_id: str
    title: str
    satisfied: bool
    explanation: str
    citation: str | None = None
    source_excerpt: str | None = None


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str
    agent: str
    message: str
    created_at: datetime = Field(default_factory=utc_now)
    trace_id: str | None = None
    span_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict, exclude=True)


class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"AD-{uuid4().hex[:8].upper()}")
    source: str
    subject: str
    requested_service: str
    original_decision: Literal["approved", "denied"]
    status: Literal["flagged", "upheld", "pending"]
    policy_id: str
    facts: DecisionFacts = Field(exclude=True)
    rationale: str
    unsat_core: list[str] = Field(default_factory=list)
    relaxations: list[str] = Field(default_factory=list)
    policy_version: str | None = None
    findings: list[RuleFinding] = Field(default_factory=list)
    events: list[AuditEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    replay_of: str | None = None


class ReplayInput(BaseModel):
    original_decision: Literal["approved", "denied"] | None = None
    fact_overrides: dict[str, bool | int] = Field(default_factory=dict)


class PubSubMessage(BaseModel):
    data: str
    messageId: str | None = None


class PubSubEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str | None = None
