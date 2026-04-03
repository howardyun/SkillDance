from __future__ import annotations

import argparse
import csv
import json
import multiprocessing
import os
import re
import sqlite3
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, Lock

try:
    from tqdm.auto import tqdm
except ImportError:  # pragma: no cover - optional UX dependency
    tqdm = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.env import load_environment
from analyzer.skills_security_matrix.cli import _analyze_skill, _build_provider_registry
from analyzer.skills_security_matrix.exporters.csv_exporter import (
    CLASSIFICATIONS_FIELDNAMES,
    DISCREPANCIES_FIELDNAMES,
    REVIEW_AUDIT_FIELDNAMES,
    RULE_CANDIDATES_FIELDNAMES,
    SKILLS_FIELDNAMES,
    candidate_rows_for_result,
    classification_rows_for_result,
    discrepancy_rows_for_result,
    review_audit_rows_for_result,
    skill_rows,
)
from analyzer.skills_security_matrix.exporters.json_exporter import (
    candidate_record,
    classification_record,
    discrepancy_record,
    review_audit_record,
    risk_mapping_record,
    skill_record,
)
from analyzer.skills_security_matrix.matrix_loader import load_matrix_definition, parse_matrix_file
from analyzer.skills_security_matrix.models import AnalysisResult, RunConfig, RunSummary, dataclass_to_dict
from analyzer.skills_security_matrix.skill_discovery import discover_skills
from crawling.skills.skills_sh.download_skills import extract_github_repo


IGNORED_DIR_NAMES = {".git"}


@dataclass(frozen=True, slots=True)
class SkillRecord:
    skill_id: str
    source: str | None
    source_url: str | None


@dataclass(frozen=True, slots=True)
class ResolvedSkill:
    skill_dir: Path
    repo: str
    repo_root: Path
    slug: str


@dataclass(frozen=True, slots=True)
class RepoSkillIndex:
    repo_root: Path
    include_hidden: bool
    repo_has_skill_md: bool
    candidate_dirs: tuple[Path, ...]
    candidate_dir_set: frozenset[Path]
    candidate_dirs_by_name: dict[str, tuple[Path, ...]]
    candidate_dirs_by_normalized_name: dict[str, tuple[Path, ...]]


class RepoSkillIndexCache:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, bool], RepoSkillIndex] = {}
        self._events: dict[tuple[str, bool], Event] = {}
        self._lock = Lock()

    def get(self, repo_root: Path, include_hidden: bool = False) -> RepoSkillIndex:
        key = (str(repo_root.resolve()), include_hidden)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

            event = self._events.get(key)
            should_build = event is None
            if should_build:
                event = Event()
                self._events[key] = event

        if should_build:
            try:
                index = build_repo_skill_index(repo_root, include_hidden=include_hidden)
            except Exception:
                with self._lock:
                    event = self._events.pop(key, None)
                    if event is not None:
                        event.set()
                raise

            with self._lock:
                self._cache[key] = index
                event = self._events.pop(key, None)
                if event is not None:
                    event.set()
            return index

        assert event is not None
        event.wait()
        with self._lock:
            cached = self._cache.get(key)
        if cached is None:
            return self.get(repo_root, include_hidden=include_hidden)
        return cached


class BatchResultWriter:
    def __init__(self, run_dir: Path, requested_formats: list[str]) -> None:
        self.run_dir = run_dir
        self.requested_formats = set(requested_formats)
        self.cases_dir = run_dir / "cases"
        self._jsonl_handles: dict[str, object] = {}
        self._csv_handles: list[object] = []
        self._csv_writers: dict[str, csv.DictWriter] = {}

        if "json" in self.requested_formats:
            self.cases_dir.mkdir(parents=True, exist_ok=True)
            for stem in (
                "skills",
                "rule_candidates",
                "classifications",
                "discrepancies",
                "risk_mappings",
                "review_audit",
            ):
                path = run_dir / f"{stem}.jsonl"
                self._jsonl_handles[stem] = path.open("w", encoding="utf-8")

        if "csv" in self.requested_formats:
            self._register_csv_writer("skills", SKILLS_FIELDNAMES)
            self._register_csv_writer("classifications", CLASSIFICATIONS_FIELDNAMES)
            self._register_csv_writer("rule_candidates", RULE_CANDIDATES_FIELDNAMES)
            self._register_csv_writer("discrepancies", DISCREPANCIES_FIELDNAMES)
            self._register_csv_writer("review_audit", REVIEW_AUDIT_FIELDNAMES)

    def _register_csv_writer(self, stem: str, fieldnames: list[str]) -> None:
        handle = (self.run_dir / f"{stem}.csv").open("w", encoding="utf-8", newline="")
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        handle.flush()
        self._csv_handles.append(handle)
        self._csv_writers[stem] = writer

    def write_result(self, result: AnalysisResult) -> None:
        if "json" in self.requested_formats:
            self._append_jsonl("skills", skill_record(result))
            self._append_jsonl("rule_candidates", candidate_record(result))
            self._append_jsonl("classifications", classification_record(result))
            self._append_jsonl("discrepancies", discrepancy_record(result))
            self._append_jsonl("risk_mappings", risk_mapping_record(result))
            self._append_jsonl("review_audit", review_audit_record(result))
            (self.cases_dir / f"{_safe_filename(result.skill_id)}.json").write_text(
                json.dumps(dataclass_to_dict(result), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if "csv" in self.requested_formats:
            self._csv_writers["skills"].writerows(skill_rows(result))
            self._csv_writers["classifications"].writerows(classification_rows_for_result(result))
            self._csv_writers["rule_candidates"].writerows(candidate_rows_for_result(result))
            self._csv_writers["discrepancies"].writerows(discrepancy_rows_for_result(result))
            self._csv_writers["review_audit"].writerows(review_audit_rows_for_result(result))
            for handle in self._csv_handles:
                handle.flush()

    def _append_jsonl(self, stem: str, payload: dict[str, object]) -> None:
        handle = self._jsonl_handles[stem]
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")
        handle.flush()

    def close(self) -> None:
        for handle in self._jsonl_handles.values():
            handle.close()
        for handle in self._csv_handles:
            handle.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve skills.sh skill paths from the DB and run the analyzer."
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Optional path to the skills.sh SQLite DB. Required only when resolving skills via DB metadata.",
    )
    parser.add_argument("--repos-root", default="skills/skill_sh_test", help="Root directory of downloaded repos.")
    parser.add_argument(
        "--skill-id",
        default=None,
        help=(
            "Optional target identifier. With --db, this is a skills.sh skill_id "
            "(e.g. aahl/skills/mcp-vods). Without --db, this is a local skill slug matched "
            "against directories under --repos-root."
        ),
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter used to invoke main.py. Defaults to the current interpreter.",
    )
    parser.add_argument("--output-dir", default="outputs/skills_security_matrix")
    parser.add_argument("--format", default="json,csv")
    parser.add_argument("--case-study-skill", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=min(32, (os.cpu_count() or 1) + 4),
        help="Number of concurrent workers used for batch analysis.",
    )
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--matrix-path", default="analyzer/security matrix.md")
    parser.add_argument("--fail-on-unknown-matrix", action="store_true")
    parser.add_argument("--llm-review-mode", default="off", choices=["off", "review", "review+fallback"])
    parser.add_argument("--llm-provider", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-low-confidence-threshold", type=float, default=0.45)
    parser.add_argument("--llm-high-risk-sparse-threshold", type=int, default=1)
    parser.add_argument("--llm-fallback-max-categories", type=int, default=0)
    parser.add_argument("--llm-timeout-seconds", type=int, default=30)
    parser.add_argument(
        "--skill-timeout-seconds",
        type=int,
        default=600,
        help="Per-skill timeout used only in batch mode.",
    )
    parser.add_argument("--llm-fail-open", action="store_true")
    parser.add_argument("--llm-fail-closed", action="store_true")
    parser.add_argument("--emit-review-audit", action="store_true")
    parser.add_argument("--goldset-path", default=None)
    return parser


def load_skill_record(db_path: Path, skill_id: str) -> SkillRecord:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT skill_id, source, source_url FROM skills WHERE skill_id = ? LIMIT 1",
            (skill_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ResolutionError(
            "skill_id_not_found",
            f"skill_id not found in DB: {skill_id}",
            skill_id=skill_id,
            repo=None,
            repo_root=None,
            source=None,
            source_url=None,
        )
    return SkillRecord(skill_id=row["skill_id"], source=row["source"], source_url=row["source_url"])


def load_skill_records(db_path: Path, limit: int | None = None) -> list[SkillRecord]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT skill_id, source, source_url FROM skills ORDER BY id ASC"
        if limit is not None:
            rows = conn.execute(f"{query} LIMIT ?", (limit,)).fetchall()
        else:
            rows = conn.execute(query).fetchall()
    finally:
        conn.close()
    return [SkillRecord(skill_id=row["skill_id"], source=row["source"], source_url=row["source_url"]) for row in rows]


def _iter_local_skill_dirs(repos_root: Path, include_hidden: bool = False) -> list[Path]:
    repos_root = repos_root.resolve()
    skill_dirs: list[Path] = []
    seen: set[Path] = set()

    for current_root, dir_names, file_names in os.walk(repos_root, topdown=True):
        if not include_hidden:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIR_NAMES and not name.startswith(".")]
        else:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIR_NAMES]

        if "SKILL.md" not in file_names:
            continue

        skill_dir = Path(current_root).resolve()
        if skill_dir in seen:
            continue
        skill_dirs.append(skill_dir)
        seen.add(skill_dir)

    return sorted(skill_dirs)


def _local_skill_id(skill_dir: Path, repos_root: Path) -> str:
    return skill_dir.resolve().relative_to(repos_root.resolve()).as_posix()


def _infer_local_repo_root(skill_dir: Path, repos_root: Path) -> Path:
    skill_dir = skill_dir.resolve()
    repos_root = repos_root.resolve()
    repo_root = skill_dir
    while repo_root.parent != repos_root and repo_root != repos_root:
        repo_root = repo_root.parent
    return repo_root


def scan_local_skill_records(repos_root: Path, include_hidden: bool = False) -> list[SkillRecord]:
    return [
        SkillRecord(
            skill_id=_local_skill_id(skill_dir, repos_root),
            source=None,
            source_url=None,
        )
        for skill_dir in _iter_local_skill_dirs(repos_root, include_hidden=include_hidden)
    ]


def resolve_local_skill_by_slug(skill_slug: str, repos_root: Path, include_hidden: bool = False) -> ResolvedSkill:
    normalized_slug = normalize_skill_dir_name(skill_slug)
    candidates = [
        skill_dir
        for skill_dir in _iter_local_skill_dirs(repos_root, include_hidden=include_hidden)
        if normalize_skill_dir_name(skill_dir.name) == normalized_slug
    ]

    if not candidates:
        raise ResolutionError(
            "skill_not_found",
            f"Could not resolve local skill path for slug: {skill_slug}",
            skill_id=skill_slug,
            repo=None,
            repo_root=repos_root,
            source=None,
            source_url=None,
        )

    if len(candidates) > 1:
        raise ResolutionError(
            "skill_ambiguous",
            f"Multiple local skill directories matched slug: {skill_slug}",
            skill_id=skill_slug,
            repo=None,
            repo_root=repos_root,
            source=None,
            source_url=None,
            candidates=candidates,
        )

    skill_dir = candidates[0]
    return ResolvedSkill(
        skill_dir=skill_dir,
        repo="",
        repo_root=_infer_local_repo_root(skill_dir, repos_root),
        slug=normalized_slug,
    )


def resolve_local_skill(record: SkillRecord, repos_root: Path, include_hidden: bool = False) -> ResolvedSkill:
    skill_dir = (repos_root / record.skill_id).resolve()
    if not (skill_dir / "SKILL.md").is_file():
        raise ResolutionError(
            "skill_not_found",
            f"Could not resolve local skill path for {record.skill_id}",
            skill_id=record.skill_id,
            repo=None,
            repo_root=repos_root,
            source=None,
            source_url=None,
        )

    return ResolvedSkill(
        skill_dir=skill_dir,
        repo="",
        repo_root=_infer_local_repo_root(skill_dir, repos_root),
        slug=normalize_skill_dir_name(skill_dir.name),
    )


class ResolutionError(RuntimeError):
    def __init__(
        self,
        error_type: str,
        message: str,
        *,
        skill_id: str,
        repo: str | None,
        repo_root: Path | None,
        source: str | None,
        source_url: str | None,
        candidates: list[Path] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.skill_id = skill_id
        self.repo = repo
        self.repo_root = repo_root
        self.source = source
        self.source_url = source_url
        self.candidates = candidates or []


def resolve_skill(
    record: SkillRecord,
    repos_root: Path,
    include_hidden: bool = False,
    repo_index_cache: RepoSkillIndexCache | None = None,
) -> ResolvedSkill:
    repo = extract_github_repo(record.source, record.source_url)
    if repo is None:
        raise ResolutionError(
            "repo_unparseable",
            f"Unable to parse repo from source fields for {record.skill_id}",
            skill_id=record.skill_id,
            repo=None,
            repo_root=None,
            source=record.source,
            source_url=record.source_url,
        )

    repo_root = (repos_root / repo.replace("/", "__")).resolve()
    if not repo_root.is_dir():
        raise ResolutionError(
            "repo_not_found",
            f"Local repo directory not found: {repo_root}",
            skill_id=record.skill_id,
            repo=repo,
            repo_root=repo_root,
            source=record.source,
            source_url=record.source_url,
        )

    slug_variants = build_skill_slug_variants(record, repo)
    repo_index = (
        repo_index_cache.get(repo_root, include_hidden=include_hidden)
        if repo_index_cache is not None
        else build_repo_skill_index(repo_root, include_hidden=include_hidden)
    )
    candidates = find_skill_candidates(repo_index, slug_variants)
    slug = slug_variants[0]

    if not candidates and _repo_level_skill_matches(record, repo, repo_root, repo_has_skill_md=repo_index.repo_has_skill_md):
        candidates = [repo_root]

    if not candidates:
        raise ResolutionError(
            "skill_not_found",
            f"Could not resolve skill path for {record.skill_id}",
            skill_id=record.skill_id,
            repo=repo,
            repo_root=repo_root,
            source=record.source,
            source_url=record.source_url,
        )

    ranked = rank_skill_candidates(candidates, repo_root, slug)
    return ResolvedSkill(skill_dir=ranked[0], repo=repo, repo_root=repo_root, slug=slug)


def slugify_skill_name(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def normalize_skill_dir_name(value: str) -> str:
    return re.sub(r"[-_]+", "-", re.sub(r"\s+", "-", value.strip().lower())).strip("-")


def build_skill_slug_variants(record: SkillRecord, repo: str) -> list[str]:
    raw_tail = record.skill_id.rsplit("/", 1)[-1].strip()
    source_parts = [slugify_skill_name(part) for part in repo.split("/") if part]
    variants: list[str] = []

    def add_variant(value: str, *, slugify: bool = True) -> None:
        normalized = slugify_skill_name(value) if slugify else value.strip()
        if normalized and normalized not in variants:
            variants.append(normalized)

    add_variant(raw_tail)

    if " " in raw_tail:
        add_variant(raw_tail.replace(" ", "-"), slugify=False)
        add_variant(raw_tail.replace(" ", "_"), slugify=False)
        add_variant(raw_tail.lower().replace(" ", "-"), slugify=False)
        add_variant(raw_tail.lower().replace(" ", "_"), slugify=False)

    for prefix in source_parts:
        if variants and variants[0].startswith(f"{prefix}-"):
            add_variant(variants[0][len(prefix) + 1 :])

    if len(source_parts) >= 2 and variants:
        combined_prefix = "-".join(source_parts)
        if variants[0].startswith(f"{combined_prefix}-"):
            add_variant(variants[0][len(combined_prefix) + 1 :])

    return variants


def build_repo_skill_index(repo_root: Path, include_hidden: bool = False) -> RepoSkillIndex:
    repo_root = repo_root.resolve()
    repo_has_skill_md = (repo_root / "SKILL.md").is_file()
    candidate_dirs: list[Path] = []
    candidate_dir_set: set[Path] = set()
    candidate_dirs_by_name: dict[str, list[Path]] = defaultdict(list)
    candidate_dirs_by_normalized_name: dict[str, list[Path]] = defaultdict(list)

    for current_root, dir_names, file_names in os.walk(repo_root, topdown=True):
        if not include_hidden:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIR_NAMES]

        if "SKILL.md" not in file_names:
            continue

        skill_dir = Path(current_root)
        if skill_dir == repo_root:
            continue

        relative_path = skill_dir.relative_to(repo_root)
        if not include_hidden and path_has_ignored_part(relative_path):
            continue
        if skill_dir in candidate_dir_set:
            continue

        candidate_dirs.append(skill_dir)
        candidate_dir_set.add(skill_dir)
        candidate_dirs_by_name[skill_dir.name].append(skill_dir)
        candidate_dirs_by_normalized_name[normalize_skill_dir_name(skill_dir.name)].append(skill_dir)

    return RepoSkillIndex(
        repo_root=repo_root,
        include_hidden=include_hidden,
        repo_has_skill_md=repo_has_skill_md,
        candidate_dirs=tuple(candidate_dirs),
        candidate_dir_set=frozenset(candidate_dir_set),
        candidate_dirs_by_name={name: tuple(paths) for name, paths in candidate_dirs_by_name.items()},
        candidate_dirs_by_normalized_name={
            name: tuple(paths) for name, paths in candidate_dirs_by_normalized_name.items()
        },
    )


def find_skill_candidates(repo_index: RepoSkillIndex, slugs: list[str]) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()

    def add_candidate(candidate: Path) -> None:
        if candidate in repo_index.candidate_dir_set and candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)

    for slug in slugs:
        add_candidate(repo_index.repo_root / "skills" / slug)
        add_candidate(repo_index.repo_root / slug)
        for candidate in repo_index.candidate_dirs_by_name.get(slug, ()):
            add_candidate(candidate)
        for candidate in repo_index.candidate_dirs_by_normalized_name.get(normalize_skill_dir_name(slug), ()):
            add_candidate(candidate)

    return candidates


def path_has_ignored_part(relative_path: Path) -> bool:
    return any(part in IGNORED_DIR_NAMES for part in relative_path.parts)


def _safe_filename(value: str) -> str:
    return value.replace("/", "__")


def candidate_rank(path: Path, repo_root: Path, slug: str) -> tuple[int, int, int]:
    relative = path.relative_to(repo_root)
    parts = relative.parts
    has_skills_slug = len(parts) >= 2 and parts[-2] == "skills" and parts[-1] == slug
    return (0 if has_skills_slug else 1, len(parts), 0)


def rank_skill_candidates(candidates: list[Path], repo_root: Path, slug: str) -> list[Path]:
    return sorted(candidates, key=lambda path: (candidate_rank(path, repo_root, slug), str(path)))


def _repo_level_skill_matches(
    record: SkillRecord,
    repo: str,
    repo_root: Path,
    *,
    repo_has_skill_md: bool | None = None,
) -> bool:
    if repo_has_skill_md is None:
        repo_has_skill_md = (repo_root / "SKILL.md").is_file()
    return record.skill_id.lower() == repo.lower() and repo_has_skill_md


def build_main_command(args: argparse.Namespace, resolved: ResolvedSkill) -> list[str]:
    command = [
        args.python_bin,
        "main.py",
        "--skills-dir",
        str(resolved.skill_dir),
        "--output-dir",
        args.output_dir,
        "--format",
        args.format,
        "--case-study-skill",
        args.case_study_skill or resolved.slug,
        "--matrix-path",
        args.matrix_path,
        "--llm-review-mode",
        args.llm_review_mode,
        "--llm-low-confidence-threshold",
        str(args.llm_low_confidence_threshold),
        "--llm-high-risk-sparse-threshold",
        str(args.llm_high_risk_sparse_threshold),
        "--llm-fallback-max-categories",
        str(args.llm_fallback_max_categories),
        "--llm-timeout-seconds",
        str(args.llm_timeout_seconds),
    ]
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if args.include_hidden:
        command.append("--include-hidden")
    if args.fail_on_unknown_matrix:
        command.append("--fail-on-unknown-matrix")
    if args.llm_provider:
        command.extend(["--llm-provider", args.llm_provider])
    if args.llm_model:
        command.extend(["--llm-model", args.llm_model])
    if args.llm_fail_open:
        command.append("--llm-fail-open")
    if args.llm_fail_closed:
        command.append("--llm-fail-closed")
    if args.emit_review_audit:
        command.append("--emit-review-audit")
    if args.goldset_path:
        command.extend(["--goldset-path", args.goldset_path])
    return command


def _error_payload(
    record: SkillRecord,
    *,
    error_type: str,
    error: str,
    repo: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, str]:
    resolved_repo = repo
    if resolved_repo is None and record.source and record.source_url:
        resolved_repo = extract_github_repo(record.source, record.source_url)
    return {
        "skill_id": record.skill_id,
        "error_type": error_type,
        "error": error,
        "repo": resolved_repo or "",
        "repo_root": str(repo_root) if repo_root else "",
    }


def _repo_root_for_record(record: SkillRecord, repos_root: Path) -> Path | None:
    if record.source and record.source_url:
        repo = extract_github_repo(record.source, record.source_url)
        if repo is not None:
            return repos_root / repo.replace("/", "__")
    skill_dir = repos_root / record.skill_id
    return _infer_local_repo_root(skill_dir, repos_root) if skill_dir.exists() else None


def _analyze_record_impl(
    record: SkillRecord,
    repos_root: Path,
    matrix_by_id,
    args: argparse.Namespace,
    provider_registry,
    failure_policy: str,
    repo_index_cache: RepoSkillIndexCache,
):
    if args.db:
        resolved = resolve_skill(
            record,
            repos_root,
            include_hidden=args.include_hidden,
            repo_index_cache=repo_index_cache,
        )
    else:
        resolved = resolve_local_skill(record, repos_root, include_hidden=args.include_hidden)
    artifact = discover_skills(resolved.skill_dir, include_hidden=args.include_hidden, limit=1)[0]
    artifact.skill_id = record.skill_id
    matrix_definition = load_matrix_definition(Path(args.matrix_path))
    return _analyze_skill(artifact, matrix_definition, matrix_by_id, args, provider_registry, failure_policy)


def _analyze_record_child(
    conn,
    record: SkillRecord,
    repos_root: Path,
    matrix_by_id,
    args: argparse.Namespace,
    failure_policy: str,
) -> None:
    try:
        load_environment()
        provider_registry = _build_provider_registry()
        result = _analyze_record_impl(
            record,
            repos_root,
            matrix_by_id,
            args,
            provider_registry,
            failure_policy,
            RepoSkillIndexCache(),
        )
        conn.send(("result", result))
    except ResolutionError as exc:
        conn.send(
            (
                "error",
                _error_payload(
                    record,
                    error_type=exc.error_type,
                    error=str(exc),
                    repo=exc.repo,
                    repo_root=exc.repo_root,
                ),
            )
        )
    except Exception as exc:  # pragma: no cover - defensive batch isolation
        conn.send(("error", _error_payload(record, error_type="analysis_error", error=str(exc))))
    finally:
        conn.close()


def analyze_record(
    record: SkillRecord,
    repos_root: Path,
    matrix_by_id,
    args: argparse.Namespace,
    failure_policy: str,
) -> tuple[str, AnalysisResult | dict[str, str]]:
    safe_args = _to_namespace(args)
    skill_timeout_seconds = getattr(args, "skill_timeout_seconds", 600)
    start_method = "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
    context = multiprocessing.get_context(start_method)
    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_analyze_record_child,
        args=(
            send_conn,
            record,
            repos_root,
            matrix_by_id,
            safe_args,
            failure_policy,
        ),
    )
    process.start()
    send_conn.close()

    try:
        deadline = skill_timeout_seconds
        while deadline > 0:
            if recv_conn.poll(min(0.5, deadline)):
                outcome = recv_conn.recv()
                process.join(timeout=1)
                return outcome
            if not process.is_alive():
                process.join(timeout=1)
                return (
                    "error",
                    _error_payload(
                        record,
                        error_type="analysis_error",
                        error=f"analysis subprocess exited unexpectedly with code {process.exitcode}",
                        repo_root=_repo_root_for_record(record, repos_root),
                    ),
                )
            deadline -= 0.5

        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        return (
            "error",
            _error_payload(
                record,
                error_type="skill_timeout",
                error=f"skill exceeded {skill_timeout_seconds} seconds",
                repo_root=_repo_root_for_record(record, repos_root),
            ),
        )
    finally:
        recv_conn.close()
        if process.is_alive():
            process.kill()
            process.join(timeout=1)


def _to_namespace(args: argparse.Namespace) -> argparse.Namespace:
    values = {key: getattr(args, key) for key in dir(args) if not key.startswith("_") and not callable(getattr(args, key))}
    return argparse.Namespace(**values)


def run_batch_analysis(args: argparse.Namespace, records: list[SkillRecord]) -> int:
    if args.workers < 1:
        print("[error] --workers must be >= 1", file=sys.stderr)
        return 2
    skill_timeout_seconds = getattr(args, "skill_timeout_seconds", 600)
    if skill_timeout_seconds < 1:
        print("[error] --skill-timeout-seconds must be >= 1", file=sys.stderr)
        return 2

    load_environment()
    requested_formats = [value.strip() for value in args.format.split(",") if value.strip()]
    matrix_categories = parse_matrix_file(Path(args.matrix_path))
    matrix_by_id = {category.category_id: category for category in matrix_categories}
    failure_policy = "fail_closed" if args.llm_fail_closed else "fail_open"
    repos_root = Path(args.repos_root)
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    writer = BatchResultWriter(run_dir, requested_formats)

    skill_errors: list[dict[str, str]] = []
    written_results = 0
    pending_outcomes: dict[int, tuple[str, AnalysisResult | dict[str, str]]] = {}
    next_index_to_write = 0
    progress = None
    if tqdm is not None:
        progress = tqdm(total=len(records), desc="Analyzing skills", unit="skill")

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {
                executor.submit(
                    analyze_record,
                    record,
                    repos_root,
                    matrix_by_id,
                    args,
                    failure_policy,
                ): (index, record)
                for index, record in enumerate(records)
            }

            for future in as_completed(future_map):
                index, record = future_map[future]
                try:
                    pending_outcomes[index] = future.result()
                except Exception as exc:  # pragma: no cover - defensive batch isolation
                    pending_outcomes[index] = (
                        "error",
                        {"skill_id": record.skill_id, "error_type": "analysis_error", "error": str(exc)},
                    )

                while next_index_to_write in pending_outcomes:
                    outcome_type, payload = pending_outcomes.pop(next_index_to_write)
                    if outcome_type == "result":
                        writer.write_result(payload)
                        written_results += 1
                    else:
                        skill_errors.append(payload)
                    next_index_to_write += 1

                if progress is not None:
                    progress.update(1)
                    progress.set_postfix_str(
                        f"ok={written_results} err={len(skill_errors)} buffered={len(pending_outcomes)}"
                    )
    finally:
        if progress is not None:
            progress.close()
        writer.close()

    summary = RunSummary(
        run_id=run_id,
        output_dir=str(run_dir),
        analyzed_skills=written_results,
        skipped_skills=len(skill_errors),
        errored_skills=len(skill_errors),
        config=RunConfig(
            skills_dir=args.repos_root,
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
            skill_timeout_seconds=skill_timeout_seconds,
            llm_failure_policy=failure_policy,
            emit_review_audit=args.emit_review_audit,
            goldset_path=args.goldset_path,
        ),
        skill_errors=skill_errors,
    )

    (run_dir / "run_manifest.json").write_text(
        json.dumps(dataclass_to_dict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Run complete: {summary.run_id}")
    print(f"Output directory: {summary.output_dir}")
    print(f"Analyzed skills: {summary.analyzed_skills}")
    print(f"Errored skills: {summary.errored_skills}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repos_root = Path(args.repos_root)

    if args.skill_id is None:
        if args.db:
            records = load_skill_records(Path(args.db), limit=args.limit)
        else:
            records = scan_local_skill_records(repos_root, include_hidden=args.include_hidden)
            if args.limit is not None:
                records = records[: args.limit]
        return run_batch_analysis(args, records)

    try:
        if args.db:
            record = load_skill_record(Path(args.db), args.skill_id)
            resolved = resolve_skill(record, repos_root, include_hidden=args.include_hidden)
        else:
            resolved = resolve_local_skill_by_slug(args.skill_id, repos_root, include_hidden=args.include_hidden)
    except ResolutionError as exc:
        print_resolution_error(exc)
        return 1

    command = build_main_command(args, resolved)
    print(f"Resolved skill path: {resolved.skill_dir}", flush=True)
    print("Executing command:", subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(command, check=False)
    return completed.returncode


def print_resolution_error(exc: ResolutionError) -> None:
    print(f"[{exc.error_type}] {exc}")
    print(f"skill_id: {exc.skill_id}")
    print(f"source: {exc.source or ''}")
    print(f"source_url: {exc.source_url or ''}")
    print(f"repo: {exc.repo or ''}")
    print(f"repo_root: {exc.repo_root or ''}")
    if exc.candidates:
        print("candidates:")
        for path in exc.candidates:
            print(f"  - {path}")


if __name__ == "__main__":
    raise SystemExit(main())
