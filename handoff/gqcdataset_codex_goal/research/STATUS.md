# gqcdataset 当前状态

更新于 2026-11-22。PR #10 已进入 `main`，PR #24 汇总了 #17–#19，PR #29 承载复评后的 #25–#27。PR #29 的远程科学验证 run `44922545190` 全部通过。[PR #24](https://github.com/jinzhezenggroup/vibedataset/pull/24) · [PR #29](https://github.com/jinzhezenggroup/vibedataset/pull/29) · [结果与全成本](RESULTS.md)

| 本轮产物 | 已核验的结果 |
|---|---|
| 盲验的目标质量 | 符合协议的留出分子有 24/33 个请求在完整真值封存时取得可审核的接受决定，独立评分全部通过，9 项缺态。量化历史触发 16 次精修；只知道旧值时保留 16 个依赖项的未知质量。[验收与费用](experiments/target_quality/README.md) |
| 真实资产与强基线 | 公开 QM9、QCArchive、Psi4 与实际水表均经核查，范围内没有合格的第三方旧标量或自然请求。留出循环三目标的双场／手写后轮同为 824 次 J/K；当数值验收已组装稠密矩阵时，按需稠密解和预取都更有竞争力。[资产](experiments/legacy_response_assets/README.md) · [全成本](experiments/response_benefit/README.md) |
| 独立 CPHF 及数据发布 | 对全部 12 份可用态重算直接／伴随、独立零场和两档正负场。153 项中 108 项通过、45 项缺态。原来仅因 CPHF 被拒的 71 项均有逐项证据。未预条件物理残差最大 3.61×10⁻¹⁵。[资格迁移](experiments/cphf_v2/migration.csv) · [新数据](experiments/cphf_v2/response-labels.jsonl) |
| 部分已知标量的剩余程序 | 十种掩码中，普通块／标量方案的后轮 J/K 为 12,370／10,371，含共有历史生产为 21,287／19,288。保存方向向量的后轮为 7,102。原 v1 的 12,319 次属于旧资格。七个氨掩码仍有少一列却多一次 J/K 的反例。[逐策略与成本](experiments/cphf_v2/cohort/README.md) |
| 既有标量与强基线 | 首批四份有态的三个对角请求合计 12 项，后轮 237→162 次 J/K；留出八份的 24 项为 1,000→518。留出保留方向向量时后轮 24 次，首轮预取全表后为零。首批稀疏流混合留存／预取为 206／237，密集为 516／237。[首批及留出重放](experiments/cphf_v2/planning/README.md) |
| 缓存与失败 | 跨版本迁移重新计算 108 项，另开进程重取或从 v2 生产批导入时均为零新 RHS。模型构造中断、普通块失败及双重失败都有可复核的实际费用，科学表回滚、重试和重开均有进程级回归。[缓存迁移](experiments/cphf_v2/cli/cache-replay.json) · [失败回执](experiments/response_dataset_cli/failure_costs/verification.json) |
| 可用算力与环境 | n2 作业 5381/5382 做过跨节点种子验证，n5 持久环境及作业 2044/2045 已交付 13 行通过的能量。n5 RTX 5090 在 2046/2047 中实算全部 17 个 QM9 分子，分别用 77 和 141 次 Fock；独立核验共保留 12 对参考态，其余五份的终态与成本均可追溯。[n5 环境](../../../docs/N5_GQC.md) · [2046](experiments/qm9_response_assets/job-2046.json) · [2047](experiments/qm9_extension/n5-job.json) |
| 前人源码 | 46 个固定 Git 快照、268,477 条索引；141 条有证据的审读观察涉及 126 个文件。完整阅读标记 27 个，94 个有行为追踪，51 个含已执行路径。另有 Materials Cloud 正式归档 915 个文件、267 个目录，逐成员核对；五个原始实现位置仍缺。已有实现包括 Schofield 属性插补、QCManyBody、OpenMDAO/CppAD、pyMOR、PySCF 伴随和 mlelec 作者归档。[锁和源码索引](SOURCE_INDEX.md) · [审计矩阵](PRIOR_ART_MATRIX.md) · [核验](ledger_validation.json) |
| 真实既有资产 | 已读取 13 份 QCFractal fixture、357 行 ANI 记录及学习/工作流工程。固定态后处理、真实缺失组合分量、统计预测和新耦合响应有独立的定义、正反例和成本记录。[资产](DATASET_ASSETS.md) · [总结果](RESULTS.md) |
| 原交接材料 | 在用户本机找回 44 页历史讨论和 3 页矢量设计稿，两份已逐字节核对并与重建文本比较。用户已取消原 ZIP 的交付要求。[原件与对照](../attachments/README.md) |

## 任务验收与剩余范围

| Issue | 阶段验收依据 |
|---|---|
| #1 | #2–#9 为历史阶段验收，审查后由 #11–#15 接续。[第二轮决定](decisions/0002-scalar-and-vector-response.md) |
| #2 | 45 份所选 Git 全树和正式归档有锁、完整性与覆盖复验。五项原始来源阻塞及论文版本/许可证/外部资产边界保留。[来源缺口](SOURCE_GAPS.md) |
| #3 | 基础能力与科学依赖、实现图、原生算子与拒绝/运行证据已提交。[工作基础](FOUNDATION_CAPABILITIES.md) |
| #4 | 已完成与本轮路线直接相关的源码审计、强基线及可执行反例，包括正版归档与后续适配的分别核对。[对照矩阵](PRIOR_ART_MATRIX.md) · [基线](BASELINES.md) |
| #5 | 真实记录/几何、原有 NA 与受控遮蔽、逐项协议和成本记录可复核。[资产与评价](EVALUATION_PROTOCOL.md) |
| #6 | 五主线与竞争解释可查，选择过的两步研究路径均保留预登记和停止条件。[路线](ROUTE_COMPARISON.md) |
| #7 | 已实现编译的分子求解、外部交叉验证、失效处理、可持续的清单式补全入口。[独立基准](experiments/gqc_dual_response/README.md) · [实现入口](../../../scripts/complete_response_dataset.py) |
| #8 | 完成首批规划和全部未见候选的外推，归档全部分母、前期和后续成本、失败/正负结果、竞争策略及多进程保存恢复。[外推报告](experiments/qm9_extension/README.md) · [资产策略](ASSET_POLICY.md) |
| #9 | 两份 PDF 已核验。用户于 2026-11-18 明确取消原 ZIP 要求，按此验收。[资料核对](../attachments/README.md) |
| #11 | 独立精度、两版本数据与缓存失效、十个掩码的重新计量已提交。[核验与费用](experiments/cphf_v2/README.md) |
| #12 | 科学表和费用回执分别核验；117 个完成、2 个失败的旧尝试已按 ID 去重核查。[失败核查](experiments/response_dataset_cli/failure_costs/reviewed-archive.json) |
| #13 | 归档一致性与实际分子 CPU 计算有独立入口、预期的拒绝控制和逐项原始报告。[检查与复现](experiments/response_ci/README.md) |
| #14 | 科学入口、精修/拒绝、近奇异反例、独立盲验、受控的严格离散界与密集强基线已实测。[生产与评分](experiments/target_quality/README.md) · [精确矩阵界](experiments/represented_matrix_bound/README.md) |
| #15 | 完成资产、单／双场、最强手写和留存／预取的同质量比较，记录预算与停止条件。[实测](experiments/response_benefit/README.md) · [研究决定](decisions/0004-blind-evidence-and-asset-budgets.md) |

这些数字来自受控三轴与三读出、固定的小分子协议。生产请求的自然到达分布、更大体系和不同物理算符的净收益尚未测量。当前科研 issues 的验收产物已经齐备，后续扩大范围仍需新的协议一致资产、请求流和独立质量证据。数值差异供用户向 GQC 反馈，后续可以复用本轮协议、资产和输入输出。

## 当前科研 issues（2026-11-21）

| Issue | 状态 | 证据 |
|---|---|---|
| #17 目标相关信息充分性 | 已完成。有限多混合场与手写双场完全等价，保留水/氨反例和 32 条留出重放。 | [information_sufficiency](experiments/information_sufficiency/README.md)，提交 `ec23b99` |
| #19 目标导向误差证书 | 已完成。残差/对偶误接受控制、SVD 覆盖、严格界非覆盖、稠密回退和全成本已汇总。 | [error_certificates](experiments/error_certificates/README.md)，提交 `bc6e2a2` |
| #18 跨协议资产边界 | 已完成。方法、基组、开放壳层、AO 表示和冻结/弛豫响应分类与独立 PySCF 重算已完成，Psi4 目标级交叉对照也已重放。 | [cross_protocol](experiments/cross_protocol/README.md)，提交 `906e923` |

## 复评后科研 issues（2026-11-21）

| Issue | 当前证据 | 剩余验收 |
|---|---|---|
| #25 独立手写基线与搜索完备性 | 独立手写 field/adjoint 已运行 96 条记录，四列候选 15 个，`multi4` 选择与三列搜索相同，全部输出通过。CI 已重放。[结果](experiments/information_sufficiency/issue25/README.md) | 已完成，提交 `906e923` |
| #26 算子级误差证书 | 10 维全空间基向量、4 个随机探针、6 个 RHS 和最小奇异方向已由生产器/独立评分器复核。近奇异与非对称控制均降级。CI 已重放。[结果](experiments/error_certificates/operator_probe/README.md) | 已完成，提交 `906e923` |
| #27 响应资产迁移盲验 | 序列化 RHF/STO-3G `direct_reuse`、跨基组初猜、DFT 精修、开放壳层拒绝和低间隙证据不可得均已独立评分。CI 已重放。[结果](experiments/cross_protocol/response_migration/README.md) | 已完成，提交 `906e923` |

## 2026-11-22 新增研究 issues

| Issue | 已完成证据 | 限制与结论 |
|---|---|---|
| #31 四臂核心方法归因 | A–D 在同一封存 manifest 上各有 51 条请求级记录。官方/patch 后端与 native/GQC 编排分别运行。独立官方 GPU4PySCF 进程重算 204 条目标和 AO 密度，四臂 51/51 通过。[原始记录与评分](experiments/attribution_4arm/README.md) | GQC 资产规划把 RHS/operator rows 降到约 0.83 倍几何均值，但本轮缓存 patch 没有端到端收益，D 相对 C 更慢。结论限定为 17 个 RHF/STO-3G 小分子和三条受控轨迹。 |
| #32 固定源码与算法矩阵 | 10 个固定 checkout、37 条关键符号/测试观察、提交和许可证由 `scripts/check_source_audit_32.py` 复核。行为边界和 #31 A–D 映射见 [SOURCE_AUDIT_32](audits/SOURCE_AUDIT_32.md) 与 [ALGORITHM_MATRIX](audits/ALGORITHM_MATRIX.md) | 五个外部路线仍是参照或强基线。它们的输出不被当作同一 CPHF 科学标签。 |
| #33 目标相关增量响应 planner | 预登记三类请求分布、三个未来概率和五种候选策略，生成 564 个决策、765 个 in-domain 候选，含 111 个几何/方法/状态 OOD 控制和 100 个外部几何 inventory 案例。独立 replay 通过。[四臂 planner](experiments/attribution_4arm/README.md) | 外部 inventory 只支持协议拒绝计数，没有响应标签。planner 输出 cost–coverage–risk frontier，不能替代响应级独立评分。自然生产请求分布和更大体系仍未测量。 |

## 2026-11-22 总控后续 issues #34–#42

| Issue | 当前状态 | 证据与未满足门槛 |
|---|---|---|
| #34 10× claim gate | 已形成 falsified/partial 结论 | `performance/attribution_profile.json` 显示官方后端 GQC 相对 native 约 1.09×，paired CI 下限未超过 1。10× 主张被拒绝，见决策 `0006`。 |
| #35 benchmark contract | 已冻结合同，规模目标阻塞 | 3 个微型控制、306 条中型受控请求、完整 timing schema 和 source_kind ledger 已有。自然请求流为 0，1000 条协议一致资产未取得。 |
| #36 GPU4PySCF/PySCF 审计 | 项目 baseline 已完成，完整上游复现部分阻塞 | 固定 2 个源码 commit、18 行覆盖和 n2 官方 baseline 已提交。完整上游 suite、v1.9.0/v1.9.2 release tag、CUPTI/Nsight 仍未知。 |
| #37 profiling | 阶段 baseline 已完成 | A–D 成本与 paired CI、未知字段清单已归档。GPU event、occupancy、FLOPs、峰值内存和能耗尚未采集。 |
| #38 PreparedPropertyBatch | planner/producer 边界已实现 | 同协议 bucket、单条失败隔离和 workspace fallback 已有 CPU 控制。真正跨样本 resident GPU runtime 尚未宣称。 |
| #39 response asset compiler | identity planner 和证书边界已实现 | 17 direct、2 refine、1 reject 的无 oracle 计划和独立 replay 已有。GPU 资产编译与独立质量 scorer 仍需扩展。 |
| #40 Hessian/CPKS | CPU micro controls 已完成 | H₂O/NH₃/LiH RHF 与带电 UHF 4/4 CPU controls 通过。IR/Raman、GPU Hessian、VeloxChem 和 FD 交叉检查未运行。 |
| #41 scale/ablation | partial-falsified | 17 几何、51 请求完成。1000-row 资产、第二 GPU 和十项 profiling/消融仍阻塞，10× gate 不成立。 |
| #42 release/claim gate | 可复现 partial 发布包已形成 | `research/release` 提供 9 个 artifact SHA、12 条 claims 和 6 个 unknowns。未知项未被隐藏，不能作为最终 Nature claim。 |
