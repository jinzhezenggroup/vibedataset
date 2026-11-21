# Issue #27 响应资产迁移盲验

本轮把 #18 的 SCF 身份实验扩展到目标响应。生产器先在水 RHF/STO-3G 上生成并
序列化 `x/q0` 响应向量，不读取目标标签。独立评分器重新打开该资产，并重新
求解 RHF/STO-3G、RHF/6-31G*、B3LYP/6-31G*、H₂⁺ UHF 和低间隙 H₂ 目标。
[生产器](../response_migration.py) · [封存输入](sealed.json) · [独立评分](score.json)

## 分类结果

| 请求 | 分类 | 结果 |
|---|---|---|
| 水 RHF/STO-3G `x/q0` | `direct_reuse` | 序列化向量重开后接受。向量最大差 `5.06×10⁻¹⁴`，目标差 `8.11×10⁻¹⁷`，残差 `2.17×10⁻¹⁶` |
| 水 RHF/6-31G* `x/q0` | `initial_guess_only` | 目标响应重新求解。维度从 10 变为 65，目标残差 `3.19×10⁻⁷`，响应证据不达当前 `1e-10` 门槛 |
| 水 B3LYP/6-31G* `x/q0` | `refine_required` | 目标响应重新求解。方法和基组均改变，目标残差 `1.48×10⁻⁶` |
| H₂⁺ UHF/STO-3G | `reject_and_recompute` | SCF 收敛，但受限 RHF/RKS 响应评估器返回 `response_evidence_unavailable` |
| 拉伸 H₂ RHF/STO-3G | `evidence_unavailable` | 最小轨道间隙 `0.1001 Eh`，低间隙控制不发布响应证书 |

同协议 direct reuse 使用非自比较的序列化资产重开和第二次独立 PySCF CPHF 计算。
方法、基组、电子态变化均没有把旧响应向量直接当作目标响应。全部分类、SCF
成本、CPHF 操作数和目标残差保存在评分结果中。

## 结论

当前证据支持响应资产的固定协议身份边界。它证明了同一 RHF/STO-3G 响应资产
可以在独立进程中重开并复核，改基组或方法需要重新求解，开放壳层和低间隙状态
需要拒绝或证据不可得。它没有证明响应向量可以跨方法、基组或电子态迁移。

## 复现

```bash
e=handoff/gqcdataset_codex_goal/research/experiments/cross_protocol/response_migration.py
.work/response-checks-env/bin/python "$e" produce --out .work/response-migration-producer
.work/response-checks-env/bin/python "$e" score \
  --sealed .work/response-migration-producer/sealed.json \
  --out .work/response-migration-scorer
```
