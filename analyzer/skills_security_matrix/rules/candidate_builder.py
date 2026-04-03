from __future__ import annotations

from collections import defaultdict

from ..models import (
    AtomicEvidenceDecision,
    CapabilityMapping,
    CategoryClassification,
    ControlDecision,
    EvidenceItem,
    FinalCategoryDecision,
    MatrixCategory,
    RuleCandidate,
)
from .catalog import bucket_confidence, highest_confidence


def build_atomic_decisions(
    evidence: list[EvidenceItem],
    layer: str,
    capability_mappings: list[CapabilityMapping],
) -> list[AtomicEvidenceDecision]:
    mapping_index = _build_mapping_index(capability_mappings)
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in evidence:
        if item.layer == layer and item.subject_type == "atomic_capability":
            grouped[item.category_id].append(item)

    decisions: list[AtomicEvidenceDecision] = []
    for atomic_id, items in sorted(grouped.items()):
        confidence_score = _calculate_confidence_score(items)
        decisions.append(
            AtomicEvidenceDecision(
                atomic_id=atomic_id,
                atomic_name=items[0].category_name,
                layer=layer,
                decision_status=_decision_status_for_evidence(items),
                supporting_evidence=_dedupe_evidence(items)[:10],
                confidence=bucket_confidence(confidence_score),
                confidence_score=confidence_score,
                mapped_category_ids=sorted(mapping_index.get(atomic_id, set())),
            )
        )
    return decisions


def build_control_decisions(evidence: list[EvidenceItem], layer: str) -> list[ControlDecision]:
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in evidence:
        if item.layer == layer and item.subject_type == "control_semantic":
            grouped[item.category_id].append(item)

    decisions: list[ControlDecision] = []
    for control_id, items in sorted(grouped.items()):
        confidence_score = _calculate_confidence_score(items)
        decisions.append(
            ControlDecision(
                control_id=control_id,
                control_name=items[0].category_name,
                layer=layer,
                decision_status=_decision_status_for_evidence(items),
                evidence=_dedupe_evidence(items)[:10],
                confidence=bucket_confidence(confidence_score),
                confidence_score=confidence_score,
            )
        )
    return decisions


def build_rule_candidates(
    atomic_decisions: list[AtomicEvidenceDecision],
    layer: str,
    matrix_by_id: dict[str, MatrixCategory],
) -> list[RuleCandidate]:
    grouped: dict[str, list[AtomicEvidenceDecision]] = defaultdict(list)
    for decision in atomic_decisions:
        if decision.layer != layer or decision.decision_status not in {"accepted", "fallback_adjudicated"}:
            continue
        for category_id in decision.mapped_category_ids:
            grouped[category_id].append(decision)

    candidates: list[RuleCandidate] = []
    for category_index, category_id in enumerate(sorted(grouped), start=1):
        matrix_category = matrix_by_id[category_id]
        decisions = grouped[category_id]
        support = _dedupe_evidence(
            [item for decision in decisions for item in decision.supporting_evidence]
        )[:10]
        confidence_score = min(
            1.0,
            max((decision.confidence_score for decision in decisions), default=0.0)
            + min(len(decisions), 3) * 0.1,
        )
        candidates.append(
            RuleCandidate(
                candidate_id=f"{layer}:{category_id}:{category_index}",
                category_id=category_id,
                category_name=matrix_category.subcategory,
                layer=layer,
                candidate_status="supported",
                supporting_evidence=support,
                conflicting_evidence=[],
                rule_confidence=bucket_confidence(confidence_score),
                confidence_score=confidence_score,
                trigger_reason="atomic_capability_rollup",
            )
        )
    return candidates


def finalize_rule_candidates(candidates: list[RuleCandidate]) -> list[FinalCategoryDecision]:
    decisions: list[FinalCategoryDecision] = []
    for candidate in candidates:
        decisions.append(
            FinalCategoryDecision(
                category_id=candidate.category_id,
                category_name=candidate.category_name,
                layer=candidate.layer,
                decision_status="accepted" if candidate.supporting_evidence else "insufficient_evidence",
                supporting_evidence=candidate.supporting_evidence,
                conflicting_evidence=candidate.conflicting_evidence,
                confidence=candidate.rule_confidence,
                confidence_score=candidate.confidence_score,
                source_candidate_ids=[candidate.candidate_id],
            )
        )
    return decisions


def decisions_to_classifications(decisions: list[FinalCategoryDecision], layer: str) -> list[CategoryClassification]:
    filtered = [decision for decision in decisions if decision.layer == layer and decision.decision_status != "rejected_by_llm"]
    classifications: list[CategoryClassification] = []
    for decision in filtered:
        evidence = _dedupe_evidence(decision.supporting_evidence + decision.conflicting_evidence)[:10]
        classifications.append(
            CategoryClassification(
                category_id=decision.category_id,
                category_name=decision.category_name,
                evidence=evidence,
                confidence=decision.confidence,
                confidence_score=decision.confidence_score,
                decision_status=decision.decision_status,
            )
        )
    return classifications


def _build_mapping_index(capability_mappings: list[CapabilityMapping]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for mapping in capability_mappings:
        index[mapping.atomic_id].add(mapping.category_id)
    return index


def _decision_status_for_evidence(items: list[EvidenceItem]) -> str:
    strengths = {item.evidence_strength for item in items}
    if "strong" in strengths:
        return "accepted"
    if len(items) >= 2 and highest_confidence([item.confidence for item in items]) in {"high", "medium"}:
        return "accepted"
    return "insufficient_evidence"


def _calculate_confidence_score(items: list[EvidenceItem]) -> float:
    if not items:
        return 0.0
    strong = sum(0.35 for item in items if item.evidence_strength == "strong")
    medium = sum(0.2 for item in items if item.evidence_strength == "medium")
    weak = sum(0.1 for item in items if item.evidence_strength == "weak")
    unique_sources = len({item.source_path for item in items}) * 0.08
    reference_bonus = 0.1 if any(item.support_reference_mode == "referenced_by_skill_md" for item in items) else 0.0
    direct_bonus = 0.08 if any(item.source_kind in {"skill_md_frontmatter", "skill_md_body"} for item in items) else 0.0
    lexical_bonus = 0.08 if highest_confidence([item.confidence for item in items]) == "high" else 0.0
    return min(1.0, strong + medium + weak + unique_sources + reference_bonus + direct_bonus + lexical_bonus)


def _dedupe_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    unique: dict[str, EvidenceItem] = {}
    for item in items:
        unique.setdefault(item.evidence_fingerprint, item)
    return list(unique.values())
