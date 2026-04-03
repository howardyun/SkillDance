---
title: feat: Add skills security matrix analyzer
type: feat
status: active
date: 2026-03-25
origin: docs/brainstorms/skills-security-matrix-analyzer-requirements.md
---

# feat: Add skills security matrix analyzer

## Overview

Build a research-oriented analyzer that scans a local `skills/` folder and produces reproducible, explainable security classifications for each skill. The analyzer will classify both the declaration layer and the implementation layer against the repository's security matrix, then compute capability drift and risk mappings suitable for both statistical analysis and case-study review.

This plan carries forward the origin decisions that the input is a local skills folder, the product goal is a paper-oriented analysis tool, the classification must be dual-layer, and the first version must output both structured tables and JSON rather than governance decisions (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`).

## Problem Statement

The repository already collects ecosystem metadata and external security results into SQLite, but it does not yet analyze downloaded skill repositories as first-class research artifacts. Current code is script-oriented and crawler-heavy, with no reusable analyzer entrypoint beyond the placeholder [`main.py`](/home/szk/code/OpenClaw-Proj/main.py#L1) and no local module for repository-scale static analysis.

The security taxonomy is also already available in [`analyzer/security matrix.md`](/home/szk/code/OpenClaw-Proj/analyzer/security%20matrix.md#L1), but it exists only as a human-authored matrix. Without a programmatic analyzer, the project cannot answer the research question the brainstorm clarified: whether the capability claims made by a skill's explicit documentation match the capabilities evidenced by its code and configuration.

## Research Findings

### Local Context

- The repo is a small Python 3.13+ scripts project with only `requests` declared in [`pyproject.toml`](/home/szk/code/OpenClaw-Proj/pyproject.toml#L1), so the plan should favor standard-library-heavy implementation and small, composable modules over framework-dependent architecture.
- The current project focus is data collection and security analysis pipelines, not app serving or dashboards, as described in [`README.md`](/home/szk/code/OpenClaw-Proj/README.md#L3) and the crawler layout in [`README.md`](/home/szk/code/OpenClaw-Proj/README.md#L16).
- Existing scripts already use patterns worth reusing: SQLite-backed pipelines, idempotent upserts, and concurrent batch processing, for example in [`crawl_skills_sh.py`](/home/szk/code/OpenClaw-Proj/crawling/skills/skills_sh/crawl_skills_sh.py#L34) and [`crawl_skills_sh.py`](/home/szk/code/OpenClaw-Proj/crawling/skills/skills_sh/crawl_skills_sh.py#L151).
- There is no `docs/solutions/` directory, so there are no institutional learnings to inherit for this feature.
- Current repo downloaders only guarantee cloned repository folders and do not preserve marketplace-level descriptive fields inside the local corpus, which reinforces that declaration-layer analysis must come from files living inside each skill repository rather than upstream DB records. Source patterns: [`download_skills.py`](/home/szk/code/OpenClaw-Proj/crawling/skills/skills_sh/download_skills.py#L21) and [`download_skills.py`](/home/szk/code/OpenClaw-Proj/crawling/skills/SkillsDirectory/download_skills.py#L21)

### External Research

- skills ecosystems are increasingly centered around `SKILL.md` as the canonical declaration artifact, with optional supporting folders such as `references/`, `scripts/`, and `assets/`, which is a better declaration-layer input model than assuming a conventional README/manifest-heavy repository. Source: <https://skills.sh/docs> and <https://docsalot.dev/blog/skill-md>
- Tree-sitter's parser and query model is a strong candidate for a later enhancement layer when syntax-aware extraction is needed across multiple languages, especially for stable node locations and query-based matching. Source: <https://tree-sitter.github.io/tree-sitter/using-parsers> and <https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html>
- Semgrep's rule model is a good reference for designing declarative code-evidence signatures, especially if the analyzer later needs portable pattern packs instead of hand-coded heuristics. Source: <https://semgrep.dev/docs/writing-rules/pattern-syntax> and <https://semgrep.dev/docs/writing-rules/rule-syntax>
- Python's standard `csv` module is sufficient for reproducible tabular export and avoids unnecessary dependencies for the first version. Source: <https://docs.python.org/3/library/csv.html>

### Planning Decision

Because this work is security-oriented and research-facing, external research was warranted. The recommended architecture is deterministic-first: explicit text/code evidence extractors, matrix-aligned rules, confidence scoring, and traceable outputs. Tree-sitter or Semgrep-inspired pattern packs should be treated as an enhancement path, not a prerequisite for the first working version.

The declaration-layer input model should also be refined: do not assume conventional software-project metadata. For skill repositories, the primary declaration source should be `SKILL.md` and its frontmatter/body structure, with `references/` treated as supplemental declared intent.

## Proposed Solution

Create a new analyzer pipeline that operates on a local directory of skill repositories and emits four artifacts:

1. A normalized per-skill record.
2. A declaration-layer classification with evidence.
3. An implementation-layer classification with evidence.
4. A derived discrepancy and risk-mapping record.

The analyzer should be organized as a small offline pipeline:

1. Parse the `security matrix` into a machine-readable taxonomy.
2. Discover skill directories and normalize basic file metadata.
3. Extract declaration evidence primarily from `SKILL.md`, its frontmatter/body, and other skill-native declarative materials such as `references/`.
4. Extract implementation evidence from source code, scripts, config, tool definitions, and external-access patterns.
5. Apply deterministic multi-label rules to produce declaration and implementation classifications.
6. Compare both layers to compute drift labels and matrix risk mappings.
7. Export both JSON and flat tabular outputs for downstream statistics and case-study review.

The first version should explicitly avoid an opaque LLM-only classifier. A deterministic core is better aligned with research reproducibility, error analysis, and later validation.

## Technical Approach

### Architecture

Add a dedicated `analyzer/skills_security_matrix/` package and route the project entrypoint through it. The implementation should keep ingestion, evidence extraction, classification, discrepancy analysis, and exporting as separate modules so that future experiments can swap individual stages without rewriting the whole pipeline.

Suggested module layout:

- `analyzer/skills_security_matrix/__init__.py`
- `analyzer/skills_security_matrix/cli.py`
- `analyzer/skills_security_matrix/matrix_loader.py`
- `analyzer/skills_security_matrix/skill_discovery.py`
- `analyzer/skills_security_matrix/skill_structure.py`
- `analyzer/skills_security_matrix/models.py`
- `analyzer/skills_security_matrix/evidence/declaration.py`
- `analyzer/skills_security_matrix/evidence/implementation.py`
- `analyzer/skills_security_matrix/rules/declaration_rules.py`
- `analyzer/skills_security_matrix/rules/implementation_rules.py`
- `analyzer/skills_security_matrix/discrepancy.py`
- `analyzer/skills_security_matrix/risk_mapping.py`
- `analyzer/skills_security_matrix/exporters/json_exporter.py`
- `analyzer/skills_security_matrix/exporters/csv_exporter.py`

Suggested output layout:

- `outputs/skills_security_matrix/run-<timestamp>/skills.json`
- `outputs/skills_security_matrix/run-<timestamp>/classifications.json`
- `outputs/skills_security_matrix/run-<timestamp>/discrepancies.json`
- `outputs/skills_security_matrix/run-<timestamp>/skills.csv`
- `outputs/skills_security_matrix/run-<timestamp>/classifications.csv`
- `outputs/skills_security_matrix/run-<timestamp>/discrepancies.csv`
- `outputs/skills_security_matrix/run-<timestamp>/cases/<skill-id>.json`

### Core Data Model

The plan should standardize around four internal entities:

- `MatrixCategory`: one row from the security matrix with category ids, names, risk codes, and control requirements.
- `SkillArtifact`: one local skill directory plus normalized file inventory and basic metadata.
- `EvidenceItem`: one extracted claim or implementation signal with source path, snippet/reference, layer, and confidence.
- `AnalysisResult`: one per-skill aggregate containing declaration labels, implementation labels, discrepancy labels, risk mappings, and export-ready summaries.

Add one supporting descriptor:

- `SkillStructureProfile`: one per-skill summary of whether the repo contains `SKILL.md`, frontmatter, `references/`, `scripts/`, templates, assets, or only code. This profile should guide which declaration extractors run and should itself be exportable for research.

### Classification Strategy

Use a three-tier deterministic strategy:

1. `Hard evidence rules`
   Detect explicit declaration or implementation signals with high precision.
   Examples:
   - `SKILL.md` text mentioning internet browsing or external API use maps to `外部信息访问`
   - `SKILL.md` frontmatter or sections referencing file access, search, code execution, or automation map to the corresponding matrix categories
   - `references/` content that is explicitly pointed to from `SKILL.md` can strengthen a declaration-layer category
   - Code invoking `requests`, `fetch`, `urllib`, `curl`, or browser tooling maps to implementation-layer `外部信息访问`
   - Files containing scheduled task definitions, cron expressions, or polling loops map to `定时与周期自动化` or `条件触发与监控自动化`
   - Repo instructions that write drafts only map to `草稿与建议写入`

2. `Supporting evidence rules`
   Use weaker lexical or structural cues to increase confidence when combined with hard evidence.

3. `Unknown / review-needed fallback`
   When evidence is sparse or contradictory, preserve that ambiguity in the output instead of over-claiming.

### Discrepancy Taxonomy

Implement a first-pass discrepancy taxonomy that goes slightly beyond the brainstorm minimum while remaining easy to validate:

- `declared_less_than_implemented`
- `declared_more_than_implemented`
- `declared_and_implemented_aligned`
- `implementation_only_high_risk`
- `insufficient_declaration_evidence`
- `insufficient_implementation_evidence`

These labels should be computed at both the skill level and the category level so a paper can analyze aggregate drift as well as category-specific drift.

### Evidence and Explainability

Each classification must retain evidence references, not just final labels. For each matched category, store:

- `source_path`
- `layer`
- `evidence_type`
- `matched_text` or normalized rule description
- `line_start`
- `line_end`
- `confidence`
- `rule_id`

This should enable direct paper case studies and later human validation.

For declaration evidence specifically, include:

- whether the evidence came from `SKILL.md` frontmatter, `SKILL.md` body, or a referenced support file
- whether the support file was directly referenced by `SKILL.md` or only colocated in the repository

### Risk Mapping

Map every matched matrix category to the matrix's `主要风险` and `控制要求` fields from [`security matrix.md`](/home/szk/code/OpenClaw-Proj/analyzer/security%20matrix.md#L1). The first version should inherit these mappings directly rather than inventing weighted risk scores. If needed, a future version can layer evidence-weighted severity on top of the base matrix.

### CLI Surface

Add a command-line interface through `main.py` or a dedicated module entrypoint with the following responsibilities:

- accept `--skills-dir`
- accept `--output-dir`
- accept `--limit`
- accept `--format json,csv`
- accept `--case-study-skill <id>`
- accept `--fail-on-unknown-matrix`
- accept `--include-hidden`

This CLI should be designed for offline repeatable runs on a local corpus.

### Implementation Phases

#### Phase 1: Analyzer Foundation

Deliverables:

- create the analyzer package under `analyzer/skills_security_matrix/`
- parse the matrix file into normalized structured records
- implement local skill directory discovery
- implement a skill-structure profiler that detects `SKILL.md`, frontmatter, and canonical subdirectories such as `references/`, `scripts/`, and `assets/`
- define typed internal models for matrix rows, evidence, and analysis results
- wire a minimal CLI through `main.py` and `analyzer/skills_security_matrix/cli.py`

Success criteria:

- the analyzer can load the matrix and enumerate skill directories from a local folder
- a dry run produces a normalized inventory output and a structure profile without classifications

#### Phase 2: Declaration-Layer Classification

Deliverables:

- implement explicit-material readers for `SKILL.md`, YAML frontmatter, and skill-native support files such as `references/`
- add declaration evidence extraction rules
- emit declaration-layer category labels with evidence and confidence

Success criteria:

- declaration classification never reads source code files as declaration evidence unless they are explicitly referenced by `SKILL.md` as declarative support material
- each declaration label has at least one evidence record

#### Phase 3: Implementation-Layer Classification

Deliverables:

- implement code/config/script scanning for network access, filesystem access, tool execution, generation/write behaviors, scheduling, and automation patterns
- add implementation classification rules
- normalize line-level or file-level evidence references

Success criteria:

- implementation labels can be produced for multi-file repositories
- the analyzer can distinguish explicit write-like behavior from read-only behavior in common cases

#### Phase 4: Discrepancy and Risk Analysis

Deliverables:

- compute declaration vs implementation deltas
- map matched categories to matrix risks and controls
- produce skill-level and category-level discrepancy outputs

Success criteria:

- every analyzed skill has a discrepancy summary, even if it is `unknown` or `insufficient_evidence`
- every matched category inherits matrix risks and controls

#### Phase 5: Research Exports and Validation

Deliverables:

- add JSON and CSV exporters
- add case-study export generation under `outputs/.../cases/`
- add a validation workflow with sample fixtures and manual-review guidance

Success criteria:

- one run produces both machine-readable JSON and analysis-friendly CSV
- researchers can inspect one skill's full evidence chain without rerunning the classifier

## Alternative Approaches Considered

### 1. LLM-First Classification

Rejected for v1. It would speed up prototyping, but it weakens reproducibility, complicates ablation, and makes error analysis harder for a paper-oriented tool.

### 2. Marketplace-Coupled Analyzer

Rejected for v1 because the brainstorm explicitly chose local skill folders as input. Source-agnostic input keeps the research question cleaner and avoids conflating platform metadata quality with repository behavior.

### 3. Tree-Sitter or Semgrep as Immediate Core Dependency

Deferred rather than rejected. These tools are promising for higher-precision implementation evidence, but they add setup and language-coverage complexity that the repository does not currently need for a first reproducible baseline.

## System-Wide Impact

### Interaction Graph

The new analyzer will read the matrix file, scan a local skills directory, extract evidence, classify artifacts, and write outputs. It should remain isolated from the existing crawler scripts, but it may later reuse downloaded repositories those crawlers already fetch. Action flow:

`CLI run -> matrix loader -> skill discovery -> declaration extraction -> implementation extraction -> classification -> discrepancy engine -> exporters -> output directory`

No existing crawler callback chains or background processes are triggered by this plan.

### Error & Failure Propagation

Likely error classes:

- matrix parse errors from malformed tabular rows
- filesystem traversal errors on unreadable repositories
- text decode errors on mixed-encoding files
- exporter schema mismatches when records are partially populated

The CLI should aggregate per-skill errors into a run summary rather than aborting the entire batch on the first problematic repository. Fatal startup errors should be limited to invalid matrix configuration or unwritable output directories.

### State Lifecycle Risks

This feature should be append-only at first. It reads local files and writes output artifacts. There is no intended mutation of source repositories, no database writes required for v1, and no external API side effects. The main state risks are:

- overwriting previous run outputs
- inconsistent schemas across JSON and CSV
- stale exports if a rerun partially fails

Mitigation:

- timestamped run directories
- a run manifest file describing config and counts
- write temp files then finalize outputs

### API Surface Parity

Equivalent interfaces that need aligned behavior:

- `main.py` and a dedicated CLI module should point to the same analyzer entrypoint
- JSON and CSV exporters must derive from the same internal result model
- case-study export must be a filtered projection of the same full analysis result, not a separate code path

### Integration Test Scenarios

- Run the analyzer on a fixture corpus containing a read-only skill, a write-capable skill, and a scheduled automation skill, then verify both layers and discrepancy outputs.
- Run the analyzer on a repository with only a README and no code, then verify declaration evidence exists and implementation evidence is marked insufficient rather than empty-aligned.
- Run the analyzer on a code-heavy repository with no explicit README claims, then verify `declared_less_than_implemented` or `insufficient_declaration_evidence` appears as appropriate.
- Run the analyzer on a repository containing mixed encodings and binary files, then verify the run completes with structured skip/error reporting.
- Run the analyzer twice with the same corpus and verify output stability for deterministic fields.

## SpecFlow Analysis

### User Flows

1. Researcher runs the analyzer on a local corpus and expects batch-level JSON/CSV outputs for statistics.
2. Researcher inspects one suspicious skill and expects a case-study artifact with evidence-backed declaration and implementation labels.
3. Researcher reruns the analyzer after rule changes and expects comparable outputs without manually cleaning the corpus.

### Gaps Incorporated Into This Plan

- The spec previously assumed declaration evidence would look like README/manifest data; the plan now reorients declaration analysis around `SKILL.md`, frontmatter, and skill-native support folders.
- The spec did not previously define behavior for sparse or contradictory evidence; this plan adds explicit `insufficient_*` outcomes instead of forcing false certainty.
- The spec did not define rerun behavior; this plan adds timestamped output directories and run manifests as the default.

### Default Assumptions

- One skill corresponds to one top-level local directory unless a later data model introduces nested manifests.
- `SKILL.md` is treated as the canonical declaration document when present.
- If `SKILL.md` is absent, declaration-layer output should degrade to `insufficient_declaration_evidence` rather than silently substituting general repository code or unrelated docs.
- Binary files and unsupported file types are skipped, not heuristically decoded.
- CSV exports are flattened views of the authoritative JSON result model.

## Acceptance Criteria

### Functional Requirements

- [ ] Add a reusable analyzer package under `analyzer/skills_security_matrix/` that accepts a local `--skills-dir` input.
- [ ] Parse [`analyzer/security matrix.md`](/home/szk/code/OpenClaw-Proj/analyzer/security%20matrix.md#L1) into a normalized taxonomy usable by rules.
- [ ] Produce declaration-layer classifications from `SKILL.md`, its frontmatter, and explicitly declared support materials only, as refined from the origin document (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`).
- [ ] Produce implementation-layer classifications from static repository evidence.
- [ ] Support multi-label category matches for both layers.
- [ ] Persist evidence for every emitted classification.
- [ ] Emit a per-skill structure profile that records whether canonical skill artifacts such as `SKILL.md` and `references/` are present.
- [ ] Compute discrepancy labels between both layers.
- [ ] Map matched categories to matrix risks and controls.
- [ ] Export both JSON and CSV outputs from a single run.
- [ ] Export per-skill case-study artifacts.

### Non-Functional Requirements

- [ ] Runs must be deterministic for the same input corpus and rule set.
- [ ] The core classifier must remain usable without external APIs or online services.
- [ ] The analyzer must fail soft on per-skill errors and continue batch processing.
- [ ] Output schemas must be stable enough for downstream statistical scripts.

### Quality Gates

- [ ] Add unit tests for matrix parsing, declaration extraction, implementation extraction, discrepancy computation, and exporters.
- [ ] Add fixture repositories that cover `SKILL.md`-present, `SKILL.md`-missing, and `references/`-heavy structures under `tests/fixtures/skills_security_matrix/`.
- [ ] Add fixture-based integration tests under a dedicated test corpus directory such as `tests/fixtures/skills_security_matrix/`.
- [ ] Document rule-writing and evidence semantics in repository docs.
- [ ] Manually review a small gold set before treating outputs as paper-ready.

## Success Metrics

- At least one end-to-end run can analyze a local skill corpus and produce complete JSON and CSV exports without manual intervention.
- A reviewer can inspect any emitted label and trace it back to at least one evidence record with file provenance.
- Repeated runs on the same corpus and configuration produce stable labels apart from intentional rule changes.
- The output schema directly supports paper tables such as category prevalence, drift prevalence, and risk/control distributions.

## Dependencies & Prerequisites

- A local corpus of skill repositories arranged under a top-level skills directory.
- Agreement on the normalized matrix ids used internally for each row in [`security matrix.md`](/home/szk/code/OpenClaw-Proj/analyzer/security%20matrix.md#L1).
- A small annotated validation subset for spot-checking rule precision and recall.
- A confirmed structural sample of real skill repositories so the structure profiler is grounded in observed layout, not only documentation.

## Risk Analysis & Mitigation

- `Risk: overly brittle heuristics`
  Mitigation: separate hard and supporting evidence, preserve unknown states, and keep rules data-driven.
- `Risk: real skill repos vary more than the documented structure`
  Mitigation: add a structure-profiling phase first, export the observed structure distribution, and validate declaration extractors against real samples before scaling up classification claims.
- `Risk: declaration and implementation rules drift apart semantically`
  Mitigation: normalize both against the same matrix ids and store shared category metadata centrally.
- `Risk: evidence overload makes outputs unusable`
  Mitigation: cap and rank evidence per category while retaining raw evidence in the full JSON artifact.
- `Risk: multilingual repositories reduce implementation accuracy`
  Mitigation: start with language-agnostic filesystem and keyword heuristics, then add syntax-aware parsers only where they materially improve signal.
- `Risk: paper claims outrun tool validity`
  Mitigation: require a manually reviewed gold subset and explicitly report unknown/uncertain cases.

## Resource Requirements

- One implementation pass to add the analyzer package and tests.
- One research validation pass to build and review the initial gold subset.
- Local disk space for corpus inputs and timestamped output runs.

## Future Considerations

- Add Tree-sitter-backed extractors for higher-precision language-specific evidence.
- Add Semgrep-style declarative rule packs so matrix mappings can evolve without code edits.
- Add SQLite export if later analysis workflows prefer relational joins over flat files.
- Add optional confidence calibration or human-in-the-loop adjudication workflows for ambiguous cases.
- Add a corpus-structure analysis note summarizing how often `SKILL.md`, `references/`, `scripts/`, or other declaration artifacts actually appear in the wild.

## Documentation Plan

- Update [`README.md`](/home/szk/code/OpenClaw-Proj/README.md#L16) with a new analyzer section and example CLI usage.
- Add analyzer-specific documentation such as `docs/analyzer/skills-security-matrix-analyzer.md` describing inputs, outputs, and evidence semantics.
- Document the validation workflow and annotation conventions for the gold subset.

## Sources & References

### Origin

- **Origin document:** [docs/brainstorms/skills-security-matrix-analyzer-requirements.md](/home/szk/code/OpenClaw-Proj/docs/brainstorms/skills-security-matrix-analyzer-requirements.md)  
  Key decisions carried forward: local skills folder input, dual-layer classification, first version includes discrepancy plus risk mapping, declaration evidence limited to explicit materials, and outputs must include both JSON and tabular formats.

### Internal References

- Project scope and script-driven architecture: [`README.md`](/home/szk/code/OpenClaw-Proj/README.md#L3)
- Existing pipeline layout: [`README.md`](/home/szk/code/OpenClaw-Proj/README.md#L16)
- Matrix taxonomy source: [`security matrix.md`](/home/szk/code/OpenClaw-Proj/analyzer/security%20matrix.md#L1)
- SQLite upsert pattern to reuse: [`crawl_skills_sh.py`](/home/szk/code/OpenClaw-Proj/crawling/skills/skills_sh/crawl_skills_sh.py#L34)
- Concurrent batch processing pattern to reuse: [`crawl_skills_sh.py`](/home/szk/code/OpenClaw-Proj/crawling/skills/skills_sh/crawl_skills_sh.py#L151)
- Repo-folder input assumption enforced by current downloaders: [`download_skills.py`](/home/szk/code/OpenClaw-Proj/crawling/skills/skills_sh/download_skills.py#L92)
- Current placeholder entrypoint: [`main.py`](/home/szk/code/OpenClaw-Proj/main.py#L1)

### External References

- Tree-sitter parser guide: <https://tree-sitter.github.io/tree-sitter/using-parsers>
- Tree-sitter query syntax: <https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html>
- Semgrep rule pattern syntax: <https://semgrep.dev/docs/writing-rules/pattern-syntax>
- Semgrep rule structure syntax: <https://semgrep.dev/docs/writing-rules/rule-syntax>
- Python CSV docs: <https://docs.python.org/3/library/csv.html>
- Skills documentation: <https://skills.sh/docs>
- skill.md overview: <https://docsalot.dev/blog/skill-md>
