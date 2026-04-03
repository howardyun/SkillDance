from __future__ import annotations

import csv
from pathlib import Path

from ..models import AnalysisResult


SKILLS_FIELDNAMES = [
    "skill_id",
    "root_path",
    "has_skill_md",
    "has_frontmatter",
    "has_references_dir",
    "has_scripts_dir",
    "has_assets_dir",
]
CLASSIFICATIONS_FIELDNAMES = [
    "skill_id",
    "layer",
    "category_id",
    "category_name",
    "confidence",
    "source_path",
    "line_start",
    "rule_id",
    "matched_text",
]
RULE_CANDIDATES_FIELDNAMES = [
    "skill_id",
    "candidate_id",
    "layer",
    "category_id",
    "category_name",
    "candidate_status",
    "rule_confidence",
    "confidence_score",
    "support_count",
    "conflict_count",
    "trigger_reason",
]
ATOMIC_DECISIONS_FIELDNAMES = [
    "skill_id",
    "layer",
    "atomic_id",
    "atomic_name",
    "decision_status",
    "confidence",
    "confidence_score",
    "mapped_category_ids",
]
CONTROL_DECISIONS_FIELDNAMES = [
    "skill_id",
    "layer",
    "control_id",
    "control_name",
    "decision_status",
    "confidence",
    "confidence_score",
]
DISCREPANCIES_FIELDNAMES = [
    "skill_id",
    "skill_level_discrepancy",
    "category_id",
    "category_name",
    "status",
    "declaration_present",
    "implementation_present",
]
REVIEW_AUDIT_FIELDNAMES = [
    "skill_id",
    "category_id",
    "layer",
    "review_status",
    "provider",
    "model",
    "reason",
    "schema_version",
]


def export_csv_files(output_dir: Path, results: list[AnalysisResult]) -> None:
    _write_csv(
        output_dir / "skills.csv",
        SKILLS_FIELDNAMES,
        [skill_rows(result)[0] for result in results],
    )
    _write_csv(
        output_dir / "classifications.csv",
        CLASSIFICATIONS_FIELDNAMES,
        classification_rows(results),
    )
    _write_csv(
        output_dir / "rule_candidates.csv",
        RULE_CANDIDATES_FIELDNAMES,
        candidate_rows(results),
    )
    _write_csv(
        output_dir / "atomic_decisions.csv",
        ATOMIC_DECISIONS_FIELDNAMES,
        atomic_decision_rows(results),
    )
    _write_csv(
        output_dir / "control_decisions.csv",
        CONTROL_DECISIONS_FIELDNAMES,
        control_decision_rows(results),
    )
    _write_csv(
        output_dir / "discrepancies.csv",
        DISCREPANCIES_FIELDNAMES,
        discrepancy_rows(results),
    )
    _write_csv(
        output_dir / "implementation_only_high_risk.csv",
        DISCREPANCIES_FIELDNAMES,
        discrepancy_rows(implementation_only_high_risk_results(results)),
    )
    _write_csv(
        output_dir / "review_audit.csv",
        REVIEW_AUDIT_FIELDNAMES,
        review_audit_rows(results),
    )


def skill_rows(result: AnalysisResult) -> list[dict[str, object]]:
    return [
        {
            "skill_id": result.skill_id,
            "root_path": result.root_path,
            "has_skill_md": result.structure_profile.has_skill_md,
            "has_frontmatter": result.structure_profile.has_frontmatter,
            "has_references_dir": result.structure_profile.has_references_dir,
            "has_scripts_dir": result.structure_profile.has_scripts_dir,
            "has_assets_dir": result.structure_profile.has_assets_dir,
        }
    ]


def classification_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        rows.extend(classification_rows_for_result(result))
    return rows


def classification_rows_for_result(result: AnalysisResult) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for layer, classifications in (
        ("declaration", result.declaration_classifications),
        ("implementation", result.implementation_classifications),
    ):
        for classification in classifications:
            for evidence in classification.evidence:
                rows.append(
                    {
                        "skill_id": result.skill_id,
                        "layer": layer,
                        "category_id": classification.category_id,
                        "category_name": classification.category_name,
                        "confidence": classification.confidence,
                        "source_path": evidence.source_path,
                        "line_start": evidence.line_start,
                        "rule_id": evidence.rule_id,
                        "matched_text": evidence.matched_text,
                    }
                )
    return rows


def implementation_only_high_risk_results(results: list[AnalysisResult]) -> list[AnalysisResult]:
    return [result for result in results if result.skill_level_discrepancy == "implementation_only_high_risk"]


def discrepancy_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        rows.extend(discrepancy_rows_for_result(result))
    return rows


def discrepancy_rows_for_result(result: AnalysisResult) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not result.category_discrepancies:
        rows.append(
            {
                "skill_id": result.skill_id,
                "skill_level_discrepancy": result.skill_level_discrepancy,
                "category_id": "",
                "category_name": "",
                "status": result.skill_level_discrepancy,
                "declaration_present": "",
                "implementation_present": "",
            }
        )
        return rows

    for item in result.category_discrepancies:
        rows.append(
            {
                "skill_id": result.skill_id,
                "skill_level_discrepancy": result.skill_level_discrepancy,
                "category_id": item.category_id,
                "category_name": item.category_name,
                "status": item.status,
                "declaration_present": item.declaration_present,
                "implementation_present": item.implementation_present,
            }
        )
    return rows


def candidate_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        rows.extend(candidate_rows_for_result(result))
    return rows


def candidate_rows_for_result(result: AnalysisResult) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for candidate in result.rule_candidates:
        rows.append(
            {
                "skill_id": result.skill_id,
                "candidate_id": candidate.candidate_id,
                "layer": candidate.layer,
                "category_id": candidate.category_id,
                "category_name": candidate.category_name,
                "candidate_status": candidate.candidate_status,
                "rule_confidence": candidate.rule_confidence,
                "confidence_score": candidate.confidence_score,
                "support_count": len(candidate.supporting_evidence),
                "conflict_count": len(candidate.conflicting_evidence),
                "trigger_reason": candidate.trigger_reason,
            }
        )
    return rows


def review_audit_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        rows.extend(review_audit_rows_for_result(result))
    return rows


def review_audit_rows_for_result(result: AnalysisResult) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in result.review_audit_records:
        rows.append(
            {
                "skill_id": result.skill_id,
                "category_id": record.category_id,
                "layer": record.layer,
                "review_status": record.review_status,
                "provider": record.provider or "",
                "model": record.model or "",
                "reason": record.reason or "",
                "schema_version": record.schema_version or "",
            }
        )
    return rows


def atomic_decision_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        for layer, decisions in (
            ("declaration", result.declaration_atomic_decisions),
            ("implementation", result.implementation_atomic_decisions),
        ):
            for decision in decisions:
                rows.append(
                    {
                        "skill_id": result.skill_id,
                        "layer": layer,
                        "atomic_id": decision.atomic_id,
                        "atomic_name": decision.atomic_name,
                        "decision_status": decision.decision_status,
                        "confidence": decision.confidence,
                        "confidence_score": decision.confidence_score,
                        "mapped_category_ids": ",".join(decision.mapped_category_ids),
                    }
                )
    return rows


def control_decision_rows(results: list[AnalysisResult]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        for layer, decisions in (
            ("declaration", result.declaration_control_decisions),
            ("implementation", result.implementation_control_decisions),
        ):
            for decision in decisions:
                rows.append(
                    {
                        "skill_id": result.skill_id,
                        "layer": layer,
                        "control_id": decision.control_id,
                        "control_name": decision.control_name,
                        "decision_status": decision.decision_status,
                        "confidence": decision.confidence,
                        "confidence_score": decision.confidence_score,
                    }
                )
    return rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
