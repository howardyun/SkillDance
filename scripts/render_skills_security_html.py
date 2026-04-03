from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


STATUS_META = {
    "implementation_only_high_risk": {
        "label": "仅实现层命中（高风险）",
        "tone": "danger",
    },
    "declared_more_than_implemented": {
        "label": "申明多于实现",
        "tone": "warn",
    },
    "declared_and_implemented_aligned": {
        "label": "申明与实现一致",
        "tone": "ok",
    },
    "insufficient_declaration_evidence": {
        "label": "申明证据不足",
        "tone": "muted",
    },
    "insufficient_implementation_evidence": {
        "label": "实现证据不足",
        "tone": "muted",
    },
}

TONE_CLASS = {
    "danger": "tone-danger",
    "warn": "tone-warn",
    "ok": "tone-ok",
    "muted": "tone-muted",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render skills security matrix discrepancy results into a standalone HTML report."
    )
    parser.add_argument("input_path", help="Run directory, discrepancies.jsonl, or a single case JSON file.")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output HTML path. Defaults next to the input.",
    )
    parser.add_argument(
        "--title",
        default="Skills Security Matrix Report",
        help="Report title shown in the HTML page.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input_path).expanduser().resolve()
    bundle = load_bundle(input_path)
    html = render_html(bundle, report_title=args.title, input_path=input_path)
    output_path = determine_output_path(input_path, args.output)
    output_path.write_text(html, encoding="utf-8")
    print(f"HTML report written to: {output_path}")
    print(f"Skills included: {len(bundle['skills'])}")
    return 0


def determine_output_path(input_path: Path, output: str | None) -> Path:
    if output:
        return Path(output).expanduser().resolve()
    if input_path.is_dir():
        return input_path / "skills_security_report.html"
    if input_path.name.endswith(".jsonl"):
        return input_path.with_name(f"{input_path.stem}.html")
    return input_path.with_suffix(".html")


def load_bundle(input_path: Path) -> dict[str, Any]:
    if input_path.is_dir():
        return load_run_directory(input_path)
    if input_path.name.endswith(".jsonl"):
        return load_jsonl_only(input_path)
    if input_path.suffix == ".json":
        case_data = json.loads(input_path.read_text(encoding="utf-8"))
        return build_bundle_from_cases([case_data], source_label=str(input_path))
    raise ValueError(f"Unsupported input path: {input_path}")


def load_run_directory(run_dir: Path) -> dict[str, Any]:
    discrepancies_path = run_dir / "discrepancies.jsonl"
    cases_dir = run_dir / "cases"
    case_payloads: list[dict[str, Any]] = []
    if cases_dir.exists():
        for path in sorted(cases_dir.glob("*.json")):
            case_payloads.append(json.loads(path.read_text(encoding="utf-8")))
    if case_payloads:
        return build_bundle_from_cases(case_payloads, source_label=str(run_dir))
    if discrepancies_path.exists():
        return load_jsonl_only(discrepancies_path)
    raise FileNotFoundError(f"No cases/ directory or discrepancies.jsonl found in {run_dir}")


def load_jsonl_only(jsonl_path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    skills = []
    for record in records:
        skills.append(
            {
                "skill_id": record.get("skill_id", "unknown"),
                "root_path": "",
                "skill_level_discrepancy": record.get(
                    "skill_level_discrepancy", "insufficient_implementation_evidence"
                ),
                "status_label": status_label(record.get("skill_level_discrepancy")),
                "status_tone": status_tone(record.get("skill_level_discrepancy")),
                "categories": [normalize_category_discrepancy(item) for item in record.get("category_discrepancies", [])],
                "errors": record.get("errors", []),
            }
        )
    return finalize_bundle(skills, source_label=str(jsonl_path))


def build_bundle_from_cases(case_payloads: list[dict[str, Any]], source_label: str) -> dict[str, Any]:
    skills = [normalize_case(case_data) for case_data in case_payloads]
    return finalize_bundle(skills, source_label=source_label)


def finalize_bundle(skills: list[dict[str, Any]], source_label: str) -> dict[str, Any]:
    level_counter = Counter(skill["skill_level_discrepancy"] for skill in skills)
    category_counter = Counter()
    for skill in skills:
        for category in skill["categories"]:
            category_counter[category["status"]] += 1
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_label": source_label,
        "skills": sorted(skills, key=skill_sort_key),
        "summary": {
            "skill_count": len(skills),
            "status_counts": dict(level_counter),
            "category_status_counts": dict(category_counter),
            "high_risk_skill_count": sum(
                1 for skill in skills if skill["skill_level_discrepancy"] == "implementation_only_high_risk"
            ),
        },
    }


def skill_sort_key(skill: dict[str, Any]) -> tuple[int, int, str]:
    severity = {
        "implementation_only_high_risk": 0,
        "declared_more_than_implemented": 1,
        "insufficient_declaration_evidence": 2,
        "insufficient_implementation_evidence": 3,
        "declared_and_implemented_aligned": 4,
    }
    discrepancy_weight = min((category_rank(item["status"]) for item in skill["categories"]), default=99)
    return (
        severity.get(skill["skill_level_discrepancy"], 98),
        discrepancy_weight,
        skill["skill_id"],
    )


def normalize_case(case_data: dict[str, Any]) -> dict[str, Any]:
    declaration_atomic = index_decisions(case_data.get("declaration_atomic_decisions", []), "atomic_id")
    implementation_atomic = index_decisions(case_data.get("implementation_atomic_decisions", []), "atomic_id")
    declaration_controls = index_decisions(case_data.get("declaration_control_decisions", []), "control_id")
    implementation_controls = index_decisions(case_data.get("implementation_control_decisions", []), "control_id")

    categories = []
    for raw in case_data.get("category_discrepancies", []):
        category = normalize_category_discrepancy(raw)
        category["declaration_details"] = collect_side_details(
            atomic_ids=raw.get("declaration_atomic_ids", []),
            control_ids=raw.get("declaration_control_ids", []),
            atomic_index=declaration_atomic,
            control_index=declaration_controls,
        )
        category["implementation_details"] = collect_side_details(
            atomic_ids=raw.get("implementation_atomic_ids", []),
            control_ids=raw.get("implementation_control_ids", []),
            atomic_index=implementation_atomic,
            control_index=implementation_controls,
        )
        categories.append(category)

    return {
        "skill_id": case_data.get("skill_id", "unknown"),
        "root_path": case_data.get("root_path", ""),
        "skill_level_discrepancy": case_data.get("skill_level_discrepancy", "insufficient_implementation_evidence"),
        "status_label": status_label(case_data.get("skill_level_discrepancy")),
        "status_tone": status_tone(case_data.get("skill_level_discrepancy")),
        "categories": categories,
        "errors": case_data.get("errors", []),
    }


def normalize_category_discrepancy(raw: dict[str, Any]) -> dict[str, Any]:
    status = raw.get("status", "declared_and_implemented_aligned")
    return {
        "category_id": raw.get("category_id", ""),
        "category_name": raw.get("category_name", raw.get("category_id", "")),
        "status": status,
        "status_label": status_label(status),
        "status_tone": status_tone(status),
        "declaration_present": bool(raw.get("declaration_present")),
        "implementation_present": bool(raw.get("implementation_present")),
        "risks": [translate_risk(item) for item in raw.get("risks", [])],
        "controls": raw.get("controls", []),
        "mismatch_ids": raw.get("mismatch_ids", []),
        "declaration_atomic_ids": raw.get("declaration_atomic_ids", []),
        "implementation_atomic_ids": raw.get("implementation_atomic_ids", []),
        "declaration_control_ids": raw.get("declaration_control_ids", raw.get("declared_control_ids", [])),
        "implementation_control_ids": raw.get("implementation_control_ids", raw.get("implemented_control_ids", [])),
        "declaration_details": [],
        "implementation_details": [],
    }


def index_decisions(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {item[key]: item for item in items if item.get(key)}


def translate_risk(risk: Any) -> Any:
    if isinstance(risk, str):
        return RISK_LABELS.get(risk, risk)
    return risk


def collect_side_details(
    atomic_ids: list[str],
    control_ids: list[str],
    atomic_index: dict[str, dict[str, Any]],
    control_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    details = []
    for atomic_id in atomic_ids:
        atomic = atomic_index.get(atomic_id, {})
        details.append(
            {
                "kind": "atomic",
                "id": atomic_id,
                "name": atomic.get("atomic_name", atomic_id),
                "confidence": atomic.get("confidence", "unknown"),
                "evidence": collect_evidence_samples(
                    atomic.get("supporting_evidence", []),
                    atomic.get("conflicting_evidence", []),
                ),
            }
        )
    for control_id in control_ids:
        control = control_index.get(control_id, {})
        details.append(
            {
                "kind": "control",
                "id": control_id,
                "name": control.get("control_name", control_id),
                "confidence": control.get("confidence", "unknown"),
                "evidence": collect_evidence_samples(control.get("evidence", []), []),
            }
        )
    return details


def collect_evidence_samples(
    supporting: list[dict[str, Any]],
    conflicting: list[dict[str, Any]],
    limit: int = 2,
) -> list[dict[str, Any]]:
    samples = []
    for entry in [*supporting, *conflicting][:limit]:
        source_path = entry.get("source_path", "")
        line_start = entry.get("line_start")
        line_end = entry.get("line_end")
        line_bits = []
        if line_start is not None:
            line_bits.append(str(line_start))
        if line_end is not None and line_end != line_start:
            line_bits.append(str(line_end))
        lines = f"L{'-'.join(line_bits)}" if line_bits else ""
        samples.append(
            {
                "source_path": source_path,
                "lines": lines,
                "matched_text": tidy_excerpt(entry.get("matched_text", "")),
            }
        )
    return samples


def tidy_excerpt(text: str, limit: int = 220) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def status_label(status: str | None) -> str:
    return STATUS_META.get(status or "", {"label": status or "unknown"})["label"]


def status_tone(status: str | None) -> str:
    return STATUS_META.get(status or "", {"tone": "muted"})["tone"]


def category_rank(status: str) -> int:
    ranks = {
        "implementation_only_high_risk": 0,
        "declared_more_than_implemented": 1,
        "declared_and_implemented_aligned": 2,
        "insufficient_declaration_evidence": 3,
        "insufficient_implementation_evidence": 4,
    }
    return ranks.get(status, 9)


def render_html(bundle: dict[str, Any], report_title: str, input_path: Path) -> str:
    data_json = json.dumps(bundle, ensure_ascii=False)
    # Prevent embedded evidence text like "</script>" from terminating the script tag early.
    data_json = (
        data_json.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    title = escape(report_title)
    source_label = escape(bundle["source_label"])
    generated_at = escape(bundle["generated_at"])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f5efe3;
      --bg-2: #fffaf0;
      --paper: rgba(255, 251, 245, 0.88);
      --ink: #1d1a16;
      --muted: #6d6257;
      --line: rgba(73, 57, 38, 0.14);
      --accent: #0f766e;
      --accent-soft: rgba(15, 118, 110, 0.12);
      --danger: #b42318;
      --danger-soft: rgba(180, 35, 24, 0.12);
      --warn: #b45309;
      --warn-soft: rgba(180, 83, 9, 0.12);
      --ok: #166534;
      --ok-soft: rgba(22, 101, 52, 0.12);
      --muted-soft: rgba(88, 73, 55, 0.08);
      --shadow: 0 24px 60px rgba(56, 42, 24, 0.10);
      --radius-xl: 28px;
      --radius-lg: 18px;
      --radius-md: 14px;
    }}

    * {{ box-sizing: border-box; }}

    html {{
      scroll-behavior: smooth;
    }}

    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(180, 83, 9, 0.16), transparent 30%),
        linear-gradient(180deg, var(--bg-2) 0%, var(--bg) 100%);
      font-family: "IBM Plex Sans", "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
    }}

    .shell {{
      width: min(1400px, calc(100vw - 32px));
      margin: 24px auto 56px;
    }}

    .hero {{
      padding: 32px;
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.78), rgba(255, 247, 236, 0.94)),
        rgba(255, 255, 255, 0.8);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
      overflow: hidden;
      position: relative;
    }}

    .hero::after {{
      content: "";
      position: absolute;
      inset: auto -120px -120px auto;
      width: 280px;
      height: 280px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(15, 118, 110, 0.12), transparent 70%);
      pointer-events: none;
    }}

    h1, h2, h3 {{
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", "Songti SC", serif;
      letter-spacing: 0.01em;
    }}

    .eyebrow {{
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 12px;
    }}

    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.9fr);
      gap: 28px;
      align-items: end;
    }}

    .subtitle {{
      margin-top: 12px;
      max-width: 58ch;
      color: var(--muted);
      line-height: 1.65;
      font-size: 15px;
    }}

    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
    }}

    .meta-chip {{
      padding: 8px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.68);
      border: 1px solid var(--line);
    }}

    .stats {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}

    .stat {{
      padding: 18px;
      border-radius: var(--radius-lg);
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.66);
    }}

    .stat-label {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }}

    .stat-value {{
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.03em;
    }}

    .toolbar {{
      position: sticky;
      top: 12px;
      z-index: 20;
      margin-top: 20px;
      padding: 14px;
      border-radius: 20px;
      border: 1px solid var(--line);
      background: rgba(255, 250, 242, 0.84);
      backdrop-filter: blur(16px);
      box-shadow: 0 16px 40px rgba(56, 42, 24, 0.08);
    }}

    .toolbar-grid {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto auto;
      gap: 12px;
      align-items: center;
    }}

    input[type="search"] {{
      width: 100%;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.84);
      border-radius: 14px;
      padding: 13px 14px;
      font: inherit;
      color: var(--ink);
      outline: none;
    }}

    .chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    button.chip {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.8);
      color: var(--ink);
      padding: 10px 12px;
      border-radius: 999px;
      cursor: pointer;
      font: inherit;
      transition: transform 180ms ease, background 180ms ease, border-color 180ms ease;
    }}

    button.chip:hover {{
      transform: translateY(-1px);
    }}

    button.chip.active {{
      background: var(--accent-soft);
      border-color: rgba(15, 118, 110, 0.28);
      color: #0b5f58;
    }}

    .results {{
      margin-top: 22px;
      display: grid;
      gap: 18px;
    }}

    .skill-card {{
      border: 1px solid var(--line);
      border-radius: 24px;
      background: var(--paper);
      box-shadow: 0 20px 50px rgba(56, 42, 24, 0.07);
      overflow: hidden;
    }}

    .skill-top {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      padding: 24px 24px 18px;
      border-bottom: 1px solid rgba(73, 57, 38, 0.08);
    }}

    .skill-id {{
      font-size: 22px;
      line-height: 1.2;
      word-break: break-word;
    }}

    .skill-path {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      word-break: break-all;
    }}

    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 12px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 600;
      border: 1px solid transparent;
      white-space: nowrap;
    }}

    .tone-danger {{ color: var(--danger); background: var(--danger-soft); border-color: rgba(180, 35, 24, 0.18); }}
    .tone-warn {{ color: var(--warn); background: var(--warn-soft); border-color: rgba(180, 83, 9, 0.18); }}
    .tone-ok {{ color: var(--ok); background: var(--ok-soft); border-color: rgba(22, 101, 52, 0.18); }}
    .tone-muted {{ color: #5f5346; background: var(--muted-soft); border-color: rgba(88, 73, 55, 0.12); }}

    .skill-summary {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      padding: 0 24px 20px;
    }}

    .mini-stat {{
      padding: 10px 12px;
      border-radius: 14px;
      background: rgba(255,255,255,0.62);
      border: 1px solid var(--line);
      font-size: 13px;
      color: var(--muted);
    }}

    .categories {{
      padding: 0 16px 16px;
      display: grid;
      gap: 12px;
    }}

    details.category {{
      border-radius: 18px;
      border: 1px solid rgba(73, 57, 38, 0.10);
      background: rgba(255,255,255,0.62);
      overflow: hidden;
    }}

    details.category[open] {{
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.45);
    }}

    summary {{
      list-style: none;
      cursor: pointer;
      padding: 16px 18px;
    }}

    summary::-webkit-details-marker {{
      display: none;
    }}

    .category-head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
    }}

    .category-title {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 10px;
      align-items: center;
    }}

    .category-name {{
      font-size: 18px;
      font-weight: 700;
    }}

    .category-id {{
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}

    .presence {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
    }}

    .presence span {{
      font-size: 12px;
      padding: 6px 9px;
      border-radius: 999px;
      background: rgba(29, 26, 22, 0.04);
      border: 1px solid rgba(29, 26, 22, 0.08);
      color: var(--muted);
    }}

    .category-body {{
      padding: 0 18px 18px;
      display: grid;
      gap: 16px;
    }}

    .side-by-side {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}

    .pane {{
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.64);
      padding: 14px;
    }}

    .pane-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 12px;
    }}

    .pane-title strong {{
      font-size: 14px;
    }}

    .token-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }}

    .token {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 9px;
      border-radius: 10px;
      font-size: 12px;
      background: rgba(29, 26, 22, 0.04);
      border: 1px solid rgba(29, 26, 22, 0.08);
    }}

    .token code {{
      font-size: 12px;
      font-family: "SFMono-Regular", "Cascadia Mono", "JetBrains Mono", monospace;
    }}

    .detail-list {{
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }}

    .detail {{
      border-radius: 14px;
      padding: 12px;
      background: rgba(255, 250, 242, 0.88);
      border: 1px solid rgba(73, 57, 38, 0.08);
    }}

    .detail-head {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }}

    .detail-head .kind {{
      font-size: 11px;
      padding: 4px 7px;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.10);
      color: #0f615b;
      border: 1px solid rgba(15, 118, 110, 0.14);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}

    .detail-head strong {{
      font-size: 14px;
    }}

    .evidence {{
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }}

    .evidence-item {{
      padding: 10px;
      border-radius: 12px;
      background: rgba(255,255,255,0.92);
      border: 1px solid rgba(73, 57, 38, 0.08);
    }}

    .evidence-meta {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
      word-break: break-all;
    }}

    .evidence-text {{
      font-family: "SFMono-Regular", "Cascadia Mono", "JetBrains Mono", monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
      word-break: break-word;
    }}

    .list-block {{
      display: grid;
      gap: 10px;
    }}

    .pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .pill {{
      padding: 7px 10px;
      border-radius: 999px;
      background: rgba(29, 26, 22, 0.05);
      border: 1px solid rgba(29, 26, 22, 0.08);
      font-size: 12px;
    }}

    .empty {{
      color: var(--muted);
      font-size: 13px;
      padding: 8px 0;
    }}

    .footer {{
      margin-top: 18px;
      text-align: center;
      color: var(--muted);
      font-size: 12px;
    }}

    @media (max-width: 980px) {{
      .hero-grid,
      .toolbar-grid,
      .side-by-side,
      .skill-top {{
        grid-template-columns: 1fr;
      }}

      .stats {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}

    @media (max-width: 640px) {{
      .shell {{
        width: min(100vw - 20px, 100%);
        margin-top: 10px;
      }}

      .hero {{
        padding: 22px;
      }}

      .stats {{
        grid-template-columns: 1fr;
      }}

      .skill-top,
      .skill-summary {{
        padding-left: 18px;
        padding-right: 18px;
      }}

      .categories {{
        padding: 0 10px 10px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="hero-grid">
        <div>
          <div class="eyebrow">Skills Security Matrix</div>
          <h1>{title}</h1>
          <p class="subtitle">把技能的申明层和实现层放到同一个视图里，直接看哪些能力只写在文档里、哪些能力已经落在脚本和引用材料里，以及哪些不一致会带来更高的安全风险。</p>
          <div class="meta">
            <span class="meta-chip">来源: {source_label}</span>
            <span class="meta-chip">生成时间: {generated_at}</span>
            <span class="meta-chip">输入路径: {escape(str(input_path))}</span>
          </div>
        </div>
        <div class="stats" id="stats"></div>
      </div>
    </section>

    <section class="toolbar">
      <div class="toolbar-grid">
        <input id="search" type="search" placeholder="搜索 skill、分类名、能力 ID、风险字母..." />
        <div class="chip-row" id="status-filters"></div>
        <div class="chip-row">
          <button class="chip active" id="toggle-open">默认展开高风险</button>
        </div>
      </div>
    </section>

    <section class="results" id="results"></section>
    <div class="footer">单文件 HTML，可直接本地打开，无需额外服务。</div>
  </div>

  <script>
    const DATA = {data_json};

    const STATUS_ORDER = [
      "implementation_only_high_risk",
      "declared_more_than_implemented",
      "declared_and_implemented_aligned",
      "insufficient_declaration_evidence",
      "insufficient_implementation_evidence",
    ];

    const STATUS_META = {{
      implementation_only_high_risk: {{ label: "仅实现层命中（高风险）", tone: "tone-danger" }},
      declared_more_than_implemented: {{ label: "申明多于实现", tone: "tone-warn" }},
      declared_and_implemented_aligned: {{ label: "申明与实现一致", tone: "tone-ok" }},
      insufficient_declaration_evidence: {{ label: "申明证据不足", tone: "tone-muted" }},
      insufficient_implementation_evidence: {{ label: "实现证据不足", tone: "tone-muted" }},
    }};

    let activeStatus = "all";
    let expandHighRisk = true;

    function escapeHtml(value) {{
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }}

    function badge(label, tone) {{
      return `<span class="badge ${{tone}}">${{escapeHtml(label)}}</span>`;
    }}

    function renderStats() {{
      const summary = DATA.summary;
      const items = [
        ["技能总数", summary.skill_count],
        ["高风险技能", summary.high_risk_skill_count],
        ["仅实现层高风险分类", summary.category_status_counts.implementation_only_high_risk || 0],
        ["申明多于实现分类", summary.category_status_counts.declared_more_than_implemented || 0],
      ];
      document.querySelector("#stats").innerHTML = items.map(([label, value]) => `
        <div class="stat">
          <div class="stat-label">${{escapeHtml(label)}}</div>
          <div class="stat-value">${{escapeHtml(value)}}</div>
        </div>
      `).join("");
    }}

    function renderStatusFilters() {{
      const container = document.querySelector("#status-filters");
      const statuses = ["all", ...STATUS_ORDER.filter((status) => (DATA.summary.status_counts[status] || 0) > 0)];
      container.innerHTML = statuses.map((status) => {{
        const label = status === "all" ? "全部技能" : STATUS_META[status].label;
        const count = status === "all" ? DATA.summary.skill_count : (DATA.summary.status_counts[status] || 0);
        const active = activeStatus === status ? "active" : "";
        return `<button class="chip ${{active}}" data-status="${{status}}">${{escapeHtml(label)}} · ${{count}}</button>`;
      }}).join("");
      container.querySelectorAll("button").forEach((button) => {{
        button.addEventListener("click", () => {{
          activeStatus = button.dataset.status;
          renderStatusFilters();
          renderResults();
        }});
      }});
    }}

    function matchesSearch(skill, query) {{
      if (!query) return true;
      const haystack = [
        skill.skill_id,
        skill.root_path,
        skill.skill_level_discrepancy,
        ...skill.categories.flatMap((category) => [
          category.category_id,
          category.category_name,
          category.status,
          ...(category.risks || []),
          ...(category.controls || []),
          ...(category.declaration_atomic_ids || []),
          ...(category.implementation_atomic_ids || []),
          ...(category.declaration_control_ids || []),
          ...(category.implementation_control_ids || []),
        ]),
      ].join("\\n").toLowerCase();
      return haystack.includes(query);
    }}

    function filteredSkills() {{
      const query = document.querySelector("#search").value.trim().toLowerCase();
      return DATA.skills.filter((skill) => {{
        const statusMatch = activeStatus === "all" || skill.skill_level_discrepancy === activeStatus;
        return statusMatch && matchesSearch(skill, query);
      }});
    }}

    function renderSidePane(title, present, ids, details) {{
      const idTokens = (ids || []).length
        ? `<div class="token-row">${{ids.map((id) => `<span class="token"><code>${{escapeHtml(id)}}</code></span>`).join("")}}</div>`
        : `<div class="empty">这一侧没有命中对应能力或控制项。</div>`;

      const detailBlocks = (details || []).length
        ? `<div class="detail-list">${{details.map((detail) => `
            <div class="detail">
              <div class="detail-head">
                <span class="kind">${{escapeHtml(detail.kind)}}</span>
                <strong><code>${{escapeHtml(detail.id)}}</code> ${{escapeHtml(detail.name || "")}}</strong>
                <span class="pill">${{escapeHtml(detail.confidence || "unknown")}}</span>
              </div>
              ${{detail.evidence && detail.evidence.length ? `
                <div class="evidence">
                  ${{detail.evidence.map((item) => `
                    <div class="evidence-item">
                      <div class="evidence-meta">${{escapeHtml(item.source_path)}} ${{escapeHtml(item.lines || "")}}</div>
                      <div class="evidence-text">${{escapeHtml(item.matched_text)}}</div>
                    </div>
                  `).join("")}}
                </div>
              ` : `<div class="empty">没有可展示的证据片段。</div>`}}
            </div>
          `).join("")}}</div>`
        : "";

      return `
        <div class="pane">
          <div class="pane-title">
            <strong>${{escapeHtml(title)}}</strong>
            ${{present ? badge("已命中", "tone-ok") : badge("未命中", "tone-muted")}}
          </div>
          ${{idTokens}}
          ${{detailBlocks}}
        </div>
      `;
    }}

    function renderCategory(category) {{
      const isOpen = expandHighRisk && category.status === "implementation_only_high_risk" ? "open" : "";
      const declarationIds = [...(category.declaration_atomic_ids || []), ...(category.declaration_control_ids || [])];
      const implementationIds = [...(category.implementation_atomic_ids || []), ...(category.implementation_control_ids || [])];
      return `
        <details class="category" ${{isOpen}}>
          <summary>
            <div class="category-head">
              <div>
                <div class="category-title">
                  <div class="category-name">${{escapeHtml(category.category_name)}}</div>
                  <div class="category-id">${{escapeHtml(category.category_id)}}</div>
                  ${{badge(category.status_label, STATUS_META[category.status]?.tone || "tone-muted")}}
                </div>
                <div class="presence">
                  <span>申明层: ${{category.declaration_present ? "是" : "否"}}</span>
                  <span>实现层: ${{category.implementation_present ? "是" : "否"}}</span>
                  <span>风险: ${{escapeHtml((category.risks || []).join(" / ") || "无")}}</span>
                </div>
              </div>
            </div>
          </summary>
          <div class="category-body">
            <div class="side-by-side">
              ${{renderSidePane("申明层", category.declaration_present, declarationIds, category.declaration_details)}}
              ${{renderSidePane("实现层", category.implementation_present, implementationIds, category.implementation_details)}}
            </div>
            <div class="list-block">
              <div>
                <strong>建议控制项</strong>
                <div class="pill-row" style="margin-top:8px;">
                  ${{(category.controls || []).length
                    ? category.controls.map((item) => `<span class="pill">${{escapeHtml(item)}}</span>`).join("")
                    : `<span class="empty">无</span>`}}
                </div>
              </div>
            </div>
          </div>
        </details>
      `;
    }}

    function renderSkill(skill) {{
      const categoryCounts = skill.categories.reduce((acc, category) => {{
        acc[category.status] = (acc[category.status] || 0) + 1;
        return acc;
      }}, {{}});
      return `
        <article class="skill-card">
          <div class="skill-top">
            <div>
              <div class="skill-id">${{escapeHtml(skill.skill_id)}}</div>
              ${{skill.root_path ? `<div class="skill-path">${{escapeHtml(skill.root_path)}}</div>` : ""}}
            </div>
            <div>${{badge(skill.status_label, STATUS_META[skill.skill_level_discrepancy]?.tone || "tone-muted")}}</div>
          </div>
          <div class="skill-summary">
            <div class="mini-stat">分类差异数: <strong>${{skill.categories.length}}</strong></div>
            ${{STATUS_ORDER.filter((status) => categoryCounts[status]).map((status) =>
              `<div class="mini-stat">${{escapeHtml(STATUS_META[status].label)}}: <strong>${{categoryCounts[status]}}</strong></div>`
            ).join("")}}
            ${{skill.errors && skill.errors.length ? `<div class="mini-stat">错误: <strong>${{skill.errors.length}}</strong></div>` : ""}}
          </div>
          <div class="categories">
            ${{skill.categories.length
              ? skill.categories.map(renderCategory).join("")
              : `<div class="empty" style="padding: 12px 18px;">这个 skill 没有分类差异记录。</div>`}}
          </div>
        </article>
      `;
    }}

    function renderResults() {{
      const skills = filteredSkills();
      const container = document.querySelector("#results");
      if (!skills.length) {{
        container.innerHTML = `<div class="skill-card"><div class="skill-top"><div><div class="skill-id">没有匹配结果</div><div class="skill-path">试试换个关键词，或切换上方状态筛选。</div></div></div></div>`;
        return;
      }}
      container.innerHTML = skills.map(renderSkill).join("");
    }}

    document.querySelector("#search").addEventListener("input", renderResults);
    document.querySelector("#toggle-open").addEventListener("click", (event) => {{
      expandHighRisk = !expandHighRisk;
      event.currentTarget.classList.toggle("active", expandHighRisk);
      event.currentTarget.textContent = expandHighRisk ? "默认展开高风险" : "默认折叠全部";
      renderResults();
    }});

    renderStats();
    renderStatusFilters();
    renderResults();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
