# Issue #26 算子级一致性盲验

本轮在 `qm9-000003` 的固定 RHF/STO-3G 响应问题上，对证书使用的装配矩阵和
生产中实际施加的 GQC 响应算子做全空间比较。生产器只读取零场源态和 GQC
源码，不读取 CPHF、目标值或评分表。评分器在独立进程中重新构造模型和算子，
再比较封存的探针结果。[协议](protocol.md) · [封存](sealed.json) · [评分](score.json)

## 探针覆盖

- 10/10 个标准基向量，覆盖完整响应空间。
- 4 个固定随机单位向量，种子 `314159`。
- 6 个归一化 field/observable RHS。
- 最小 SVD 右奇异向量，覆盖近奇异方向。
- AO→MO 装配矩阵、SVD 和原生算子作用分别计费。

生产与独立评分的矩阵、标准基输出、随机探针、RHS 探针和近奇异探针全部通过
二进制级复核。装配矩阵与原生算子的最大绝对差为 `7.22×10⁻¹⁶`，最大随机
探针差为 `2.78×10⁻¹⁵`，最大 RHS 探针差为 `9.47×10⁻¹⁶`。生产和评分各支付
21 次原生 J/K 探针，矩阵占用 800 字节，保存探针占用 880 字节。

## 负控制

近奇异 `diag(1, 1e-12)` 控制中，残差 `1e-12` 会被残差-only 规则接受，而目标
误差为 1。算子级证书返回 `evidence_unavailable`。将装配矩阵加入 `1e-6`
非对称扰动后，与原生算子的最大差为 `1.0e-6`，同样降级为
`evidence_unavailable`。

这项协议支持把“离散证书”限定为当前固定方程的算子级数值证据。它没有证明
连续量子化学模型误差，也没有跨方法、基组或状态外推含义。

## 复现

```bash
e=handoff/gqcdataset_codex_goal/research/experiments/error_certificates/operator_probe.py
export PATH="$PWD/.work/response-checks-env/bin:$PATH" \
       SCCACHE_DIR="$PWD/.work/operator-probe-sccache" \
       SCCACHE_SERVER_PORT=42326 \
       OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
sccache --start-server
.work/response-checks-env/bin/python "$e" produce --out .work/operator-producer
.work/response-checks-env/bin/python "$e" score \
  --sealed .work/operator-producer/sealed.json --out .work/operator-scorer
```
