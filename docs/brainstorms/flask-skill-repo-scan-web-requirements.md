---
date: 2026-04-02
topic: flask-skill-repo-scan-web
---

# Flask Skill Repo Scan Web

## Problem Frame

当前仓库已经具备本地 skill 扫描与分析能力，但使用方式仍以命令行为主。对于只想快速验证“某个 GitHub 仓库里有没有这个 skill、它在什么位置、扫描结果是什么”的用户来说，现有流程门槛偏高：需要自己下载仓库、定位 skill 路径、拼接命令并理解输出目录结构。

本需求要增加一个基于 Flask 的轻量网页，把“输入 GitHub 仓库 + skill 名称 → 下载仓库 → 定位 skill → 调用现有扫描脚本 → 展示结果”串成一个单次完成的浏览器工作流。第一版以快速单次分析为主，不做重型任务系统。

## Requirements

- R1. 系统必须提供一个网页表单，允许用户输入 GitHub 仓库地址，并可选输入目标 skill 名称。
- R2. 当用户提交 GitHub 仓库地址后，系统必须自动下载该仓库到本地工作目录，供后续 skill 发现与扫描使用。
- R3. 当用户同时提供 skill 名称时，系统必须优先尝试在目标仓库中定位该 skill 的实际目录位置。
- R4. 当用户未提供 skill 名称时，系统必须自动发现该仓库中的全部 skill，并向用户展示可选 skill 列表。
- R5. 当用户提供了 skill 名称但无法直接匹配时，系统不得直接失败；必须自动退回到“扫描仓库中的全部 skill 并展示候选列表”的流程。
- R6. skill 定位与扫描流程必须复用现有的 [`run_single_skill_from_skills_sh.py`](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py) 能力，而不是重新实现另一套独立分析逻辑。
- R7. 系统必须在前端明确展示 skill 的仓库内路径、skill 标识或名称，以及本次扫描是否成功。
- R8. 当扫描成功时，系统必须在前端展示足够理解结果的核心输出，而不是只给出“成功/失败”状态。
- R9. 当扫描失败时，系统必须向用户展示可理解的失败原因，例如仓库无法下载、仓库内未发现 skill、脚本执行失败或结果文件缺失。
- R10. 第一版交互必须是单页同步式体验：用户提交后在当前页面等待，完成后直接看到结果或错误信息。
- R11. 第一版必须只关注单个 GitHub 仓库的一次分析请求，不要求支持跨仓库批量任务、任务排队或历史任务管理。
- R12. 系统必须尽量避免让用户理解底层输出目录结构；前端应把关键结果整理成可读视图。

## Success Criteria

- 用户无需手动克隆仓库或运行命令，就能从浏览器完成一次仓库级 skill 定位和扫描。
- 当仓库中存在目标 skill 时，用户能清楚看到它在仓库中的位置以及扫描结果。
- 当用户输错或记错 skill 名称时，系统仍能通过自动发现候选 skill 帮助用户继续完成分析，而不是直接中断。
- 第一版能够稳定支撑单次分析流程，且不要求引入复杂任务队列或后台管理。

## Scope Boundaries

- 不要求第一版支持 GitHub 以外的代码托管平台。
- 不要求第一版支持多仓库批量提交。
- 不要求第一版保留历史扫描记录、任务列表或可分享结果页。
- 不要求第一版提供账户系统、权限系统或多用户隔离。
- 不要求第一版重写底层扫描逻辑；应优先包装现有 CLI 能力。
- 不要求第一版做复杂前端框架；核心目标是完成可用工作流，而不是构建大型前端应用。

## Key Decisions

- 以“GitHub 仓库 + skill 名称”为默认输入方式：这符合用户最快到达结果的主路径。
- 保留“只输仓库、自动发现 skill”的兜底路径：这样既支持探索，也能处理 skill 名称缺失或记错的情况。
- 当 skill 名称匹配失败时自动回退为全仓发现：相比直接报错，这更贴合用户真实意图，也减少重复输入。
- 第一版采用同步式页面交互：范围更小，足以验证核心价值，不必一开始就引入任务状态管理。
- 后端复用现有扫描脚本：这样可以最大化继承当前分析逻辑与输出格式，降低重复实现与结果漂移风险。

## Dependencies / Assumptions

- 当前运行环境允许后端进程拉取 GitHub 仓库并在本地写入工作目录。
- [`run_single_skill_from_skills_sh.py`](/home/szk/code/OpenClaw-Proj/scripts/run_single_skill_from_skills_sh.py) 已经具备发现本地 skill 与输出结果文件的基础能力，可被 Flask 后端调用。
- 仓库下载和单次扫描的耗时在第一版同步页面中是可接受的，或至少可以通过加载态和错误提示维持基本可用体验。

## Outstanding Questions

### Resolve Before Planning

- 无

### Deferred to Planning

- [Affects R2][Technical] 仓库下载目录、重复下载缓存和同仓库复用策略应如何设计，才能避免磁盘浪费与结果混淆？
- [Affects R3][Technical] skill 名称匹配规则应支持哪些形式，例如精确名、slug、目录名归一化或模糊匹配？
- [Affects R6][Technical] Flask 后端应通过直接导入 Python 模块还是子进程调用脚本来复用现有能力？
- [Affects R8][Technical] 前端应展示哪些分析摘要字段，才能在不暴露原始 JSON 全细节的前提下保持结果有用？
- [Affects R9][Technical] 错误分类与日志透出粒度应如何设计，才能兼顾可理解性与调试效率？
- [Affects R10][Technical] 单页同步式请求的超时、加载态和长耗时反馈应如何处理，避免用户误以为页面卡死？

## Next Steps

→ /prompts:ce-plan for structured implementation planning
