from __future__ import annotations

from pathlib import Path

from ..matrix_loader import load_matrix_definition
from ..models import CategoryClassification, EvidenceItem
from .candidate_builder import build_atomic_decisions, build_rule_candidates, decisions_to_classifications, finalize_rule_candidates


def classify_declaration(evidence: list[EvidenceItem]) -> list[CategoryClassification]:
    definition = load_matrix_definition(Path("analyzer/security matrix.md"))
    matrix_by_id = {category.category_id: category for category in definition.categories}
    atomic_decisions = build_atomic_decisions(evidence, layer="declaration", capability_mappings=definition.capability_mappings)
    candidates = build_rule_candidates(atomic_decisions, layer="declaration", matrix_by_id=matrix_by_id)
    return decisions_to_classifications(finalize_rule_candidates(candidates), layer="declaration")
