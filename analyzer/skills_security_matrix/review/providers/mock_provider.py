from __future__ import annotations

from ..llm_provider import LLMReviewProvider
from ..models import ReviewRequest, ReviewResponse, StructuredReviewDecision


class MockReviewProvider(LLMReviewProvider):
    provider_name = "mock"

    def review_category(self, request: ReviewRequest, *, model: str | None, timeout_seconds: int) -> ReviewResponse:
        candidate = request.candidate
        support = candidate.supporting_evidence
        if candidate.confidence_score < 0.2:
            decision_status = "rejected_by_llm"
            confidence = "low"
            confidence_score = 0.0
        elif candidate.confidence_score < 0.55:
            decision_status = "downgraded"
            confidence = "low"
            confidence_score = min(candidate.confidence_score, 0.35)
        else:
            decision_status = "accepted"
            confidence = candidate.rule_confidence
            confidence_score = candidate.confidence_score

        return ReviewResponse(
            category_id=candidate.category_id,
            layer=candidate.layer,
            provider=self.provider_name,
            model=model,
            review_status="reviewed",
            decision=StructuredReviewDecision(
                decision_status=decision_status,
                reason=f"mock review applied from confidence_score={candidate.confidence_score:.2f}",
                confidence=confidence,
                confidence_score=confidence_score,
                supporting_fingerprints=[item.evidence_fingerprint for item in support[:3]],
                conflicting_fingerprints=[item.evidence_fingerprint for item in candidate.conflicting_evidence[:3]],
            ),
            raw_payload={"mock": True, "timeout_seconds": timeout_seconds},
        )
