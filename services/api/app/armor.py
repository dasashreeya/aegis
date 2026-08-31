"""Input and output shields on the fleet boundary.

Two layers, always both:

1. A local pattern shield that runs in every mode with no network. It catches
   the injection and policy-bypass phrasings an attacker puts in a claim
   narrative, plus the obvious personal identifiers that must never reach a
   model or an audit log.
2. Hosted **Model Armor**, when a template is configured. It screens the same
   text against the sanitizer Google operates, and it is the layer that produces
   the block events shown in the Cloud console.

The shield is the one component that fails closed. If a configured hosted
template cannot be reached and ``model_armor_fail_closed`` is set, the decision
is refused rather than processed unscreened -- an oversight system that silently
stops screening is worse than one that stops.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from app.config import Settings
from app.models import DecisionInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArmorFinding:
    category: str
    detail: str
    matched: str


@dataclass(frozen=True)
class ArmorResult:
    safe: bool
    findings: tuple[str, ...]
    engine: str = "local"
    degraded: bool = False
    detail: str = ""
    detections: tuple[ArmorFinding, ...] = field(default=())

    @property
    def summary(self) -> str:
        if self.safe:
            suffix = " (hosted template unreachable, local shield only)" if self.degraded else ""
            return f"Screened by {self.engine}; no injection, bypass or PII detected.{suffix}"
        categories = ", ".join(sorted({item.category for item in self.detections})) or "policy"
        return f"Blocked by {self.engine}: {categories}."


class Shield(Protocol):
    def inspect(self, decision: DecisionInput) -> ArmorResult: ...

    def inspect_response(self, text: str) -> ArmorResult: ...


_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (category, re.compile(expression, re.IGNORECASE))
    for category, expression in (
        ("prompt_injection", r"ignore (all|any|the) (previous|prior) instructions"),
        ("prompt_injection", r"disregard (the |your )?(above|previous|prior)"),
        ("prompt_injection", r"reveal (the )?(system|developer) prompt"),
        ("prompt_injection", r"you are now (a|an|in) "),
        ("policy_bypass", r"bypass (the )?(policy|rules|controls|guardrails)"),
        ("policy_bypass", r"(approve|deny) (this|the) (claim|case) regardless"),
        ("policy_bypass", r"override (the )?(solver|adjudicat\w+|determination)"),
        ("tool_poisoning", r"(call|invoke|use) the .{0,24}tool to (exfiltrate|send|post)"),
        ("tool_poisoning", r"<\s*(script|iframe|object)\b"),
    )
)

_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pii_ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("pii_email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("pii_mrn", re.compile(r"\bMRN[:\s#-]*\d{6,}\b", re.IGNORECASE)),
    ("pii_card", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
)


def screened_text(decision: DecisionInput) -> str:
    """The free-text surface of a decision -- everything an attacker controls."""
    return (
        f"{decision.source} {decision.subject} "
        f"{decision.requested_service} {decision.policy_id}"
    )


class InputShield:
    """Local pattern shield. Runs in every mode, needs no credentials."""

    engine = "local pattern shield"

    def _scan(self, content: str) -> tuple[ArmorFinding, ...]:
        detections: list[ArmorFinding] = []
        for category, pattern in _INJECTION_PATTERNS + _PII_PATTERNS:
            match = pattern.search(content)
            if match:
                detections.append(
                    ArmorFinding(
                        category=category,
                        detail=pattern.pattern,
                        matched=_redact(match.group(0)),
                    )
                )
        return tuple(detections)

    def inspect(self, decision: DecisionInput) -> ArmorResult:
        return self._result(self._scan(screened_text(decision)))

    def inspect_response(self, text: str) -> ArmorResult:
        return self._result(self._scan(text))

    def _result(self, detections: tuple[ArmorFinding, ...]) -> ArmorResult:
        return ArmorResult(
            safe=not detections,
            findings=tuple(item.detail for item in detections),
            engine=self.engine,
            detections=detections,
        )


class ModelArmorShield:
    """Hosted Model Armor, layered over the local shield.

    The local scan always runs first, so a hosted outage degrades screening
    rather than removing it.
    """

    engine = "Model Armor"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._local = InputShield()
        self._template = settings.armor_resource_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import modelarmor_v1

            endpoint = f"modelarmor.{self._settings.model_armor_location}.rep.googleapis.com"
            self._client = modelarmor_v1.ModelArmorClient(
                client_options={"api_endpoint": endpoint}
            )
        return self._client

    def inspect(self, decision: DecisionInput) -> ArmorResult:
        return self._merge(self._local.inspect(decision), screened_text(decision), "prompt")

    def inspect_response(self, text: str) -> ArmorResult:
        return self._merge(self._local.inspect_response(text), text, "response")

    def _merge(self, local: ArmorResult, content: str, direction: str) -> ArmorResult:
        try:
            detections = self._sanitize(content, direction)
        except Exception as error:  # noqa: BLE001 - any failure means unscreened text
            logger.warning("Model Armor unavailable (%s); local shield only", error)
            fail_closed = self._settings.model_armor_fail_closed
            return ArmorResult(
                safe=local.safe and not fail_closed,
                findings=local.findings or ("model_armor_unreachable",),
                engine=self.engine,
                degraded=True,
                detail=str(error)[:200],
                detections=local.detections,
            )
        combined = local.detections + detections
        return ArmorResult(
            safe=not combined,
            findings=tuple(item.detail for item in combined),
            engine=self.engine,
            detections=combined,
        )

    def _sanitize(self, content: str, direction: str) -> tuple[ArmorFinding, ...]:
        from google.cloud import modelarmor_v1

        client = self._get_client()
        data = modelarmor_v1.DataItem(text=content)
        if direction == "prompt":
            response = client.sanitize_user_prompt(
                request=modelarmor_v1.SanitizeUserPromptRequest(
                    name=self._template, user_prompt_data=data
                )
            )
        else:
            response = client.sanitize_model_response(
                request=modelarmor_v1.SanitizeModelResponseRequest(
                    name=self._template, model_response_data=data
                )
            )
        return _detections_from(response.sanitization_result, modelarmor_v1.FilterMatchState)


def _detections_from(result, match_state) -> tuple[ArmorFinding, ...]:
    """Flatten the Model Armor filter tree into the findings Aegis records."""
    if result.filter_match_state != match_state.MATCH_FOUND:
        return ()
    detections: list[ArmorFinding] = []
    for name, filter_result in (result.filter_results or {}).items():
        for attribute in (
            "rai_filter_result",
            "sdp_filter_result",
            "pi_and_jailbreak_filter_result",
            "malicious_uri_filter_result",
            "csam_filter_result",
        ):
            inner = getattr(filter_result, attribute, None)
            if inner is None:
                continue
            state = getattr(inner, "match_state", None)
            if state == match_state.MATCH_FOUND:
                detections.append(
                    ArmorFinding(category=name, detail=attribute, matched="model-armor")
                )
    if not detections:
        detections.append(
            ArmorFinding(category="model_armor", detail="filter_match", matched="model-armor")
        )
    return tuple(detections)


def _redact(value: str) -> str:
    """Never echo the matched text back into an audit log verbatim."""
    stripped = value.strip()
    if len(stripped) <= 6:
        return "*" * len(stripped)
    return f"{stripped[:3]}{'*' * (len(stripped) - 6)}{stripped[-3:]}"


def build_shield(settings: Settings) -> Shield:
    """Hosted Model Armor when a template is configured, local shield otherwise."""
    if settings.armor_configured and settings.wants_network:
        return ModelArmorShield(settings)
    return InputShield()
