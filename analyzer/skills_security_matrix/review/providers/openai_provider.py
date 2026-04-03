from __future__ import annotations

import json
import os
from dataclasses import asdict

from ..llm_provider import LLMReviewProvider
from ..models import ReviewRequest, ReviewResponse, StructuredReviewDecision
from .prompting import build_review_system_prompt


class OpenAIReviewProvider(LLMReviewProvider):
    provider_name = "openai"

    def review_category(self, request: ReviewRequest, *, model: str | None, timeout_seconds: int) -> ReviewResponse:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE_URL")
        if not api_key:
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error="OPENAI_API_KEY is not set",
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            return ReviewResponse(
                category_id=request.candidate.category_id,
                layer=request.candidate.layer,
                provider=self.provider_name,
                model=model,
                review_status="provider_error",
                error=f"openai package is not installed: {exc}",
            )

        try:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_seconds)
            response = client.responses.create(
                model=model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                input=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": build_review_system_prompt(),
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": _build_payload(request)}],
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "skills_security_matrix_review",
                        "strict": True,
                        "schema": _review_schema(),
                    }
                },
            )
            parsed = json.loads(response.output_text)
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
            decision=StructuredReviewDecision(
                decision_status=str(parsed["decision_status"]),
                reason=str(parsed["reason"]),
                confidence=str(parsed["confidence"]),
                confidence_score=float(parsed["confidence_score"]),
                supporting_fingerprints=[str(item) for item in parsed.get("supporting_fingerprints", [])],
                conflicting_fingerprints=[str(item) for item in parsed.get("conflicting_fingerprints", [])],
            ),
            raw_payload=parsed,
        )


def _review_schema() -> dict[str, object]:
    return {
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
    }


def _build_payload(request: ReviewRequest) -> str:
    return json.dumps(
        {
            "task": "Review exactly one pre-existing category candidate and decide whether it should be accepted, downgraded, or rejected_by_llm.",
            "skill_id": request.skill_id,
            "candidate": {
                "category_id": request.candidate.category_id,
                "category_name": request.candidate.category_name,
                "layer": request.candidate.layer,
                "candidate_status": request.candidate.candidate_status,
                "rule_confidence": request.candidate.rule_confidence,
                "confidence_score": request.candidate.confidence_score,
            },
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
            "supporting_evidence": [
                {
                    "fingerprint": item.evidence_fingerprint,
                    "path": item.source_path,
                    "text": item.matched_text,
                }
                for item in request.supporting_evidence[:5]
            ],
            "conflicting_evidence": [
                {
                    "fingerprint": item.evidence_fingerprint,
                    "path": item.source_path,
                    "text": item.matched_text,
                }
                for item in request.conflicting_evidence[:5]
            ],
            "output_requirements": {
                "reason_style": "brief, concrete, evidence-focused",
                "fingerprint_rule": "Only return fingerprints that appear in the supplied evidence arrays.",
            },
        },
        ensure_ascii=False,
    )
