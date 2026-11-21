# QM9 独立 CPHF 参照和标签迁移

v2 对 17 个固定候选的 153 项响应逐条给出结果。12 份基态的 108 项通过独立数值验收。另 5 个构型缺少合格零场态，对应 45 项保留空值与原始原因。v1 的 37 项继续合格，原先仅因 CPHF 差值超限的 71 项均在新测量后取得资格。发布门槛仍为解析读出 1e−8、两档有限场各 1e−4。[新发布表](response-labels.jsonl) · [逐目标迁移含两版读出与散列](migration.csv) · [v1 原始发布表](../qm9_extension/response-labels.jsonl)

## 为什么这批资格发生了变化

在 qm9-000010 上重新积分 AO 场和读出、独立收敛零场及正负外场。其 77 维响应矩阵的二范数条件数约 65.91。原 Krylov 算法用这套独立输入重现 v1 CPHF 标量，最大绝对差 1.30×10⁻¹³。最后记录的子空间新方向范数为零，但把解代回未预条件 AO 方程，仍得到下表中的残差。[全部 RHS、解向量、读出与终止信息](seed/oracles/qm9-000010.json) · [v1 参照原件](../gqc_dual_response/oracles/qm9-000010.json)

| 电场 | 原 Krylov 解的物理残差 L2 | 稠密解的物理残差 L2 |
|---|---:|---:|
| x | 1.67515×10⁻⁵ | 1.68×10⁻¹⁵ |
| y | 1.50623×10⁻⁶ | 2.70×10⁻¹⁵ |
| z | 1.66534×10⁻⁵ | 9.87×10⁻¹⁶ |

x 场的 zz 分量最能看到这一差异。原 CPHF 为 5.408012190293，稠密解为 5.408018249818，相差 6.06×10⁻⁶。八个原拒绝项全部有独立解、直接与伴随结果和两步长有限场作逐项对照。三轴上的 q0、r2、zz 九项均通过。在固定版的三列块实现中，最后一次 QR 没有保留新方向时日志范数等于零。这一终止分支覆盖 12 个分子中的 8 个，含 qm9-000010。另 4 个在日志范数仍介于 1.21×10⁻⁷ 与 2.15×10⁻⁷ 时触发 1e−13 的平方范数阈值。跨 12 份有态分子，稠密解最大的物理残差为 3.61×10⁻¹⁵，最大的目标读出数值误差估计为 1.66×10⁻¹¹。直接或伴随与独立 CPHF 的最大绝对差为 8.07×10⁻¹²，两档有限场与它们的最大差为 3.96×10⁻⁵。各分量按自己的单位比较。[门槛、方程及估计适用范围](protocol.md) · [首批索引](seed/index.json) · [留出索引](extension/index.json)

最小二维控制在 tol=1e−12 时返回有限解 [1,0]，实测残差为 2e−7。发布器对旧版本、超限残差、读出误差预算不足和缺失精度证据分别返回 oracle_unqualified，保留候选原值。通过参照资格后，错误的候选值触发单独的 withheld 状态。另在固定 PySCF 源码上执行了三个上游 Krylov 测试（多个 RHS、零 RHS 和 level shift），三个均通过。[重新实算的分子和合成控制](controls.json.gz) · [控制入口](../../../../../scripts/check_cphf_reference.py)

## 这次核验花费的工作

| 发布参照阶段 | 全批实际消耗 |
|---|---:|
| 12 次 GQC 建模 | 60 J/K |
| GQC 直接及伴随盲算 | 1,237 + 1,227 J/K，72 列 RHS |
| PySCF 零场与正负有限场 | 156 次 SCF，7,582 个周期，7,894 次 J/K |
| PySCF 原 Krylov 对照与两种解的物理残差检查 | 102 批 J/K，290 列密度 |
| 独立稠密方程 | 24 次 AO→MO 积分变换、12 次 SVD、12 组稠密求解共 36 个 RHS |

两批分别在单线程 CPU 上运行，全部分子的建模、求解及验收累计墙时 36.37 秒。GQC 的算子作用和 PySCF 的批 J/K 有各自的列计数。表中为发布参照的实际工作。另一次 qm9-000010 回归的科学费用在 controls.json.gz；同一环境的 PR 回归会再产生费用。两次生产的零场输入仍来自 n5 作业 2046、2047，五份既有缺态记录有各自的失败成本。[按分子分项账本](qualification-costs.json) · [首批事件](seed/events.jsonl.gz) · [留出事件](extension/events.jsonl.gz)

普通 CLI 先用审查提交从空 SQLite 重建整批 v1，再将同一数据库及 v1 生产批交给 v2。37 条旧历史记录因目录摘要不同被剔除。迁移时 12 份有态分子都重新计算，各版分别支付 60 次准备 J/K、1,237 次后轮 J/K、36 个 RHS。随后分别重开 v2 数据库、把 v2 实测历史导入空库，两次均服务 108 项，新增科学调用为零。5 份缺态在四次运行都返回原原因。回执与 SQLite 逐项比对，退出码 1 对应完整批次中的 45 项缺态。[四批回执与散列](cli/cache-replay.json) · [迁移批原始输出](cli/v2.json.gz)

新资格改变了可参与扣除的历史。十个受控掩码下，严格标量策略的后轮 J/K 从普通块的 12,370 降至 10,371，节省 16.16%。计入共同的 8,917 次历史生产为 21,287 对 19,288，节省 9.39%。可保存方向向量时后轮为 7,102 次。留出八份有态分子的三个对角请求合计 24 项，正式标量路径为 1,000→518 J/K，向量路径为 24 次。实验中获得完整独立参照的费用已单列；计算生产净收益还需要实际资产、请求与在线质量证据。[600 组正式计划的变化](cohort/README.md) · [向量、手写和预取对照](planning/README.md)

## 复现

从仓库根目录使用已锁定的 GQC、PySCF 源码及 CPU 环境。每次给驱动新的输出目录。归档的 index.json 是驱动生成的 summary.json 原始字节。当前输入、版本、代码/二进制散列及线程数见两份索引。[统一环境及自动检查](../../../../../README.md#响应验证)

```bash
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
e=handoff/gqcdataset_codex_goal/research/experiments
python scripts/probe_gqc_dual_response.py --index "$e/qm9_response_assets/index.json" --out .work/new-reference-seed
python scripts/probe_gqc_dual_response.py --index "$e/qm9_extension/assets/index.json" --out .work/new-reference-extension
python scripts/check_cphf_reference.py --out .work/new-cphf-controls
python3 scripts/summarize_cphf_migration.py --out .work/new-migration-tables
git worktree add --detach .work/v1-reviewed faf93dd4a95d9a12ee06bdcf85040ecb38d9107b
mkdir -p .work/v1-reviewed/_references
ln -s "$PWD/_references/gqc" .work/v1-reviewed/_references/gqc
python "$e/cphf_v2/replay_cache.py" --v1-checkout .work/v1-reviewed --out .work/new-cache-migration
```
