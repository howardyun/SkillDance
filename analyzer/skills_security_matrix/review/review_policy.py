from __future__ import annotations

from dataclasses import dataclass

from ..models import MatrixCategory, RuleCandidate
from .models import ReviewRequest, ReviewTrigger


@dataclass(slots=True)
class ReviewPolicyConfig:
    mode: str
    low_confidence_threshold: float
    high_risk_sparse_threshold: int
    fallback_max_categories: int
    failure_policy: str


def build_review_requests(
    skill_id: str,
    candidates: list[RuleCandidate],
    matrix_by_id: dict[str, MatrixCategory],
    config: ReviewPolicyConfig,
) -> list[ReviewRequest]:
    if config.mode == "off":
        return []

    requests: list[ReviewRequest] = []
    fallback_budget = config.fallback_max_categories
    for candidate in candidates:
        triggers = _collect_triggers(candidate, matrix_by_id, config)
        if not triggers:
            continue
        fallback_allowed = config.mode == "review+fallback" and fallback_budget > 0
        if fallback_allowed:
            fallback_budget -= 1
        requests.append(
            ReviewRequest(
                skill_id=skill_id,
                candidate=candidate,
                supporting_evidence=candidate.supporting_evidence,
                conflicting_evidence=candidate.conflicting_evidence,
                triggers=triggers,
                fallback_allowed=fallback_allowed,
            )
        )
    return requests


def _collect_triggers(
    candidate: RuleCandidate,
    matrix_by_id: dict[str, MatrixCategory],
    config: ReviewPolicyConfig,
) -> list[ReviewTrigger]:
    triggers: list[ReviewTrigger] = []
    if candidate.confidence_score <= config.low_confidence_threshold:
        triggers.append(
            ReviewTrigger(
                category_id=candidate.category_id,
                layer=candidate.layer,
                trigger_type="low_confidence",
                reason=f"confidence_score={candidate.confidence_score:.2f} <= {config.low_confidence_threshold:.2f}",
            )
        )
    if candidate.conflicting_evidence:
        triggers.append(
            ReviewTrigger(
                category_id=candidate.category_id,
                layer=candidate.layer,
                trigger_type="conflict",
                reason=f"conflicting_evidence={len(candidate.conflicting_evidence)}",
            )
        )
    matrix_category = matrix_by_id.get(candidate.category_id)
    if matrix_category and _is_high_risk(matrix_category) and len(candidate.supporting_evidence) <= config.high_risk_sparse_threshold:
        triggers.append(
            ReviewTrigger(
                category_id=candidate.category_id,
                layer=candidate.layer,
                trigger_type="high_risk_sparse_support",
                reason=(
                    f"high_risk category with support_count={len(candidate.supporting_evidence)} "
                    f"<= {config.high_risk_sparse_threshold}"
                ),
            )
        )
    return triggers


def _is_high_risk(category: MatrixCategory) -> bool:
    high_risk_codes = {"E", "D", "T", "I", "R"}
    return any(risk in high_risk_codes for risk in category.primary_risks)
