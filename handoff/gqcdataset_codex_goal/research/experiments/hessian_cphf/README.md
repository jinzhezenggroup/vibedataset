# Hessian/CPKS micro controls（Issue #40）

`scripts/run_hessian_cphf_controls.py` 在固定 PySCF 2.14.0、RHF/STO-3G、FP64 下运行 H₂O、NH₃ 和 LiH 的 relaxed Hessian/CPKS，并保留带电 LiH UHF control。结果保存能量、gradient 最大分量、Hessian shape/hash、负本征值数和运行时间。4/4 CPU controls 完成。

当前结果是主负载的 CPU 参考入口。IR/Raman readout、GPU4PySCF analytic Hessian、VeloxChem 交叉实现、有限差分 Hessian 和多样本 PreparedPropertyBatch 还没有运行。它们在结果文件中标为 `not_run` 或 `not_available`，不把 Hessian micro control 升级成端到端收益。
