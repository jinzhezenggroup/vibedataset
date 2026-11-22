# 2026-11-23 收尾快照

主仓库已合并到 `ed0c7364ed23398d9fb77e9a6b4bca8595beae0b`（#75）。#34 保留 `falsified-partial`。原合同的 1.093482× 和新双卡各自的 1.305766×、1.288099× 使用不同运行记录。双卡各有 204/204 官方和独立 CPU 评分。完整冷/热跟踪的 408 行另行评分通过。#69、#70、#71、#72、#75 已合并。[四臂数据](environment/gpu4pyscf-20261122/single-gpu-pairs/README.md) · [完整 GPU 跟踪](environment/gpu4pyscf-20261122/full-queue-trace/README.md)

## QM9

n5 数组 2405 的 20 个分片全部结束。1000 个唯一请求和 1000 个独立 CPU 参考均已产生。首轮 993 条通过，7 条候选物理残差超出冻结阈值。封存的 1002 次尝试包括 n5 作业 2411 中两条严格 SCF 重算失败。编号 27、62、321、324、351、354、490 的标签在本快照中均未发布。每个通过的样本含 3×3 极化率、独立参考、散列、残差和成本。核查原始 bundle 的 SHA-256 见 manifest。作业 2427 和 2428 的结果独立追加；已封存的初次结果保持可复核。[993 条标签及 7 条处置](experiments/qm9_scale_response/checkpoint-993/labels.jsonl.gz) · [计数和成本](experiments/qm9_scale_response/checkpoint-993/summary.json) · [原始张量包散列](experiments/qm9_scale_response/checkpoint-993/raw-bundle.json)

## 交接位置

| 项目 | 已核实的结果 | 本地或集群入口 |
|---|---|---|
| #36 | 1.9.0/1.9.2 官方 wheel 均可运行。匹配 CPU 七个测试文件 138 通过、18 跳过。完整 GPU 套件保留失败和超时。首次数值 benchmark 的 8 项均报 PASSED，pytest-benchmark 写 JSON 时缺少 cpuinfo。已安装并验证依赖，计时按项重跑。 | n2 `~/vibedataset/runs/upstream-v192-afecd514`，RKS 5673、归并 5674、计时 5693、归档 5637，分支 `codex/upstream-complete-campaign` |
| #37 | 全部 A–D 请求已取得 kernel、拷贝、显存、板级能耗和存储记录。GPU 性能计数器返回 `ERR_NVGPUCTRPERM`，实际 achieved occupancy 与硬件 FLOP 数待授权。 | 已合并 #75 |
| #38 | 120 条矩阵测试中，117 条通过，3 条预设故障被隔离。其余 60 条稠密/FP32 精修和 48 条标量读出消融通过独立 CPU 评分。该微队列两组 CUPTI 对照都测得跨流重叠 0 ns。 | PR #74，工作区 `.work/prepared-{5652,5660,5661}` 与 `.work/prepared-nsight-5663` |
| #39 | 三分子有 3 个直接复用、6 个真实跨基组/方法精修、5 个真实重算，开放壳层显式保留。 | 已合并 #72 |
| #40 | 三种请求密度的逐请求/共享路径，经独立 VeloxChem 和实际 Raman 纠正，每路 12/12。Cartesian CPHF 另有 27 个 RHS 的独立 CPU 物理残差。补充 DF 控制作业 5697 单列。 | PR #76，`.work/shared-spectroscopy-raw` |
| #41 | 306 条冻结中型队列正使用单独科学进程、独立 scorer 和持久化标签采集完整墙时。须检查四臂终态。 | n2 `~/vibedataset/runs/controlled-middle-full-cost/cost-5671`，n5 2425 为小型预检，分支 `codex/full-cost-middle-queue` |

本机原始 QM9 张量包位于 `.work/goal-wrapup/qm9-checkpoint-raw.tar.gz`，正在重算的 n5 记录位于 `~/vibedataset/runs/qm9-response-retries` 和 `~/vibedataset/runs/qm9-full-fock-recovery`。后续先读各作业的结果文件、退出记录和独立质量评分，再更新计数。当前科学验收保持开放。
