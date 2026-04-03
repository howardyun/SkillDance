from __future__ import annotations

from ..models import FinalCategoryDecision, ReviewAuditRecord, RuleCandidate
from .fallback import build_fallback_decision
from .llm_provider import LLMReviewProvider
from .models import ReviewRequest, ReviewResponse, StructuredReviewDecision


def review_candidates(
    review_requests: list[ReviewRequest],
    default_decisions: list[FinalCategoryDecision],
    provider: LLMReviewProvider | None,
    *,
    model: str | None,
    timeout_seconds: int,
    failure_policy: str,
) -> tuple[list[FinalCategoryDecision], list[ReviewAuditRecord]]:
    decisions_by_key = {(decision.layer, decision.category_id): decision for decision in default_decisions}
    audit_records: list[ReviewAuditRecord] = []
    for request in review_requests:
        decision_key = (request.candidate.layer, request.candidate.category_id)
        if provider is None:
            fallback_or_default = _handle_provider_unavailable(request, decisions_by_key[decision_key], failure_policy)
            decisions_by_key[decision_key] = fallback_or_default
            audit_records.append(_audit_for_unavailable_provider(request, failure_policy))
            continue

        response = provider.review_category(request, model=model, timeout_seconds=timeout_seconds)
        final_decision = _merge_review_response(request, decisions_by_key[decision_key], response, failure_policy)
        decisions_by_key[decision_key] = final_decision
        audit_records.append(_audit_from_response(response))
    return list(decisions_by_key.values()), audit_records


def _merge_review_response(
    request: ReviewRequest,
    default_decision: FinalCategoryDecision,
    response: ReviewResponse,
    failure_policy: str,
) -> FinalCategoryDecision:
    if response.review_status != "reviewed" or response.decision is None:
        if request.fallback_allowed:
            return build_fallback_decision(request)
        if failure_policy == "fail_closed":
            return _decision_from_candidate(request.candidate, "rejected_by_llm", 0.0, "low")
        return default_decision

    validated = _validate_decision(request, response.decision)
    if validated is None:
        if request.fallback_allowed:
            return build_fallback_decision(request)
        if failure_policy == "fail_closed":
            return _decision_from_candidate(request.candidate, "rejected_by_llm", 0.0, "low")
        return default_decision
    return validated


def _validate_decision(request: ReviewRequest, decision: StructuredReviewDecision) -> FinalCategoryDecision | None:
    if decision.decision_status not in {"accepted", "downgraded", "rejected_by_llm"}:
        return None
    supporting = [
        item for item in request.supporting_evidence if item.evidence_fingerprint in set(decision.supporting_fingerprints or [])
    ] or request.supporting_evidence
    conflicting = [
        item for item in request.conflicting_evidence if item.evidence_fingerprint in set(decision.conflicting_fingerprints or [])
    ]
    return FinalCategoryDecision(
        category_id=request.candidate.category_id,
        category_name=request.candidate.category_name,
        layer=request.candidate.layer,
        decision_status=decision.decision_status,
        supporting_evidence=supporting,
        conflicting_evidence=conflicting,
        confidence=decision.confidence,
        confidence_score=decision.confidence_score,
        source_candidate_ids=[request.candidate.candidate_id],
    )


def _decision_from_candidate(
    candidate: RuleCandidate,
    status: str,
    confidence_score: float,
    confidence: str,
) -> FinalCategoryDecision:
    return FinalCategoryDecision(
        category_id=candidate.category_id,
        category_name=candidate.category_name,
        layer=candidate.layer,
        decision_status=status,
        supporting_evidence=candidate.supporting_evidence,
        conflicting_evidence=candidate.conflicting_evidence,
        confidence=confidence,
        confidence_score=confidence_score,
        source_candidate_ids=[candidate.candidate_id],
    )


def _handle_provider_unavailable(
    request: ReviewRequest,
    default_decision: FinalCategoryDecision,
    failure_policy: str,
) -> FinalCategoryDecision:
    if request.fallback_allowed:
        return build_fallback_decision(request)
    if failure_policy == "fail_closed":
        return _decision_from_candidate(request.candidate, "rejected_by_llm", 0.0, "low")
    return default_decision


def _audit_from_response(response: ReviewResponse) -> ReviewAuditRecord:
    return ReviewAuditRecord(
        category_id=response.category_id,
        layer=response.layer,
        review_status=response.review_status,
        provider=response.provider,
        model=response.model,
        reason=response.error if response.error else None,
        schema_version=response.schema_version,
    )


def _audit_for_unavailable_provider(request: ReviewRequest, failure_policy: str) -> ReviewAuditRecord:
    status = "fallback_adjudicated" if request.fallback_allowed else "provider_unavailable"
    return ReviewAuditRecord(
        category_id=request.candidate.category_id,
        layer=request.candidate.layer,
        review_status=status,
        provider=None,
        model=None,
        reason=f"provider unavailable with failure_policy={failure_policy}",
        schema_version="skills-security-matrix-review-v1",
    )
