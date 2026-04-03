from __future__ import annotations

from ..models import FinalCategoryDecision
from .models import ReviewRequest


def build_fallback_decision(request: ReviewRequest) -> FinalCategoryDecision:
    candidate = request.candidate
    if candidate.supporting_evidence and candidate.confidence_score >= 0.2:
        decision_status = "fallback_adjudicated"
        confidence = "low"
        confidence_score = min(candidate.confidence_score, 0.4)
    else:
        decision_status = "insufficient_evidence"
        confidence = "low"
        confidence_score = 0.0
    return FinalCategoryDecision(
        category_id=candidate.category_id,
        category_name=candidate.category_name,
        layer=candidate.layer,
        decision_status=decision_status,
        supporting_evidence=candidate.supporting_evidence,
        conflicting_evidence=candidate.conflicting_evidence,
        confidence=confidence,
        confidence_score=confidence_score,
        source_candidate_ids=[candidate.candidate_id],
    )
