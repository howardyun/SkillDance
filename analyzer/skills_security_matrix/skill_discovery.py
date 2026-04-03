from __future__ import annotations

import os
from pathlib import Path

from .models import SkillArtifact
from .skill_structure import detect_structure


SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".sh",
    ".bash",
    ".zsh",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".md",
}

IGNORED_SCAN_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "vendor",
    "dist",
    "build",
    "target",
    "coverage",
}

# Bound per-skill scan cost so a few huge documentation-heavy skills cannot stall the batch.
MAX_ARTIFACT_FILES = 2000
MAX_SOURCE_FILES = 1000


def _build_artifact(path: Path, *, include_hidden: bool = False) -> SkillArtifact:
    file_paths: list[Path] = []
    source_files: list[Path] = []
    root = path.resolve()

    for current_root, dir_names, file_names in os.walk(root, topdown=True):
        if not include_hidden:
            dir_names[:] = [
                name for name in dir_names if not name.startswith(".") and name not in IGNORED_SCAN_DIR_NAMES
            ]
        else:
            dir_names[:] = [name for name in dir_names if name not in IGNORED_SCAN_DIR_NAMES]

        current_path = Path(current_root)
        for file_name in sorted(file_names):
            if not include_hidden and file_name.startswith("."):
                continue
            file_path = current_path / file_name
            try:
                if not file_path.is_file():
                    continue
            except OSError:
                continue

            file_paths.append(file_path)
            if file_path.suffix.lower() in SOURCE_SUFFIXES and len(source_files) < MAX_SOURCE_FILES:
                source_files.append(file_path)
            if len(file_paths) >= MAX_ARTIFACT_FILES:
                break

        if len(file_paths) >= MAX_ARTIFACT_FILES:
            break

    return SkillArtifact(
        skill_id=path.name,
        root_path=root,
        structure=detect_structure(path),
        file_paths=sorted(file_paths),
        source_files=sorted(source_files),
    )


def discover_skills(skills_dir: Path, include_hidden: bool = False, limit: int | None = None) -> list[SkillArtifact]:
    if (skills_dir / "SKILL.md").is_file():
        return [_build_artifact(skills_dir, include_hidden=include_hidden)]

    candidates = sorted(path for path in skills_dir.iterdir() if path.is_dir())
    artifacts: list[SkillArtifact] = []
    for path in candidates:
        if not include_hidden and path.name.startswith("."):
            continue
        artifacts.append(_build_artifact(path, include_hidden=include_hidden))
        if limit is not None and len(artifacts) >= limit:
            break
    return artifacts
