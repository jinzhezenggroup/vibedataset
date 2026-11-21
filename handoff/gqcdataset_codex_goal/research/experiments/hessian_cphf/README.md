# Hessian/CPKS micro controls（Issue #40）

`scripts/run_hessian_cphf_controls.py` 在固定 PySCF 2.14.0、RHF/STO-3G、FP64 下运行 H₂O、NH₃ 和 LiH 的 relaxed Hessian/CPKS，并保留带电 LiH UHF control。结果保存能量、gradient 最大分量、Hessian shape/hash、负本征值数和运行时间。4/4 CPU controls 完成。

GPU4PySCF 在 n2 RTX PRO 6000 上又完成 H2O/RHF、NH3/RHF 和 H2O/RKS(B3LYP) analytic Hessian，结果见 `gpu-results.json`。同一 H2O/RHF control 还完成了 IR frequency/intensity 和 Raman activity/depolarization，结果见 `gpu-spectroscopy.json`。当前结果是主负载的 CPU/GPU micro control。VeloxChem 交叉实现、有限差分 Hessian 和多样本 PreparedPropertyBatch 还没有运行。它们不被写成端到端收益。

这组 GPU 控制使用独立 Slurm 进程，环境和 source commit 见 `research/environment/gpu4pyscf-20261122/baseline.json`。
