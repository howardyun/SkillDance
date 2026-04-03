from __future__ import annotations

from .models import AnalysisResult, MatrixCategory


def build_risk_mappings(result: AnalysisResult, matrix_by_id: dict[str, MatrixCategory]) -> list[dict[str, object]]:
    category_ids = {decision.category_id for decision in result.final_decisions if decision.decision_status != "rejected_by_llm"}
    declaration_atomic_by_category = _group_atomic_ids(result.declaration_atomic_decisions)
    implementation_atomic_by_category = _group_atomic_ids(result.implementation_atomic_decisions)
    declaration_controls = sorted(
        {item.control_id for item in result.declaration_control_decisions if item.decision_status == "accepted"}
    )
    implementation_controls = sorted(
        {item.control_id for item in result.implementation_control_decisions if item.decision_status == "accepted"}
    )
    mappings: list[dict[str, object]] = []
    for category_id in sorted(category_ids):
        matrix_category = matrix_by_id[category_id]
        mappings.append(
            {
                "category_id": category_id,
                "category_name": matrix_category.subcategory,
                "major_category": matrix_category.major_category,
                "risks": matrix_category.primary_risks,
                "controls": matrix_category.control_requirements,
                "declaration_atomic_ids": sorted(declaration_atomic_by_category.get(category_id, set())),
                "implementation_atomic_ids": sorted(implementation_atomic_by_category.get(category_id, set())),
                "declared_control_ids": declaration_controls,
                "implemented_control_ids": implementation_controls,
                "missing_control_ids": sorted(set(declaration_controls) - set(implementation_controls)),
            }
        )
    return mappings


def _group_atomic_ids(decisions) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for decision in decisions:
        if decision.decision_status != "accepted":
            continue
        for category_id in decision.mapped_category_ids:
            grouped.setdefault(category_id, set()).add(decision.atomic_id)
    return grouped
