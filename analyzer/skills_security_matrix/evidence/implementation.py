from __future__ import annotations

import re
from pathlib import Path

from ..models import EvidenceItem, SkillArtifact


ATOMIC_IMPLEMENTATION_RULES = (
    ("R5", "读取本地 repo 文件", (r"\.read_text\(", r"\.read_bytes\(", r"\bopen\("), "medium"),
    ("R9", "批量枚举文件或资源", (r"\brg\b", r"\bglob\(", r"\brglob\(", r"\biterdir\("), "medium"),
    ("W1", "访问公开网页", (r"requests\.(get|post|put|delete)\(", r"httpx\.", r"urllib\.request", r"\bfetch\("), "high"),
    ("W2", "调用外部公开 API", (r"requests\.(get|post|put|delete)\(", r"client\.(get|post|put|delete)\(", r"axios\."), "high"),
    ("Q1", "只读查询或搜索", (r"\bsearch\(", r"\bquery\(", r"\bfilter\(", r"\blist_[a-z0-9_]+\("), "medium"),
    ("X1", "执行 shell 命令", (r"subprocess\.", r"os\.system\(", r"pty", r"\bexec_command\("), "high"),
    ("X2", "执行解释器代码", (r"\beval\(", r"\bexec\(", r"python\s+-c", r"node\s+-e"), "high"),
    ("X3", "执行容器任务", (r"\bdocker\b", r"\bcontainer\b", r"\bkubectl\b"), "high"),
    ("X4", "安装依赖或拉取包", (r"\bpip install\b", r"\bnpm install\b", r"\bcargo install\b", r"\bapt-get install\b"), "high"),
    ("X7", "访问环境变量或凭证", (r"os\.environ", r"os\.getenv\(", r"getpass", r"credential"), "high"),
    ("X8", "调用外部二进制或本地工具", (r"\bgit\b", r"\bcurl\b", r"\bgh\b", r"\bcli\b"), "medium"),
    ("G1", "生成文本建议", (r"\bsummar", r"\brender\(", r"\btemplate\b", r"markdown"), "medium"),
    ("G2", "生成结构化草稿", (r"\bdraft\b", r"\bproposal\b", r"\bpreview\b"), "medium"),
    ("G3", "写本地临时文件", (r"write_text\(", r"\bopen\(", r"\btempfile\b"), "medium"),
    ("G4", "写本地项目文件", (r"apply_patch", r"write_text\(", r"\bopen\("), "medium"),
    ("G5", "批量本地写文件", (r"for .*write_text\(", r"while .*write_text\(", r"batch"), "medium"),
    ("A3", "定时调度", (r"\bcron\b", r"\bschedule\.", r"apscheduler", r"every\("), "high"),
    ("A4", "事件触发", (r"\bwebhook\b", r"on_message", r"on_change", r"listener"), "medium"),
    ("A5", "持续监控", (r"while true", r"\bwatch\(", r"\bpoll\(", r"\bmonitor\b"), "high"),
    ("A7", "自动重试或循环执行", (r"\bretry\b", r"\bbackoff\b", r"while true"), "medium"),
    ("I2", "跨系统身份代理", (r"\bconnector\b", r"\boauth\b", r"\bsignin\b"), "medium"),
    ("I4", "凭证注入到外部调用", (r"authorization", r"bearer ", r"api[_-]?key", r"token="), "high"),
)

CONTROL_IMPLEMENTATION_RULES = (
    ("C3", "显式确认", (r"\bconfirm\b", r"\bapproval\b", r"wait for confirmation"), "high"),
    ("C4", "预览或回显", (r"\bpreview\b", r"\bdiff\b", r"show changes"), "medium"),
    ("C5", "dry-run", (r"dry[_-]?run",), "medium"),
    ("C6", "回滚或幂等", (r"\brollback\b", r"\bidempotent\b"), "medium"),
    ("C7", "白名单", (r"\bwhitelist\b", r"\ballowlist\b", r"approved domains"), "medium"),
    ("C8", "脱敏", (r"\bredact\b", r"mask sensitive", r"\bsanitize\b"), "medium"),
    ("C9", "审计日志", (r"audit", r"logger", r"\blog\b"), "low"),
    ("C10", "kill switch", (r"kill switch", r"stop flag", r"enabled"), "medium"),
    ("C11", "频率或规模限制", (r"rate limit", r"batch cap", r"max batch", r"retry cap"), "medium"),
    ("C12", "高敏禁外连", (r"offline only", r"disable network", r"no network"), "medium"),
)


def extract_implementation_evidence(skill: SkillArtifact) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for file_path in skill.source_files:
        if file_path.name in {"SKILL.md", "README.md"}:
            continue
        text = _safe_read_text(file_path)
        if text is None:
            continue
        relative_path = file_path.relative_to(skill.root_path).as_posix()
        lines = text.splitlines()
        for line_number, line in enumerate(lines, start=1):
            lowered = line.lower()
            if not lowered.strip():
                continue
            evidence.extend(
                _match_rule_set(
                    ATOMIC_IMPLEMENTATION_RULES,
                    "atomic_capability",
                    lowered,
                    line,
                    line_number,
                    relative_path,
                    lines,
                )
            )
            evidence.extend(
                _match_rule_set(
                    CONTROL_IMPLEMENTATION_RULES,
                    "control_semantic",
                    lowered,
                    line,
                    line_number,
                    relative_path,
                    lines,
                )
            )
        evidence.extend(_derive_loop_scheduler_evidence(relative_path, lines))
        evidence.extend(_derive_read_only_control(relative_path, lines, existing=evidence))
    return _dedupe_evidence(evidence)


def _match_rule_set(
    rules: tuple[tuple[str, str, tuple[str, ...], str], ...],
    subject_type: str,
    lowered: str,
    raw_line: str,
    line_number: int,
    source_path: str,
    lines: list[str],
) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for subject_id, subject_name, patterns, confidence in rules:
        matched_pattern = next((pattern for pattern in patterns if re.search(pattern, lowered)), None)
        if not matched_pattern:
            continue
        excluded_by_rule = _excluded_implementation_rule(subject_id, lowered, raw_line, lines, line_number)
        if excluded_by_rule:
            continue
        matched_text, line_start, line_end = _build_context_excerpt(lines, line_number)
        evidence.append(
            EvidenceItem(
                category_id=subject_id,
                category_name=subject_name,
                source_path=source_path,
                layer="implementation",
                evidence_type="static_scan",
                matched_text=matched_text,
                line_start=line_start,
                line_end=line_end,
                confidence=confidence,
                rule_id=f"impl.{subject_type}.{subject_id.lower()}",
                source_kind="source_file",
                source_role="implementation_artifact",
                subject_type=subject_type,
                matched_pattern=matched_pattern,
                evidence_strength="strong" if confidence == "high" else "medium",
            )
        )
    return evidence


def _excluded_implementation_rule(
    subject_id: str,
    lowered: str,
    raw_line: str,
    lines: list[str],
    line_number: int,
) -> str | None:
    stripped = raw_line.strip()
    if stripped.startswith("#"):
        return "comment_only"
    if subject_id in {"W1", "W2"} and _looks_like_plain_url_text(stripped):
        return "plain_url_text"
    if subject_id in {"X1", "X2"} and ("```" in stripped or stripped.startswith(("bash ", "python "))) and not _is_actual_exec_context(lowered):
        return "command_example"
    if subject_id == "I4" and "token" in lowered and not any(term in lowered for term in ("authorization", "bearer", "api_key", "api-key")):
        return "token_text_only"
    if subject_id == "A3" and any(term in lowered for term in ("sleep(", "settimeout(")):
        return "sleep_without_scheduler"
    if subject_id in {"G3", "G4"} and "open(" in lowered and not _is_write_open(lowered):
        return "read_open"
    if subject_id == "G5" and "batch" not in lowered and "write_text" not in lowered:
        return "non_batch_write"
    if subject_id == "A7" and "while true" in lowered and not any(term in "\n".join(lines[max(0, line_number - 3): line_number + 2]).lower() for term in ("retry", "backoff")):
        return "loop_without_retry_signal"
    return None


def _build_context_excerpt(lines: list[str], center_line_number: int, radius: int = 1) -> tuple[str, int, int]:
    start_index = max(0, center_line_number - 1 - radius)
    end_index = min(len(lines), center_line_number + radius)
    excerpt = "\n".join(lines[start_index:end_index]).strip()[:400]
    return excerpt, start_index + 1, end_index


def _derive_loop_scheduler_evidence(source_path: str, lines: list[str]) -> list[EvidenceItem]:
    joined = "\n".join(lines).lower()
    if "while true" not in joined or "sleep(" not in joined:
        return []
    if not any(term in joined for term in ("requests.", "httpx.", "urllib.", "fetch(")):
        return []
    return [
        EvidenceItem(
            category_id="A3",
            category_name="定时调度",
            source_path=source_path,
            layer="implementation",
            evidence_type="structural_inference",
            matched_text="long-running loop with network polling and sleep interval",
            line_start=1,
            line_end=len(lines),
            confidence="high",
            rule_id="impl.atomic_capability.a3.loop_schedule",
            source_kind="source_file",
            source_role="implementation_artifact",
            subject_type="atomic_capability",
            matched_pattern="while true + sleep + network call",
            evidence_strength="strong",
        )
    ]


def _derive_read_only_control(source_path: str, lines: list[str], existing: list[EvidenceItem]) -> list[EvidenceItem]:
    has_atomic_read = any(item.subject_type == "atomic_capability" and item.category_id in {"R5", "R9", "W1", "W2", "Q1"} for item in existing)
    has_write = any(item.subject_type == "atomic_capability" and item.category_id in {"G3", "G4", "G5", "O2", "O3", "O4", "O5"} for item in existing)
    if not has_atomic_read or has_write:
        return []
    return [
        EvidenceItem(
            category_id="C1",
            category_name="只读约束",
            source_path=source_path,
            layer="implementation",
            evidence_type="derived_control",
            matched_text="read-oriented implementation without write sinks",
            line_start=1,
            line_end=len(lines),
            confidence="medium",
            rule_id="impl.control_semantic.c1.derived_read_only",
            source_kind="source_file",
            source_role="implementation_artifact",
            subject_type="control_semantic",
            matched_pattern="derived read-only profile",
            evidence_strength="medium",
        )
    ]


def _is_write_open(lowered: str) -> bool:
    return bool(re.search(r"open\([^)]*,\s*[\"'](?:w|a|x|\+)", lowered))


def _looks_like_plain_url_text(stripped: str) -> bool:
    return stripped.startswith(("http://", "https://")) or stripped.startswith(("'", '"')) and "http" in stripped


def _is_actual_exec_context(lowered: str) -> bool:
    return any(term in lowered for term in ("subprocess", "os.system", "exec_command", "spawn"))


def _dedupe_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    unique: dict[str, EvidenceItem] = {}
    for item in items:
        unique.setdefault(item.evidence_fingerprint, item)
    return list(unique.values())


def _safe_read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
