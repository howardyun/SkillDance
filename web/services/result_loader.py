from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

STATUS_META = {
    "implementation_only_high_risk": {
        "label": "检测到高风险代码模式",
        "tone": "danger",
    },
    "declared_more_than_implemented": {
        "label": "声明能力未完全实现",
        "tone": "warn",
    },
    "declared_and_implemented_aligned": {
        "label": "声明与实现一致",
        "tone": "ok",
    },
    "insufficient_declaration_evidence": {
        "label": "声明证据不足",
        "tone": "muted",
    },
    "insufficient_implementation_evidence": {
        "label": "实现证据不足",
        "tone": "muted",
    },
}

FILTER_BUCKET_META = {
    "implementation_only_high_risk": "risk",
    "declared_more_than_implemented": "warning",
    "declared_and_implemented_aligned": "safe",
    "insufficient_declaration_evidence": "warning",
    "insufficient_implementation_evidence": "warning",
}

RISK_LABELS = {
    "S": "S 身份伪造",
    "Spoofing": "S 身份伪造",
    "T": "T 篡改",
    "Tampering": "T 篡改",
    "R": "R 抵赖",
    "Repudiation": "R 抵赖",
    "I": "I 信息泄露",
    "Information Disclosure": "I 信息泄露",
    "D": "D 拒绝服务",
    "Denial of Service": "D 拒绝服务",
    "E": "E 权限提升",
    "Elevation of Privilege": "E 权限提升",
}


def load_case_summary(case_json_path: Path) -> dict[str, Any]:
    payload = json.loads(case_json_path.read_text(encoding="utf-8"))
    detail_index = _build_detail_index(payload)
    categories = [_normalize_category(item, detail_index) for item in payload.get("category_discrepancies", [])]
    category_status_counts = Counter(item.get("status", "unknown") for item in categories)
    category_filter_counts = Counter(item.get("filter_bucket", "warning") for item in categories)
    skill_status = payload.get("skill_level_discrepancy", "unknown")
    skill_meta = STATUS_META.get(skill_status, {"label": skill_status, "tone": "muted"})

    return {
        "skill_id": payload.get("skill_id", ""),
        "root_path": payload.get("root_path", ""),
        "skill_level_discrepancy": skill_status,
        "skill_level_label": skill_meta["label"],
        "skill_level_tone": skill_meta["tone"],
        "category_count": len(categories),
        "category_status_counts": dict(category_status_counts),
        "category_filter_counts": {
            "risk": int(category_filter_counts.get("risk", 0)),
            "warning": int(category_filter_counts.get("warning", 0)),
            "safe": int(category_filter_counts.get("safe", 0)),
        },
        "category_discrepancies": categories,
        "risk_mappings": [_normalize_risk_mapping(item) for item in payload.get("risk_mappings", [])],
        "errors": payload.get("errors", []),
    }


def _normalize_category(raw: dict[str, Any], detail_index: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    status = raw.get("status", "unknown")
    meta = STATUS_META.get(status, {"label": status, "tone": "muted"})
    category_id = raw.get("category_id", "")
    filter_bucket = FILTER_BUCKET_META.get(status, "warning")
    declaration_details = _merge_detail_lists(
        raw.get("declaration_details", []),
        detail_index.get(category_id, {}).get("declaration", []),
    )
    implementation_details = _merge_detail_lists(
        raw.get("implementation_details", []),
        detail_index.get(category_id, {}).get("implementation", []),
    )
    return {
        "category_id": category_id,
        "category_name": raw.get("category_name") or category_id,
        "status": status,
        "status_label": meta["label"],
        "status_tone": meta["tone"],
        "filter_bucket": filter_bucket,
        "declaration_present": bool(raw.get("declaration_present")),
        "implementation_present": bool(raw.get("implementation_present")),
        "mismatch_ids": raw.get("mismatch_ids", []),
        "risks": [_translate_risk(item) for item in raw.get("risks", [])],
        "controls": raw.get("controls", []),
        "declaration_atomic_ids": raw.get("declaration_atomic_ids", []),
        "implementation_atomic_ids": raw.get("implementation_atomic_ids", []),
        "declaration_control_ids": raw.get("declaration_control_ids", []),
        "implementation_control_ids": raw.get("implementation_control_ids", []),
        "declaration_details": declaration_details,
        "implementation_details": implementation_details,
    }


def _build_detail_index(payload: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    index: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for layer in ("declaration", "implementation"):
        for bucket in ("atomic", "control"):
            for raw in payload.get(f"{layer}_{bucket}_decisions", []):
                detail = _normalize_detail(raw, bucket)
                for category_id in raw.get("mapped_category_ids", []):
                    index.setdefault(category_id, {}).setdefault(layer, []).append(detail)
    return index


def _normalize_detail(raw: dict[str, Any], kind: str) -> dict[str, Any]:
    detail_id = raw.get("atomic_id") if kind == "atomic" else raw.get("control_id")
    detail_name = raw.get("atomic_name") if kind == "atomic" else raw.get("control_name")
    return {
        "kind": kind,
        "id": detail_id or "",
        "name": detail_name or detail_id or "",
        "confidence": raw.get("confidence", "unknown"),
        "evidence": [_normalize_evidence(item) for item in raw.get("supporting_evidence", [])],
    }


def _normalize_evidence(raw: dict[str, Any]) -> dict[str, Any]:
    line_start = raw.get("line_start")
    line_end = raw.get("line_end")
    lines = ""
    if line_start and line_end:
        lines = f"L{line_start}" if line_start == line_end else f"L{line_start}-{line_end}"
    elif line_start:
        lines = f"L{line_start}"

    return {
        "source_path": raw.get("source_path", ""),
        "lines": lines,
        "matched_text": raw.get("matched_text", ""),
    }


def _translate_risk(risk: Any) -> Any:
    if isinstance(risk, str):
        return RISK_LABELS.get(risk, risk)
    return risk


def _normalize_risk_mapping(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    normalized = dict(raw)
    if "risk" in normalized:
        normalized["risk"] = _translate_risk(normalized["risk"])
    if isinstance(normalized.get("risks"), list):
        normalized["risks"] = [_translate_risk(item) for item in normalized["risks"]]
    return normalized


def _merge_detail_lists(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for current in lists:
        for item in current or []:
            normalized = _normalize_existing_detail(item)
            marker = (normalized.get("kind", ""), normalized.get("id", ""))
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(normalized)

    return merged


def _normalize_existing_detail(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": raw.get("kind", ""),
        "id": raw.get("id", ""),
        "name": raw.get("name") or raw.get("id", ""),
        "confidence": raw.get("confidence", "unknown"),
        "evidence": [
            {
                "source_path": item.get("source_path", ""),
                "lines": item.get("lines", ""),
                "matched_text": item.get("matched_text", ""),
            }
            for item in raw.get("evidence", [])
        ],
    }
