from __future__ import annotations

import re
from pathlib import Path

from ..models import EvidenceItem, SkillArtifact
from ..skill_structure import FRONTMATTER_RE, extract_frontmatter_and_body, parse_frontmatter


REFERENCE_PATTERN = re.compile(
    r"`(?P<code>[^`]+)`|\[(?P<label>[^\]]+)\]\((?P<link>[^)]+)\)"
)

FENCE_PATTERN = re.compile(r"^\s*```")


ATOMIC_DECLARATION_RULES = (
    ("R1", "读取当前用户输入", (r"\binput\b", r"\bprompt\b"), "medium"),
    ("R2", "读取当前会话历史", (r"chat history", r"previous turns", r"conversation history", r"message history"), "high"),
    ("R4", "读取会话附件", (r"\battachment\b", r"file input", r"uploaded file"), "high"),
    ("R5", "读取本地 repo 文件", (r"read project files", r"read local references", r"read files", r"project files"), "high"),
    ("R7", "读取知识库或文档库", (r"knowledge base", r"internal docs", r"document library", r"\breferences\b"), "medium"),
    ("R9", "批量枚举文件或资源", (r"search files", r"list files", r"enumerate", r"scan all"), "medium"),
    ("W1", "访问公开网页", (r"browse public webpages", r"public webpages", r"public web", r"\bbrowse the web\b"), "high"),
    ("W2", "调用外部公开 API", (r"\bapi\b", r"remote endpoint", r"fetch api", r"public api"), "high"),
    ("Q1", "只读查询或搜索", (r"\bsearch documentation\b", r"\bsearch\b", r"\bquery\b", r"\bfind\b"), "medium"),
    ("Q4", "自动推荐或判定", (r"\brecommend\b", r"\bsuggest\b", r"\bclassify\b", r"\bprioriti"), "medium"),
    ("G1", "生成文本建议", (r"source-backed answers", r"generate .*summary", r"\bsummar", r"\banalysis\b"), "medium"),
    ("G2", "生成结构化草稿", (r"\bdraft\b", r"pre-fill", r"prefill", r"pr description"), "high"),
    ("G4", "写本地项目文件", (r"edit repo", r"modify files", r"update project files"), "high"),
    ("O1", "创建外部草稿", (r"create draft", r"save draft"), "medium"),
    ("O2", "外部单对象写入", (r"update one", r"write after confirmation", r"single write"), "medium"),
    ("O3", "外部多对象批量写入", (r"\bbatch\b", r"\bbulk\b", r"auto-apply"), "medium"),
    ("O5", "自动外发", (r"send automatically", r"publish automatically", r"post automatically"), "medium"),
    ("A2", "需确认后执行", (r"after user confirmation", r"after approval", r"wait for confirmation"), "high"),
    ("A3", "定时调度", (r"every hour", r"daily", r"scheduled", r"\bcron\b"), "high"),
    ("A4", "事件触发", (r"on change", r"webhook", r"on event"), "medium"),
    ("A5", "持续监控", (r"\bmonitor\b", r"\bwatch\b", r"\bpoll\b"), "high"),
    ("A6", "触发后自动动作", (r"trigger alerts", r"automatically write", r"directly execute"), "medium"),
    ("I2", "跨系统身份代理", (r"\bconnector\b", r"desktop app integration", r"authorized identity"), "medium"),
)

CONTROL_DECLARATION_RULES = (
    ("C1", "只读约束", (r"\breadonly\b", r"read only", r"gather public information only"), "high"),
    ("C2", "范围限制", (r"local references", r"project files only", r"public webpages"), "medium"),
    ("C3", "显式确认", (r"after user confirmation", r"after approval", r"wait for confirmation"), "high"),
    ("C4", "预览或回显", (r"\bpreview\b", r"\bdiff\b", r"show changes"), "medium"),
    ("C5", "dry-run", (r"dry-run", r"dry run"), "medium"),
    ("C6", "回滚或幂等", (r"\brollback\b", r"\bidempotent\b"), "medium"),
    ("C7", "白名单", (r"\bwhitelist\b", r"\ballowlist\b", r"approved domains"), "medium"),
    ("C8", "脱敏", (r"\bredact\b", r"mask sensitive", r"\bdesensiti"), "medium"),
    ("C9", "审计日志", (r"audit log", r"access log", r"retain logs"), "medium"),
    ("C10", "kill switch", (r"kill switch", r"pause automation", r"stop switch"), "medium"),
    ("C11", "频率或规模限制", (r"rate limit", r"batch cap", r"retry cap"), "medium"),
    ("C12", "高敏禁外连", (r"no network", r"disable network", r"offline only"), "medium"),
)

NEGATIVE_DECLARATION_RULES = {
    "R2": (r"story about one session", r"one-off project context"),
    "W2": (r"api urls", r"json api", r"ledger api", r"admin api"),
    "X1": (r"```bash", r"\bbash example\b"),
    "X2": (r"```python", r"```node"),
    "I2": (r"--token", r"\btoken\b"),
}


def extract_declaration_evidence(skill: SkillArtifact) -> list[EvidenceItem]:
    skill_md = skill.root_path / "SKILL.md"
    skill_root_resolved = skill.root_path.resolve()
    if not skill_md.exists():
        return []
    skill_text = _safe_read_text(skill_md)
    if skill_text is None:
        return []

    frontmatter, body = extract_frontmatter_and_body(skill_text)
    body_start_line = _body_start_line_number(skill_text)
    frontmatter_map = parse_frontmatter(frontmatter) if frontmatter else {}
    evidence: list[EvidenceItem] = []

    for key, value in frontmatter_map.items():
        evidence.extend(
            _scan_text_for_declaration(
                text=f"{key}: {value}",
                source_path=skill_md.relative_to(skill.root_path).as_posix(),
                source_kind="skill_md_frontmatter",
                source_role="primary_declaration",
                support_reference_mode="direct",
            )
        )
    evidence.extend(
        _scan_text_for_declaration(
            text=body,
            source_path=skill_md.relative_to(skill.root_path).as_posix(),
            source_kind="skill_md_body",
            source_role="primary_declaration",
            support_reference_mode="direct",
            base_line_number=body_start_line,
        )
    )

    referenced_files = _extract_referenced_support_files(skill.root_path, body)
    for support_file in referenced_files:
        support_text = _safe_read_text(support_file)
        if support_text is None:
            continue
        evidence.extend(
            _scan_text_for_declaration(
                text=support_text,
                source_path=support_file.relative_to(skill_root_resolved).as_posix(),
                source_kind="support_file",
                source_role="referenced_supporting_material",
                support_reference_mode="referenced_by_skill_md",
            )
        )
    return evidence


def _extract_referenced_support_files(skill_root: Path, body: str) -> list[Path]:
    resolved_root = skill_root.resolve()
    files: set[Path] = set()
    body_without_fences = _strip_fenced_code_blocks(body)
    for match in REFERENCE_PATTERN.finditer(body_without_fences):
        reference = (match.group("code") or match.group("link") or "").strip()
        if not _is_supported_relative_reference(reference):
            continue
        try:
            candidate = (resolved_root / reference).resolve()
            candidate.relative_to(resolved_root)
            if candidate.is_file():
                files.add(candidate)
        except (OSError, ValueError):
            continue
    return sorted(files)


def _strip_fenced_code_blocks(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


def _is_supported_relative_reference(reference: str) -> bool:
    if not reference:
        return False
    if "\n" in reference or "\r" in reference:
        return False
    if len(reference) > 240:
        return False
    if reference.startswith(("http://", "https://", "#", "/")):
        return False
    if reference.endswith("/"):
        return False
    return "/" in reference or "." in Path(reference).name


def _scan_text_for_declaration(
    text: str,
    source_path: str,
    source_kind: str,
    source_role: str,
    support_reference_mode: str,
    base_line_number: int = 1,
) -> list[EvidenceItem]:
    lines = text.splitlines() or [text]
    evidence: list[EvidenceItem] = []
    in_fence = False
    for index, line in enumerate(lines, start=1):
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
        lowered = line.lower()
        if not line.strip():
            continue
        evidence.extend(
            _match_rule_set(
                ATOMIC_DECLARATION_RULES,
                "atomic_capability",
                lowered,
                base_line_number + index - 1,
                lines,
                base_line_number,
                source_path,
                source_kind,
                source_role,
                support_reference_mode,
                in_fence=in_fence,
            )
        )
        evidence.extend(
            _match_rule_set(
                CONTROL_DECLARATION_RULES,
                "control_semantic",
                lowered,
                base_line_number + index - 1,
                lines,
                base_line_number,
                source_path,
                source_kind,
                source_role,
                support_reference_mode,
                in_fence=in_fence,
            )
        )
    return evidence


def _match_rule_set(
    rules: tuple[tuple[str, str, tuple[str, ...], str], ...],
    subject_type: str,
    lowered: str,
    line_number: int,
    lines: list[str],
    base_line_number: int,
    source_path: str,
    source_kind: str,
    source_role: str,
    support_reference_mode: str,
    *,
    in_fence: bool,
) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for subject_id, subject_name, patterns, confidence in rules:
        matched_pattern = next((pattern for pattern in patterns if re.search(pattern, lowered)), None)
        if not matched_pattern:
            continue
        excluded_by_rule = _excluded_declaration_rule(subject_id, lowered, in_fence=in_fence)
        if excluded_by_rule:
            continue
        matched_text, line_start, line_end = _build_context_excerpt(lines, line_number, base_line_number=base_line_number)
        evidence.append(
            EvidenceItem(
                category_id=subject_id,
                category_name=subject_name,
                source_path=source_path,
                layer="declaration",
                evidence_type="text_match",
                matched_text=matched_text,
                line_start=line_start,
                line_end=line_end,
                confidence=confidence,
                rule_id=f"decl.{subject_type}.{subject_id.lower()}",
                source_kind=source_kind,
                source_role=source_role,
                support_reference_mode=support_reference_mode,
                subject_type=subject_type,
                matched_pattern=matched_pattern,
                evidence_strength="strong" if confidence == "high" else "medium",
            )
        )
    return evidence


def _build_context_excerpt(
    lines: list[str],
    center_line_number: int,
    radius: int = 1,
    *,
    base_line_number: int = 1,
) -> tuple[str, int, int]:
    relative_center = center_line_number - base_line_number + 1
    start_index = max(0, relative_center - 1 - radius)
    end_index = min(len(lines), relative_center + radius)
    excerpt = "\n".join(lines[start_index:end_index]).strip()[:400]
    return excerpt, base_line_number + start_index, base_line_number + end_index - 1


def _excluded_declaration_rule(subject_id: str, lowered: str, *, in_fence: bool) -> str | None:
    if in_fence and subject_id in {"X1", "X2"}:
        return "fenced_code_block"
    for pattern in NEGATIVE_DECLARATION_RULES.get(subject_id, ()):
        if re.search(pattern, lowered):
            return "negative_text_guard"
    return None


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _body_start_line_number(skill_text: str) -> int:
    match = FRONTMATTER_RE.search(skill_text)
    if not match:
        return 1
    return skill_text[: match.end()].count("\n") + 1
