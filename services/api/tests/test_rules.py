"""Track A: policy prose -> extraction -> Z3 -> minimal core -> relaxations.

Extraction is stubbed everywhere, so CI never reaches Gemini.
"""

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from app.models import DecisionFacts, DecisionInput
from app.rules import (
    DEFAULT_POLICY,
    PolicyExtraction,
    PolicyRegistry,
    RuleExtractionError,
    RuleExtractor,
    validate_extraction,
)
from app.solver import EligibilitySolver

POLICY_TEXT = (Path(__file__).parent / "fixtures" / "cms_snf.md").read_text(encoding="utf-8")


class StubGemini:
    """Stands in for `GeminiClient`; records what the extractor asked for."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        return deepcopy(self.payload)


def model_payload() -> dict[str, Any]:
    """The JSON a well-behaved model returns for `cms_snf.md`."""
    return {"rules": [rule.model_dump() for rule in DEFAULT_POLICY.rules]}


def extract(payload: dict[str, Any] | None = None) -> PolicyExtraction:
    client = StubGemini(payload or model_payload())
    return RuleExtractor(client).extract(
        policy_id="CMS-SNF-100",
        policy_text=POLICY_TEXT,
        version="2025-10-01",
    )


def decision(**overrides: Any) -> DecisionInput:
    facts = {
        "medically_necessary": True,
        "skilled_care_required": True,
        "benefit_days_used": 19,
        "requested_days": 7,
    }
    facts.update({k: v for k, v in overrides.items() if k in DecisionFacts.model_fields})
    return DecisionInput(
        source="Benefits Engine",
        subject="Case 2048",
        requested_service="Post-acute skilled nursing care",
        original_decision=overrides.get("original_decision", "denied"),
        policy_id=overrides.get("policy_id", "CMS-SNF-100"),
        facts=DecisionFacts(**facts),
    )


def solver_for(extraction: PolicyExtraction) -> EligibilitySolver:
    return EligibilitySolver(PolicyRegistry([extraction]))


def citations(result: Any, extraction: PolicyExtraction) -> set[str]:
    by_id = {rule.rule_id: rule.citation for rule in extraction.rules}
    return {by_id[name] for name in result.unsat_core if name in by_id}


# --- extraction -------------------------------------------------------------------------


def test_extractor_sends_the_document_and_the_fact_schema() -> None:
    client = StubGemini(model_payload())
    RuleExtractor(client).extract(policy_id="CMS-SNF-100", policy_text=POLICY_TEXT)

    prompt = client.calls[0]["prompt"]
    assert "§ 30.6 Benefit period limitation" in prompt
    assert "benefit_days_used: integer" in prompt
    assert "medically_necessary: boolean" in prompt


def test_extraction_produces_cited_rules() -> None:
    extraction = extract()
    assert [rule.rule_id for rule in extraction.rules] == [
        "medical_necessity",
        "skilled_care_required",
        "benefit_days_available",
    ]
    assert [rule.citation for rule in extraction.rules] == ["§ 30.2", "§ 30.3", "§ 30.6"]
    assert extraction.version_label == "CMS-SNF-100@2025-10-01"


def test_undeclared_version_falls_back_to_a_content_hash() -> None:
    extraction = RuleExtractor(StubGemini(model_payload())).extract(
        policy_id="CMS-SNF-100",
        policy_text=POLICY_TEXT,
    )
    assert len(extraction.version) == 12
    assert extraction.version != "2025-10-01"


def test_checked_in_default_policy_is_grounded_in_the_fixture() -> None:
    validate_extraction(
        model_payload(),
        policy_id="CMS-SNF-100",
        version="2025-10-01",
        policy_text=POLICY_TEXT,
    )


def test_hallucinated_quotation_is_rejected() -> None:
    payload = model_payload()
    payload["rules"][0]["source_excerpt"] = "coverage requires prior authorization by the plan"
    with pytest.raises(RuleExtractionError) as caught:
        extract(payload)
    assert "source_excerpt is not present in the document" in str(caught.value)


def test_invented_fact_field_is_rejected() -> None:
    payload = model_payload()
    payload["rules"][0]["predicate"] = {"kind": "require_true", "fields": ["prior_auth_on_file"]}
    with pytest.raises(RuleExtractionError) as caught:
        extract(payload)
    assert "unknown fact field(s) ['prior_auth_on_file']" in str(caught.value)


def test_threshold_without_a_limit_is_rejected() -> None:
    payload = model_payload()
    payload["rules"][2]["predicate"]["limit"] = None
    with pytest.raises(RuleExtractionError) as caught:
        extract(payload)
    assert "at_most needs an integer limit" in str(caught.value)


def test_boolean_field_in_a_threshold_is_rejected() -> None:
    payload = model_payload()
    payload["rules"][2]["predicate"]["fields"] = ["medically_necessary"]
    with pytest.raises(RuleExtractionError) as caught:
        extract(payload)
    assert "needs numeric field(s)" in str(caught.value)


def test_empty_document_never_reaches_the_model() -> None:
    client = StubGemini(model_payload())
    with pytest.raises(RuleExtractionError):
        RuleExtractor(client).extract(policy_id="CMS-SNF-100", policy_text="   \n  ")
    assert client.calls == []


# --- solving ----------------------------------------------------------------------------


def test_unsupported_denial_core_names_every_governing_clause() -> None:
    extraction = extract()
    result = solver_for(extraction).evaluate(decision(original_decision="denied"))

    assert result.eligible is True
    assert result.conflicts_with_original is True
    assert set(result.unsat_core) == {
        "medical_necessity",
        "skilled_care_required",
        "benefit_days_available",
        "original_denied",
    }
    assert citations(result, extraction) == {"§ 30.2", "§ 30.3", "§ 30.6"}
    assert result.policy_version == "CMS-SNF-100@2025-10-01"
    assert result.relaxations[0].startswith("Approve the request")


def test_core_is_minimal_when_one_clause_fails() -> None:
    extraction = extract()
    result = solver_for(extraction).evaluate(
        decision(medically_necessary=False, original_decision="approved"),
    )

    assert result.eligible is False
    assert result.unsat_core == ["medical_necessity", "original_approved"]
    assert citations(result, extraction) == {"§ 30.2"}
    assert result.relaxations == [
        (
            "Document that the services are reasonable and necessary for the "
            "beneficiary's condition (§ 30.2)."
        )
    ]


def test_relaxation_quantifies_the_benefit_day_overrun() -> None:
    extraction = extract()
    result = solver_for(extraction).evaluate(
        decision(benefit_days_used=95, requested_days=10, original_decision="approved"),
    )

    assert result.unsat_core == ["benefit_days_available", "original_approved"]
    assert result.relaxations == [
        "Reduce the request to at most 5 days, 5 fewer than requested (§ 30.6)."
    ]


def test_findings_carry_the_clause_they_came_from() -> None:
    extraction = extract()
    result = solver_for(extraction).evaluate(decision())

    days = next(item for item in result.findings if item.rule_id == "benefit_days_available")
    assert days.citation == "§ 30.6"
    assert "may not exceed that 100-day maximum" in (days.source_excerpt or "")
    assert days.explanation == "81 covered days remain; 7 were requested."


def test_supported_decision_has_no_conflict_set() -> None:
    extraction = extract()
    result = solver_for(extraction).evaluate(decision(original_decision="approved"))

    assert result.conflicts_with_original is False
    assert result.unsat_core == []
    assert result.relaxations == []


def test_unknown_policy_reports_the_policy_that_actually_ran() -> None:
    result = EligibilitySolver().evaluate(decision(policy_id="CMS-HHA-200"))
    assert result.policy_version == "CMS-SNF-100@2025-10-01"


def test_extracted_policy_overrides_the_frozen_default() -> None:
    payload = model_payload()
    payload["rules"][2]["predicate"]["limit"] = 20
    extraction = extract(payload)

    result = solver_for(extraction).evaluate(
        decision(benefit_days_used=19, requested_days=7, original_decision="denied"),
    )
    assert result.eligible is False
    assert result.conflicts_with_original is False
