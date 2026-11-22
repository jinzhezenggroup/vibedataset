# 逐请求设备活动与能耗（#37）

同一张 RTX PRO 6000、一个 Slurm allocation 内依次运行 A、D、C、B。每臂对固定队列首个分子的三个原始请求运行两遍。首次从空的 CuPy/CUDA 磁盘缓存启动，第二次在新 Python 进程中使用该臂留下的缓存。CPHF 文件摘要核对了实际导入的后端，B/D 使用同一份可回滚补丁。Slurm 作业 5627 的 Nsight Systems 2025.2.1 采集了 CUDA activity 和 NVTX 区间。独立官方进程在作业 5631 对冷、热各 12 个输出重新评分，24/24 通过。[实验与评分回执](receipt.json)

| 臂 | 热缓存三次请求的 kernel launches | H→D 字节 | D→H 字节 | 三次请求的板卡能量（J） |
|---|---:|---:|---:|---:|
| A | 4,687 | 78,024 | 5,515 | 527.386 |
| B | 6,457 | 113,504 | 9,895 | 788.467 |
| C | 3,088 | 54,456 | 4,857 | 352.397 |
| D | 3,800 | 68,648 | 7,121 | 456.798 |

表内按同步的 request 区间求和，单独的 SCF 区间见原表。能量是 NVML 的设备累计毫焦耳之差。报告同时提供每阶段 CUPTI 可见设备分配的高水位和约 10 ms 采样间隔下的整卡已用显存峰值，二者的计量对象不同。带 profiler 的墙时包含注入和同步成本。首轮的初始化和编译成本包含在实际经过的区间内。[各阶段与 kernel 名称](summary.json)

八个 GZip 文件记录每个 kernel 的时间戳、流、关联 ID、网格和线程块，以及设备分配与逐笔传输。原生 nsys-rep 和 SQLite 留在回执指向的 n2 工作目录，每份可按摘要校验。独立 scorer 原始结果和产生这些结果的请求逐字节压缩保存于 scientific 目录。可用以下命令复核阶段归属。

```bash
e=handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/nsight-control
python3 scripts/summarize_request_traces.py summarize "$e" /tmp/nsight-matrix.json
cmp "$e/summary.json" /tmp/nsight-matrix.json
```

作业 5628 在相同 wheel 的真实 Rys kernel 上请求 achieved occupancy 和 FP64 指令计数，Nsight Compute 返回 ERR_NVGPUCTRPERM，驱动报告 RmProfilingAdminOnly=1。这两项计数保留为未知。项目尚需更大队列和不含 profiler 开销的完整成本测量。[原始拒绝](ncu.log)
