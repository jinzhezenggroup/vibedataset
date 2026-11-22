# 规模、消融和全成本状态（Issue #41）

当前可复现实测规模是 17 个协议一致几何和 51 条请求级记录。另已归档 CC0 QM9 的 1000 行 geometry-only manifest，源 SHA 和缺失 response-label 状态见 `performance/qm9-scale-manifest.json.gz`。按重原子数分层的完整 cost ledger 在 `scale_ablation_plan.json`。n2 RTX PRO 6000 和历史 n5 RTX 5090 都有环境证据。A100/H100 不在当前可用资源中。

十个后续消融项已逐项登记为 `not_run`，原因包括需要 #37 的 CUPTI 分段、需要新 runtime、需要物理等价 patch、缺少 adjoint 合同或保持 FP64 约束。1000 行几何已取得，但协议一致响应资产、质量参考和第二种常见 NVIDIA GPU 仍未取得。报告保留 `partial-falsified-response-labels-blocked` 状态，不把 geometry-only 行外推成生产标签。

当前四臂结果把 GQC 官方后端相对 native 的端到端几何均值 speedup 约束在 1.09×，paired CI 下限没有超过 1，10× claim gate 不成立。下一阶段必须先取得许可清楚、协议一致的更大请求资产和第二 GPU，再运行冻结合同的消融。
