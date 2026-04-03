from __future__ import annotations

import argparse
import tempfile
from datetime import datetime
from pathlib import Path

from ..env import load_environment
from .discrepancy import compute_discrepancies
from .evidence.declaration import extract_declaration_evidence
from .evidence.implementation import extract_implementation_evidence
from .exporters.csv_exporter import export_csv_files
from .exporters.json_exporter import export_json_files
from .matrix_loader import load_matrix_definition
from .models import AnalysisResult, RunConfig, RunSummary
from .review.llm_provider import ProviderRegistry
from .review.llm_reviewer import review_candidates
from .review.providers.litellm_provider import LiteLLMReviewProvider
from .review.providers.mock_provider import MockReviewProvider
from .review.providers.openai_provider import OpenAIReviewProvider
from .review.review_policy import ReviewPolicyConfig, build_review_requests
from .risk_mapping import build_risk_mappings
from .rules.candidate_builder import (
    build_atomic_decisions,
    build_control_decisions,
    build_rule_candidates,
    decisions_to_classifications,
    finalize_rule_candidates,
)
from .skill_discovery import discover_skills
from .validation.goldset import load_goldset, validate_against_goldset


DEFAULT_MATRIX_PATH = Path("analyzer/security matrix.md")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze local skill repositories against the security matrix.")
    parser.add_argument("--skills-dir", required=True, help="Top-level directory containing skill repositories.")
    parser.add_argument(
        "--output-dir",
        default="outputs/skills_security_matrix",
        help="Base output directory. A timestamped run directory will be created within it.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Analyze only the first N skills.")
    parser.add_argument("--format", default="json,csv", help="Comma-separated formats: json,csv")
    parser.add_argument("--case-study-skill", default=None, help="Skill id to highlight in the run summary.")
    parser.add_argument("--fail-on-unknown-matrix", action="store_true", help="Fail if the matrix contains unknown categories.")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden skill directories.")
    parser.add_argument(
        "--matrix-path",
        default=str(DEFAULT_MATRIX_PATH),
        help="Path to the markdown matrix table file.",
    )
    parser.add_argument(
        "--llm-review-mode",
        default="off",
        choices=["off", "review", "review+fallback"],
        help="Optional category-level review mode.",
    )
    parser.add_argument("--llm-provider", default=None, help="Review provider registry key, for example mock, litellm, or openai.")
    parser.add_argument("--llm-model", default=None, help="Model name passed through to the selected review provider.")
    parser.add_argument(
        "--llm-low-confidence-threshold",
        type=float,
        default=0.45,
        help="Review categories with confidence scores at or below this threshold.",
    )
    parser.add_argument(
        "--llm-high-risk-sparse-threshold",
        type=int,
        default=1,
        help="Review high-risk categories whose support evidence count is at or below this threshold.",
    )
    parser.add_argument(
        "--llm-fallback-max-categories",
        type=int,
        default=0,
        help="Maximum number of triggered categories that may use fallback adjudication.",
    )
    parser.add_argument("--llm-timeout-seconds", type=int, default=30, help="Per-category provider timeout.")
    failure_policy = parser.add_mutually_exclusive_group()
    failure_policy.add_argument("--llm-fail-open", action="store_true", help="Keep offline decisions when provider calls fail.")
    failure_policy.add_argument("--llm-fail-closed", action="store_true", help="Reject reviewed categories when provider calls fail.")
    parser.add_argument("--emit-review-audit", action="store_true", help="Emit review audit records in outputs and manifest.")
    parser.add_argument("--goldset-path", default=None, help="Optional JSON gold set for validation against final decisions.")
    return parser


def run_analysis(args: argparse.Namespace) -> RunSummary:
    load_environment()
    requested_formats = [value.strip() for value in args.format.split(",") if value.strip()]
    matrix_definition = load_matrix_definition(Path(args.matrix_path))
    matrix_by_id = {category.category_id: category for category in matrix_definition.categories}
    provider_registry = _build_provider_registry()
    failure_policy = "fail_closed" if getattr(args, "llm_fail_closed", False) else "fail_open"

    skills = discover_skills(Path(args.skills_dir), include_hidden=args.include_hidden, limit=args.limit)
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[AnalysisResult] = []
    skill_errors: list[dict[str, str]] = []
    for skill in skills:
        try:
            result = _analyze_skill(skill, matrix_definition, matrix_by_id, args, provider_registry, failure_policy)
        except Exception as exc:  # pragma: no cover - defensive batch isolation
            skill_errors.append({"skill_id": skill.skill_id, "error": str(exc)})
            result = AnalysisResult(
                skill_id=skill.skill_id,
                root_path=str(skill.root_path),
                structure_profile=skill.structure,
                errors=[str(exc)],
            )
        results.append(result)

    summary = RunSummary(
        run_id=run_id,
        output_dir=str(run_dir),
        analyzed_skills=len(results),
        skipped_skills=0,
        errored_skills=len(skill_errors),
        config=RunConfig(
            skills_dir=args.skills_dir,
            output_dir=args.output_dir,
            requested_formats=requested_formats,
            limit=args.limit,
            case_study_skill=args.case_study_skill,
            include_hidden=args.include_hidden,
            fail_on_unknown_matrix=args.fail_on_unknown_matrix,
            llm_review_mode=args.llm_review_mode,
            llm_provider=args.llm_provider,
            llm_model=args.llm_model,
            llm_low_confidence_threshold=args.llm_low_confidence_threshold,
            llm_high_risk_sparse_threshold=args.llm_high_risk_sparse_threshold,
            llm_fallback_max_categories=args.llm_fallback_max_categories,
            llm_timeout_seconds=args.llm_timeout_seconds,
            llm_failure_policy=failure_policy,
            emit_review_audit=args.emit_review_audit,
            goldset_path=args.goldset_path,
        ),
        skill_errors=skill_errors,
    )
    if args.goldset_path:
        expectations = load_goldset(Path(args.goldset_path))
        summary.validation_summary = validate_against_goldset(results, expectations)

    if "json" in requested_formats:
        export_json_files(run_dir, results, summary)
    if "csv" in requested_formats:
        export_csv_files(run_dir, results)

    return summary


def _analyze_skill(skill, matrix_definition, matrix_by_id, args, provider_registry: ProviderRegistry, failure_policy: str):
    declaration_evidence = extract_declaration_evidence(skill)
    implementation_evidence = extract_implementation_evidence(skill)
    declaration_atomic_decisions = build_atomic_decisions(
        declaration_evidence,
        layer="declaration",
        capability_mappings=matrix_definition.capability_mappings,
    )
    implementation_atomic_decisions = build_atomic_decisions(
        implementation_evidence,
        layer="implementation",
        capability_mappings=matrix_definition.capability_mappings,
    )
    declaration_control_decisions = build_control_decisions(declaration_evidence, layer="declaration")
    implementation_control_decisions = build_control_decisions(implementation_evidence, layer="implementation")
    declaration_candidates = build_rule_candidates(declaration_atomic_decisions, layer="declaration", matrix_by_id=matrix_by_id)
    implementation_candidates = build_rule_candidates(implementation_atomic_decisions, layer="implementation", matrix_by_id=matrix_by_id)
    rule_candidates = declaration_candidates + implementation_candidates
    final_decisions = finalize_rule_candidates(rule_candidates)
    review_requests = build_review_requests(
        skill.skill_id,
        rule_candidates,
        matrix_by_id,
        ReviewPolicyConfig(
            mode=args.llm_review_mode,
            low_confidence_threshold=args.llm_low_confidence_threshold,
            high_risk_sparse_threshold=args.llm_high_risk_sparse_threshold,
            fallback_max_categories=args.llm_fallback_max_categories,
            failure_policy=failure_policy,
        ),
    )
    review_audit_records = []
    if review_requests:
        provider = provider_registry.get(args.llm_provider)
        final_decisions, review_audit_records = review_candidates(
            review_requests,
            final_decisions,
            provider,
            model=args.llm_model,
            timeout_seconds=args.llm_timeout_seconds,
            failure_policy=failure_policy,
        )
    declaration_classifications = decisions_to_classifications(final_decisions, layer="declaration")
    implementation_classifications = decisions_to_classifications(final_decisions, layer="implementation")
    result = AnalysisResult(
        skill_id=skill.skill_id,
        root_path=str(skill.root_path),
        structure_profile=skill.structure,
        declaration_atomic_decisions=declaration_atomic_decisions,
        implementation_atomic_decisions=implementation_atomic_decisions,
        declaration_control_decisions=declaration_control_decisions,
        implementation_control_decisions=implementation_control_decisions,
        rule_candidates=rule_candidates,
        final_decisions=final_decisions,
        declaration_classifications=declaration_classifications,
        implementation_classifications=implementation_classifications,
        review_audit_records=review_audit_records if args.emit_review_audit or args.llm_review_mode != "off" else [],
    )
    result.skill_level_discrepancy, result.category_discrepancies = compute_discrepancies(
        result,
        matrix_by_id,
        matrix_definition.capability_mappings,
        matrix_definition.control_semantics,
    )
    result.risk_mappings = build_risk_mappings(result, matrix_by_id)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = run_analysis(args)
    print(f"Run complete: {summary.run_id}")
    print(f"Output directory: {summary.output_dir}")
    print(f"Analyzed skills: {summary.analyzed_skills}")
    print(f"Errored skills: {summary.errored_skills}")
    if summary.config.case_study_skill:
        print(f"Case study requested: {summary.config.case_study_skill}")
    if summary.validation_summary:
        print(f"Validation accuracy: {summary.validation_summary['accuracy']:.2%}")
    return 0


def _build_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(MockReviewProvider())
    registry.register(LiteLLMReviewProvider())
    registry.register(OpenAIReviewProvider())
    return registry


if __name__ == "__main__":
    raise SystemExit(main())
