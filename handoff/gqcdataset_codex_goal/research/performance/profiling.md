# 四臂端到端 profiling 基线（Issues #34、#37）

`attribution_profile.json` 从四臂请求级 receipt 和独立评分摘要重建阶段账本。A–D 使用相同 manifest、17 个分子和 51 条请求。

| 臂 | 端到端 molecule seconds | response seconds | operator rows | H2D bytes | D2H bytes |
|---|---:|---:|---:|---:|---:|
| A 官方/native | 408.16 | 113.40 | 677 | 176,928 | 52,752 |
| B patch/native | 558.71 | 201.60 | 643 | 176,928 | 52,752 |
| C 官方/GQC | 367.47 | 76.71 | 352 | 109,160 | 26,376 |
| D patch/GQC | 428.89 | 108.12 | 352 | 109,160 | 26,376 |

C 相对 A 的端到端几何均值 speedup 为约 1.09×。其 molecule-time paired bootstrap 区间跨过零。B 相对 A 的几何均值比为 1.28，D 相对 C 为 1.14。交互项 `(D−B)−(C−A)` 的 molecule-time 中位数为 `−1.254 s`，95% 区间 `[-2.375, -0.353]`。这表示本轮后端 patch 的额外开销改变了交互项，不能写成 10× 后端收益。

已记录的物理代理包括响应 induced-potential operator rows、SCF cycles、响应 wall time、质量核验行数、H2D/D2H 字节和完整端到端时间。没有实测的 kernel launch、occupancy、FLOPs、CUPTI/Nsight event、峰值显存、主存、能耗、compile/JIT 分段、独立 scorer wall time 和冷/热细分均保留为 `null`。未知项不会用估计值补齐。

`claim_gate` 明确把 10× 标记为未支持。该结果可作为 #34 的 falsified/partial 阶段证据，并作为 #38/#39 继续优化前的 baseline。

## 单分子 phase telemetry control

在同一封存 manifest 的 `qm9-000001` 上，额外用独立 Slurm 进程取得官方 GPU4PySCF A 与 GQC planner-assets C 的 CUDA event 和显存池回执，见 `environment/gpu4pyscf-20261122/phase-profile-control/`。A 的三条请求 CPHF 加独立 residual 段分别为 1.372041、1.372145 和 1.408969 秒。C 的前两条新响应为 1.359896 和 1.369461 秒，第三条请求复用已有资产而没有新的响应调用。每条请求还保留 SCF/Fock、property readout、H2D/D2H 字节、operator rows、residual 和 `memGetInfo` 快照。

这组 telemetry 只补齐了一个小分子的 A/C 阶段观测。B/D patched arm、完整四臂队列统计、冷/热分段、kernel launches、occupancy、FLOPs、CUPTI/Nsight 和能耗仍为 unknown。响应段包含该驱动中的独立 residual 计算，不能按单独质量阶段解读。
