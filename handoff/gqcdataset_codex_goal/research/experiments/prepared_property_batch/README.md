# PreparedPropertyBatch 规划入口（Issue #38）

`scripts/prepared_property_batch.py` 提供一个可审查的 request DAG 和 shape bucket 中间表示。每条 request 绑定 method、basis、charge、spin、AO 表示、原点和单位。节点包括 reference、CPKS、energy、forces、Hessian、IR 和 Raman。相同身份与 `nao` 的 request 进入同一 bucket，单条失败可以标为 `reject-and-recompute` 而不污染其余 request。

当前实现是 planner/producer 边界和资源预算入口。它没有把 DAG 直接写成 GPU kernel，也没有把已有 GQC resident 或 batch 代码改名为新算法。`resident=True` 加上 `max_workspace_bytes` 时，预算超限的节点降级为 fallback。`scripts/check_prepared_property_batch.py` 覆盖同协议 bucket、错基组隔离、单条失败和工作区超限。

`check_prepared_property_batch.py` 的固定控制结果为 2 个 shape bucket、12 个节点、1 个隔离失败和 2 个预算回退。真正的跨样本 GPU residency、异步 stream、ragged batch 和融合 J/K 需要 #37 的分段 profile 后在 n2/n5 上实测，当前不宣称已经获得端到端收益。

`run_prepared_property_batch_replay.py` 还将 51 条已封存 C 轨请求作为 producer receipt 重放。51 条请求按 8 个 shape bucket 组织，bucket setup accounting 从逐请求 51 次降为 8 次，51/51 receipt 保持 accepted。这个数字是静态图/资源准备账本，不是 GPU wall-time speedup，也没有重新生成科学标签。

`gpu-control.json` 是一个独立 n2 GPU 控制。它在同一 CUDA context 中把 `qm9-000009`、`qm9-000011` 和 `qm9-000017` 的 9 条请求放入一个 `nao=19` shape bucket，实际 setup 为 1 次，serial setup reference 为 3 次，9/9 request receipts accepted。每条新响应保留官方 GPU4PySCF 的 residual、operator rows、H2D/D2H 和 target。`gpu-control-verification.json` 将 27 个 target 分量与已封存 C receipt 比较，最大差为 `5.22e-12`，并确认对应的 51 条独立 scorer C 行均 accepted。

这个控制只验证单进程、单 CUDA context 的跨样本编排和逐条失败隔离。resident buffer 是编排层 workspace，未被写成共享 GPU4PySCF operator asset。

## Runtime probe

`scripts/run_prepared_gpu4pyscf_processes.py` 提供一个 process-isolated worker runtime。三个 `nao=19` 分子各自拥有一个 spawned worker 和一个 CUDA context，worker 内按 request DAG 顺序生产三条响应请求。9/9 请求通过，独立比较器给出相对 serial receipt 的最大 target 差 `5.780265155408415e-12` 和最大 residual 差 `6.4191273824176776e-15`。process runtime 墙时为 `34.79380883008707 s`，serial 为 `34.33253801194951 s`，比值为 `1.013435383599576`。启动成本、三个 CUDA context 和重复 workspace 都计入墙时。

同一 CUDA context 的 `async_streams` 试验使用两个 non-blocking CuPy streams，并按分子保持 request chain 顺序。官方 GPU4PySCF 1.9.2 的 `RYS_build_jk` 在作业 5588 中触发 `cudaErrorIllegalAddress`，进程没有写出成功回执。该路径被标记为 unsafe，serial producer 是当前 fallback。完整日志和失败回执见 [prepared-runtime](../../environment/gpu4pyscf-20261122/prepared-runtime/runtime-summary.json)。

当前 runtime 证据覆盖 process-isolated scheduling、shape bucket、resident workspace、失败分类和 serial fallback。ragged metadata 已进入 request scheduler，融合 J/K、跨分子 operator-value reuse、same-context stream safety、独立 scorer 和端到端 speedup 仍需要后续实测。
