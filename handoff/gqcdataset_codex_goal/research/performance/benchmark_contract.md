# 端到端 benchmark contract（Issue #35）

核对日期：2026-11-22。该合同冻结 #34 的 10× 假设输入和计时口径。它把 3 个微型控制、17 个已封存几何和 306 条中型受控请求固定为可重放分母。合同绑定 [attribution_4arm/manifest.json](../experiments/attribution_4arm/manifest.json) 的 SHA-256。

## Workload 层

| 层 | 数量 | 状态 | 说明 |
|---|---:|---|---|
| H2O/NH3/LiH 微型闭环 | 3 | H2O/NH3 已测，LiH control-only 未运行 | LiH 保留在分母，避免把未支持状态写成通过。 |
| 中型受控请求 | 306 | 首轮 51 条有 GPU 原始记录，其余请求保持 `not_run` | 17 个几何、3 条轨迹、6 个固定重复顺序。 |
| 公开规模目标 | 1000 | blocked-unavailable | 当前可取得的协议一致响应请求不足。合同记录阻塞，不用重复记录伪装规模。 |

每条请求包含 geometry hash、原子序、坐标、method、basis、charge、spin、AO 表示、原点、单位、FP64、SCF/response 收敛阈值、目标属性、状态分支和 missingness mask。`source_kind` 把 controlled-request、natural-request、negative-control、not-exported、quality-insufficient 和 compute-failed 分开。当前 natural-request 数量为 0，不能从受控队列推出生产分布。

## 计时边界

单条 receipt 的 timing schema 固定为 `prepare`、`environment_startup`、`data_read`、`compile_jit`、`warmup`、`h2d`、`scf_fock`、`cp_hf_gmres`、`property_readout`、`physical_residual`、`independent_scorer`、`serialization`、`retry` 和 `fallback`。缺少实测值写 `null`，不能用推算填补。现有四臂原始记录另保存 operator rows、RHS、host/device bytes、SCF cycles、response seconds 和端到端 molecule seconds。

主指标是每条记录的端到端 wall seconds。派生统计固定为 throughput、geometric mean speedup、median、p95、GPU-hours、operator/Fock rows、RHS、传输字节、峰值内存、coverage 和 failure rate。cold/warm、单样本/批量和多轮请求分开记录。质量验证、失败重试、回退和序列化属于端到端成本。

## 公平性、oracle 和负对照

A–D 四臂读取同一逐字节 manifest 和 request order。生产进程不加载 scorer 或 oracle。独立 scorer 在封存后重建官方 GPU4PySCF 响应，并检查目标、AO 密度和残差。错误基组复用、近奇异界和状态不匹配均保留为 `reject-and-recompute`。

## 规模阻塞与停止条件

公开可取得的 1000 条协议一致响应请求资产尚未找到。下一步必须先取得许可、协议字段和独立质量证据，再扩展规模。合同冻结后，不允许通过删除 `not_run`、质量不足或失败记录把目标规模写成已达成。10× 仍是预注册假设，当前结果只支持局部机制和负结果边界。

机器可读合同是 `benchmark_contract.json`，队列是 `middle-queue.jsonl`，来源账本是 `source-kind-ledger.json`。复核入口是 `scripts/check_benchmark_contract.py`。
