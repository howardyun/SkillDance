---
title: feat: Extend skills security matrix analyzer
type: feat
status: active
date: 2026-03-27
origin: docs/brainstorms/skills-security-matrix-analyzer-requirements.md
supersedes:
  - docs/plans/2026-03-25-001-feat-skills-security-matrix-analyzer-plan.md
---

# feat: Extend skills security matrix analyzer

## Overview

Extend the existing offline `skills_security_matrix` analyzer so it fully satisfies the newer research requirements in the origin document, especially around explainable evidence capture, batch/case-study exports, discrepancy taxonomy, and the explicitly optional LLM-enhanced review path.

This plan carries forward the origin decisions that the analyzer must operate on a local `skills/` corpus, classify both declaration and implementation layers, support multi-label outcomes, remain offline-first by default, and treat LLMs as a tightly controlled enhancement rather than the primary classifier (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`).

## Problem Statement

The repo already contains a working baseline under `analyzer/skills_security_matrix/`, but the current implementation only partially covers the research workflow implied by the brainstorm:

- the offline rule path exists, which helps with R1-R11
- JSON/CSV exports and case-study outputs exist, which helps with R8-R10
- discrepancy and risk mapping exist, which helps with R6-R7
- the controlled LLM review path from R12-R16 does not exist yet
- evidence, confidence, and discrepancy semantics are still too coarse for paper-grade reproducibility and false-positive analysis
- declaration extraction currently reads `README.md` directly, which conflicts with the origin decision that declaration evidence should come from `SKILL.md`, frontmatter, and explicit support materials only (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`)

So the planning task is not greenfield anymore. It is to close the gap between the current baseline and the refined research-grade design.

## Research Findings

### Local Context

- The project is still a lightweight Python 3.13+ scripts repository with only `requests` declared in [`pyproject.toml`](/home/szk/code/OpenClaw-Proj/pyproject.toml#L1), so the implementation should stay standard-library-first and avoid introducing heavyweight orchestration dependencies.
- The analyzer package already exists in [`cli.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/cli.py#L1), [`models.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/models.py#L1), [`declaration.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/evidence/declaration.py#L1), [`implementation.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/evidence/implementation.py#L1), [`discrepancy.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/discrepancy.py#L1), and the exporter modules, so the plan should evolve those modules instead of replacing them.
- The current declaration extractor scans `SKILL.md` but also scans `README.md` unconditionally in [`declaration.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/evidence/declaration.py#L27), which is inconsistent with the origin boundary on declaration evidence (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`).
- The current implementation classifier is pure lexical scan in [`implementation.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/evidence/implementation.py#L83), which is a good deterministic baseline but not enough to represent candidate-level support, conflict, ambiguity, or low-confidence review triggers.
- The current output model stores `confidence`, evidence, discrepancies, and risk mappings, but it does not yet represent rule candidates, conflict sets, LLM review status, or `rejected_by_llm`, which are required to satisfy R13-R16 from the origin document (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`).
- There is no `docs/solutions/` directory in this repo, so there are no institutional learnings to inherit for this feature.

### External Research

- OpenAI’s Structured Outputs guide recommends strict schema-backed responses instead of loose JSON mode, which is a strong fit for category-level LLM review records where the analyzer needs stable statuses, reasons, and evidence references instead of free-form prose. Source: <https://platform.openai.com/docs/guides/structured-outputs>
- The Responses API reference documents `json_schema` output with `strict: true`, which is relevant if the optional LLM mode is implemented with provider-backed structured review objects rather than regex parsing of natural-language model output. Source: <https://platform.openai.com/docs/api-reference/responses>
- LiteLLM is a credible candidate for the implementation layer of multi-provider support because it offers a unified model invocation surface, provider routing, and compatibility helpers around structured-output style parameters. For this project, that makes it a strong default adapter substrate, but not a replacement for the analyzer’s own provider-neutral review abstraction. Sources: <https://docs.litellm.ai/> and <https://github.com/BerriAI/litellm>
- Semgrep’s rule syntax remains a strong reference for moving from flat keyword lists toward declarative rule definitions with ids, severities, and pattern families. That is useful for representing “candidate category + support/conflict evidence + confidence” before any LLM review happens. Sources: <https://semgrep.dev/docs/writing-rules/pattern-syntax> and <https://semgrep.dev/docs/writing-rules/rule-syntax>
- Tree-sitter remains relevant as a later enhancement path for syntax-aware extraction, but it is still better treated as optional follow-on work than as a prerequisite for the next milestone. Source: <https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html>

### Planning Decision

This feature still qualifies as high-risk planning because it is explicitly security-facing and because the optional LLM mode could weaken reproducibility if it is not tightly constrained. So the plan should preserve the current offline baseline, make rule outputs more structured first, and only then add category-scoped LLM review behind explicit CLI flags.

The right sequencing is:

1. tighten the deterministic rule pipeline and evidence schema
2. add explicit candidate/conflict/low-confidence review triggers
3. add a provider-agnostic LLM review interface with strict structured outputs
4. add controlled fallback adjudication and validation workflows

## Stakeholders

- Researchers need reproducible outputs for statistics, ablation, and case studies.
- Developers need a modular analyzer whose rule logic and review workflow can evolve without rewriting the pipeline.
- Future reviewers or auditors need traceable evidence and stable statuses so false positives and LLM vetoes can be inspected later.

## Proposed Solution

Keep the existing analyzer package and extend it into a two-mode pipeline:

1. `Offline deterministic mode`  
   The default path. It performs discovery, declaration evidence extraction, implementation evidence extraction, multi-label rule recall, discrepancy analysis, risk mapping, and export generation without any external model calls.

2. `Controlled LLM-enhanced mode`  
   An opt-in path enabled only through explicit CLI flags. It starts from rule candidates produced by the offline pipeline, reviews categories one by one when conflict, ambiguity, or low-confidence thresholds are met, and can only keep, downgrade, or reject a candidate. It cannot freely invent categories without a matching rule candidate or explicit fallback quota trigger (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`).

The data model should shift from “final classifications only” to “rule candidates first, final decisions second” so the analyzer can preserve both baseline evidence and post-review outcomes.

## Technical Approach

### Architecture Changes

Retain the current package layout, but add these new modules:

- `analyzer/skills_security_matrix/rules/catalog.py`
- `analyzer/skills_security_matrix/rules/candidate_builder.py`
- `analyzer/skills_security_matrix/review/review_policy.py`
- `analyzer/skills_security_matrix/review/models.py`
- `analyzer/skills_security_matrix/review/llm_provider.py`
- `analyzer/skills_security_matrix/review/llm_reviewer.py`
- `analyzer/skills_security_matrix/review/providers/litellm_provider.py`
- `analyzer/skills_security_matrix/review/providers/openai_provider.py`  # optional direct adapter if LiteLLM proves insufficient
- `analyzer/skills_security_matrix/review/fallback.py`
- `analyzer/skills_security_matrix/validation/goldset.py`

Extend these existing modules rather than replacing them:

- [`models.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/models.py#L1)
- [`cli.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/cli.py#L1)
- [`declaration.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/evidence/declaration.py#L1)
- [`implementation.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/evidence/implementation.py#L1)
- [`discrepancy.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/discrepancy.py#L1)
- [`json_exporter.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/exporters/json_exporter.py#L1)
- [`csv_exporter.py`](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/exporters/csv_exporter.py#L1)

### Core Data Model Revisions

Add the following entities:

- `RuleCandidate`
  One category proposal emitted by the deterministic layer. Includes `category_id`, `layer`, `candidate_status`, `supporting_evidence`, `conflicting_evidence`, `rule_confidence`, and `trigger_reason`.
- `FinalCategoryDecision`
  One resolved category outcome after offline-only classification or optional LLM review. Includes `decision_status` such as `accepted`, `downgraded`, `rejected_by_llm`, `insufficient_evidence`, or `fallback_adjudicated`.
- `ReviewTrigger`
  One record explaining why a category was sent to LLM review, for example `conflict`, `ambiguous_support`, `low_confidence`, or `quota_limited_fallback`.
- `ReviewAuditRecord`
  One traceable review record containing the prompt inputs, structured schema version, model/provider metadata, output status, and failure/retry metadata.
- `LLMReviewProvider`
  One provider-neutral abstraction for structured category review. It should expose a small stable contract such as `review_category(request) -> structured_decision`, so analyzer logic depends on the interface rather than any single vendor SDK or response format.

Revise existing entities:

- `EvidenceItem` should add normalized `excerpt_hash` or stable fingerprint fields so repeated evidence can be deduplicated across exports.
- `CategoryClassification` should become a resolved decision record instead of the only place where rule output is stored.
- `AnalysisResult` should separately contain rule candidates, final decisions, discrepancies, risk mappings, and review audit records.

### Evidence Semantics

To answer the origin’s deferred evidence-granularity question, use a two-level evidence model:

- `Citation-level evidence`
  One file path plus line span plus matched text excerpt for researcher review.
- `Decision-level evidence bundle`
  One compact group of the top supporting and conflicting citations carried into the classification and review steps.

This keeps batch outputs small enough for analysis while preserving case-study traceability.

Declaration evidence rules must be tightened:

- `SKILL.md` frontmatter and body are primary declaration inputs (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`)
- support files only count when explicitly referenced from `SKILL.md`
- `README.md` should not be treated as declaration evidence unless it is explicitly referenced from `SKILL.md`
- implementation code must never backfill declaration evidence

### Candidate-Building Strategy

Replace the current flat classification pass with a three-step deterministic pipeline:

1. `Evidence extraction`
   Gather declaration and implementation citations.
2. `Rule candidate building`
   Evaluate category rules into `RuleCandidate` records with support/conflict evidence and an initial confidence band.
3. `Finalization`
   Resolve candidates directly in offline mode, or pass a narrow subset into LLM review in enhanced mode.

Confidence should be derived from explicit scoring inputs rather than only `low|medium|high` literals:

- number of supporting citations
- diversity of evidence sources
- presence of explicit verbs or tool names
- presence of contradictory signals
- declaration-vs-implementation mismatch severity

The exported confidence can still be bucketed into `low`, `medium`, and `high`, but the internal model should keep a numeric score for thresholding.

### LLM Review Policy

The LLM integration should be split into two layers:

- `Review orchestration layer`
  Owns trigger policy, retry policy, fallback quotas, audit recording, and post-response validation.
- `LLM provider adapter layer`
  Owns vendor-specific request construction, authentication, transport, and response parsing into the shared review schema.

This boundary is important because the analyzer should never encode provider-specific fields, SDK objects, or response parsing rules inside classification or discrepancy logic. Replacing the underlying model provider should only require a new adapter plus configuration wiring, not changes to the analysis pipeline.

Recommended implementation direction:

- keep `LLMReviewProvider` as the project-owned abstraction
- prefer a `LiteLLMReviewProvider` as the default concrete adapter
- retain the option to add direct vendor adapters only if LiteLLM cannot satisfy strict schema, auditability, or failure-mode requirements for this workflow

The LLM path must remain opt-in and constrained:

- disabled by default
- enabled only through explicit CLI flags
- invoked at category granularity, never whole-skill freeform review
- primary job is false-positive reduction
- allowed actions are `accept`, `downgrade`, or `reject`
- disallowed action is “invent brand-new category” unless a separate fallback quota is triggered and explicitly recorded

Suggested trigger conditions:

- `low_confidence_score < threshold`
- both supporting and conflicting evidence exist
- rule family disagreement for the same category
- category is high-risk and the support bundle is sparse

Suggested controlled fallback for R15:

- add `--llm-fallback-max-categories <n>` with a default of `0`
- only permit fallback adjudication for categories that already have unresolved ambiguity markers
- mark every fallback decision distinctly in output

### CLI Surface

Preserve the existing offline CLI and add an explicit enhancement group:

- `--llm-review-mode off|review|review+fallback`
- `--llm-provider <name>`
- `--llm-model <name>`
- `--llm-low-confidence-threshold <float>`
- `--llm-high-risk-sparse-threshold <int>`
- `--llm-fallback-max-categories <int>`
- `--llm-timeout-seconds <int>`
- `--llm-fail-open`
- `--llm-fail-closed`
- `--emit-review-audit`

Default behavior should remain identical to today’s offline mode when no LLM flags are supplied (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`).

Implementation note:

- `--llm-provider` should resolve through a registry of provider adapters rather than branching inline inside the analyzer workflow.
- The first shipped adapter should preferably be `LiteLLMReviewProvider`, while the abstraction is introduced up front so future replacement does not require touching analysis logic.
- Direct vendor-specific adapters should be treated as fallback implementations, not the default path, unless LiteLLM turns out to be incompatible with the required structured review schema.

### Output Schema

Keep JSON and CSV exports, but normalize around these artifacts:

- `run_manifest.json`
- `skills.json`
- `rule_candidates.json`
- `classifications.json`
- `discrepancies.json`
- `risk_mappings.json`
- `review_audit.json`
- `skills.csv`
- `classifications.csv`
- `discrepancies.csv`
- `review_audit.csv`
- `cases/<skill-id>.json`

Case-study exports should include:

- structure profile
- declaration evidence bundle
- implementation evidence bundle
- candidate categories
- final category decisions
- discrepancy summary
- mapped risks and controls
- review audit trail when LLM mode is enabled

## SpecFlow Analysis

### User Flows

1. Researcher runs the analyzer on a local corpus in offline mode and expects reproducible declaration labels, implementation labels, discrepancy labels, and risk mappings for all skills.
2. Researcher reruns the analyzer with LLM review enabled and expects only ambiguous or low-confidence category candidates to be reviewed, not the full corpus.
3. Researcher inspects one skill for a qualitative case study and expects to see the evidence chain, the rule candidate history, and any `rejected_by_llm` outcomes.
4. Researcher compares offline and enhanced runs and expects to measure whether the optional review mode lowered false positives without silently changing the scope of classification.

### Gaps Incorporated Into This Plan

1. Critical: the current code has no representation of candidate-level support/conflict evidence, so category-level review triggers cannot be implemented reliably.
2. Critical: the current declaration extractor reads `README.md` directly, which risks contaminating declaration-layer analysis with materials outside the origin boundary.
3. Important: the current outputs do not preserve reviewable status transitions such as `rejected_by_llm`, so false-positive analysis would be lossy.
4. Important: the current plan and code do not define how fallback LLM adjudication is quota-limited, which risks drifting into an LLM-first workflow.
5. Important: there is no validation harness yet for gold-set comparison or offline-vs-enhanced ablation.
6. Minor: the current CLI does not make failure policy explicit for optional LLM calls.

### Questions

1. How minimal can the first `LLMReviewProvider` contract be while still allowing future provider swaps without touching analyzer logic?  
   Stakes: too much abstraction creates unnecessary complexity, but no abstraction hard-codes the analyzer to one vendor.  
   Default assumption: define a very small provider-neutral interface now and ship one concrete adapter first.
2. Does LiteLLM preserve enough control over strict structured outputs, provider capability detection, and audit metadata to serve as the default adapter for this analyzer?  
   Stakes: if yes, it reduces provider lock-in and adapter maintenance; if not, the project may need direct vendor adapters earlier.  
   Default assumption: start with LiteLLM as the default adapter candidate and validate it against the review schema before committing fully.
3. For paper evaluation, what is the minimum gold-set size needed before claiming false-positive reduction from LLM review?  
   Stakes: without a reviewed subset, the enhanced mode cannot be evaluated credibly.  
   Default assumption: start with a stratified gold set of at least 30 to 50 category decisions across high-risk and low-risk classes.
4. Should `declared_and_implemented_aligned` require exact category-set equality, or should it allow partially matched but non-conflicting categories when evidence is weak on one side?  
   Stakes: this changes drift prevalence metrics.  
   Default assumption: keep exact equality for the primary metric and add secondary “partially aligned” analytics later if needed.

## Implementation Phases

### Phase 1: Align the Offline Baseline With the Origin

Deliverables:

- remove unconditional `README.md` declaration scanning
- tighten declaration support-file handling to explicit `SKILL.md` references only
- enrich evidence records with stable fingerprints and source-role metadata
- add rule-candidate generation with support/conflict evidence bundles
- keep existing offline outputs working during the refactor

Success criteria:

- declaration evidence respects the origin boundary exactly (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`)
- every final offline classification can be traced back to at least one rule candidate
- no LLM dependency is introduced into the default path

### Phase 2: Controlled Category-Level Review

Deliverables:

- add review models and policy engine
- add a provider-neutral LLM abstraction layer and adapter registry
- add CLI flags for LLM review mode, thresholds, provider/model selection, and failure policy
- add a `LiteLLMReviewProvider` as the default concrete adapter and validate it against the structured review schema
- keep room for direct vendor adapters if LiteLLM cannot meet schema or audit requirements
- preserve `rejected_by_llm` and `downgraded` decisions in exports

Success criteria:

- only categories meeting explicit trigger conditions are reviewed
- reviewed categories always retain their original rule candidate and evidence bundle
- the reviewer cannot add categories outside the allowed policy path
- changing providers does not require edits to rule evaluation, discrepancy logic, or exporters

### Phase 3: Controlled Fallback Adjudication

Deliverables:

- add fallback quota controls
- add explicit fallback statuses and audit fields
- add fail-open and fail-closed behavior for provider errors

Success criteria:

- fallback review never exceeds configured quotas
- provider failures do not silently collapse the batch semantics
- every fallback decision is distinguishable from ordinary review decisions

### Phase 4: Research Exports and Validation

Deliverables:

- extend JSON/CSV exporters with candidate and review audit outputs
- add fixture corpora for aligned, under-declared, over-declared, and high-risk implementation-only skills
- add a gold-set validation workflow for offline vs enhanced comparison
- document how researchers should interpret statuses, evidence bundles, and review audit fields

Success criteria:

- one run can produce both statistics-friendly outputs and case-study artifacts
- offline and enhanced runs can be compared mechanically
- researchers can review false positives without inspecting raw logs manually

## Acceptance Criteria

### Functional Requirements

- [ ] The analyzer continues to accept a local skills folder as its primary input, without depending on marketplace metadata to run.
- [ ] Declaration-layer classification is derived from `SKILL.md`, frontmatter, and explicit support materials only (see origin: `docs/brainstorms/skills-security-matrix-analyzer-requirements.md`).
- [ ] Implementation-layer classification remains static-analysis-based in the default path.
- [ ] Both layers support multi-label outcomes.
- [ ] Every category outcome retains explainable evidence.
- [ ] Discrepancy output covers at least `declared_less_than_implemented`, `declared_more_than_implemented`, and `declared_and_implemented_aligned`, plus any extra statuses retained by the analyzer.
- [ ] Risk mappings inherit the security matrix’s risks and controls.
- [ ] Batch outputs remain suitable for downstream statistical analysis.
- [ ] Per-skill case-study exports remain available.
- [ ] The default mode remains pure offline rules.
- [ ] LLM enhancement is enabled only through explicit CLI flags.
- [ ] LLM review is triggered at category granularity, not whole-skill granularity.
- [ ] LLM review primarily reduces false positives and cannot freely invent categories.
- [ ] Rejected rule candidates remain visible in output as `rejected_by_llm` or equivalent preserved status.
- [ ] The analyzer depends on a provider-neutral LLM review abstraction rather than hard-coded vendor logic in the analysis pipeline.

### Non-Functional Requirements

- [ ] Repeated offline runs on the same corpus and rules remain deterministic.
- [ ] Optional LLM calls use schema-constrained outputs rather than free-form parsing.
- [ ] Per-skill failures do not abort the entire batch.
- [ ] Output schemas remain stable enough for reproducible research scripts.

### Quality Gates

- [ ] Add unit tests for rule-candidate building, review trigger policy, discrepancy logic, and export schemas.
- [ ] Add integration tests for offline-only runs and LLM-enhanced dry-run behavior.
- [ ] Add validation fixtures that cover category conflict, low-confidence, and fallback quota scenarios.
- [ ] Document the ablation method for comparing offline and enhanced modes.

## Risks and Mitigations

- `Risk: LLM mode drifts into a hidden primary classifier`  
  Mitigation: candidate-first pipeline, explicit trigger policy, fallback quotas, and preserved rejected candidates.
- `Risk: declaration evidence boundary drifts over time`  
  Mitigation: hard tests that prevent unreferenced README or source-code evidence from entering the declaration layer.
- `Risk: review outputs are structured but still semantically inconsistent`  
  Mitigation: strict schemas plus post-parse policy validation before accepting a review decision.
- `Risk: evaluation claims overstate model benefit`  
  Mitigation: require gold-set comparison and preserve both pre-review and post-review decisions for every reviewed category.

## Documentation Plan

- Update [`README.md`](/home/szk/code/OpenClaw-Proj/README.md#L1) with analyzer mode descriptions and example CLI commands.
- Add `docs/analyzer/skills-security-matrix-analyzer.md` for pipeline stages, evidence semantics, and output schema.
- Add a short validation note describing the gold-set workflow and offline-vs-enhanced comparison method.

## Sources

### Origin

- **Origin document:** [docs/brainstorms/skills-security-matrix-analyzer-requirements.md](/home/szk/code/OpenClaw-Proj/docs/brainstorms/skills-security-matrix-analyzer-requirements.md)

### Internal References

- Existing plan being superseded: [2026-03-25-001-feat-skills-security-matrix-analyzer-plan.md](/home/szk/code/OpenClaw-Proj/docs/plans/2026-03-25-001-feat-skills-security-matrix-analyzer-plan.md)
- Project overview: [README.md](/home/szk/code/OpenClaw-Proj/README.md#L1)
- Matrix taxonomy: [security matrix.md](/home/szk/code/OpenClaw-Proj/analyzer/security%20matrix.md#L1)
- Existing CLI: [cli.py](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/cli.py#L1)
- Existing models: [models.py](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/models.py#L1)
- Existing declaration evidence extractor: [declaration.py](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/evidence/declaration.py#L1)
- Existing implementation evidence extractor: [implementation.py](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/evidence/implementation.py#L1)
- Existing discrepancy logic: [discrepancy.py](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/discrepancy.py#L1)
- Existing JSON exporter: [json_exporter.py](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/exporters/json_exporter.py#L1)
- Existing CSV exporter: [csv_exporter.py](/home/szk/code/OpenClaw-Proj/analyzer/skills_security_matrix/exporters/csv_exporter.py#L1)

### External References

- OpenAI Structured Outputs guide: <https://platform.openai.com/docs/guides/structured-outputs>
- OpenAI Responses API reference: <https://platform.openai.com/docs/api-reference/responses>
- Semgrep pattern syntax: <https://semgrep.dev/docs/writing-rules/pattern-syntax>
- Semgrep rule syntax: <https://semgrep.dev/docs/writing-rules/rule-syntax>
- Tree-sitter query syntax: <https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html>
