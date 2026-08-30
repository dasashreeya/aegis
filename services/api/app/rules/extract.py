"""Policy prose -> structured, grounded constraints.

The model proposes; deterministic validation disposes. Every rule the extractor returns has
been checked against the fact schema and against the source document, so a hallucinated field
or an invented quotation fails loudly instead of silently becoming a constraint.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.llm import LLMClient
from app.models import DecisionFacts

PredicateKind = Literal["require_true", "at_most", "at_least"]

BOOLEAN_FACTS = frozenset(
    name for name, field in DecisionFacts.model_fields.items() if field.annotation is bool
)
NUMERIC_FACTS = frozenset(
    name
    for name, field in DecisionFacts.model_fields.items()
    if field.annotation is int and name not in BOOLEAN_FACTS
)
KNOWN_FACTS = BOOLEAN_FACTS | NUMERIC_FACTS


class RuleExtractionError(ValueError):
    """Raised when the model's output cannot be trusted as a constraint set."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


class RulePredicate(BaseModel):
    """The machine-checkable core of a clause."""

    kind: PredicateKind
    fields: list[str] = Field(min_length=1)
    limit: int | None = None


class ExtractedRule(BaseModel):
    rule_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    predicate: RulePredicate
    citation: str = Field(min_length=1, max_length=80)
    source_excerpt: str = Field(min_length=1)
    satisfied_explanation: str = Field(min_length=1)
    unsatisfied_explanation: str = Field(min_length=1)
    relaxation: str = Field(min_length=1)


class PolicyExtraction(BaseModel):
    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    rules: list[ExtractedRule] = Field(min_length=1)

    @property
    def version_label(self) -> str:
        return f"{self.policy_id}@{self.version}"


SYSTEM_INSTRUCTION = """\
You convert governing policy prose into machine-checkable constraints for a formal solver.

Rules you must follow:
- Emit one rule per operative condition in the document. Ignore scope, definitions and preamble.
- Only reference fields from the supplied fact schema. Never invent a field.
- `source_excerpt` must be copied verbatim from the document, as one contiguous span.
- `citation` is the section marker the excerpt came from, e.g. "§ 30.2".
- Explanations are one plain sentence each, written for a claims reviewer, no jargon.
- `relaxation` states the smallest change that would satisfy the clause.
- Explanations and relaxations may use {placeholders} naming fact fields, plus {limit},
  {remaining} (limit minus the used field), {total} (sum of the fields) and {deficit}
  (total minus limit). Use them only when a number genuinely helps.
"""

_PREDICATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["require_true", "at_most", "at_least"]},
        "fields": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "limit": {"type": ["integer", "null"]},
    },
    "required": ["kind", "fields"],
}

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string"},
                    "title": {"type": "string"},
                    "predicate": _PREDICATE_SCHEMA,
                    "citation": {"type": "string"},
                    "source_excerpt": {"type": "string"},
                    "satisfied_explanation": {"type": "string"},
                    "unsatisfied_explanation": {"type": "string"},
                    "relaxation": {"type": "string"},
                },
                "required": [
                    "rule_id",
                    "title",
                    "predicate",
                    "citation",
                    "source_excerpt",
                    "satisfied_explanation",
                    "unsatisfied_explanation",
                    "relaxation",
                ],
            },
        }
    },
    "required": ["rules"],
}


def content_version(policy_text: str) -> str:
    """Provenance for a document that does not declare its own version."""
    return hashlib.sha256(policy_text.encode("utf-8")).hexdigest()[:12]


def _normalize(value: str) -> str:
    return " ".join(value.split()).lower()


def _predicate_problems(rule_id: str, predicate: RulePredicate) -> list[str]:
    problems: list[str] = []
    unknown = [name for name in predicate.fields if name not in KNOWN_FACTS]
    if unknown:
        problems.append(f"{rule_id}: unknown fact field(s) {sorted(unknown)}")

    if predicate.kind == "require_true":
        if predicate.limit is not None:
            problems.append(f"{rule_id}: require_true takes no limit")
        if len(predicate.fields) != 1:
            problems.append(f"{rule_id}: require_true takes exactly one field")
        wrong = [name for name in predicate.fields if name in NUMERIC_FACTS]
        if wrong:
            problems.append(f"{rule_id}: require_true needs boolean field(s), got {sorted(wrong)}")
    else:
        if predicate.limit is None:
            problems.append(f"{rule_id}: {predicate.kind} needs an integer limit")
        wrong = [name for name in predicate.fields if name in BOOLEAN_FACTS]
        if wrong:
            problems.append(f"{rule_id}: {predicate.kind} needs numeric field(s), got {sorted(wrong)}")
    return problems


def validate_extraction(
    payload: dict[str, Any],
    *,
    policy_id: str,
    version: str,
    policy_text: str,
) -> PolicyExtraction:
    """Parse and ground the model's output, or raise with every problem found."""
    try:
        rules = [ExtractedRule.model_validate(item) for item in payload.get("rules") or []]
    except ValidationError as error:
        raise RuleExtractionError([f"malformed rule: {error.errors()[0]['msg']}"]) from error
    if not rules:
        raise RuleExtractionError(["the model returned no rules"])

    problems: list[str] = []
    haystack = _normalize(policy_text)
    seen: set[str] = set()
    for rule in rules:
        if rule.rule_id in seen:
            problems.append(f"{rule.rule_id}: duplicate rule_id")
        seen.add(rule.rule_id)
        problems.extend(_predicate_problems(rule.rule_id, rule.predicate))
        if _normalize(rule.source_excerpt) not in haystack:
            problems.append(f"{rule.rule_id}: source_excerpt is not present in the document")
    if problems:
        raise RuleExtractionError(problems)

    return PolicyExtraction(policy_id=policy_id, version=version, rules=rules)


class RuleExtractor:
    """Turns a policy document into a `PolicyExtraction`, or fails loudly."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def extract(
        self,
        *,
        policy_id: str,
        policy_text: str,
        version: str | None = None,
    ) -> PolicyExtraction:
        if not policy_text.strip():
            raise RuleExtractionError(["the policy document is empty"])

        payload = self._client.generate_json(
            system=SYSTEM_INSTRUCTION,
            prompt=self._prompt(policy_id, policy_text),
            schema=EXTRACTION_SCHEMA,
        )
        return validate_extraction(
            payload,
            policy_id=policy_id,
            version=version or content_version(policy_text),
            policy_text=policy_text,
        )

    @staticmethod
    def _prompt(policy_id: str, policy_text: str) -> str:
        schema_lines = "\n".join(
            f"- {name}: {'boolean' if name in BOOLEAN_FACTS else 'integer'}"
            for name in sorted(KNOWN_FACTS)
        )
        return (
            f"Policy identifier: {policy_id}\n\n"
            f"Fact schema available to the solver:\n{schema_lines}\n\n"
            f"Policy document:\n---\n{policy_text}\n---"
        )
