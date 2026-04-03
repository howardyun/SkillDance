from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..models import AnalysisResult


@dataclass(slots=True)
class GoldsetExpectation:
    skill_id: str
    layer: str
    category_id: str
    decision_status: str | None = None


def load_goldset(path: Path) -> list[GoldsetExpectation]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        GoldsetExpectation(
            skill_id=str(item["skill_id"]),
            layer=str(item["layer"]),
            category_id=str(item["category_id"]),
            decision_status=str(item["decision_status"]) if item.get("decision_status") else None,
        )
        for item in payload
    ]


def validate_against_goldset(results: list[AnalysisResult], expectations: list[GoldsetExpectation]) -> dict[str, object]:
    observed = {
        (result.skill_id, decision.layer, decision.category_id): decision
        for result in results
        for decision in result.final_decisions
        if decision.decision_status != "rejected_by_llm"
    }
    matched = 0
    missing: list[dict[str, str]] = []
    mismatched_status: list[dict[str, str]] = []
    for expectation in expectations:
        key = (expectation.skill_id, expectation.layer, expectation.category_id)
        decision = observed.get(key)
        if decision is None:
            missing.append(
                {
                    "skill_id": expectation.skill_id,
                    "layer": expectation.layer,
                    "category_id": expectation.category_id,
                }
            )
            continue
        if expectation.decision_status and decision.decision_status != expectation.decision_status:
            mismatched_status.append(
                {
                    "skill_id": expectation.skill_id,
                    "layer": expectation.layer,
                    "category_id": expectation.category_id,
                    "expected_status": expectation.decision_status,
                    "actual_status": decision.decision_status,
                }
            )
            continue
        matched += 1
    total = len(expectations)
    accuracy = matched / total if total else 1.0
    return {
        "expected_count": total,
        "matched_count": matched,
        "missing_count": len(missing),
        "mismatched_status_count": len(mismatched_status),
        "accuracy": accuracy,
        "missing": missing,
        "mismatched_status": mismatched_status,
    }
