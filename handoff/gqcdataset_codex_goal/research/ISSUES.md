# Codex 任务导航

创建日期：2026-11-18（Asia/Shanghai）。初轮为 #1–#9。PR #10 的修订和自动检查对应 #11–#13，PR #16 的独立研究证据已折叠为当前科研 issues #17–#19 的输入和历史验收。

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
| [#14 真实缺项的质量证据](https://github.com/jinzhezenggroup/vibedataset/issues/14) | 源态隔离运行与两批封存独立评分，留出有态 24 项均通过，含真实精修、拒绝和全部费用。[研究证据](experiments/target_quality/README.md) | #11 的评估基准 |
| [#15 真实资产与请求的净收益](https://github.com/jinzhezenggroup/vibedataset/issues/15) | 第三方档案逐项核查；普通、手写、单／双场、向量和稠密预取实测，附时间与存储区间。[资产](experiments/legacy_response_assets/README.md) · [实测](experiments/response_benefit/README.md) | #11、#12；生产净收益需 #14 的成本 |

机器可读映射见 [ISSUES.json](ISSUES.json)。不要只凭序号判断工作已经就绪；每项 issue 的具体证据要求和当前输入决定下一步。

## 给 Codex 的启动指令

读取根目录 AGENTS.md、交接 Goal 及当前状态，从各 issue 的验收证据接续。此次 PR 再评审核对 #11、#12 的修复和 #13 的提交检查。后续两项研究已按预登记完成首个判别阶段。项目重启扩大范围的条件见[研究决定](decisions/0004-blind-evidence-and-asset-budgets.md)。[审查后的导航](https://github.com/jinzhezenggroup/vibedataset/issues/1#issuecomment-6968146709) · [后续研究决定](decisions/0003-independent-response-qualification.md)

研究记录的路径以 `handoff/gqcdataset_codex_goal/` 为基准，第三方 checkout 默认位于仓库未跟踪的 `_references/`。不要把创建任务、获取文件或自动索引当成源码阅读/研究实验的完成。

## 结项规则

每项 issue 已包含任务、输入、产物和可勾选验收条件。完成时附提交、固定版本代码证据、命令/原始结果、限制、失败和下一步。不能执行的部分说明真实阻塞；附件可通过取得原件并核对，或由用户明确取消原件要求来验收。

请以 [STATUS.md](STATUS.md) 和后续 issue 更新为准。创建这些 issues 不表示 Codex 已启动，也不表示源码获取、实验或科研结论已经完成。

## 当前科研 issues（按执行顺序）

| Issue | 状态 | 产物与验收 |
|---|---|---|
| [#17 目标相关信息充分性](https://github.com/jinzhezenggroup/vibedataset/issues/17) | 已完成 | 有限 14 候选多混合场、手写/双场/普通/向量/稠密比较，8 个有态留出构型的 32 次重放，水/氨反例和负结论。[实验](experiments/information_sufficiency/README.md) |
| [#19 目标导向误差证书](https://github.com/jinzhezenggroup/vibedataset/issues/19) | 已完成 | 残差、近似对偶、SVD、严格离散界、直接/稠密回退的覆盖、误接受、证据不可得、精修和成本汇总。[实验](experiments/error_certificates/README.md) |
| [#18 跨方法、基组和状态边界](https://github.com/jinzhezenggroup/vibedataset/issues/18) | 已完成 | RHF/基组/DFT/开放壳层/表示/冻结与弛豫响应矩阵，直接复用、初猜、精修、拒绝和重算分类。[实验](experiments/cross_protocol/README.md) |

执行顺序为 #17 → #19 → #18。#20、#21、#22、#23 为重复或已折叠入口，不再作为独立科研主线。最终路线决定见 [0005](decisions/0005-information-certificates-and-migration-boundaries.md)。

## 新增科研 issues（按复评顺序）

| Issue | 状态 | 产物与验收 |
|---|---|---|
| [#25 独立手写基线与搜索完备性](https://github.com/jinzhezenggroup/vibedataset/issues/25) | 已完成 | 独立手写 field/adjoint、15 个四列候选、三场景和完整成本，并由 PR #29 的科学 CI 重放。[实验入口](experiments/information_sufficiency/issue25/README.md) |
| [#26 算子级误差证书](https://github.com/jinzhezenggroup/vibedataset/issues/26) | 已完成 | 全空间基向量、固定随机探针、RHS、近奇异和非对称控制，并由独立评分器和科学 CI 重放。[实验入口](experiments/error_certificates/operator_probe/README.md) |
| [#27 响应资产迁移盲验](https://github.com/jinzhezenggroup/vibedataset/issues/27) | 已完成 | 序列化 direct reuse、跨基组/方法精修、开放壳层/低间隙拒绝和独立评分，并由科学 CI 重放。[实验入口](experiments/cross_protocol/response_migration/README.md) |

## 首轮研究证据

基础审计、真实资产评价、路线选择及首个分子实现分别见 [工作基础](FOUNDATION_CAPABILITIES.md)、[资产与评价](DATASET_ASSETS.md)、[比较与决定](ROUTE_COMPARISON.md) 和 [三轮实验](experiments/gqc_residual_multiround/README.md)。首轮之后，#2 完成可得来源锁和证据化缺口，#4 补齐响应、着色与正式发布源码的对照，#8 交付 17 个候选的多轮成本与外推实证。两份 PDF 已核验，用户已取消原 ZIP 要求，#9 随之验收。[当前状态](STATUS.md) · [外推数据](experiments/qm9_extension/README.md)

## 新增 issues #31–#33 的验收

| Issue | 状态 | 产物与复核 |
|---|---|---|
| #31 四臂核心方法归因 | 已完成 | 同一 manifest 的 A–D 原始 JSON、官方独立 scorer、AO 密度和目标误差、成本及主效应/交互项。[实验](experiments/attribution_4arm/README.md) |
| #32 固定源码与算法矩阵 | 已完成 | 10 个固定来源、37 条符号/测试行为观察和机器复核器。[源码审计](audits/SOURCE_AUDIT_32.md) · [算法矩阵](audits/ALGORITHM_MATRIX.md) |
| #33 目标相关增量响应 planner | 已完成 | 三类请求分布、未来概率、五种策略、OOD 边界、564 个决策、765 个 in-domain 候选、100 个外部几何 inventory 案例和独立 replay。[实验](experiments/attribution_4arm/README.md) |

#31 的缓存 patch 是最小后端因素，不构成新的物理求解器。#33 的 planner 结论限定为当前 17 个小分子和预登记请求模型。自然生产请求、较大体系和新的物性仍需要新的协议一致资产及独立质量证据。

## 总控后续 issues #34–#42 的阶段产物

| Issue | 阶段状态 | 产物 |
|---|---|---|
| #34 10× claim gate | falsified/partial | [10× 决策](decisions/0006-nature-10x-claim-gate.md) · [profile](performance/attribution_profile.json) |
| #35 benchmark contract | 合同冻结，规模阻塞 | [benchmark_contract.md](performance/benchmark_contract.md) · [contract JSON](performance/benchmark_contract.json) |
| #36 GPU4PySCF/PySCF | 项目 baseline 与 v1.9.0/v1.9.2 tags 已取得，上游执行阻塞 | [gpu4pyscf.md](audits/gpu4pyscf.md) · [coverage](audits/gpu4pyscf_source_coverage.csv) · [release tags](environment/gpu4pyscf-20261122/release-tags.json) · [环境](environment/gpu4pyscf-20261122/baseline.json) |
| #37 profiling | 阶段 baseline 完成 | [profiling](performance/profiling.md) · [profile JSON](performance/attribution_profile.json) |
| #38 PreparedPropertyBatch | planner/producer 控制完成 | [实验入口](experiments/prepared_property_batch/README.md) |
| #39 response asset compiler | identity/证书 planner 完成 | [实验入口](experiments/response_asset_compiler/README.md) |
| #40 Hessian/CPKS | CPU/GPU/FD micro controls 完成 | [实验入口](experiments/hessian_cphf/README.md)；VeloxChem 和多样本共享运行时仍未完成 |
| #41 scale/ablation | partial-falsified | [状态](performance/scale_ablation.md) · [计划 JSON](performance/scale_ablation_plan.json) |
| #42 release/claim gate | partial release package | [release checklist](release/release_checklist.md) · [claims.csv](release/claims.csv) |

这些阶段产物保留了未取得的资产、未运行的 profiling 和未知成本。它们不把 partial 结果写成所有验收条件已满足。
