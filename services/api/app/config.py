"""Runtime configuration for the Aegis oversight fleet.

Three modes govern every external call the fleet can make:

``mock``    no network, no spend. Deterministic adjudicator, local input shield,
            in-process traces. CI runs here and needs no credentials.
``cached``  replays recorded provider responses and falls through to ``live`` on
            a miss. Used for demo rehearsal so the on-camera run cannot fail.
``live``    real Vertex AI, real hosted Model Armor, real Cloud Trace.

The mode is the only switch a deployment needs to flip. Everything downstream
reads it through :meth:`Settings.resolve_runtime` rather than probing for
credentials itself, so a half-configured environment degrades in one predictable
place instead of five.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

Mode = Literal["mock", "cached", "live"]
StorageBackend = Literal["memory", "firestore"]
FleetRuntime = Literal["auto", "adk", "local"]
TraceExporter = Literal["auto", "none", "memory", "console", "cloud"]


class Settings(BaseSettings):
    # Both the working directory and the repository root, so `pytest` from
    # services/api and `uvicorn` from the root see the same configuration.
    model_config = SettingsConfigDict(
        env_prefix="AEGIS_",
        env_file=(".env", str(REPO_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- runtime -------------------------------------------------------------
    environment: str = "development"
    mode: Mode = "mock"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    service_name: str = "aegis-api"

    # -- google cloud --------------------------------------------------------
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    google_application_credentials: str | None = None
    use_vertexai: bool = True

    # -- models --------------------------------------------------------------
    model_adjudicator: str = "gemini-2.5-flash"
    model_narrator: str = "gemini-2.5-flash"
    adjudicator_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    adjudicator_max_output_tokens: int = Field(default=4096, ge=256, le=65536)
    adjudicator_timeout_seconds: float = Field(default=45.0, gt=0)

    # -- model armor ---------------------------------------------------------
    model_armor_template: str | None = None
    model_armor_location: str = "us-central1"
    model_armor_fail_closed: bool = True

    # -- storage -------------------------------------------------------------
    storage_backend: StorageBackend = "memory"
    firestore_collection_decisions: str = "decisions"
    firestore_collection_ledger: str = "decision_ledger"

    # -- async plane ---------------------------------------------------------
    pubsub_topic: str = "aegis-decisions"
    pubsub_audience: str | None = None

    # -- fleet ---------------------------------------------------------------
    fleet_runtime: FleetRuntime = "auto"
    fleet_app_name: str = "aegis"

    # -- telemetry -----------------------------------------------------------
    trace_exporter: TraceExporter = "auto"
    trace_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _export_google_credentials(self) -> Settings:
        """Publish the key path into the process so google-auth ADC finds it.

        Aegis reads it under the ``AEGIS_`` prefix like everything else; the
        Google libraries only look at the unprefixed name.
        """
        path = self.google_application_credentials
        already_set = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
        if path and not already_set and Path(path).is_file():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        return self

    # -- derived -------------------------------------------------------------
    @property
    def wants_network(self) -> bool:
        return self.mode in ("cached", "live")

    @property
    def vertex_configured(self) -> bool:
        return bool(self.google_cloud_project) and self.wants_network

    @property
    def armor_configured(self) -> bool:
        return bool(self.model_armor_template) and bool(self.google_cloud_project)

    @property
    def armor_resource_name(self) -> str | None:
        """Accept either a bare template id or a fully qualified resource name."""
        template = self.model_armor_template
        if not template:
            return None
        if template.startswith("projects/"):
            return template
        return (
            f"projects/{self.google_cloud_project}"
            f"/locations/{self.model_armor_location}/templates/{template}"
        )

    @property
    def resolved_trace_exporter(self) -> TraceExporter:
        if self.trace_exporter != "auto":
            return self.trace_exporter
        if self.mode == "live" and self.google_cloud_project:
            return "cloud"
        return "memory"

    def describe(self) -> dict[str, object]:
        """Non-secret runtime summary, surfaced on /api/health and in reports."""
        return {
            "environment": self.environment,
            "mode": self.mode,
            "project": self.google_cloud_project,
            "location": self.google_cloud_location,
            "storage_backend": self.storage_backend,
            "fleet_runtime": self.fleet_runtime,
            "adjudicator_model": self.model_adjudicator,
            "trace_exporter": self.resolved_trace_exporter,
            "model_armor": "hosted" if self.armor_configured else "local",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
