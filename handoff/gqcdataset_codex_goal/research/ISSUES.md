# Codex 任务导航

创建日期：2026-11-18（Asia/Shanghai）。初轮为 #1–#9。PR #10 再评审的依据由 #11–#13 跟踪，#14、#15 进入后续研究。

| Issue | 工作与产物 | 依赖 |
|---|---|---|
| [#1 总 Goal](https://github.com/jinzhezenggroup/vibedataset/issues/1) | 总体目标、任务队列、科学约束与研究完成标准 | 先读根 AGENTS.md 和 CODEX_GOAL.md |
| [#2 完整源码接管](https://github.com/jinzhezenggroup/vibedataset/issues/2) | 环境、完整源码获取、版本锁、完整性与覆盖台账 | #1 |
| [#3 GQC/xTBloom 审计](https://github.com/jinzhezenggroup/vibedataset/issues/3) | 真实能力、科学依赖、执行解耦、底层改造点及图 | #2 中所需源码已固定 |
| [#4 相近实现审计](https://github.com/jinzhezenggroup/vibedataset/issues/4) | 前人能力地图、强基线、创新边界与代码缺口 | #2 中所需源码已固定 |
| [#5 数据资产与评价](https://github.com/jinzhezenggroup/vibedataset/issues/5) | 真实字段、缺失机制、科学目标、分组及成本协议 | #2 的来源核查；可与 #3/#4 并行 |
| [#6 五主线比较](https://github.com/jinzhezenggroup/vibedataset/issues/6) | 最近邻差异、可证伪假设、首轮实验和路线决定 | #3/#4/#5 的关键证据齐备 |
| [#7 实现与科学验证](https://github.com/jinzhezenggroup/vibedataset/issues/7) | 最小机制、正确性、反例、响应依赖与失效边界 | #6 |
| [#8 全成本与多轮扩展](https://github.com/jinzhezenggroup/vibedataset/issues/8) | 全成本、消融、覆盖/失败、资产长期价值及结论 | #7 科学正确性通过 |
| [#9 原附件缺件](https://github.com/jinzhezenggroup/vibedataset/issues/9) | 原 ZIP/PDF 的来源、哈希与差异核对 | 独立跟踪，不阻塞公开源码研究 |
| [#11 CPHF 独立资格](https://github.com/jinzhezenggroup/vibedataset/issues/11) | 108 个有态目标独立实算，153 项迁移、缓存失效、规划与成本重放。[证据](experiments/cphf_v2/README.md) | PR #10 的原始基态、参照和审查反例 |
| [#12 失败费用](https://github.com/jinzhezenggroup/vibedataset/issues/12) | 构造、普通失败及双回退的 SQLite 与 JSON 回执，科学表回滚和重试。[回归](experiments/response_dataset_cli/failure_costs/verification.json) | 正常 CLI 与真实 SQLite |
| [#13 PR 检查](https://github.com/jinzhezenggroup/vibedataset/issues/13) | 默认 PR 运行归档／代数及固定依赖的 CPU 科学回归，保留预期缺态和失败。[检查入口](../../../README.md#响应验证) | #11、#12 的版本化证据及控制 |
| [#14 真实缺项的质量证据](https://github.com/jinzhezenggroup/vibedataset/issues/14) | 对规划器隐藏完整参照，比较接受／精修／拒绝、误接受与取得证据的成本 | #11 的评估基准 |
| [#15 真实资产与请求的净收益](https://github.com/jinzhezenggroup/vibedataset/issues/15) | 遗留标量和在线留存分别评价，普通块、手写、单／双场、向量及预取公平比较 | #11、#12；生产净收益需 #14 的成本 |

机器可读映射见 [ISSUES.json](ISSUES.json)。不要只凭序号判断工作已经就绪；每项 issue 的具体证据要求和当前输入决定下一步。

## 给 Codex 的启动指令

读取根目录 AGENTS.md、交接 Goal 及当前状态，从各 issue 的验收证据接续。此次 PR 再评审核对 #11、#12 的修复和 #13 的提交检查。接下来的质量证据和强基线实验有各自的输入、预算、竞争解释及停止条件。[审查后的导航](https://github.com/jinzhezenggroup/vibedataset/issues/1#issuecomment-6968146709) · [后续研究决定](decisions/0003-independent-response-qualification.md)

研究记录的路径以 `handoff/gqcdataset_codex_goal/` 为基准，第三方 checkout 默认位于仓库未跟踪的 `_references/`。不要把创建任务、获取文件或自动索引当成源码阅读/研究实验的完成。

## 结项规则

每项 issue 已包含任务、输入、产物和可勾选验收条件。完成时附提交、固定版本代码证据、命令/原始结果、限制、失败和下一步。不能执行的部分说明真实阻塞；附件可通过取得原件并核对，或由用户明确取消原件要求来验收。

请以 [STATUS.md](STATUS.md) 和后续 issue 更新为准。创建这些 issues 不表示 Codex 已启动，也不表示源码获取、实验或科研结论已经完成。

## 首轮研究证据

基础审计、真实资产评价、路线选择及首个分子实现分别见 [工作基础](FOUNDATION_CAPABILITIES.md)、[资产与评价](DATASET_ASSETS.md)、[比较与决定](ROUTE_COMPARISON.md) 和 [三轮实验](experiments/gqc_residual_multiround/README.md)。首轮之后，#2 完成可得来源锁和证据化缺口，#4 补齐响应、着色与正式发布源码的对照，#8 交付 17 个候选的多轮成本与外推实证。两份 PDF 已核验，用户已取消原 ZIP 要求，#9 随之验收。[当前状态](STATUS.md) · [外推数据](experiments/qm9_extension/README.md)
