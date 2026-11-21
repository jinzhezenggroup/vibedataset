# 对已序列化离散方程的确定性目标界

17 个原始 QM9 候选各只请求一个目标，即 x 场下首原子 Mulliken 净电荷的导数。读取先前求得的 x 方向向量，按物理身份、内容散列和实际残差重新验收，再检验已装配矩阵的严格行对角占优。所有行差、残差和收缩按输入 FP64 实数对应的精确有理数计算。三个分子取得 1e−8 以内的确定性读出误差界。[证明和冻结条件](protocol.md) · [封存决定](decisions.json)

| QM9 构型 | 最小行差 δ | 输入矩阵上读出绝对误差上界 |
|---|---:|---:|
| 000001 | 0.398494 | 3.82×10⁻¹⁴ |
| 000002 | 0.353380 | 3.77×10⁻¹⁴ |
| 000003 | 0.344572 | 4.41×10⁻¹³ |

**覆盖范围。** 以上 3 项均在首批。其他 9 份有态分子的最小行差小于零，其中包括全部 8 份有态留出分子。它们得到 evidence_unavailable，另 5 个候选保留原缺态原因。独立评分进程核验封存判定后才读取对应的 v2 CPHF 与两档有限场，3 个接受项全部通过。δ≤0 只使这条充分条件失效。本轮据此停止把固定轨道基底的行占优条件推广到这组留出构型。[逐分子结果及外部评分](score.json)

**误差层级。** 严格界覆盖精确取已序列化 A、b、w 值的线性系统，以及候选 q 的最后一次点乘舍入。AO 积分、FP64 装配、SCF 态、基组及物理模型另有各自的误差。对实际分子读出的证据还包括原生残差复核及盲验对照。[可重算的二进制矩阵、右端、读出、向量和候选值](systems.zip)

**费用。** 12 次建模共 60 次 GQC J/K，12 个存档向量各花一次原生作用，合计 12 次复核 J/K，未提交新的响应 RHS。本次共享 #14 的准备入口，实付 24 次 AO→MO 变换和 12 次数值 SVD。行占优判据的算术本身只读取矩阵。12 份有理数检查合计 0.153 秒，整个产出过程含内核准备及归档读写为 30.40 秒。压缩的矩阵系统共 507,784 字节。历史向量的原生产与磁盘档案另有完整回执。[历史资产及生产费用](../partial_response_blocks/cohort/README.md)

在已固定的 GQC 与科学 CPU 环境下，生成和离线评分可独立运行。生产器禁止读取 v2 参照、oracle 目录和标签表。离线核查只需 Python 标准库。

```bash
d=handoff/gqcdataset_codex_goal/research/experiments/represented_matrix_bound
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
python "$d/run.py" --out .work/represented-matrix-run
python3 "$d/verify.py" --bundle .work/represented-matrix-run --out .work/represented-matrix-run/score.json
python3 "$d/verify.py"
```
