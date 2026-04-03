from __future__ import annotations

import json
from pathlib import Path

from ..models import AnalysisResult, RunSummary, dataclass_to_dict


def export_json_files(output_dir: Path, results: list[AnalysisResult], summary: RunSummary) -> None:
    _write_json(output_dir / "skills.json", [skill_record(result) for result in results])
    _write_json(output_dir / "rule_candidates.json", [candidate_record(result) for result in results])
    _write_json(output_dir / "classifications.json", [classification_record(result) for result in results])
    _write_json(output_dir / "discrepancies.json", [discrepancy_record(result) for result in results])
    _write_json(
        output_dir / "implementation_only_high_risk.json",
        [discrepancy_record(result) for result in implementation_only_high_risk_results(results)],
    )
    _write_json(output_dir / "risk_mappings.json", [risk_mapping_record(result) for result in results])
    _write_json(output_dir / "review_audit.json", [review_audit_record(result) for result in results])
    _write_json(output_dir / "run_manifest.json", dataclass_to_dict(summary))
    if summary.validation_summary is not None:
        _write_json(output_dir / "validation.json", summary.validation_summary)

    cases_dir = output_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        _write_json(cases_dir / f"{_safe_filename(result.skill_id)}.json", dataclass_to_dict(result))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_filename(value: str) -> str:
    return value.replace("/", "__")


def implementation_only_high_risk_results(results: list[AnalysisResult]) -> list[AnalysisResult]:
    return [result for result in results if result.skill_level_discrepancy == "implementation_only_high_risk"]


def skill_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "root_path": result.root_path,
        "structure_profile": dataclass_to_dict(result.structure_profile),
        "errors": result.errors,
    }


def classification_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "declaration_atomic_decisions": [dataclass_to_dict(item) for item in result.declaration_atomic_decisions],
        "implementation_atomic_decisions": [dataclass_to_dict(item) for item in result.implementation_atomic_decisions],
        "declaration_control_decisions": [dataclass_to_dict(item) for item in result.declaration_control_decisions],
        "implementation_control_decisions": [dataclass_to_dict(item) for item in result.implementation_control_decisions],
        "final_decisions": [dataclass_to_dict(item) for item in result.final_decisions],
        "declaration_classifications": [dataclass_to_dict(item) for item in result.declaration_classifications],
        "implementation_classifications": [dataclass_to_dict(item) for item in result.implementation_classifications],
        "risk_mappings": result.risk_mappings,
        "errors": result.errors,
    }


def candidate_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "rule_candidates": [dataclass_to_dict(item) for item in result.rule_candidates],
        "errors": result.errors,
    }


def discrepancy_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "skill_level_discrepancy": result.skill_level_discrepancy,
        "category_discrepancies": [dataclass_to_dict(item) for item in result.category_discrepancies],
        "errors": result.errors,
    }


def risk_mapping_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "risk_mappings": result.risk_mappings,
        "errors": result.errors,
    }


def review_audit_record(result: AnalysisResult) -> dict[str, object]:
    return {
        "skill_id": result.skill_id,
        "review_audit_records": [dataclass_to_dict(item) for item in result.review_audit_records],
        "errors": result.errors,
    }
