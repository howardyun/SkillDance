from __future__ import annotations

from collections import defaultdict

from .models import AnalysisResult, CapabilityMapping, CategoryDiscrepancy, ControlSemantic, MatrixCategory


WRITE_OR_BATCH_ATOMICS = {"G4", "G5", "O2", "O3", "O4", "O5", "A6", "I2", "I3"}
SCOPE_DRIFT_ATOMICS = {"O3", "G5", "I2", "I3"}
AUTONOMY_DRIFT_ATOMICS = {"A3", "A4", "A5", "A6", "A7", "O5"}
MANUAL_GUARD_ATOMICS = {"A2", "G2", "O1"}


def compute_discrepancies(
    result: AnalysisResult,
    matrix_by_id: dict[str, MatrixCategory],
    capability_mappings: list[CapabilityMapping],
    control_semantics: list[ControlSemantic],
) -> tuple[str, list[CategoryDiscrepancy]]:
    mapping_index = _build_mapping_index(capability_mappings)
    declaration_by_category = _group_atomic_decisions(result.declaration_atomic_decisions, mapping_index)
    implementation_by_category = _group_atomic_decisions(result.implementation_atomic_decisions, mapping_index)
    control_category_index = _build_control_category_index(control_semantics, mapping_index)
    declaration_controls_by_category = _group_control_decisions(
        result.declaration_control_decisions,
        control_category_index,
    )
    implementation_controls_by_category = _group_control_decisions(
        result.implementation_control_decisions,
        control_category_index,
    )

    all_ids = sorted(
        set(matrix_by_id)
        | set(declaration_by_category)
        | set(implementation_by_category)
        | set(declaration_controls_by_category)
        | set(implementation_controls_by_category)
    )
    category_discrepancies: list[CategoryDiscrepancy] = []
    mismatch_totals: list[str] = []
    for category_id in all_ids:
        matrix_category = matrix_by_id.get(category_id)
        if matrix_category is None:
            continue
        declaration_atomic_ids = sorted(declaration_by_category.get(category_id, set()))
        implementation_atomic_ids = sorted(implementation_by_category.get(category_id, set()))
        declaration_control_ids = sorted(declaration_controls_by_category.get(category_id, set()))
        implementation_control_ids = sorted(implementation_controls_by_category.get(category_id, set()))
        declaration_present = bool(declaration_atomic_ids or declaration_control_ids)
        implementation_present = bool(implementation_atomic_ids or implementation_control_ids)
        mismatch_ids = _collect_mismatch_ids(
            declaration_atomic_ids,
            implementation_atomic_ids,
            set(declaration_control_ids),
            set(implementation_control_ids),
        )
        if not mismatch_ids and not declaration_present and not implementation_present:
            continue
        mismatch_totals.extend(mismatch_ids)
        category_discrepancies.append(
            CategoryDiscrepancy(
                category_id=category_id,
                category_name=matrix_category.subcategory,
                status=_legacy_status_for_mismatches(mismatch_ids, declaration_present, implementation_present, matrix_category),
                declaration_present=declaration_present,
                implementation_present=implementation_present,
                risks=matrix_category.primary_risks,
                controls=matrix_category.control_requirements,
                mismatch_ids=mismatch_ids,
                declaration_atomic_ids=declaration_atomic_ids,
                implementation_atomic_ids=implementation_atomic_ids,
                declaration_control_ids=declaration_control_ids,
                implementation_control_ids=implementation_control_ids,
            )
        )

    skill_level_discrepancy = _skill_level_status(
        result,
        mismatch_totals,
        matrix_by_id,
        declaration_by_category,
        implementation_by_category,
    )
    return skill_level_discrepancy, category_discrepancies


def _group_atomic_decisions(decisions, mapping_index: dict[str, set[str]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for decision in decisions:
        if decision.decision_status != "accepted":
            continue
        mapped_ids = decision.mapped_category_ids or sorted(mapping_index.get(decision.atomic_id, set()))
        for category_id in mapped_ids:
            grouped[category_id].add(decision.atomic_id)
    return grouped


def _build_mapping_index(capability_mappings: list[CapabilityMapping]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for mapping in capability_mappings:
        index[mapping.atomic_id].add(mapping.category_id)
    return index


def _build_control_category_index(
    control_semantics: list[ControlSemantic],
    mapping_index: dict[str, set[str]],
) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for control in control_semantics:
        for atomic_id in control.applicable_atomic_ids:
            for category_id in mapping_index.get(atomic_id, set()):
                index[control.control_id].add(category_id)
    return index


def _group_control_decisions(decisions, control_category_index: dict[str, set[str]]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for decision in decisions:
        if decision.decision_status != "accepted":
            continue
        for category_id in sorted(control_category_index.get(decision.control_id, set())):
            grouped[category_id].add(decision.control_id)
    return grouped


def _collect_mismatch_ids(
    declaration_atomic_ids: list[str],
    implementation_atomic_ids: list[str],
    declaration_controls: set[str],
    implementation_controls: set[str],
) -> list[str]:
    mismatch_ids: list[str] = []
    declared = set(declaration_atomic_ids)
    implemented = set(implementation_atomic_ids)
    if not declared and implemented:
        mismatch_ids.append("M1")
    if implemented - declared:
        mismatch_ids.append("M2")
    if declared - implemented:
        mismatch_ids.append("M3")
    if declaration_controls - implementation_controls:
        mismatch_ids.append("M4")
    if any(item in implemented for item in SCOPE_DRIFT_ATOMICS) and not any(item in declared for item in SCOPE_DRIFT_ATOMICS):
        mismatch_ids.append("M5")
    if any(item in implemented for item in AUTONOMY_DRIFT_ATOMICS) and (declared & MANUAL_GUARD_ATOMICS or "C3" in declaration_controls):
        mismatch_ids.append("M6")
    if implemented and not declared and not any(item in implemented for item in WRITE_OR_BATCH_ATOMICS):
        mismatch_ids.append("M7")
    return sorted(set(mismatch_ids))


def _legacy_status_for_mismatches(
    mismatch_ids: list[str],
    declaration_present: bool,
    implementation_present: bool,
    matrix_category: MatrixCategory,
) -> str:
    mismatch_set = set(mismatch_ids)
    if not mismatch_ids and declaration_present and implementation_present:
        return "declared_and_implemented_aligned"
    if "M1" in mismatch_set or ("M2" in mismatch_set and _has_high_risk(matrix_category)):
        return "implementation_only_high_risk"
    if "M2" in mismatch_set:
        return "declared_less_than_implemented"
    if "M3" in mismatch_set:
        return "declared_more_than_implemented"
    if "M4" in mismatch_set:
        if declaration_present and not implementation_present:
            return "declared_more_than_implemented"
        if implementation_present and not declaration_present:
            return "declared_less_than_implemented"
        return "declared_more_than_implemented"
    if "M7" in mismatch_set:
        return "insufficient_implementation_evidence"
    if not declaration_present and not implementation_present:
        return "insufficient_declaration_evidence"
    return "declared_and_implemented_aligned"


def _skill_level_status(
    result: AnalysisResult,
    mismatch_totals: list[str],
    matrix_by_id: dict[str, MatrixCategory],
    declaration_by_category: dict[str, set[str]],
    implementation_by_category: dict[str, set[str]],
) -> str:
    if not result.declaration_atomic_decisions and not result.implementation_atomic_decisions:
        return "insufficient_declaration_evidence"
    if not result.declaration_atomic_decisions:
        if any(_has_high_risk(matrix_by_id[category_id]) for category_id in implementation_by_category):
            return "implementation_only_high_risk"
        return "insufficient_declaration_evidence"
    if not implementation_by_category:
        return "declared_more_than_implemented"
    mismatch_set = set(mismatch_totals)
    if "M1" in mismatch_set:
        return "implementation_only_high_risk"
    if "M2" in mismatch_set:
        high_risk_gap = any(
            _has_high_risk(matrix_by_id[category_id])
            for category_id, implemented in implementation_by_category.items()
            if implemented - declaration_by_category.get(category_id, set())
        )
        return "implementation_only_high_risk" if high_risk_gap else "declared_less_than_implemented"
    if "M3" in mismatch_set:
        return "declared_more_than_implemented"
    if "M7" in mismatch_set:
        return "insufficient_implementation_evidence"
    return "declared_and_implemented_aligned"


def _has_high_risk(category: MatrixCategory) -> bool:
    high_risk_codes = {"E", "D", "T", "I", "R"}
    return any(risk in high_risk_codes for risk in category.primary_risks)
