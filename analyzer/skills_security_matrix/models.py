from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MatrixCategory:
    category_id: str
    major_category: str
    subcategory: str
    security_definition: str
    data_level: str
    primary_risks: list[str]
    control_requirements: list[str]


@dataclass(slots=True)
class AtomicCapability:
    atomic_id: str
    atomic_name: str
    minimal_condition: str
    primary_risks: list[str]
    necessary_controls: list[str]


@dataclass(slots=True)
class ControlSemantic:
    control_id: str
    control_name: str
    minimal_condition: str
    applicable_atomic_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CapabilityMapping:
    atomic_id: str
    category_id: str


@dataclass(slots=True)
class MismatchDefinition:
    mismatch_id: str
    mismatch_name: str
    definition: str
    trigger_condition: str


@dataclass(slots=True)
class MatrixDefinition:
    categories: list[MatrixCategory] = field(default_factory=list)
    atomic_capabilities: list[AtomicCapability] = field(default_factory=list)
    control_semantics: list[ControlSemantic] = field(default_factory=list)
    capability_mappings: list[CapabilityMapping] = field(default_factory=list)
    mismatch_definitions: list[MismatchDefinition] = field(default_factory=list)


@dataclass(slots=True)
class SkillStructureProfile:
    has_skill_md: bool
    has_frontmatter: bool
    has_references_dir: bool
    has_scripts_dir: bool
    has_assets_dir: bool
    has_templates_dir: bool
    top_level_files: list[str] = field(default_factory=list)
    top_level_dirs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillArtifact:
    skill_id: str
    root_path: Path
    structure: SkillStructureProfile
    file_paths: list[Path]
    source_files: list[Path]


@dataclass(slots=True)
class EvidenceItem:
    category_id: str
    category_name: str
    source_path: str
    layer: str
    evidence_type: str
    matched_text: str
    line_start: int | None
    line_end: int | None
    confidence: str
    rule_id: str
    source_kind: str | None = None
    source_role: str | None = None
    support_reference_mode: str | None = None
    subject_type: str = "atomic_capability"
    matched_pattern: str | None = None
    evidence_strength: str = "medium"
    excluded_by_rule: str | None = None
    excerpt_hash: str = ""
    evidence_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.excerpt_hash:
            self.excerpt_hash = _stable_hash(self.matched_text)
        if not self.evidence_fingerprint:
            payload = "|".join(
                [
                    self.layer,
                    self.category_id,
                    self.source_path,
                    str(self.line_start or ""),
                    str(self.line_end or ""),
                    self.rule_id,
                    self.matched_text,
                ]
            )
            self.evidence_fingerprint = _stable_hash(payload)


@dataclass(slots=True)
class CategoryClassification:
    category_id: str
    category_name: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    confidence: str = "unknown"
    confidence_score: float = 0.0
    decision_status: str = "accepted"


@dataclass(slots=True)
class AtomicEvidenceDecision:
    atomic_id: str
    atomic_name: str
    layer: str
    decision_status: str
    supporting_evidence: list[EvidenceItem] = field(default_factory=list)
    conflicting_evidence: list[EvidenceItem] = field(default_factory=list)
    confidence: str = "unknown"
    confidence_score: float = 0.0
    mapped_category_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ControlDecision:
    control_id: str
    control_name: str
    layer: str
    decision_status: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    confidence: str = "unknown"
    confidence_score: float = 0.0
    applicable_atomic_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuleCandidate:
    candidate_id: str
    category_id: str
    category_name: str
    layer: str
    candidate_status: str
    supporting_evidence: list[EvidenceItem] = field(default_factory=list)
    conflicting_evidence: list[EvidenceItem] = field(default_factory=list)
    rule_confidence: str = "unknown"
    confidence_score: float = 0.0
    trigger_reason: str = ""


@dataclass(slots=True)
class FinalCategoryDecision:
    category_id: str
    category_name: str
    layer: str
    decision_status: str
    supporting_evidence: list[EvidenceItem] = field(default_factory=list)
    conflicting_evidence: list[EvidenceItem] = field(default_factory=list)
    confidence: str = "unknown"
    confidence_score: float = 0.0
    source_candidate_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReviewAuditRecord:
    category_id: str
    layer: str
    review_status: str
    provider: str | None = None
    model: str | None = None
    reason: str | None = None
    schema_version: str | None = None


@dataclass(slots=True)
class CategoryDiscrepancy:
    category_id: str
    category_name: str
    status: str
    declaration_present: bool
    implementation_present: bool
    risks: list[str]
    controls: list[str]
    mismatch_ids: list[str] = field(default_factory=list)
    declaration_atomic_ids: list[str] = field(default_factory=list)
    implementation_atomic_ids: list[str] = field(default_factory=list)
    declaration_control_ids: list[str] = field(default_factory=list)
    implementation_control_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnalysisResult:
    skill_id: str
    root_path: str
    structure_profile: SkillStructureProfile
    declaration_atomic_decisions: list[AtomicEvidenceDecision] = field(default_factory=list)
    implementation_atomic_decisions: list[AtomicEvidenceDecision] = field(default_factory=list)
    declaration_control_decisions: list[ControlDecision] = field(default_factory=list)
    implementation_control_decisions: list[ControlDecision] = field(default_factory=list)
    rule_candidates: list[RuleCandidate] = field(default_factory=list)
    final_decisions: list[FinalCategoryDecision] = field(default_factory=list)
    declaration_classifications: list[CategoryClassification] = field(default_factory=list)
    implementation_classifications: list[CategoryClassification] = field(default_factory=list)
    skill_level_discrepancy: str = "insufficient_implementation_evidence"
    category_discrepancies: list[CategoryDiscrepancy] = field(default_factory=list)
    risk_mappings: list[dict[str, Any]] = field(default_factory=list)
    review_audit_records: list[ReviewAuditRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunConfig:
    skills_dir: str
    output_dir: str
    requested_formats: list[str]
    limit: int | None
    case_study_skill: str | None
    include_hidden: bool
    fail_on_unknown_matrix: bool
    llm_review_mode: str = "off"
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_low_confidence_threshold: float = 0.45
    llm_high_risk_sparse_threshold: int = 1
    llm_fallback_max_categories: int = 0
    llm_timeout_seconds: int = 30
    skill_timeout_seconds: int = 600
    llm_failure_policy: str = "fail_open"
    emit_review_audit: bool = False
    goldset_path: str | None = None


@dataclass(slots=True)
class RunSummary:
    run_id: str
    output_dir: str
    analyzed_skills: int
    skipped_skills: int
    errored_skills: int
    config: RunConfig
    skill_errors: list[dict[str, str]] = field(default_factory=list)
    validation_summary: dict[str, Any] | None = None


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return value


def _stable_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()
