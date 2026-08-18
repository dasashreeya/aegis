from functools import lru_cache

from app.config import get_settings
from app.orchestrator import DecisionOrchestrator
from app.store import FirestoreDecisionStore, MemoryDecisionStore


@lru_cache
def get_orchestrator() -> DecisionOrchestrator:
    settings = get_settings()
    store = (
        FirestoreDecisionStore(settings.google_cloud_project)
        if settings.storage_backend == "firestore"
        else MemoryDecisionStore()
    )
    return DecisionOrchestrator(store)

