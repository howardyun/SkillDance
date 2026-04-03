from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import (
    AtomicCapability,
    CapabilityMapping,
    ControlSemantic,
    MatrixCategory,
    MatrixDefinition,
    MismatchDefinition,
)


CATEGORY_ID_MAP = {
    "会话与上下文访问": "session_context_access",
    "文件与知识库访问": "file_knowledge_access",
    "外部信息访问": "external_information_access",
    "检索与查询执行": "retrieval_query_execution",
    "代码与计算执行": "code_computation_execution",
    "内容生成与文件处理": "content_generation_file_processing",
    "草稿与建议写入": "draft_suggestion_write",
    "受确认的单次写入": "confirmed_single_write",
    "自动或批量写入": "automatic_batch_write",
    "跨应用身份代理": "cross_app_identity_proxy",
    "定时与周期自动化": "scheduled_periodic_automation",
    "条件触发与监控自动化": "conditional_trigger_monitoring_automation",
}


def parse_matrix_file(matrix_path: Path) -> list[MatrixCategory]:
    return load_matrix_definition(matrix_path).categories


def load_matrix_definition(matrix_path: Path) -> MatrixDefinition:
    text = matrix_path.read_text(encoding="utf-8")
    section_rows = _parse_sections(text, matrix_path)
    definition = MatrixDefinition(
        categories=_parse_category_section(section_rows.get("Category Matrix", []), matrix_path),
        atomic_capabilities=_parse_atomic_section(section_rows.get("Atomic Capabilities", []), matrix_path),
        control_semantics=_parse_control_section(section_rows.get("Control Semantics", []), matrix_path),
        capability_mappings=_parse_mapping_section(section_rows.get("Capability Mappings", []), matrix_path),
        mismatch_definitions=_parse_mismatch_section(section_rows.get("Mismatch Definitions", []), matrix_path),
    )
    if not definition.categories:
        raise ValueError(f"Category Matrix section is empty: {matrix_path}")
    return definition


def _parse_sections(text: str, matrix_path: Path) -> dict[str, list[list[str]]]:
    sections: dict[str, list[str]] = {}
    current_name: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current_name = line[3:].strip()
            sections[current_name] = []
            continue
        if current_name is None or not line.strip():
            continue
        sections[current_name].append(line)

    parsed_sections: dict[str, list[list[str]]] = {}
    for name, lines in sections.items():
        parsed_sections[name] = list(csv.reader(lines, delimiter="\t"))
    if not parsed_sections:
        raise ValueError(f"Matrix file is empty: {matrix_path}")
    return parsed_sections


def _parse_category_section(rows: list[list[str]], matrix_path: Path) -> list[MatrixCategory]:
    if not rows:
        return []
    header = rows[0]
    expected_header = ["大类", "小类", "安全定义", "数据等级", "主要风险", "控制要求"]
    if header != expected_header:
        raise ValueError(f"Unexpected category matrix header in {matrix_path}: {header}")

    categories: list[MatrixCategory] = []
    for row in rows[1:]:
        normalized = [cell.strip() for cell in row]
        if len(normalized) != 6:
            raise ValueError(f"Unexpected matrix row shape in {matrix_path}: {row}")
        major_category, subcategory, definition, data_level, risks, controls = normalized
        if not subcategory:
            continue
        category_id = CATEGORY_ID_MAP.get(subcategory)
        if not category_id:
            raise ValueError(f"Unknown matrix category: {subcategory}")
        categories.append(
            MatrixCategory(
                category_id=category_id,
                major_category=major_category,
                subcategory=subcategory,
                security_definition=definition,
                data_level=data_level,
                primary_risks=_split_values(risks),
                control_requirements=_split_controls(controls),
            )
        )
    return categories


def _parse_atomic_section(rows: list[list[str]], matrix_path: Path) -> list[AtomicCapability]:
    if not rows:
        return []
    header = rows[0]
    expected_header = ["原子ID", "原子能力", "最小成立条件", "主要风险", "必要控制"]
    if header != expected_header:
        raise ValueError(f"Unexpected atomic capabilities header in {matrix_path}: {header}")
    capabilities: list[AtomicCapability] = []
    for row in rows[1:]:
        normalized = [cell.strip() for cell in row]
        if len(normalized) != 5:
            raise ValueError(f"Unexpected atomic capability row shape in {matrix_path}: {row}")
        atomic_id, atomic_name, minimal_condition, risks, controls = normalized
        capabilities.append(
            AtomicCapability(
                atomic_id=atomic_id,
                atomic_name=atomic_name,
                minimal_condition=minimal_condition,
                primary_risks=_split_values(risks),
                necessary_controls=_split_controls(controls),
            )
        )
    return capabilities


def _parse_control_section(rows: list[list[str]], matrix_path: Path) -> list[ControlSemantic]:
    if not rows:
        return []
    header = rows[0]
    expected_header = ["控制ID", "控制语义", "最小成立条件", "适用原子能力"]
    if header != expected_header:
        raise ValueError(f"Unexpected control semantics header in {matrix_path}: {header}")
    controls: list[ControlSemantic] = []
    for row in rows[1:]:
        normalized = [cell.strip() for cell in row]
        if len(normalized) != 4:
            raise ValueError(f"Unexpected control semantic row shape in {matrix_path}: {row}")
        control_id, control_name, minimal_condition, atomic_ids = normalized
        controls.append(
            ControlSemantic(
                control_id=control_id,
                control_name=control_name,
                minimal_condition=minimal_condition,
                applicable_atomic_ids=_split_values(atomic_ids),
            )
        )
    return controls


def _parse_mapping_section(rows: list[list[str]], matrix_path: Path) -> list[CapabilityMapping]:
    if not rows:
        return []
    header = rows[0]
    expected_header = ["原子ID", "上卷类目"]
    if header != expected_header:
        raise ValueError(f"Unexpected capability mappings header in {matrix_path}: {header}")
    mappings: list[CapabilityMapping] = []
    for row in rows[1:]:
        normalized = [cell.strip() for cell in row]
        if len(normalized) != 2:
            raise ValueError(f"Unexpected capability mapping row shape in {matrix_path}: {row}")
        atomic_id, category_id = normalized
        mappings.append(CapabilityMapping(atomic_id=atomic_id, category_id=category_id))
    return mappings


def _parse_mismatch_section(rows: list[list[str]], matrix_path: Path) -> list[MismatchDefinition]:
    if not rows:
        return []
    header = rows[0]
    expected_header = ["MismatchID", "名称", "定义", "触发条件"]
    if header != expected_header:
        raise ValueError(f"Unexpected mismatch definitions header in {matrix_path}: {header}")
    mismatches: list[MismatchDefinition] = []
    for row in rows[1:]:
        normalized = [cell.strip() for cell in row]
        if len(normalized) != 4:
            raise ValueError(f"Unexpected mismatch row shape in {matrix_path}: {row}")
        mismatch_id, mismatch_name, definition, trigger_condition = normalized
        mismatches.append(
            MismatchDefinition(
                mismatch_id=mismatch_id,
                mismatch_name=mismatch_name,
                definition=definition,
                trigger_condition=trigger_condition,
            )
        )
    return mismatches


def _split_values(value: str) -> list[str]:
    cleaned = value.replace("（", "(").replace("）", ")")
    parts = re.split(r"[、,，]", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _split_controls(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[；;]", value) if part.strip()]
