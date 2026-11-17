# gqcdataset 当前状态

更新于 2026-11-18，工作分支 `codex/source-intake-20261118`。当前首要目标是用 GQC 科学编译器在同一精度和物理定义下减少补全数据所需的量化工作。数值异常单列输入、差值和命令，保留给用户向 GQC 项目反馈。[草稿 PR #10](https://github.com/jinzhezenggroup/vibedataset/pull/10) · [结果与全成本](RESULTS.md)

| 本轮产物 | 已核验的结果 |
|---|---|
| GQC 三轮响应补全 | 42 个标量请求，水 21 项及 LiH 10 项发布，11 项保留诊断。水三轮 J/K 为仅存标签 76 次、按需程序 54 次、手写按需 54 次、预取三轴 38 次；首次全流程未见加速。[数据](experiments/gqc_residual_multiround/response-labels.jsonl) · [报告](experiments/gqc_residual_multiround/README.md) |
| n5 能量新列 | 13 行、5 个不同量化目标，全部通过独立 PySCF 对照。按目标身份去重使 Fock 构建从 131 降至 50，普通字典也取得此收益；原生批使调用从 5 降到 1。[CSV](experiments/n5_dataset_energy/labels.csv) · [运行记录](experiments/n5_dataset_energy/README.md) |
| n2 / n5 执行环境 | n2 作业 5381、5382 通过固定 H₂ 的 CP-001。n5 项目 venv 在新会话可用，RTX 5090 作业 2044 完成跨节点 checkpoint 验证，2045 完成实际新列；调度终态、实际 CDLL、参考和计数均有回执。[n2](experiments/checkpoint_probe/README.md) · [n5](../../../docs/N5_GQC.md) |
| 已有实现 | 新取得作者发布版 mol_prop_imputation 和 QCManyBody 全树。实跑发表权重信息不足反例及三轮 4/3/0 次 SCF 的多体基线。xTBloom 本地原生 CPU CTest、GQC 驻点与经验门槛测试、PySCF 跨基组投影已执行。[前人能力](PRIOR_ART_MATRIX.md) · [工作基础](FOUNDATION_CAPABILITIES.md) |
| 真实资产与负结果 | 13 份 QCFractal fixture、ANI 原始发布 357 行有字段级记录。三份存档态复现已有偶极；ANI 323 个真实空位全部缺少七个分量，另 34 个对照的公式值未通过发布标签门槛。[数据资产](DATASET_ASSETS.md) · [评价协议](EVALUATION_PROTOCOL.md) |
| 源码接管 | 38 份固定快照、264,598 条逐文件索引。20 个完整阅读标记、60 个文件含已追踪行为、30 个文件含已执行路径。这三种标记独立，仅表示记录中的具体文件或路径。新增匹配存档/运行的 Psi4、PySCF、默认 libcint 全树，xTBloom 补齐版本历史。[来源索引](SOURCE_INDEX.md) · [覆盖核验](ledger_validation.json) · [主张](claims.csv) |

## 任务验收与剩余问题

| Issue | 当前证据与剩余范围 |
|---|---|
| #1 | 首轮数据、代码和全成本归因已可复查。长期科研目标继续推进。 |
| #2 | 固定树、完整性、版本角色、子模块与 LFS 均可复核。6 个原始实现/资产入口及部分论文提交、许可证与外部构建依赖闭包继续跟踪。[缺口](SOURCE_GAPS.md) |
| #3 | 首轮基础能力地图、编辑式依赖图、源码和原生/编译器判别实验已有证据；各自后端、测试与尚未验证的域在记录中独立标识。[基础能力](FOUNDATION_CAPABILITIES.md) |
| #4 | 精确分量复用、插补、投影/后处理、批处理、缓存、响应和程序化简已建立对照。更广扰动下的子空间回收、降阶/伴随和原始实现映射仍需证据。[基线](BASELINES.md) |
| #5 | 有实际字段、缺失来源、标签语义、盲验与分组/成本协议，并已实跑代表性场景。[资产](DATASET_ASSETS.md) |
| #6 | 五条路线、竞争解释、首轮可证伪假设、停止条件及阶段决定已入库。[路线](ROUTE_COMPARISON.md) · [决定](decisions/0001-gqc-response.md) |
| #7 | 完成 GQC 最小分子闭环、同目标强基线、错误复用拒绝与独立验证，保留未通过项。[响应结果](experiments/gqc_residual_multiround/README.md) |
| #8 | 两份分子分三轮及 n5 五个唯一能量目标已核算。更广来源、不同扰动秩/到达顺序和独立分子队列的端到端收益尚未建立。[资产策略](ASSET_POLICY.md) |
| #9 | 原 ZIP 与两份历史 PDF 原件未取得，保持独立跟踪。公开论文的补充材料属于另一个来源。 |

下一项可判别问题是，未来目标未知时，按需生成剩余响应程序在什么条件下比预先求完整扰动基少做量化工作。现有三维均匀电场试验已给出有利于完整预取的实例；扩大前应锁定扰动定义、请求顺序、基线可获得的先验信息及每个真实算子调用的计数。源码审计和已取得的负结果继续作为约束。
