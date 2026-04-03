from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class ScanError(RuntimeError):
    """Raised when analyzer execution fails."""


@dataclass(frozen=True, slots=True)
class ScanRunResult:
    run_id: str
    run_dir: Path
    case_json_path: Path
    command: list[str]
    stdout: str
    stderr: str


def run_single_skill_scan(
    *,
    project_root: Path,
    skill_dir: Path,
    runs_workspace: Path,
    repo_key: str,
    skill_key: str,
    python_bin: str | None = None,
    matrix_path: str = "analyzer/security matrix.md",
) -> ScanRunResult:
    runs_workspace.mkdir(parents=True, exist_ok=True)
    safe_repo = _safe_segment(repo_key)
    safe_skill = _safe_segment(skill_key)
    final_dir = runs_workspace / safe_repo / safe_skill
    final_case_path = final_dir / f"{safe_skill}.json"

    with tempfile.TemporaryDirectory(prefix="scan-", dir=str(runs_workspace)) as temp_root:
        temp_output_root = Path(temp_root)
        command = [
            python_bin or sys.executable,
            "main.py",
            "--skills-dir",
            str(skill_dir),
            "--output-dir",
            str(temp_output_root),
            "--format",
            "json",
            "--llm-review-mode",
            "off",
            "--matrix-path",
            matrix_path,
        ]
        completed = subprocess.run(
            command,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "analyzer run failed"
            raise ScanError(detail)

        run_dir = _resolve_latest_run_dir(temp_output_root)
        source_case_path = _resolve_case_json_path(run_dir, skill_dir.name)
        _persist_case_only(source_case_path, final_case_path)

    return ScanRunResult(
        run_id=f"{safe_repo}/{safe_skill}",
        run_dir=final_dir,
        case_json_path=final_case_path,
        command=command,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _resolve_latest_run_dir(output_root: Path) -> Path:
    run_dirs = [path for path in output_root.glob("run-*") if path.is_dir()]
    if not run_dirs:
        raise ScanError("Analyzer completed but no run directory was generated.")
    return sorted(run_dirs, key=lambda path: path.name)[-1]


def _resolve_case_json_path(run_dir: Path, skill_id: str) -> Path:
    case_path = run_dir / "cases" / f"{_safe_filename(skill_id)}.json"
    if case_path.is_file():
        return case_path

    cases_dir = run_dir / "cases"
    fallback_cases = sorted(cases_dir.glob("*.json")) if cases_dir.is_dir() else []
    if len(fallback_cases) == 1:
        return fallback_cases[0]

    raise ScanError("Scan succeeded but case output was missing.")


def _safe_filename(value: str) -> str:
    return value.replace("/", "__")


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "unknown"


def _persist_case_only(source_case_path: Path, final_case_path: Path) -> None:
    final_dir = final_case_path.parent
    final_dir.mkdir(parents=True, exist_ok=True)
    for child in final_dir.iterdir():
        if child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child)
    shutil.copy2(source_case_path, final_case_path)
