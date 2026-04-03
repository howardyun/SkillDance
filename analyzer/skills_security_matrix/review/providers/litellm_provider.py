from __future__ import annotations

import json
import os
from dataclasses import asdict

from ..llm_provider import LLMReviewProvider
from ..models import ReviewRequest, ReviewResponse, StructuredReviewDecision
from .prompting import build_review_system_prompt


class LiteLLMReviewProvider(LLMReviewProvider):
    provider_name = "litellm"

    def review_category(self, request: ReviewRequest, *, model: str | None, timeout_seconds: int) -> ReviewResponse:
        try:
            import litellm  # type: ignore
        except ImportError as exc:
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=f"LiteLLM is not installed: {exc}",
            )

        schema = _review_schema()
        prompt = _build_prompt(request)
        try:
            response = litellm.completion(
                model=model or os.getenv("LITELLM_MODEL", ""),
                messages=[
                    {"role": "system", "content": build_review_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_schema", "json_schema": schema},
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content
            payload = json.loads(content)
        except Exception as exc:  # pragma: no cover - network/provider defensive path
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=str(exc),
            )
        return ReviewResponse(
            category_id=request.candidate.category_id,
            layer=request.candidate.layer,
            provider=self.provider_name,
            model=model,
            review_status="reviewed",
            decision=_decision_from_payload(payload),
            raw_payload=payload,
        )


def _review_schema() -> dict[str, object]:
    return {
        "name": "skills_security_matrix_review",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "decision_status": {
                    "type": "string",
                    "enum": ["accepted", "downgraded", "rejected_by_llm"],
                },
                "reason": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "confidence_score": {"type": "number"},
                "supporting_fingerprints": {"type": "array", "items": {"type": "string"}},
                "conflicting_fingerprints": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "decision_status",
                "reason",
                "confidence",
                "confidence_score",
                "supporting_fingerprints",
                "conflicting_fingerprints",
            ],
            "additionalProperties": False,
        },
    }


def _build_prompt(request: ReviewRequest) -> str:
    support = [
        {
            "path": item.source_path,
            "lines": [item.line_start, item.line_end],
            "text": item.matched_text,
            "fingerprint": item.evidence_fingerprint,
        }
        for item in request.supporting_evidence[:5]
    ]
    conflicts = [
        {
            "path": item.source_path,
            "lines": [item.line_start, item.line_end],
            "text": item.matched_text,
            "fingerprint": item.evidence_fingerprint,
        }
        for item in request.conflicting_evidence[:5]
    ]
    return json.dumps(
        {
            "task": "Review exactly one pre-existing category candidate and decide whether it should be accepted, downgraded, or rejected_by_llm.",
            "skill_id": request.skill_id,
            "category_id": request.candidate.category_id,
            "category_name": request.candidate.category_name,
            "layer": request.candidate.layer,
            "candidate_status": request.candidate.candidate_status,
            "rule_confidence": request.candidate.rule_confidence,
            "confidence_score": request.candidate.confidence_score,
            "triggers": [asdict(trigger) for trigger in request.triggers],
            "decision_policy": {
                "allowed_statuses": ["accepted", "downgraded", "rejected_by_llm"],
                "accepted": "Use only when the evidence is direct and sufficient.",
                "downgraded": "Use when support exists but is weak, sparse, indirect, or ambiguous.",
                "rejected_by_llm": "Use when support is not grounded in the provided evidence or conflicts dominate.",
                "forbidden_actions": [
                    "inventing new categories",
                    "reclassifying the entire skill",
                    "using evidence that is not included in the payload",
                ],
            },
            "supporting_evidence": support,
            "conflicting_evidence": conflicts,
            "output_requirements": {
                "reason_style": "brief, concrete, evidence-focused",
                "fingerprint_rule": "Only return fingerprints that appear in the supplied evidence arrays.",
            },
        },
        ensure_ascii=False,
    )


def _decision_from_payload(payload: dict[str, object]) -> StructuredReviewDecision:
    return StructuredReviewDecision(
        decision_status=str(payload["decision_status"]),
        reason=str(payload["reason"]),
        confidence=str(payload["confidence"]),
        confidence_score=float(payload["confidence_score"]),
        supporting_fingerprints=[str(item) for item in payload.get("supporting_fingerprints", [])],
        conflicting_fingerprints=[str(item) for item in payload.get("conflicting_fingerprints", [])],
    )
