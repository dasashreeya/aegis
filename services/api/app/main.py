import base64
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agents.registry import FleetDescription
from app.agents.replay import ForkRequest, Timeline
from app.dependencies import get_orchestrator
from app.models import DecisionInput, DecisionRecord, PubSubEnvelope, ReplayInput
from app.orchestrator import DecisionOrchestrator, UnsafeDecisionError
from app.store import LedgerEntry
from app.telemetry import instrument_app, telemetry

logger = logging.getLogger(__name__)


class SpanView(BaseModel):
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    duration_ms: float
    attributes: dict[str, Any] = Field(default_factory=dict)


class TracePage(BaseModel):
    """Everything the Traces view needs in one request."""

    exporter: str
    entries: list[LedgerEntry]
    spans: list[SpanView]


class HealthResponse(BaseModel):
    status: str
    runtime: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The fleet is built on the first request. On Cloud Run that is the startup
    # probe against /api/health, so a misconfigured revision still fails before
    # it takes traffic, without this process reaching for credentials at import.
    instrument_app(app)
    logger.info("Aegis API starting")
    yield
    telemetry.shutdown()


app = FastAPI(
    title="Aegis API",
    version="0.2.0",
    summary="Independent oversight of automated eligibility and claims decisions",
    lifespan=lifespan,
)
Orchestrator = Annotated[DecisionOrchestrator, Depends(get_orchestrator)]


@app.get("/api/health", response_model=HealthResponse)
def health(orchestrator: Orchestrator) -> HealthResponse:
    runtime = orchestrator.settings.describe()
    runtime["fleet_runtime"] = orchestrator.fleet.runtime
    runtime["trace_exporter"] = telemetry.exporter
    runtime["ledger"] = type(orchestrator.ledger).__name__
    runtime["store"] = type(orchestrator.store).__name__
    return HealthResponse(status="ok", runtime=runtime)


@app.get("/api/v1/fleet", response_model=FleetDescription)
def describe_fleet(orchestrator: Orchestrator) -> FleetDescription:
    """The Agent Registry entry for every agent currently wired in."""
    return orchestrator.describe()


@app.get("/api/v1/decisions", response_model=list[DecisionRecord])
def list_decisions(orchestrator: Orchestrator) -> list[DecisionRecord]:
    return orchestrator.store.list()


@app.post("/api/v1/decisions", response_model=DecisionRecord, status_code=status.HTTP_201_CREATED)
async def create_decision(
    decision: DecisionInput,
    orchestrator: Orchestrator,
) -> DecisionRecord:
    try:
        return await orchestrator.arun(decision)
    except UnsafeDecisionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@app.get("/api/v1/decisions/{decision_id}", response_model=DecisionRecord)
def get_decision(decision_id: str, orchestrator: Orchestrator) -> DecisionRecord:
    decision = orchestrator.store.get(decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return decision


@app.get("/api/v1/decisions/{decision_id}/timeline", response_model=Timeline)
def get_timeline(decision_id: str, orchestrator: Orchestrator) -> Timeline:
    """The hash-chained ledger for one decision, with its integrity check."""
    if orchestrator.store.get(decision_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return orchestrator.timeline(decision_id)


@app.post("/api/v1/decisions/{decision_id}/fork", response_model=DecisionRecord)
async def fork_decision(
    decision_id: str,
    request: ForkRequest,
    orchestrator: Orchestrator,
) -> DecisionRecord:
    """Replay to a point in the ledger, substitute a fact, re-execute the rest."""
    try:
        record = await orchestrator.afork(decision_id, request)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    except UnsafeDecisionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return record


@app.post("/api/v1/decisions/{decision_id}/replay", response_model=DecisionRecord)
async def replay_decision(
    decision_id: str,
    replay: ReplayInput,
    orchestrator: Orchestrator,
) -> DecisionRecord:
    """Compatibility alias for the fork endpoint, using the default fork point."""
    request = ForkRequest(
        fact_overrides=replay.fact_overrides,
        original_decision=replay.original_decision,
    )
    return await fork_decision(decision_id, request, orchestrator)


@app.get("/api/v1/traces", response_model=TracePage)
def list_traces(
    orchestrator: Orchestrator,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> TracePage:
    """Recent ledger entries and, when traces are held in process, their spans."""
    return TracePage(
        exporter=telemetry.exporter,
        entries=orchestrator.recent_events(limit),
        spans=[
            SpanView(
                name=span.name,
                trace_id=span.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                duration_ms=span.duration_ms,
                attributes=span.attributes,
            )
            for span in telemetry.recorded_spans()[-limit:]
        ],
    )


@app.post("/api/v1/pubsub", status_code=status.HTTP_204_NO_CONTENT)
async def receive_pubsub(envelope: PubSubEnvelope, orchestrator: Orchestrator) -> Response:
    try:
        payload = base64.b64decode(envelope.message.data).decode("utf-8")
        decision = DecisionInput.model_validate(json.loads(payload))
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Pub/Sub payload"
        ) from error
    try:
        await orchestrator.arun(decision)
    except UnsafeDecisionError:
        # The block is recorded in the ledger. Acknowledge so Pub/Sub does not
        # redeliver a message the shield will reject again.
        logger.warning("Shield blocked a decision delivered over Pub/Sub")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


web_dist = Path(__file__).resolve().parents[3] / "apps" / "web" / "dist"
if web_dist.exists():
    assets = web_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def web_app(path: str) -> FileResponse:
        candidate = (web_dist / path).resolve()
        inside_bundle = candidate.is_file() and candidate.is_relative_to(web_dist.resolve())
        return FileResponse(candidate if inside_bundle else web_dist / "index.html")
