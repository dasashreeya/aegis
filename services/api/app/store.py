"""Persistence for decisions and for the append-only event ledger.

Two stores, because they answer different questions:

``DecisionStore``  the current state of a decision -- what the fleet concluded.
``EventLedger``    how it got there, as an ordered, hash-chained log.

The ledger is what makes Replay meaningful. Each entry commits to its
predecessor by hash, so a ledger that has been edited after the fact fails
verification, and a fork can name the exact entry it diverged from. Both stores
have an in-process implementation for tests and the demo, and a Firestore
implementation for the deployed service.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from threading import RLock
from typing import Any

from pydantic import BaseModel, Field

from app.models import DecisionRecord, utc_now

GENESIS_HASH = "0" * 64


class LedgerEntry(BaseModel):
    """One committed step of one decision, chained to the step before it."""

    decision_id: str
    sequence: int
    kind: str
    agent: str
    message: str
    recorded_at: datetime = Field(default_factory=utc_now)
    trace_id: str | None = None
    span_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str = GENESIS_HASH
    entry_hash: str = ""

    def compute_hash(self) -> str:
        body = {
            "decision_id": self.decision_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "agent": self.agent,
            "message": self.message,
            "recorded_at": self.recorded_at.isoformat(),
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "payload": self.payload,
            "previous_hash": self.previous_hash,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def sealed(self, previous_hash: str, sequence: int) -> LedgerEntry:
        """Return this entry positioned in the chain and committed by hash."""
        entry = self.model_copy(update={"previous_hash": previous_hash, "sequence": sequence})
        return entry.model_copy(update={"entry_hash": entry.compute_hash()})


class LedgerVerification(BaseModel):
    decision_id: str
    intact: bool
    entries: int
    head_hash: str
    broken_at: int | None = None
    detail: str = ""


class DecisionStore(ABC):
    @abstractmethod
    def list(self) -> list[DecisionRecord]: ...

    @abstractmethod
    def get(self, decision_id: str) -> DecisionRecord | None: ...

    @abstractmethod
    def put(self, decision: DecisionRecord) -> DecisionRecord: ...


class EventLedger(ABC):
    """Append-only, hash-chained log of everything the fleet did."""

    @abstractmethod
    def append(self, entries: list[LedgerEntry]) -> list[LedgerEntry]: ...

    @abstractmethod
    def entries(self, decision_id: str) -> list[LedgerEntry]: ...

    @abstractmethod
    def recent(self, limit: int = 200) -> list[LedgerEntry]: ...

    def head(self, decision_id: str) -> tuple[str, int]:
        """The hash and sequence to chain the next entry onto."""
        existing = self.entries(decision_id)
        if not existing:
            return GENESIS_HASH, 0
        return existing[-1].entry_hash, existing[-1].sequence + 1

    def seal(self, decision_id: str, entries: list[LedgerEntry]) -> list[LedgerEntry]:
        """Chain a batch onto the current head and commit it."""
        previous_hash, sequence = self.head(decision_id)
        sealed: list[LedgerEntry] = []
        for entry in entries:
            positioned = entry.model_copy(update={"decision_id": decision_id})
            committed = positioned.sealed(previous_hash, sequence)
            sealed.append(committed)
            previous_hash = committed.entry_hash
            sequence += 1
        return self.append(sealed)

    def verify(self, decision_id: str) -> LedgerVerification:
        """Recompute the chain. Any post-hoc edit shows up as a break."""
        entries = self.entries(decision_id)
        if not entries:
            return LedgerVerification(
                decision_id=decision_id,
                intact=True,
                entries=0,
                head_hash=GENESIS_HASH,
                detail="No entries recorded for this decision.",
            )
        previous_hash = GENESIS_HASH
        for index, entry in enumerate(entries):
            if entry.previous_hash != previous_hash or entry.sequence != index:
                return LedgerVerification(
                    decision_id=decision_id,
                    intact=False,
                    entries=len(entries),
                    head_hash=entries[-1].entry_hash,
                    broken_at=entry.sequence,
                    detail="Chain link does not match the preceding entry.",
                )
            if entry.compute_hash() != entry.entry_hash:
                return LedgerVerification(
                    decision_id=decision_id,
                    intact=False,
                    entries=len(entries),
                    head_hash=entries[-1].entry_hash,
                    broken_at=entry.sequence,
                    detail="Entry contents do not match the committed hash.",
                )
            previous_hash = entry.entry_hash
        return LedgerVerification(
            decision_id=decision_id,
            intact=True,
            entries=len(entries),
            head_hash=entries[-1].entry_hash,
            detail="Every entry matches its committed hash.",
        )


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


class MemoryEventLedger(EventLedger):
    def __init__(self) -> None:
        self._by_decision: dict[str, list[LedgerEntry]] = defaultdict(list)
        self._order: list[LedgerEntry] = []
        self._lock = RLock()

    def append(self, entries: list[LedgerEntry]) -> list[LedgerEntry]:
        with self._lock:
            for entry in entries:
                self._by_decision[entry.decision_id].append(entry)
                self._order.append(entry)
        return entries

    def entries(self, decision_id: str) -> list[LedgerEntry]:
        with self._lock:
            return list(self._by_decision.get(decision_id, ()))

    def recent(self, limit: int = 200) -> list[LedgerEntry]:
        with self._lock:
            return list(reversed(self._order[-limit:]))


class FirestoreDecisionStore(DecisionStore):
    def __init__(self, project: str | None, collection: str = "decisions") -> None:
        self._collection = _firestore_client(project).collection(collection)

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


class FirestoreEventLedger(EventLedger):
    """Ledger entries as immutable documents keyed ``<decision id>:<sequence>``.

    Writes use ``create`` rather than ``set`` so a repeated sequence number is
    rejected by the database, not merely by this process.
    """

    def __init__(self, project: str | None, collection: str = "decision_ledger") -> None:
        self._collection = _firestore_client(project).collection(collection)

    def append(self, entries: list[LedgerEntry]) -> list[LedgerEntry]:
        for entry in entries:
            document = self._collection.document(f"{entry.decision_id}:{entry.sequence:04d}")
            document.create(entry.model_dump(mode="json"))
        return entries

    def entries(self, decision_id: str) -> list[LedgerEntry]:
        documents = (
            self._collection.where("decision_id", "==", decision_id)
            .order_by("sequence")
            .stream()
        )
        return [LedgerEntry.model_validate(document.to_dict()) for document in documents]

    def recent(self, limit: int = 200) -> list[LedgerEntry]:
        from google.cloud import firestore

        documents = (
            self._collection.order_by("recorded_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        return [LedgerEntry.model_validate(document.to_dict()) for document in documents]


def _firestore_client(project: str | None):
    try:
        from google.cloud import firestore
    except ImportError as error:
        raise RuntimeError("Install the 'cloud' dependency group to use Firestore") from error
    return firestore.Client(project=project)
