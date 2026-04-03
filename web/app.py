from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request

from .services.repo_fetcher import RepositoryError, clone_or_refresh_repo, parse_github_repo
from .services.result_loader import load_case_summary
from .services.scan_runner import ScanError, run_single_skill_scan
from .services.skill_locator import discover_skill_candidates, find_skill_matches


def create_app(config: dict | None = None) -> Flask:
    project_root = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(project_root / "web" / "templates"),
        static_folder=str(project_root / "web" / "static"),
    )
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev"),
        PROJECT_ROOT=project_root,
        REPOS_WORKSPACE=project_root / "web" / "workspaces" / "repos",
        RUNS_WORKSPACE=project_root / "web" / "workspaces" / "runs",
        PYTHON_BIN=sys.executable,
    )
    if config:
        app.config.update(config)

    @app.get("/")
    def index():
        recent_scans = _load_recent_scans(Path(app.config["RUNS_WORKSPACE"]))
        return render_template(
            "index.html",
            form_data={"repo_url": "", "skill_name": ""},
            recent_scans=recent_scans,
            error_title=None,
            error_message=None,
        )

    @app.get("/history/<repo_key>/<skill_key>")
    def history_result(repo_key: str, skill_key: str):
        if not (_is_safe_segment(repo_key) and _is_safe_segment(skill_key)):
            return _render_result_error(
                repo_url="",
                skill_name=skill_key,
                error_type="invalid_history_path",
                error_message="Invalid history path.",
            ), 400

        runs_workspace = Path(app.config["RUNS_WORKSPACE"])
        run_dir = runs_workspace / repo_key / skill_key
        case_json_path = run_dir / f"{skill_key}.json"
        if not case_json_path.is_file():
            candidates = sorted(run_dir.glob("*.json")) if run_dir.is_dir() else []
            if len(candidates) != 1:
                return _render_result_error(
                    repo_url=_guess_repo_url(repo_key),
                    skill_name=skill_key,
                    error_type="history_not_found",
                    error_message="Cached scan result is missing. Please run a fresh scan.",
                ), 404
            case_json_path = candidates[0]

        try:
            summary = load_case_summary(case_json_path)
        except (OSError, ValueError) as exc:
            return _render_result_error(
                repo_url=_guess_repo_url(repo_key),
                skill_name=skill_key,
                error_type="history_load_failed",
                error_message=str(exc),
            ), 500

        repo_path = Path(app.config["REPOS_WORKSPACE"]) / repo_key
        summary_root = Path(summary.get("root_path") or skill_key)
        try:
            relative_path = str(summary_root.relative_to(repo_path.resolve()))
        except ValueError:
            relative_path = str(summary_root)
        repo_url = _guess_repo_url(repo_key)
        return render_template(
            "result.html",
            repo_url=repo_url,
            skill_name=skill_key,
            repo_path=repo_path,
            relative_path=relative_path,
            summary=summary,
            scan_meta={
                "run_id": f"{repo_key}/{skill_key}",
                "run_dir": str(run_dir),
                "case_json_path": str(case_json_path),
                "command": "cached-result (skip clone & scan)",
            },
            error_type=None,
            error_message=None,
        )

    @app.post("/scan")
    def scan():
        repo_url = (request.form.get("repo_url") or "").strip()
        skill_name = (request.form.get("skill_name") or "").strip()
        form_data = {"repo_url": repo_url, "skill_name": skill_name}

        try:
            repo_ref = parse_github_repo(repo_url)
        except RepositoryError as exc:
            return _render_index_error(
                form_data,
                "invalid_repo_url",
                str(exc),
                recent_scans=_load_recent_scans(Path(app.config["RUNS_WORKSPACE"])),
            ), 400

        try:
            repo_path = clone_or_refresh_repo(repo_ref, Path(app.config["REPOS_WORKSPACE"]))
        except RepositoryError as exc:
            return _render_index_error(
                form_data,
                "repo_download_failed",
                str(exc),
                recent_scans=_load_recent_scans(Path(app.config["RUNS_WORKSPACE"])),
            ), 502

        candidates = discover_skill_candidates(repo_path)
        if not candidates:
            return _render_result_error(
                repo_url=repo_url,
                skill_name=skill_name,
                error_type="no_skills_found",
                error_message="No SKILL.md was found in this repository.",
            )

        if not skill_name:
            return render_template(
                "choose_skill.html",
                repo_url=repo_url,
                skill_name=skill_name,
                message="Skill name was empty. Please choose one discovered skill.",
                candidates=candidates,
            )

        matches = find_skill_matches(skill_name, candidates)
        if len(matches) != 1:
            message = (
                "No exact skill match found. Please choose from discovered skills."
                if len(matches) == 0
                else "Multiple matches found. Please choose one skill."
            )
            return render_template(
                "choose_skill.html",
                repo_url=repo_url,
                skill_name=skill_name,
                message=message,
                candidates=candidates,
            )

        return _run_and_render_result(repo_url=repo_url, skill_name=skill_name, repo_path=repo_path, relative_path=matches[0].relative_path)

    @app.post("/scan/select-skill")
    def select_skill():
        repo_url = (request.form.get("repo_url") or "").strip()
        skill_name = (request.form.get("skill_name") or "").strip()
        relative_path = (request.form.get("relative_path") or "").strip()
        form_data = {"repo_url": repo_url, "skill_name": skill_name}

        if not relative_path:
            return _render_index_error(
                form_data,
                "invalid_selection",
                "You must choose a discovered skill.",
                recent_scans=_load_recent_scans(Path(app.config["RUNS_WORKSPACE"])),
            ), 400

        try:
            repo_ref = parse_github_repo(repo_url)
            repo_path = clone_or_refresh_repo(repo_ref, Path(app.config["REPOS_WORKSPACE"]))
        except RepositoryError as exc:
            return _render_index_error(
                form_data,
                "repo_download_failed",
                str(exc),
                recent_scans=_load_recent_scans(Path(app.config["RUNS_WORKSPACE"])),
            ), 502

        selected_skill_dir = (repo_path / relative_path).resolve()
        try:
            selected_skill_dir.relative_to(repo_path.resolve())
        except ValueError:
            return _render_index_error(
                form_data,
                "invalid_selection",
                "Invalid skill path selection.",
                recent_scans=_load_recent_scans(Path(app.config["RUNS_WORKSPACE"])),
            ), 400

        if not (selected_skill_dir / "SKILL.md").is_file():
            return _render_index_error(
                form_data,
                "invalid_selection",
                "Selected skill path does not contain SKILL.md anymore.",
                recent_scans=_load_recent_scans(Path(app.config["RUNS_WORKSPACE"])),
            ), 400

        return _run_and_render_result(
            repo_url=repo_url,
            skill_name=skill_name or selected_skill_dir.name,
            repo_path=repo_path,
            relative_path=relative_path,
        )

    def _run_and_render_result(*, repo_url: str, skill_name: str, repo_path: Path, relative_path: str):
        skill_dir = (repo_path / relative_path).resolve()
        try:
            run_result = run_single_skill_scan(
                project_root=Path(app.config["PROJECT_ROOT"]),
                skill_dir=skill_dir,
                runs_workspace=Path(app.config["RUNS_WORKSPACE"]),
                repo_key=repo_path.name,
                skill_key=skill_dir.name,
                python_bin=str(app.config["PYTHON_BIN"]),
            )
            summary = load_case_summary(run_result.case_json_path)
        except ScanError as exc:
            return _render_result_error(
                repo_url=repo_url,
                skill_name=skill_name,
                error_type="analysis_failed",
                error_message=str(exc),
            ), 500
        except OSError as exc:
            return _render_result_error(
                repo_url=repo_url,
                skill_name=skill_name,
                error_type="case_output_missing",
                error_message=str(exc),
            ), 500

        return render_template(
            "result.html",
            repo_url=repo_url,
            skill_name=skill_name,
            repo_path=repo_path,
            relative_path=relative_path,
            summary=summary,
            scan_meta={
                "run_id": run_result.run_id,
                "run_dir": str(run_result.run_dir),
                "case_json_path": str(run_result.case_json_path),
                "command": " ".join(run_result.command),
            },
            error_type=None,
            error_message=None,
        )

    return app


def _render_index_error(
    form_data: dict[str, str],
    error_type: str,
    error_message: str,
    recent_scans: list[dict[str, str | int]] | None = None,
):
    return render_template(
        "index.html",
        form_data=form_data,
        recent_scans=recent_scans or [],
        error_title=error_type,
        error_message=error_message,
    )


def _load_recent_scans(runs_workspace: Path, limit: int = 20) -> list[dict[str, str | int]]:
    if not runs_workspace.is_dir():
        return []

    records: list[tuple[float, dict[str, str | int]]] = []
    for case_path in runs_workspace.glob("*/*/*.json"):
        if not case_path.is_file():
            continue
        try:
            summary = load_case_summary(case_path)
        except (OSError, ValueError):
            continue

        mtime = case_path.stat().st_mtime
        item = {
            "repo_key": case_path.parent.parent.name,
            "skill_key": case_path.parent.name,
            "skill_id": str(summary.get("skill_id") or case_path.stem),
            "status_label": str(summary.get("skill_level_label") or "Unknown"),
            "status_tone": str(summary.get("skill_level_tone") or "muted"),
            "category_count": int(summary.get("category_count") or 0),
            "updated_at": _format_unix_ts(mtime),
            "history_path": f"/history/{case_path.parent.parent.name}/{case_path.parent.name}",
        }
        records.append((mtime, item))

    records.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in records[:limit]]


def _format_unix_ts(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _guess_repo_url(repo_key: str) -> str:
    if "__" not in repo_key:
        return repo_key
    owner, repo = repo_key.split("__", 1)
    return f"https://github.com/{owner}/{repo}"


def _is_safe_segment(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", value or ""))


def _render_result_error(*, repo_url: str, skill_name: str, error_type: str, error_message: str):
    return render_template(
        "result.html",
        repo_url=repo_url,
        skill_name=skill_name,
        repo_path=None,
        relative_path=None,
        summary=None,
        scan_meta=None,
        error_type=error_type,
        error_message=error_message,
    )


app = create_app()


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
