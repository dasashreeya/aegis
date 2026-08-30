import base64
import json
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.dependencies import get_orchestrator
from app.models import DecisionInput, DecisionRecord, PubSubEnvelope, ReplayInput
from app.orchestrator import DecisionOrchestrator, UnsafeDecisionError

app = FastAPI(title="Aegis API", version="0.1.0")
Orchestrator = Annotated[DecisionOrchestrator, Depends(get_orchestrator)]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/decisions", response_model=list[DecisionRecord])
def list_decisions(
    orchestrator: Orchestrator,
) -> list[DecisionRecord]:
    return orchestrator.store.list()


@app.post("/api/v1/decisions", response_model=DecisionRecord, status_code=status.HTTP_201_CREATED)
def create_decision(
    decision: DecisionInput,
    orchestrator: Orchestrator,
) -> DecisionRecord:
    try:
        return orchestrator.run(decision)
    except UnsafeDecisionError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error


@app.get("/api/v1/decisions/{decision_id}", response_model=DecisionRecord)
def get_decision(
    decision_id: str,
    orchestrator: Orchestrator,
) -> DecisionRecord:
    decision = orchestrator.store.get(decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return decision


@app.post("/api/v1/decisions/{decision_id}/replay", response_model=DecisionRecord)
def replay_decision(
    decision_id: str,
    replay: ReplayInput,
    orchestrator: Orchestrator,
) -> DecisionRecord:
    original = orchestrator.store.get(decision_id)
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    facts = original.facts.model_copy(update=replay.fact_overrides)
    replay_input = DecisionInput(
        source=original.source,
        subject=f"{original.subject} / replay",
        requested_service=original.requested_service,
        original_decision=replay.original_decision or original.original_decision,
        policy_id=original.policy_id,
        facts=facts,
    )
    return orchestrator.run(replay_input, replay_of=original.id)


@app.post("/api/v1/pubsub", status_code=status.HTTP_204_NO_CONTENT)
def receive_pubsub(
    envelope: PubSubEnvelope,
    orchestrator: Orchestrator,
) -> Response:
    try:
        payload = base64.b64decode(envelope.message.data).decode("utf-8")
        orchestrator.run(DecisionInput.model_validate(json.loads(payload)))
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Pub/Sub payload") from error
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
