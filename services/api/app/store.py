from abc import ABC, abstractmethod
from threading import RLock

from app.models import DecisionRecord


class DecisionStore(ABC):
    @abstractmethod
    def list(self) -> list[DecisionRecord]: ...

    @abstractmethod
    def get(self, decision_id: str) -> DecisionRecord | None: ...

    @abstractmethod
    def put(self, decision: DecisionRecord) -> DecisionRecord: ...


class MemoryDecisionStore(DecisionStore):
    def __init__(self) -> None:
        self._items: dict[str, DecisionRecord] = {}
        self._lock = RLock()

    def list(self) -> list[DecisionRecord]:
        with self._lock:
            return sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)

    def get(self, decision_id: str) -> DecisionRecord | None:
        with self._lock:
            return self._items.get(decision_id)

    def put(self, decision: DecisionRecord) -> DecisionRecord:
        with self._lock:
            self._items[decision.id] = decision
        return decision


class FirestoreDecisionStore(DecisionStore):
    def __init__(self, project: str | None) -> None:
        try:
            from google.cloud import firestore
        except ImportError as error:
            raise RuntimeError("Install the 'cloud' dependency group to use Firestore") from error
        self._collection = firestore.Client(project=project).collection("decisions")

    def list(self) -> list[DecisionRecord]:
        documents = self._collection.order_by("created_at", direction="DESCENDING").stream()
        return [DecisionRecord.model_validate(document.to_dict()) for document in documents]

    def get(self, decision_id: str) -> DecisionRecord | None:
        document = self._collection.document(decision_id).get()
        return DecisionRecord.model_validate(document.to_dict()) if document.exists else None

    def put(self, decision: DecisionRecord) -> DecisionRecord:
        payload = decision.model_dump(mode="json")
        payload["facts"] = decision.facts.model_dump()
        self._collection.document(decision.id).set(payload)
        return decision

