# Skills Security Matrix Analyzer

`skills_security_matrix` 是一个面向研究的本地离线分析器，用来扫描 `skills/` 语料目录，并把每个 skill 的声明层与实现层能力映射到仓库里的安全矩阵。

## Inputs

- `--skills-dir`：技能仓库顶层目录
- `--output-dir`：输出根目录，实际运行会创建 `run-<timestamp>` 子目录
- `--limit`：只分析前 N 个 skill
- `--format`：`json`、`csv` 或两者组合
- `--case-study-skill`：在运行摘要中标记一个重点复核对象
- `--fail-on-unknown-matrix`：为后续矩阵演进保留的严格模式开关
- `--include-hidden`：是否包含隐藏目录
- `--llm-review-mode`：`off`、`review`、`review+fallback`
- `--llm-provider`：可选 review provider，当前内置 `mock`、`litellm`、`openai`
- `--llm-model`：透传给 provider 的模型名
- `--llm-low-confidence-threshold`：低置信度 review 阈值
- `--llm-high-risk-sparse-threshold`：高风险且证据稀疏时的 review 阈值
- `--llm-fallback-max-categories`：允许 fallback adjudication 的最大类别数
- `--llm-timeout-seconds`：单类别 review 超时
- `--llm-fail-open` / `--llm-fail-closed`：provider 失败时保留离线决策或关闭该类别
- `--emit-review-audit`：显式输出 review audit
- `--goldset-path`：可选 gold set JSON，用于离线与增强模式比对

## Outputs

每次运行都会产出：

- `skills.json` / `skills.csv`：skill 结构画像与基础元数据
- `rule_candidates.json` / `rule_candidates.csv`：离线规则候选及其初始置信度
- `classifications.json` / `classifications.csv`：最终声明层、实现层决策与证据
- `discrepancies.json` / `discrepancies.csv`：层间能力漂移与风险映射
- `risk_mappings.json`：最终类别对应的矩阵风险和控制项
- `review_audit.json` / `review_audit.csv`：可选 review 轨迹、provider 元数据与失败信息
- `run_manifest.json`：运行参数、计数和逐 skill 错误摘要
- `validation.json`：当提供 `--goldset-path` 时输出 gold set 对比结果
- `cases/<skill-id>.json`：适合论文 case study 的单 skill 全量证据视图

## Evidence Semantics

- 声明层只读取 `SKILL.md`、frontmatter，以及 `SKILL.md` 明确引用的支持材料。
- 实现层扫描代码、脚本和配置文件的静态信号，不把 `SKILL.md` 本体当作实现证据。
- 每条证据都保留 `source_path`、`layer`、`rule_id`、`line_start`、`matched_text` 等字段，方便手工抽查。
- 每条证据还会带稳定的 `excerpt_hash` 和 `evidence_fingerprint`，便于 case study、去重和后续人工复核。
- 当声明或实现证据不足时，输出会保留 `insufficient_*` 状态，而不是强行对齐。

## Review Modes

- 默认 `off`：只运行离线候选构建和最终化，不做任何外部模型调用。
- `review`：只对命中触发条件的类别进行 category-level review，review 只能 `accepted`、`downgraded` 或 `rejected_by_llm`。
- `review+fallback`：在 `review` 基础上，对配额内且仍未解决的类别允许 `fallback_adjudicated`。
- provider 失败时，`--llm-fail-open` 会保留离线决策，`--llm-fail-closed` 会把触发 review 的类别收紧为拒绝结果。

## Gold Set Validation

- gold set 文件是一个 JSON 数组，元素至少包含 `skill_id`、`layer`、`category_id`，可选 `decision_status`。
- 当传入 `--goldset-path` 时，运行摘要和 `validation.json` 会输出命中数、缺失数、状态不匹配数和准确率。
- 这使离线与增强模式的 ablation 可以机械化比较，而不需要人工翻日志。

## Rule Writing Notes

- 规则按矩阵 category id 归一化，这样声明层和实现层可以直接比较。
- 优先增加高精度硬证据，再补低强度支持证据。
- 新规则应尽量返回可复核的文本片段，不要只返回抽象标签。
- 如果后续要提高语言感知精度，可以在当前模块边界内替换为 Tree-sitter 或 Semgrep 风格的规则引擎，而无需改 CLI 和导出层。

## Example

```bash
python main.py \
  --skills-dir skills \
  --output-dir outputs/skills_security_matrix \
  --format json,csv \
  --case-study-skill readonly-skill
```

```bash
python main.py \
  --skills-dir skills \
  --llm-review-mode review \
  --llm-provider mock \
  --llm-low-confidence-threshold 0.6 \
  --emit-review-audit \
  --goldset-path tests/fixtures/skills_security_matrix/goldset.json
```
