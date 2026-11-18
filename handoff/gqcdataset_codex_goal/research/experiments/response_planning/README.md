# 既有信息如何改变下一轮分子响应计算

下述规划结果和费用对应 v1。当前首批和留出均基于 v2 合格历史重放。[v2 规划与逐策略对照](../cphf_v2/planning/README.md)

用 QM9 发布的原始几何定义新的 conventional RHF/STO-3G 数据列。核固定，原点为 (0,0,0)，FP64 求静态均匀外场 x、y、z 下首原子 Mulliken 净电荷、电子二阶矩 〈Σr²〉 和电子 〈Σz²〉 的导数。电子响应保留诱导密度和相应 J/K，q0 的单位为 e/原子单位电场，r2 和 zz 为 Bohr²/原子单位电场。对 133,885 个源记录按事前规则分层，17 个满足化学筛选条件，8 个层中 2 层为空，6 个代表对应 54 个目标。4 份基态可计算，产生 36 个实测分量。其中 28 个通过独立验收，8 个有诊断值，另 18 个缺合格基态。机器可读输出保留全部 54 行、原因和来源 SHA，可以直接按分子、场、读出联结。[逐项数据](response-labels.jsonl) · [n5 入组与基态](../qm9_response_assets/README.md) · [独立数值证据](../gqc_dual_response/README.md)

## 历史只留下已验收标量

在同一个物理响应问题中，一次 x+y+z 电场的解允许读出三个量。若一个读出已有另外两轴的合格标量，对组合场读数减去这两项即可恢复第三轴。实际 GQC 程序将组合后的物理右端交给原求解器，再把存档的两个标量绑定到 FP64 减法程序。每个被减数必须对应同一读出、状态、场的尺度与原点。目标资格仍由直接、伴随、独立 PySCF CPHF 及两个步长的自洽有限场决定。[预登记](scalar_protocol.md) · [实现](../../../../../scripts/probe_scalar_response.py) · [实际算符和门槛](../gqc_dual_response/protocol.md)

先计算六个非配对项，再请求配对的 (x,q0)、(y,r2)、(z,zz)。以下数字累计 QM9 000001、000002、000003 三份有全部九个合格分量的参考态。第一轮的标量及状态从头实算、保存；第二轮重新从磁盘读取。J/K 计数覆盖求解和旧向量的物理复核，一次性建模和独立参考在下文单列。

| 两轮策略 | 首轮 J/K | 后轮新增 RHS | 后轮 J/K | 累计 J/K | 首轮保留字节 |
|---|---:|---:|---:|---:|---:|
| 保存六个标量，直接重算三轴 | 93 | 9 | 93 | 186 | 2,524 |
| 保存六个标量，组合场与扣除 | 93 | 3 | 72 | 165 | 2,524 |
| 同时保存完整场方向解 | 93 | 0 | 9 | 102 | 11,554 |
| 首轮求全九项并保存标量表 | 93 | 0 | 0 | 93 | 3,459 |
| 删除标量信息的消融，回到直接计算 | 93 | 9 | 93 | 186 | 先产生 2,524，再忽略 |

三分子的后轮分别为 41→24、30→30、22→18 次 J/K，共省 21/93（22.6%），9 个缺项全部通过原门槛。三种读出的 GQC 减法与手写 FP64 减法逐项相同。把未请求的项径直当零，会让 q0、r2、zz 的最大绝对偏差分别达到 1.89、11.02、1.72（各自的单位）。原始操作数、实际组合场与 CPHF 差异可回放。[校验及误差](verification.json) · [每分子原始记录](raw/plan002-first-summary.json.gz)

000010 只有一个合格的非配对标量，直接补算花费 144 次 J/K，三个缺项均被拒绝。计入它以后，两种只存标量的后轮共由 237 降到 216，累计成本由 474 降到 453。另两份代表未获得合格基态。以初始六份为分母，三项对角补全为 9/18，两个策略发布相同的分量。四个有态分子均拒绝了故意改错科学身份的旧标量。源数据只剩标量时能省下这些求解；若可以控制第一次写档，这批已知候选量中，提前多投影三个标量更便宜。[分母、时间和字节](scalar-costs.csv)

## 后续请求未知时的直接与伴随选择

场响应解和读出伴随解都能给出同一个目标。因此在只允许选这些端点的单位成本模型里，可以将本轮缺项视作二分图的边，用最小顶点覆盖选出最少的新增端点。首轮四个请求只需一个场与一个读出；纯直接或纯伴随都需三个端点。全部 32,768 个小图与已有端点组合都与独立穷举相符。实际算子迭代还取决于块 RHS、条件性和已有资产，端点数的保证只适用于该组合问题。[规划器](../../../../../scripts/response_cover.py) · [穷举验证](cover-check.json) · [成熟着色与代入基线](../../audits/response-dual-prior-coloring.md)

七种策略以相同的首轮、相同的候选字典、相同精度开始，每轮只接收当轮请求。稀疏轨迹在第二轮后停止（5 个唯一项，6 个请求）；另两条轨迹按场或按读出扩展，都填满 9 项。下表是实测 J/K，每格先列有态分子全部花费（含 000010 的拒绝），括号内是三份全矩阵合格分子的花费。这里各策略可记住自己已实际观察、且科学身份与散列仍匹配的独立参照拒绝。两个重复运行的算子计数一致。[预登记及配对敏感性](protocol.md) · [逐策略计数、时间与读写](planning-costs.csv)

| 策略 | 稀疏后停止 | 逐场补齐 | 逐读出补齐 |
|---|---:|---:|---:|
| 仅存已请求合格标签 | 397 (165) | 601 (249) | 601 (251) |
| 按需保存场方向解 | 241 (96) | 249 (102) | 257 (108) |
| 按需保存读出伴随解 | 241 (96) | 257 (108) | 249 (102) |
| 每轮选择最少端点 | 210 (89) | 520 (233) | 520 (233) |
| 首轮三场生成全表 | 237 (93) | 237 (93) | 237 (93) |
| 首轮三读出生成全表 | 237 (93) | 237 (93) | 237 (93) |
| 每轮选择最少端点并顺带保存可得标量 | 206 (86) | 516 (230) | 516 (230) |

稀疏流中，每份分子的后续请求恰由首轮混合端点覆盖。顺带保存结果可把第二轮全部变成有来源的查询。在实测节点上，四份有态分子的该策略热服务累计耗时两次为 101.7 和 107.5 ms，保留 15,649 字节。首轮三场全表为 122.2 和 126.3 ms，保留 5,656 字节。逐场补齐时，前者为 232.5 和 269.9 ms，后者为 115.9 和 139.7 ms。这里的计时包括轮内规划、计算/验收、资产读取和写入，整轮启动及研究流水线时间另计。每组两次短跑、单机固定负载，只支持这些轨迹上的观测。

稀疏轨迹按六份代表统计为 19/36 个合格请求，去重为 16/30 个。稠密轨迹为 28/54 个。首轮混合方法能少做工作，但在稠密轨迹后续要解新的块，成本高于直接预取。按这里两类轨迹的实测成本，若稠密扩展概率为 p，混合顺带保存策略与三场预取的差额为 −31+310p 次 J/K，交点 p=0.10；三份全矩阵合格子组的交点为 7/144。真实请求分布没有在此估计。

默认只保存合格值时，同一个失败标量会在后续被再尝试。四个有态分子的默认三场预取在三种轨迹分别为 357、445、501 次，允许复用已观察的参照拒绝后为 237、237、237 次。相反，在稀疏流中，仅存标签策略从 383 变为 397，少了一条失败边会改变该轮直接／伴随选择和块求解的工作。两组发布分量完全相同。[默认重试原始记录](raw/plan001-paired-retry-operations.jsonl.gz) · [绑定拒绝的原始记录](raw/plan001-paired-remember-operations.jsonl.gz)

## 完整成本、原始字节与复现

- n5 作业 2046 以 1 张 RTX 5090 对所有六份代表实算一批能量，GQC 72 次 SCF 迭代、77 次 Fock 构建。独立基态生产用 6 次 PySCF SCF 共 362 个周期，保留全部失败。4 对合格参考态文件占 602,811 字节。此批成本在所有规划策略间共享。[生产与 Slurm 回执](../qm9_response_assets/README.md)
- CPU GQC 的四份分子基准另用 20 次建模 J/K、237 次直接和 237 次伴随 J/K。独立验收用 52 次 PySCF SCF（2772 周期，2876 次 SCF J/K）和 4 次 CPHF（22 个批回调，58 个密度列）。另有身份重放、失效控制及一次写出前失败，成本单列于基准记录。不同后端的批调用口径分别保留。[独立参考及重放成本](../gqc_dual_response/README.md)
- 本报告的四次 PLAN-001 执行都入账，每次 168 条轨迹，含 4 个分子、3 种轨迹、7 种策略和 2 次重复。前两次是初测和加强科学身份后的重放；后两次才是同版配对。PLAN-002 执行 20 条双轮轨迹。合计实测 692 条策略轨迹、64,847 次策略 J/K、2,511 列新 RHS，另 100 次共享准备 J/K。五次执行累计 83.40 s，其中建模/编译等共享准备 44.57 s。组合场减法核的独立启动 0.380 s 已包含在该次墙时。每个来源运行五个 GQC 数值内核。归档校验和表格生成属于离线整理。未量测电耗、独占硬件计费或长期运维成本。学习训练及推理未参与这一机制。[逐次成本](verification.json)
- 原始摘要、按实序的 JSONL 日志、各次实际落盘的标量/向量以及观察到的拒绝均以无损 gzip 保存。资产 tar 仅含 JSON 文件。原生库散列、TensorIR 核、编译版本和执行环境在相应摘要与独立基准中。清单给出压缩前后 SHA-256。初测和 PLAN-002 实际加载的分子接口与提交 `97608c1` 的文件逐字节相同，首轮工作树当时并行开发，执行时 HEAD 单列。配对重放的驱动和接口均可在 `bc71c8b` 找到。[原始清单](raw/manifest.json) · [离线核验与导出](../../../../../scripts/summarize_response_planning.py)

仓库根目录下可用 Python 标准库校验所有输入摘要、日志、资格与请求顺序，再生成四份表格/校验产物。计算环境与固定 GQC/PySCF 版本见分子基准。实际重算命令如下，输出路径须为新目录。

```bash
experiments=handoff/gqcdataset_codex_goal/research/experiments
python3 scripts/summarize_response_planning.py --out .work/response-report-recheck
cmp "$experiments/response_planning/response-labels.jsonl" .work/response-report-recheck/response-labels.jsonl
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
uv venv --python 3.13 .work/response-reproduction-env
uv pip install --python .work/response-reproduction-env/bin/python numpy==2.5.5 pyscf==2.14.0 scipy==1.18.1 h5py==3.16.0 sccache==0.16.0
source .work/response-reproduction-env/bin/activate
python scripts/probe_response_planning.py --assets "$experiments/qm9_response_assets" --oracles "$experiments/gqc_dual_response/oracles" --out .work/response-retry-new
python scripts/probe_response_planning.py --assets "$experiments/qm9_response_assets" --oracles "$experiments/gqc_dual_response/oracles" --remember-reference-rejections --out .work/response-remember-new
python scripts/probe_scalar_response.py --assets "$experiments/qm9_response_assets" --oracles "$experiments/gqc_dual_response/oracles" --out .work/scalar-recovery-new
```

这些受控缺口和请求顺序用于区分计算机制。源几何来自真实发布，新增 RHF 响应列与 QM9 的历史 DFT 标签有各自的科学身份。独立数值通过属于本协议的实证；病态响应和减法消去仍可能放大误差，跨方法/基组或更广样本的严格误差界尚无证据。
