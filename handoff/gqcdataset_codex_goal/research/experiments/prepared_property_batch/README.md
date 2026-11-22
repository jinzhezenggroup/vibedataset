# PreparedPropertyBatch 规划入口（Issue #38）

`scripts/prepared_property_batch.py` 提供一个可审查的 request DAG 和 shape bucket 中间表示。每条 request 绑定 method、basis、charge、spin、AO 表示、原点和单位。节点包括 reference、CPKS、energy、forces、Hessian、IR 和 Raman。相同身份与 `nao` 的 request 进入同一 bucket，单条失败可以标为 `reject-and-recompute` 而不污染其余 request。

当前实现是 planner/producer 边界和资源预算入口。它没有把 DAG 直接写成 GPU kernel，也没有把已有 GQC resident 或 batch 代码改名为新算法。`resident=True` 加上 `max_workspace_bytes` 时，预算超限的节点降级为 fallback。`scripts/check_prepared_property_batch.py` 覆盖同协议 bucket、错基组隔离、单条失败和工作区超限。

`check_prepared_property_batch.py` 的固定控制结果为 2 个 shape bucket、12 个节点、1 个隔离失败和 2 个预算回退。真正的跨样本 GPU residency、异步 stream、ragged batch 和融合 J/K 需要 #37 的分段 profile 后在 n2/n5 上实测，当前不宣称已经获得端到端收益。

`run_prepared_property_batch_replay.py` 还将 51 条已封存 C 轨请求作为 producer receipt 重放。51 条请求按 8 个 shape bucket 组织，bucket setup accounting 从逐请求 51 次降为 8 次，51/51 receipt 保持 accepted。这个数字是静态图/资源准备账本，不是 GPU wall-time speedup，也没有重新生成科学标签。
