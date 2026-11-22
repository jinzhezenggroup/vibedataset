# 规模、消融和全成本状态（Issue #41）

当前可复现实测规模是 17 个协议一致几何和 51 条请求级记录。另已归档 CC0 QM9 的 1000 行 geometry-only manifest，源 SHA 和缺失 response-label 状态见 `performance/qm9-scale-manifest.json.gz`。按重原子数分层的完整 cost ledger 在 `scale_ablation_plan.json`。n2 RTX PRO 6000 和 n5 RTX 5090 的同协议实测见下文。A100/H100 不在当前可用资源中。

十个消融项已逐项登记。shape bucket 和 GPU residency 现在有一个 3 分子、9 请求、同 `nao=19` 的 bounded control，1 次 bucket setup 对应 3 次 serial setup reference，且 target 与封存 C receipt 的最大差为 `5.22e-12`。该控制没有运行 async streams、融合 J/K、mixed precision 或完整 batch-size 统计。1000 行几何已取得，但协议一致响应资产、质量参考和第二种常见 NVIDIA GPU 仍未取得。报告保留 `partial-falsified-response-labels-blocked` 状态，不把 geometry-only 行外推成生产标签。

当前四臂结果把 GQC 官方后端相对 native 的端到端几何均值 speedup 约束在 1.09×，paired CI 下限没有超过 1，10× claim gate 不成立。下一阶段需完成更大请求集的独立质量参考和冻结合同的逐项消融。

在匹配的 GPU4PySCF 1.9.2 wheel 上，两卡各自重新执行同一套四臂，每卡有 204 个独立 GPU scorer 结果及 204 个新 CPU AO 残差证书。按分子配对的 A/C 生产墙时比为 RTX 5090 的 1.306× 和 RTX PRO 6000 的 1.288×。该范围为 17 个几何、每个三个请求，发布和独立评分的成本单列。[原始数据和区间](../environment/gpu4pyscf-20261122/single-gpu-pairs/README.md)
