---
title: feat: Add Flask skill repo scan web
type: feat
status: active
date: 2026-04-02
origin: docs/brainstorms/flask-skill-repo-scan-web-requirements.md
---

# feat: Add Flask skill repo scan web

## Overview

Add a lightweight Flask web workflow that lets a user submit a GitHub repository URL and an optional skill name, then performs repository download, skill discovery, skill-path resolution, analyzer execution, and result rendering in one browser flow.

This plan carries forward the origin decisions that the first version should optimize for the fastest single-repository path, default to `GitHub URL + skill name`, automatically fall back to full-repository skill discovery when the skill name cannot be matched, stay synchronous from the user’s perspective, and reuse the existing analyzer entrypoints rather than inventing a parallel scanning stack (see origin: `docs/brainstorms/flask-skill-repo-scan-web-requirements.md`).

## Problem Statement / Motivation

The repo already has the hard part of the workflow: local skill discovery and analysis via [`main.py`](/home/szk/code/OpenClaw-Proj/main.py#L1), [`scripts/run_single_skill_from_skills_sh.py`](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py#L202), and the case-study outputs described in [`README.md`](/home/szk/code/OpenClaw-Proj/README.md#L242). What it does not have is an accessible browser entrypoint for users who only want to answer a simple question:

- does this GitHub repo contain the skill I care about?
- where is that skill in the repo?
- what does the current analyzer say about it?

Without a web layer, the user must manually clone a repository, guess the skill slug, invoke the CLI, and inspect run directories. The feature should remove that friction without destabilizing the current analyzer architecture.

## Research Findings

### Local Context

- The project is a lightweight Python repository with `Flask` already declared in [`pyproject.toml`](/home/szk/code/OpenClaw-Proj/pyproject.toml#L1), so the web entrypoint can be added without introducing a new framework.
- The current top-level runtime entrypoint is CLI-only in [`main.py`](/home/szk/code/OpenClaw-Proj/main.py#L1), so the web feature should likely live alongside the CLI rather than replacing it.
- The single-skill helper script already supports local-scan mode without a database in [`scripts/run_single_skill_from_skills_sh.py`](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py#L939), which is the right base for repository-local web requests.
- That script currently resolves a single slug and then shells out to `main.py` in [`scripts/run_single_skill_from_skills_sh.py`](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py#L960). It already prints structured resolution failures such as `skill_not_found` and `skill_ambiguous`, which can be turned into web-facing states.
- Existing report rendering logic in [`scripts/render_skills_security_html.py`](/home/szk/code/OpenClaw-Proj/scripts/render_skills_security_html.py#L1) shows that case JSON files already contain enough structured data to build a human-readable view without exposing raw output directories.
- There is currently no existing Flask app, `templates/`, or `static/` directory in the repo, so this should be treated as a net-new but intentionally small web surface.
- There is no `docs/solutions/` knowledge base in this repository, so there are no institutional learnings to inherit for this feature.

### External Research Decision

Proceed without external research.

Reasoning:

- The repo already has clear local patterns for the analyzer pipeline and output model.
- The feature is an internal composition layer around existing local capabilities rather than a novel framework or external API design problem.
- `Flask` is already a declared dependency, and the first version is intentionally simple and synchronous.

## Planning Decision

The right first cut is a thin Flask orchestration layer with three responsibilities:

1. validate and normalize user input
2. prepare a local repository workspace and resolve candidate skills
3. invoke the existing analyzer path and render a compact results page

The key design choice is to reuse the current CLI/script behavior where it provides stable semantics, while extracting only the minimal reusable helpers needed to support the web fallback flow cleanly. That keeps the web layer small and avoids creating a second source of truth for skill resolution.

## Stakeholders

- End users or researchers who want a quick browser-based way to inspect one repository.
- Developers maintaining the analyzer, who need the web feature to reuse current logic rather than fork it.
- Future contributors who may extend the web UI into a richer tool later, and therefore need a clean separation between orchestration, analyzer invocation, and presentation.

## Proposed Solution

Add a small Flask application with one primary page and one POST workflow:

1. `GET /`
   Render a form with:
   - GitHub repository URL
   - optional skill name
   - optional advanced switches only if they are low-cost and already stable, otherwise omit in v1

2. `POST /scan`
   Perform synchronous request handling:
   - validate and normalize the GitHub URL
   - clone or refresh the repository into a controlled local workspace
   - if a skill name is present, try direct resolution first
   - if resolution fails or skill name is omitted, discover all skills in the repository
   - if one clear match is available, run analysis immediately
   - if multiple candidates exist, return a result page with candidate choices instead of a hard failure
   - if analysis completes, render a summary page from the generated case JSON

3. `POST /scan/select-skill`
   Handle the fallback continuation when the first request returns multiple candidate skills. This keeps the user on a simple server-rendered flow while still honoring the origin decision that failed direct matching should degrade into repository-wide discovery rather than a dead end (see origin: `docs/brainstorms/flask-skill-repo-scan-web-requirements.md`).

## Technical Approach

### Architecture

Add a small web package rather than growing ad hoc logic directly inside `main.py`. Suggested layout:

- `web/app.py`
- `web/services/repo_fetcher.py`
- `web/services/skill_locator.py`
- `web/services/scan_runner.py`
- `web/services/result_loader.py`
- `web/templates/base.html`
- `web/templates/index.html`
- `web/templates/result.html`
- `web/templates/choose_skill.html`
- `web/static/app.css`

This keeps responsibilities separated:

- `repo_fetcher`: clone/update repo and return local path
- `skill_locator`: discover skills and resolve direct or fallback matches
- `scan_runner`: invoke analyzer-compatible execution path and capture output paths
- `result_loader`: read the produced case JSON and derive a presentation-friendly summary

### Reuse Strategy for Existing Analyzer Logic

Prefer a hybrid reuse strategy:

- Extract or reuse pure-Python helpers from [`scripts/run_single_skill_from_skills_sh.py`](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py#L333) for local skill discovery and slug normalization.
- Keep the actual analyzer invocation as a subprocess call to the existing entrypoint for v1.

Why this split is the best fit:

- discovery and slug matching are cheap and deterministic to reuse in-process
- the current script already treats analyzer execution as a shell-out boundary
- keeping the final run step in a subprocess preserves current CLI semantics, isolates analyzer-side crashes, and reduces the amount of refactoring required before the web UI becomes usable

Planning implication:

- factor out shared local-resolution helpers into a reusable module, or import the existing functions into the web layer if the dependency surface remains small and stable
- keep the subprocess execution path as the contract for “run one resolved skill and produce a case JSON”

### Repository Download and Workspace Strategy

Use a dedicated local workspace such as `tmp/web_repos/` or `web/workspaces/repos/` under the repo root.

Rules:

- normalize each GitHub repo into a deterministic local directory name such as `owner__repo`
- if the directory does not exist, clone it
- if it already exists, refresh it in a safe, non-destructive way for v1, or reclone into a clean directory if refresh semantics are brittle
- write scan outputs into a web-owned output root distinct from ad hoc research runs so result pages do not mix with manual CLI experiments

Recommendation for v1:

- prefer “clean per-request output directory + reusable local clone directory”
- avoid building a generalized cache invalidation system
- if repository refresh becomes error-prone, fall back to deleting and recloning only the web-managed repo directory, not arbitrary user directories

### Skill Resolution Flow

Implement the user flow explicitly instead of burying it in generic error handling:

1. Normalize the submitted skill name using the same slug-normalization rules already used by the analyzer helper.
2. Scan the local repo for all directories containing `SKILL.md`.
3. If no skill name was submitted:
   - return the discovered skills as candidates
4. If a skill name was submitted:
   - try exact normalized directory-name match
   - if one match exists, run analysis
   - if zero matches exist, return the full candidate list with a “not found, choose one instead” message
   - if multiple matches exist, return the candidate list with an “ambiguous match” message

This is simpler and more web-native than relying on CLI stderr parsing alone, while still matching the origin fallback requirement (see origin: `docs/brainstorms/flask-skill-repo-scan-web-requirements.md`).

### Result Rendering Strategy

Render from the single-skill case JSON rather than from raw logs.

Minimum result payload to show:

- submitted repository URL
- resolved local repo name
- selected skill name / skill ID
- resolved skill path in the repository
- overall scan success or failure
- top-level discrepancy/status summary
- key category outcomes
- key risks / controls if present
- surfaced errors if present

Do not expose the entire output directory tree by default. A small optional “debug details” panel can show:

- subprocess command used
- run directory path
- case JSON path

### Error Model

Define explicit web-facing error states:

- `invalid_repo_url`
- `repo_download_failed`
- `repo_not_accessible`
- `no_skills_found`
- `skill_not_found_with_candidates`
- `skill_ambiguous`
- `analysis_failed`
- `case_output_missing`

Each state should map to:

- a user-facing title
- a short explanation
- optional technical detail block for debugging
- a suggested next action

### Routes and Request Model

Recommended first-pass routes:

- `GET /` -> input form
- `POST /scan` -> initial workflow
- `POST /scan/select-skill` -> fallback candidate confirmation

Avoid adding REST APIs in v1 unless the HTML flow clearly needs them. Server-rendered templates are enough for the stated scope.

## System-Wide Impact

### Interaction Graph

`POST /scan` triggers:

1. request validation in Flask
2. repository clone/update in the repo-fetch service
3. local skill discovery in the skill-locator service
4. optional analyzer subprocess execution in the scan-runner service
5. output file loading in the result-loader service
6. final template rendering back to the browser

If fallback is needed, the first request stops after step 3 and renders candidate choices. The second request resumes at steps 4-6 with the chosen skill.

### Error & Failure Propagation

- clone/update failures should stop before any analyzer call
- discovery failures should render a repository-level error page
- analyzer non-zero exit should become `analysis_failed`
- missing case JSON after a zero-exit analyzer run should become `case_output_missing`
- user input validation failures should re-render the form with inline messages instead of generic error pages

### State Lifecycle Risks

- partial clone or interrupted refresh can leave a broken local repo cache
- repeated scans can accumulate many output directories if they are never cleaned
- synchronous requests can tie up the Flask worker if analysis time grows unexpectedly

Mitigation for v1:

- limit the first version to low concurrency expectations
- keep clone directories separate from run output directories
- record the exact run directory returned by the scan runner instead of guessing later

### API Surface Parity

The new web feature should not replace:

- the existing CLI in [`main.py`](/home/szk/code/OpenClaw-Proj/main.py#L1)
- the helper script in [`scripts/run_single_skill_from_skills_sh.py`](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py#L939)

It should compose them. If shared logic emerges, extract it into reusable modules rather than drifting the CLI and web paths apart.

### Integration Test Scenarios

- submit a valid repo URL plus an exact skill name and verify the page renders the resolved path and result summary
- submit a valid repo URL plus an unknown skill name and verify the flow degrades to a candidate-selection page
- submit a valid repo URL with no skill name and verify repository-wide discovery is shown
- submit a repo with no `SKILL.md` anywhere and verify a clear “no skills found” result
- simulate analyzer success with missing case output and verify the page reports a structured failure instead of crashing

## SpecFlow Analysis

### User Flows

1. Direct scan flow
   - Entry point: user lands on `/`
   - Inputs: repo URL and skill name
   - Happy path: repo downloads, skill resolves directly, analyzer runs, result page renders
   - Terminal state: result summary page

2. Discovery-first flow
   - Entry point: user lands on `/`
   - Inputs: repo URL only
   - Happy path: repo downloads, all skills are discovered, user selects one, analyzer runs
   - Terminal state: candidate page followed by result summary page

3. Fallback recovery flow
   - Entry point: user submits repo URL and an incorrect skill name
   - Happy path: system explains the direct match failed but shows discovered candidates
   - Terminal state: candidate selection page instead of a hard error

4. Failure flow
   - Entry point: invalid or inaccessible repo, or analyzer failure
   - Happy path: not applicable
   - Terminal state: same-page error view with next-step guidance

### Gaps Addressed in This Plan

1. Important: the brainstorm said “同步单页体验”, but the fallback selection path needs a second server round-trip.
   Why it matters: if this is not made explicit, implementation may force everything into one overcomplicated POST handler.
   Plan default: keep the overall experience simple and synchronous, but allow a second form submission for fallback candidate selection.

2. Important: result shape for the page was previously under-specified.
   Why it matters: without a defined summary surface, the UI may dump raw JSON or hide too much.
   Plan default: render from case JSON into a compact result summary with optional debug details.

3. Minor: repository refresh semantics were open.
   Why it matters: update-vs-reclone complexity can consume disproportionate effort.
   Plan default: keep a deterministic web-managed clone location, but prioritize correctness over clever update behavior in v1.

## Alternative Approaches Considered

### 1. Import the analyzer fully in-process from Flask

Pros:

- fewer subprocess boundaries
- easier to return rich Python objects directly

Cons:

- requires more refactoring of current script/CLI structure
- tighter coupling between web request lifecycle and analyzer internals
- increases blast radius if analyzer code raises unexpectedly

Decision:

- not preferred for v1

### 2. Treat the web app as a thin wrapper around the existing helper script only

Pros:

- fastest path to “something works”
- minimal refactoring

Cons:

- hard to implement graceful fallback candidate selection
- brittle if logic depends on parsing stdout/stderr text
- poorer control over user-facing states

Decision:

- partially reuse the script, but not as the only integration boundary

### 3. Build an async job system immediately

Pros:

- better long-running request handling
- easier future scaling

Cons:

- directly conflicts with the origin scope and first-version simplicity goal
- introduces state, polling, and task management complexity too early

Decision:

- explicitly out of scope for this plan (see origin: `docs/brainstorms/flask-skill-repo-scan-web-requirements.md`)

## Implementation Phases

### Phase 1: Web Foundation

- add the Flask app entrypoint and server-rendered template structure
- add input validation and form rendering
- add a web-owned config for repo workspace and output workspace
- wire a basic `/` and `/scan` route

Success criteria:

- app boots locally
- invalid input is handled cleanly
- templates render without analyzer integration

### Phase 2: Repository and Skill Resolution

- implement repository clone/update service
- implement local repo scan for `SKILL.md` directories
- implement skill-name normalization and candidate generation
- implement fallback selection page and follow-up route

Success criteria:

- a submitted repo can be cloned to a deterministic location
- direct match, no match, multiple matches, and no-skill scenarios are all represented explicitly

### Phase 3: Analyzer Execution and Result Rendering

- implement scan runner using subprocess invocation of the existing analyzer-compatible path
- capture run directory and locate the produced case JSON
- build a presentation-oriented result loader
- render final result and structured failure states

Success criteria:

- a single selected skill can be analyzed end-to-end from the web UI
- result pages show path, summary, and errors without requiring the user to inspect output folders

### Phase 4: Verification and Polish

- add tests for route flows and service helpers
- add a small amount of visual polish to make the page readable
- document how to run the web app locally

Success criteria:

- happy path and key failure paths are covered by automated tests
- README or dedicated web docs explain startup and expected behavior

## Acceptance Criteria

### Functional Requirements

- [ ] Users can submit a GitHub repository URL and optional skill name from a browser form.
- [ ] The server downloads the repository into a controlled local workspace.
- [ ] If the submitted skill name matches one repository skill, analysis runs immediately.
- [ ] If no skill name is provided, the UI shows discovered skill candidates.
- [ ] If the submitted skill name does not match, the UI falls back to discovered candidates instead of hard-failing.
- [ ] Successful scans display the resolved repository path, selected skill identity, resolved skill location, and core analyzer summary.
- [ ] Failures display structured, understandable error states.

### Non-Functional Requirements

- [ ] The implementation remains standard-library-first plus Flask, without introducing a heavyweight frontend stack.
- [ ] The web flow reuses existing analyzer semantics instead of duplicating classification logic.
- [ ] Web-managed repositories and output runs are isolated from ad hoc manual runs.

### Quality Gates

- [ ] Unit tests cover repo URL validation, skill normalization, and candidate fallback logic.
- [ ] Route-level tests cover direct success, missing-skill fallback, no-skill repo, and analyzer failure.
- [ ] Documentation explains how to start and use the Flask app.

## Success Metrics

- A user can complete a single-repo scan from browser input without using the CLI.
- The fallback candidate flow rescues incorrect skill-name submissions instead of forcing a full retry.
- The first version stays small enough that the analyzer’s current CLI behavior remains the system of record.

## Dependencies & Risks

### Dependencies

- `Flask` dependency already present in [`pyproject.toml`](/home/szk/code/OpenClaw-Proj/pyproject.toml#L1)
- existing analyzer and helper script behavior in [`main.py`](/home/szk/code/OpenClaw-Proj/main.py#L1) and [`scripts/run_single_skill_from_skills_sh.py`](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py#L939)
- filesystem write access for repository clones and output runs

### Risks

- synchronous scans may be slower than expected for larger repositories
- Git clone/update behavior may be brittle if reused repositories are left in inconsistent states
- analyzer output contracts may shift if the helper script changes without the web layer being updated

### Mitigations

- keep the first version scoped to synchronous single-user workflows
- isolate web-owned workspaces
- centralize the result-loading contract so output path assumptions are tested rather than duplicated across templates

## Sources & References

- **Origin document:** [docs/brainstorms/flask-skill-repo-scan-web-requirements.md](/home/szk/code/OpenClaw-Proj/docs/brainstorms/flask-skill-repo-scan-web-requirements.md)
- Existing CLI entrypoint: [main.py](/home/szk/code/OpenClaw-Proj/main.py#L1)
- Existing single-skill helper: [scripts/run_single_skill_from_skills_sh.py](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py#L202)
- Existing analyzer/report output description: [README.md](/home/szk/code/OpenClaw-Proj/README.md#L242)
- Existing HTML report renderer: [scripts/render_skills_security_html.py](/home/szk/code/OpenClaw-Proj/scripts/render_skills_security_html.py#L1)
