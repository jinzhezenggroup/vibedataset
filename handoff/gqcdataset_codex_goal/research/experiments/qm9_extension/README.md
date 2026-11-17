# QM9 剩余 11 个合格候选几何的外推

已按事前登记处理首轮以外的全部 11 个 QM9 几何。加上首批 6 个，这覆盖固定 1–3 个非氢原子筛选下的全部 17 个候选。每个分子请求相同的 3 个观测量对 3 个电场的导数。数据表共有 153 个唯一目标，其中 37 个有通过独立检验的数值，71 个保留原始响应与差异，45 个缺合格零场态。对外的 value 只在通过时填写。这是基于 QM9 几何新算的 RHF/STO-3G 派生列。[直接读取 153 行 JSONL](response-labels.jsonl) · [筛选与实验预登记](protocol.md) · [首批 6 例](../response_planning/README.md)

## 哪些已有信息真的能少算

下表为新增 11 个分子的第二轮。三份参考态生产时独立外部稳定性检查未通过，另外 8 份均执行了响应求解。每份预期补三项，对角缺项分母为 33。严格发布路径共得到 3 个合格对角值，各策略发布相同的结果。所有试验的原始程序、算子、FP64 精度及残差阈值都固定。[逐策略工作量和全部时间、字节](costs.csv)

| 进入第二轮时的资产 | 第一轮 J/K | 第二轮新 RHS | 第二轮 J/K | 两轮 J/K |
|---|---:|---:|---:|---:|
| 已发布标量，直接计算缺项 | 1,000 | 24 | 1,000 | 2,000 |
| 已发布标量，信息够时尝试组合场 | 1,000 | 24 | 1,000 | 2,000 |
| 同时存完整场方向解并做物理复核 | 1,000 | 0 | 24 | 1,024 |
| 首轮预取完整标量表，后轮重试未过项 | 1,000 | 21 | 956 | 1,956 |
| 删除可复用标量的消融 | 1,000 | 24 | 1,000 | 2,000 |

这 8 份档案没有一份保有足以减少 RHS 的合格标量组合，规划器全部转回直接求解。与首批 6 例合并，严格标量路径后轮 1,237→1,216 次 J/K，省掉的 21 次全部来自首批。完整方向向量在外推中仍有直接价值。写入 74,222 字节向量与 2,364 字节标量，后轮重新读取并做 24 次 J/K 检查，花 0.041 s；只存标量并直接重算花 1.248 s。这两个时间是同一 CPU 环境上的单次轮内观测。[原始策略执行](scalar-summary.json.gz) · [原始操作日志](scalar-events.jsonl.gz)

### 隔离 GQC 同一算子的计算量

另对这 8 份参考态从头运行同一个 GQC 算子，把其实际算出的六个非配对项写入专用诊断文件。重新读取后，用一个 x+y+z 组合电场和同读出的两次扣除恢复三个配对项。直接对照从空向量缓存做三轴 block，核与精度相同。两条路径都做真实残差检查。此对照在观察外推独立门槛后登记，计算前已固定误差判据。[登记时序](protocol.md) · [诊断驱动](../../../../../scripts/probe_response_equivalence.py)

- 八个分子逐一少做了 J/K。合计新 RHS 从 24 降至 8，后轮 J/K **1,000→518，减少 48.2%**。六个历史标量若需从头获取，第一轮另有共同的 1,000 次 J/K，两轮为 2,000→1,518。另有共同建模/算子检查 40 次。组合场耗时含读取操作数并执行扣除，累计 0.478 s，直接求解累计 1.110 s。写出的操作数文件占 17,997 字节。[分子逐项成本](same-operator-costs.csv)
- 24/24 个诊断标量在事前指定的 1e−8 同算子阈值内重现直接求解，各读出均在自己的单位内比较，最大差 7.62×10⁻¹²。独立验收的对角值仍为 3 个。诊断文件从未写进发布标签缓存，产出行数保持原样。[诊断算子、操作数、差异和运行 SHA](same-operator.json.gz) · [事件日志](same-operator-events.jsonl.gz)

## 计算来源与实耗

n5 的 RTX 5090 作业 2047 批量产生 11 个能量，GQC 实际用了 139 个 SCF 周期、141 次 Fock 构建。独立 PySCF 基态求解用 11 次 SCF、共 498 个周期。000004、000006、000012 的独立参考态外部稳定性未通过。程序完成 11 份报告后按协议退出 1，Slurm 记录 FAILED、8 秒、零重启，8 对合格的 JSON/NPZ 共 5,780,168 字节。此前同一环境作业 2046 的首批 6 份独立计费。[n5 环境](../../../../../docs/N5_GQC.md) · [2047 回执](n5-job.json) · [逐行基态与指纹](assets/index.json) · [日志](n5-events.jsonl.gz)

这 8 份外推态均在本地 CPU 上运行原生 GQC 编译响应和独立基准。三场与三读出分别用 1,000、990 次 J/K，另有 40 次共同建模 J/K。独立验收用 104 次 PySCF 自洽场、4,823 个周期、5,031 次 SCF J/K，以及 8 个 CPHF block（56 个 J/K 回调、160 个密度列）。外推的 99 个分量中 9 个合格、63 个有实测诊断、27 个缺基态。五个存档策略实际重放 40 条轨迹，另计 8,980 次策略 J/K、40 次建模 J/K、28.58 s。额外同算子对照和独立用户入口各有自己的运行回执。最初一次启动误用了仅装 sccache 的解释器，在导入 NumPy 时退出，未发生 SCF 或 J/K，随后用锁定的科学环境完成。[独立基准索引与八份原始观测](oracle-index.json) · [成本总表](verification.json)

## 读取与复现

将同一批 99 条真实请求经过持久缓存 CLI，逐项与独立结果表核对，9/63/27 个状态和全部发布值完全一致。该次新数据库用 40 次建模与 1,000 次响应 J/K，墙时 17.81 s。返回码 1 表示清单中有暂缓或缺态记录，完整输出已经写出。重复请求、并发、原子提交和历史标量文件的使用见 CLI 文档。[实测请求](requests.jsonl) · [实测客户端输出](cli-result.json.gz) · [输入、缓存和复用历史](../response_dataset_cli/README.md)

在仓库根目录执行，使用首批实验记录中的独立 Python 环境。n5 几何选择增加 `--remaining-from`，完整复扫同一发布文件，逐层核对首批记录原文和 SHA，再选择余下成员。重新调度可沿用作业 2046 的分发命令，将 cohort 路径改为本目录的 cohort.json，并作为 sbatch 脚本的第一个参数；作业 2047 的输入摘要在本目录中。

```bash
e=handoff/gqcdataset_codex_goal/research/experiments
python3 scripts/select_qm9_assets.py --cache .work/qm9_source --remaining-from "$e/qm9_response_assets/cohort.json" --out .work/qm9-unseen-cohort.json
python3 scripts/summarize_qm9_extension.py --out .work/qm9-unseen-verified
cmp "$e/qm9_extension/response-labels.jsonl" .work/qm9-unseen-verified/response-labels.jsonl
source .work/response-reproduction-env/bin/activate
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
python scripts/probe_gqc_dual_response.py --index "$e/qm9_extension/assets/index.json" --out .work/qm9-unseen-oracle-new
python scripts/probe_scalar_response.py --assets "$e/qm9_extension/assets" --oracles "$e/qm9_extension/oracles" --out .work/qm9-unseen-scalar-new
python scripts/probe_response_equivalence.py --assets "$e/qm9_extension/assets" --oracles "$e/qm9_extension/oracles" --out .work/qm9-unseen-same-operator-new
python scripts/complete_response_dataset.py --requests "$e/qm9_extension/requests.jsonl" --source-index "$e/qm9_extension/assets/index.json" --oracle-index "$e/qm9_extension/oracle-index.json" --cache-db .work/qm9-unseen-new.sqlite --out .work/qm9-unseen-client-new.json
```

全量 17 例仅代表这个重原子数范围和这三种读出。本次实测区分了同算子工作节省、实际可复用资产是否齐全、以及最终目标的独立资格。真实生产的缺失模式及请求频率仍待观察。
