"""Composition root.

One place decides which store, which ledger, which fleet runtime and which trace
exporter this process uses. Everything else takes them as arguments, which is
what makes the fleet testable without a cloud project.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import Settings, get_settings
from app.orchestrator import DecisionOrchestrator
from app.store import (
    DecisionStore,
    EventLedger,
    FirestoreDecisionStore,
    FirestoreEventLedger,
    MemoryDecisionStore,
    MemoryEventLedger,
)
from app.telemetry import telemetry

logger = logging.getLogger(__name__)


def build_stores(settings: Settings) -> tuple[DecisionStore, EventLedger]:
    if settings.storage_backend != "firestore":
        return MemoryDecisionStore(), MemoryEventLedger()
    project = settings.google_cloud_project
    try:
        return (
            FirestoreDecisionStore(project, settings.firestore_collection_decisions),
            FirestoreEventLedger(project, settings.firestore_collection_ledger),
        )
    except Exception as error:  # noqa: BLE001 - oversight must outlive its database
        # A misconfigured database must not take the oversight service offline;
        # it degrades to in-process storage and says so on /api/health.
        logger.error("Firestore unavailable, falling back to in-process stores: %s", error)
        return MemoryDecisionStore(), MemoryEventLedger()


@lru_cache
def get_orchestrator() -> DecisionOrchestrator:
    settings = get_settings()
    logging.getLogger("app").setLevel(settings.log_level.upper())
    exporter = telemetry.configure(settings)
    store, ledger = build_stores(settings)
    orchestrator = DecisionOrchestrator(store, ledger, settings)
    logger.info(
        "Aegis fleet ready: runtime=%s mode=%s storage=%s traces=%s",
        orchestrator.fleet.runtime,
        settings.mode,
        type(store).__name__,
        exporter,
    )
    return orchestrator
