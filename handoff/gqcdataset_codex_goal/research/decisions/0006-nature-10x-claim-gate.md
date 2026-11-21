# 0006：10× 主张门槛与当前 partial 结果

日期：2026-11-22。

#34 的预注册命题要求在同一 GPU、同一协议和同一质量门下，把完整端到端成本降到官方 GPU4PySCF 的 0.1 倍以内。必须同时满足几何平均 speedup 至少 10×、paired 95% 区间下限大于 1、质量门通过并且第三方可由原始 JSON 重放。

当前四臂结果满足 204 条独立评分记录的质量门。官方后端 GQC planner 相对 native 的端到端几何平均 speedup 约 1.09×，paired CI 下限没有超过 1。patch 后端的 native 和 GQC 两臂均更慢。因而 10× 假设在当前 workload 上是 falsified-partial。结果没有删除失败、未知 telemetry、not-run 请求或外部资产缺口。

后续扩大主张前置条件是取得合同一致的更大请求资产、补齐 CUPTI/Nsight 和内存/能耗字段、加入第二种 GPU，并按 `benchmark_contract.json` 重跑 A–D。论文表述保持在协议保持、目标相关和带证据的增量响应规划范围内。
