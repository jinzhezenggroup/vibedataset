# gqcdataset 当前状态

更新于 2026-11-18，工作分支 `codex/source-intake-20261118`。当前首要目标是用 GQC 科学编译器在同一精度和物理定义下减少补全数据所需的量化工作。数值异常单列输入、差值和命令，保留给用户向 GQC 项目反馈。[草稿 PR #10](https://github.com/jinzhezenggroup/vibedataset/pull/10) · [结果与全成本](RESULTS.md)

| 本轮产物 | 已核验的结果 |
|---|---|
| 部分已知标量的剩余程序 | GQC 已能把适合已知标签的二轴／三轴组合场与剩余普通列放入同一原生块。n5 单核作业 2048 的水分子对照为 36→20 次 J/K，普通三轴 22 次。全部 17 例、10 种受控模式中，正式合格历史的后轮 12,370→12,319，同算子诊断为 12,370→10,371。较少 RHS 仍可能多花一次 J/K，完整方向解、普通块和两个混合种子的竞争结果均保留。[研究报告](experiments/partial_response_blocks/README.md) · [前置与后续费用](experiments/partial_response_blocks/cohort/costs.csv.gz) |
| GQC 响应数据与工具 | QM9 官方源 133,885 条中，按规则取到的全部 17 个候选对应 153 个唯一目标。37 个通过独立门槛，71 个保留原始响应，45 个缺可用基态。清单 CLI 支持持久标量/向量、可验证的历史标量、独立拒绝及原子恢复。[153 行数据](experiments/qm9_extension/response-labels.jsonl) · [CLI](experiments/response_dataset_cli/README.md) |
| 已有标量怎样进入剩余程序 | 首批三份基态的 9 个缺项用一次组合场和已验收标量扣除，边际 J/K 合计 93→72。另 11 个留出分子在原发布门槛下没有足量标量可扣，严格路径 1,000→1,000。单列同 GQC 算子诊断时，外推 8 份有效基态、24 个缺项的 J/K 从 1,000 降到 518，最大差 7.62×10⁻¹²。原始资格保持可查。[首批](experiments/response_planning/README.md) · [外推](experiments/qm9_extension/README.md) |
| 多轮与强基线 | 四份初始可计算基态，短请求的混合策略 206 次 J/K、完整预取 237 次；密集扩展为 516 对 237 次。外推保留有效方向解时后轮只需 24 次复核，发布同样三个对角标签。水与 LiH 早期 42 项中 31 项通过。[规划成本](experiments/response_planning/planning-costs.csv) · [早期实验](experiments/gqc_residual_multiround/README.md) |
| 可用算力与环境 | n2 作业 5381/5382 做过跨节点种子验证，n5 持久环境及作业 2044/2045 已交付 13 行通过的能量。n5 RTX 5090 在 2046/2047 中实算全部 17 个 QM9 分子，分别用 77 和 141 次 Fock；独立核验共保留 12 对参考态，其余五份的终态与成本均可追溯。[n5 环境](../../../docs/N5_GQC.md) · [2046](experiments/qm9_response_assets/job-2046.json) · [2047](experiments/qm9_extension/n5-job.json) |
| 前人源码 | 45 个固定 Git 快照、268,259 条索引；125 条有证据的审读观察涉及 119 个文件。完整阅读标记 23 个，88 个有行为追踪，46 个含已执行路径。另有 Materials Cloud 正式归档 915 个文件、267 个目录，逐成员核对；五个原始实现位置仍缺。已有实现包括 Schofield 属性插补、QCManyBody、OpenMDAO/CppAD、pyMOR、PySCF 伴随和 mlelec 作者归档。[锁和源码索引](SOURCE_INDEX.md) · [审计矩阵](PRIOR_ART_MATRIX.md) · [核验](ledger_validation.json) |
| 真实既有资产 | 已读取 13 份 QCFractal fixture、357 行 ANI 记录及学习/工作流工程。固定态后处理、真实缺失组合分量、统计预测和新耦合响应有独立的定义、正反例和成本记录。[资产](DATASET_ASSETS.md) · [总结果](RESULTS.md) |
| 原交接材料 | 在用户本机找回 44 页历史讨论和 3 页矢量设计稿，两份已逐字节核对并与重建文本比较。原 ZIP 仍待取得。[原件与对照](../attachments/README.md) |

## 任务验收与剩余范围

| Issue | 阶段验收依据 |
|---|---|
| #1 | 科研队列 #2–#8 已有可复核产物和决定。五条主线后续可扩展，独立附件 #9 保留原 ZIP 缺口。[第二轮决定](decisions/0002-scalar-and-vector-response.md) |
| #2 | 45 份所选 Git 全树和正式归档有锁、完整性与覆盖复验。五项原始来源阻塞及论文版本/许可证/外部资产边界保留。[来源缺口](SOURCE_GAPS.md) |
| #3 | 基础能力与科学依赖、实现图、原生算子与拒绝/运行证据已提交。[工作基础](FOUNDATION_CAPABILITIES.md) |
| #4 | 已完成与本轮路线直接相关的源码审计、强基线及可执行反例，包括正版归档与后续适配的分别核对。[对照矩阵](PRIOR_ART_MATRIX.md) · [基线](BASELINES.md) |
| #5 | 真实记录/几何、原有 NA 与受控遮蔽、逐项协议和成本记录可复核。[资产与评价](EVALUATION_PROTOCOL.md) |
| #6 | 五主线与竞争解释可查，选择过的两步研究路径均保留预登记和停止条件。[路线](ROUTE_COMPARISON.md) |
| #7 | 已实现编译的分子求解、外部交叉验证、失效处理、可持续的清单式补全入口。[独立基准](experiments/gqc_dual_response/README.md) · [实现入口](../../../scripts/complete_response_dataset.py) |
| #8 | 完成首批规划和全部未见候选的外推，归档全部分母、前期和后续成本、失败/正负结果、竞争策略及多进程保存恢复。[外推报告](experiments/qm9_extension/README.md) · [资产策略](ASSET_POLICY.md) |
| #9 | 两份 PDF 已核验。原 ZIP 未在已查范围内取得，继续单独跟踪。[资料核对](../attachments/README.md) |

这些数字来自受控三轴与三读出、固定的小分子协议。生产请求的自然到达分布、更大体系和不同物理算符的净收益尚未测量。数值差异供用户向 GQC 反馈，后续可以复用本轮协议、资产和输入输出。
