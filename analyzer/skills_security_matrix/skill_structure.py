from __future__ import annotations

import re
from pathlib import Path

from .models import SkillStructureProfile


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def detect_structure(skill_dir: Path) -> SkillStructureProfile:
    top_level_files = sorted(path.name for path in skill_dir.iterdir() if path.is_file())
    top_level_dirs = sorted(path.name for path in skill_dir.iterdir() if path.is_dir())
    skill_md = skill_dir / "SKILL.md"
    has_frontmatter = False
    if skill_md.exists():
        try:
            has_frontmatter = bool(FRONTMATTER_RE.search(skill_md.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            has_frontmatter = False
    return SkillStructureProfile(
        has_skill_md=skill_md.exists(),
        has_frontmatter=has_frontmatter,
        has_references_dir=(skill_dir / "references").is_dir(),
        has_scripts_dir=(skill_dir / "scripts").is_dir() or (skill_dir / "dist" / "scripts").is_dir(),
        has_assets_dir=(skill_dir / "assets").is_dir(),
        has_templates_dir=(skill_dir / "templates").is_dir(),
        top_level_files=top_level_files,
        top_level_dirs=top_level_dirs,
    )


def extract_frontmatter_and_body(text: str) -> tuple[str, str]:
    match = FRONTMATTER_RE.search(text)
    if not match:
        return "", text
    return match.group(1), text[match.end() :]


def parse_frontmatter(frontmatter: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    for line in frontmatter.splitlines():
        if not line.strip():
            if current_key:
                current_lines.append("")
            continue
        if not line.startswith((" ", "\t")) and ":" in line:
            if current_key is not None:
                parsed[current_key] = "\n".join(current_lines).strip()
            key, value = line.split(":", 1)
            current_key = key.strip()
            current_lines = [value.strip()]
            continue
        if current_key is not None:
            current_lines.append(line.rstrip())
    if current_key is not None:
        parsed[current_key] = "\n".join(current_lines).strip()
    return parsed
