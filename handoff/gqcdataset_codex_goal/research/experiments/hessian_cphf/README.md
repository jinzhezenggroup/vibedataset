# Hessian/CPKS micro controls（Issue #40）

`scripts/run_hessian_cphf_controls.py` 在固定 PySCF 2.14.0、RHF/STO-3G、FP64 下运行 H₂O、NH₃ 和 LiH 的 relaxed Hessian/CPKS，并保留带电 LiH UHF control。结果保存能量、gradient 最大分量、Hessian shape/hash、逐分量 Hessian、负本征值数和运行时间。4/4 CPU controls 完成。

GPU4PySCF 在 n2 RTX PRO 6000 上又完成 H2O/RHF、NH3/RHF 和 H2O/RKS(B3LYP) analytic Hessian，结果见 `gpu-results.json`。同一 H2O/RHF control 还完成了 IR frequency/intensity 和 Raman activity/depolarization，结果见 `gpu-spectroscopy.json`。当前结果是主负载的 CPU/GPU micro control。有限差分 Hessian 已在同一 PySCF 协议下完成，VeloxChem 交叉实现和多样本 PreparedPropertyBatch 仍没有运行。它们不被写成端到端收益。

这组 GPU 控制使用独立 Slurm 进程，环境和 source commit 见 `research/environment/gpu4pyscf-20261122/baseline.json`。`cpu-gpu-crosscheck.json` 对相同 Bohr/STO-3G 几何的 H₂O/RHF 和 NH₃/RHF 做逐分量比较，最大绝对差分别为 `3.7248e-08` 和 `7.1957e-09`，在 `1e-7` 控制阈值内通过。H₂O/RHF 的中心有限差分梯度 Hessian 也通过同一阈值，步长为 `1e-4` Bohr，最大绝对差为 `9.5555e-08`。GPU RKS(B3LYP) 行尚无对应 CPU RKS 行，因此没有把它纳入逐分量交叉结论。

逐分量回执由以下命令重建：

```bash
python3 scripts/compare_hessian_controls.py \
  --cpu handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/results.json \
  --gpu handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/gpu-results.json \
  --finite-difference handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/finite-difference.json \
  --out handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/cpu-gpu-crosscheck.json
```
