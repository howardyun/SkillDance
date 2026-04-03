from __future__ import annotations

from dataclasses import dataclass, field

from ..models import EvidenceItem, RuleCandidate


@dataclass(slots=True)
class ReviewTrigger:
    category_id: str
    layer: str
    trigger_type: str
    reason: str


@dataclass(slots=True)
class ReviewRequest:
    skill_id: str
    candidate: RuleCandidate
    supporting_evidence: list[EvidenceItem] = field(default_factory=list)
    conflicting_evidence: list[EvidenceItem] = field(default_factory=list)
    triggers: list[ReviewTrigger] = field(default_factory=list)
    fallback_allowed: bool = False


@dataclass(slots=True)
class StructuredReviewDecision:
    decision_status: str
    reason: str
    confidence: str
    confidence_score: float
    supporting_fingerprints: list[str] = field(default_factory=list)
    conflicting_fingerprints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReviewResponse:
    category_id: str
    layer: str
    provider: str
    model: str | None
    review_status: str
    decision: StructuredReviewDecision | None = None
    raw_payload: dict[str, object] | None = None
    error: str | None = None
    schema_version: str = "skills-security-matrix-review-v1"
