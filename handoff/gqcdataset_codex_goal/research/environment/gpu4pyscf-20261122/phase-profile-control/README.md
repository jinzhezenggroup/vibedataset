# GPU4PySCF phase telemetry control（Issue #37）

`profile-A.json` 和 `profile-C.json` 在固定 `qm9-000001`、同一封存 manifest、RHF/STO-3G/FP64 协议下由独立 Slurm 进程取得。A 是 native-ordinary，C 是 GQC planner-assets。两个作业使用 n2 RTX PRO 6000、GPU4PySCF 1.8.1、CuPy 14.2.0、Python 3.11.17。

每条请求保留 Python wall time 和 CUDA event time，分开记录首次 prepare、SCF/Fock、CPHF 与 residual 合并段、property readout、operator rows、residual、H2D/D2H 字节和 `memGetInfo`/CuPy memory-pool 快照。A 的三条请求响应段为 `1.372041`、`1.372145`、`1.408969` 秒，C 的已计算段为 `1.359896` 和 `1.369461` 秒，第三条请求复用资产且无新的响应调用。该结果只说明这一受控小分子的阶段观测，不能替代完整四臂统计或端到端收益结论。

未采集 kernel launch count、occupancy、FLOPs、CUPTI/Nsight、能耗、B/D patched arm 和冷/热分段。响应段包含该驱动中的独立 residual 计算，未将其伪装为单独质量阶段。

复现命令由 `receipt.json` 绑定到 driver SHA、manifest SHA、Slurm job 和原始日志。失败的 5524/5525 是参数传递错误的启动尝试，不计入结果，保留在 n2 原始目录但未纳入 artifact。
