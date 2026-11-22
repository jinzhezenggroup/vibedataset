# GPU4PySCF/PySCF 源码与官方基线审计（Issue #36）

核对日期：2026-11-22。GPU4PySCF 当前审计 checkout 固定为 `5a717f899cb40d64a5799ef1df7e3626c505c3bd`，PySCF 固定为 `c63a953ba603a5ad8c1d65d88da72aaf05ede4d8`。官方 v1.9.0 (`2fdc1951670a8e173dce063e697727bbc9f97616`) 和 v1.9.2 (`8536a80c1e03260aab030e108ef1d181a3709057`) tag 也已取回为独立源码树。完整 checkout、构建文件和测试树在 `_references/`，版本锁已在 `sources.lock.json`。逐文件覆盖见 [gpu4pyscf_source_coverage.csv](gpu4pyscf_source_coverage.csv)，tag 树的文件数、tree 和归档散列见 [release-tags.json](../environment/gpu4pyscf-20261122/release-tags.json)。

## 行为追踪

- `gpu4pyscf/scf/cphf.py::solve` 和 `solve_nos1` 接受二维 RHS，内部调用 `cupy_helper.krylov`。`mo10` 是初始猜测，不是科学身份证明。
- `gpu4pyscf/lib/cupy_helper.py::krylov` 用 stable QR 组织共享 Krylov 空间，`max_cycle`、`lindep` 和 true convergence failure 都是官方路径。
- `gpu4pyscf/properties/polarizability.py::gen_vind` 将 MO 旋转映射为 AO induced potential，`eval_polarizability` 当前入口只接受 restricted RHF。B3LYP/RKS 与 UHF 扩展控制因此保留拒绝/重算。
- `gpu4pyscf/scf/hf.py::gen_response` 提供 SCF response potential。`cusolver.py`、`cutensor.py` 负责后端库加载和张量收缩，不能被当作 GQC planner 能力。
- PySCF `scf/cphf.py`、`ucphf.py`、`lib/linalg_helper.py` 以及 gradient/Hessian 路径提供 CPU 交叉参照。它们的固定态、响应、梯度和 Hessian 语义分开记录。

## 执行证据

项目官方 baseline A 在 n2 GPU 实跑 17 个分子、三条 RHF/STO-3G 轨迹，`runs/run-A.json` 保存 Python、GPU、CuPy、输入 hash 和 blind flags，`raw/raw-A.jsonl` 保存 51 条请求级记录。固定 checkout 的 GPU4PySCF `test_polarizability.py` 也在同一 n2 GPU 环境执行，7 tests passed、1 skipped，退出码 0。`scf/tests/test_cphf.py` 另有 3 tests passed。原始日志保存在 `environment/gpu4pyscf-20261122/`。IR/Raman upstream files 另行执行，8 passed、2 skipped、1 failed。失败是 `test_pcm_not_supported` 传入 `hessian_obj=None` 后先触发 AttributeError。官方 `tests/test_benchmark_properties.py` 需要 pytest-benchmark，补装后仍因插件与当前 pytest node API 不兼容而 8 项 error。全部输出和 exit receipts 均保留。独立 scorer 在新进程中用官方 GPU4PySCF 重建 204 条 A–D 记录，`score.json` 保存目标、AO density 和残差门。

该执行集是项目按固定合同重放的官方后端 baseline。v1.9.0/v1.9.2 的源码 tag 已取得并完成 license、测试和 benchmark inventory。v1.9.2 的官方 PyPI CUDA 12 wheel 也已在 n2 的 RTX PRO 6000 上隔离执行，固定 wheel SHA、CUDA/PySCF/CuPy 身份、原始 Slurm 日志和兼容性设置见 [v1.9.2-wheel-test-receipt.json](../environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/v1.9.2-wheel-test-receipt.json)。选定的 polarizability/CPHF/IR/Raman 文件为 19 passed、3 skipped，benchmark-properties 中排除 `slow` 和 `high_memory` 的选定测试为 8 passed。测试使用官方 wheel，未把源码 CMake 构建失败伪装成成功；15 次隔离构建尝试及最终 nvcc implicit-link failure 仍见 [v1.9.2-build-attempt.json](../environment/gpu4pyscf-20261122/v1.9.2-build-attempt.json)。因此 #36 已从“没有匹配可执行版本”推进到“官方 v1.9.2 wheel 的选定上游测试已执行”，该回执只覆盖选定测试。当时的文件、版本和设备缺口由下文的后续实验追踪。

## 与四臂的映射

| 能力 | A | B | C | D |
|---|---:|---:|---:|---:|
| 官方 GPU4PySCF SCF/CPHF | ✓ | ✓ | ✓ | ✓ |
| 官方二维 RHS/Krylov | ✓ | ✓ | ✓ | ✓ |
| exact operator-image patch |  | ✓ |  | ✓ |
| GQC request/asset planner |  |  | ✓ | ✓ |
| 独立 scorer | 封存后统一执行 | 封存后统一执行 | 封存后统一执行 | 封存后统一执行 |

## 全新目录重放与论文版本

从仓库根目录运行 `python3 scripts/check_gpu4pyscf_audit.py --acquire` 可获取四棵锁定源码树。离线复核使用同一脚本，另可用 `--references-dir` 指定独立目录。逐文件检查比较 Git blob、类型和可执行位；已存在的 tag 导出也能用相同对象核验。全新目录中原审计 GPU4PySCF、PySCF 2.14、GPU4PySCF 1.9.0 和 1.9.2 分别核对了 1031、2295、993、1002 个跟踪文件。与本地旧目录的回放结果一致。[完整性回执](../environment/gpu4pyscf-20261122/upstream-v192/fresh-source-check.json)

GQC 论文的水簇能量/力基准明确使用 GPU4PySCF 1.9.0。固定 GQC 源码公开的 H100、RTX 5090 数据每卡有 192 条 GPU4PySCF 计时记录，均自报 1.9.0；另外每卡的 40 个复用数值参考记录标为 1.8.1。本文档的 1.9.2 是本项目的强基线。较早的 GPU4PySCF 积分直接法论文和应用扩展论文各有独立的版本范围：后者描述 v1.0，原始 PySCF 论文的特性表对应 1.3。论文版本文字、公开 tag 和可执行文件摘要分列保存。[论文与原始记录摘要](../environment/gpu4pyscf-20261122/upstream-v192/paper-sources.json) · [GQC 论文](https://arxiv.org/abs/2611.24744)

n2 作业 5639 在官方 1.9.0 wheel 和匹配的源码测试上执行了相同的四个选定文件，19 passed、3 skipped，退出码 0。1.9.2 的完整源码收集另外得到 2649 个测试，243 个测试文件的执行状态逐文件保存。上游计时 benchmark 单独运行。[1.9.0 原始结果](../environment/gpu4pyscf-20261122/v190-selected/receipt.json) · [1.9.2 完整 suite](../environment/gpu4pyscf-20261122/upstream-v192/campaign.json)

在 v1.9.2 中，`gpu4pyscf/scf/jk.py` 的壳层任务进入 `lib/gvhf-rys/rys_contract_jk.cu::RYS_build_jk`。该入口未向调用者暴露 stream 参数。CUPTI 确认了串行调用触发的 Rys kernels。密度拟合的 `df/df.py` 在 Cholesky 分解与按阈值保留特征向量之间选择，`df/hessian/rhf.py::make_h1` 涉及辅助基响应和 DF 状态重建。直接 RHF Hessian 的 `hessian/rhf.py::solve_mo1` 把几何 RHS 分批转换到 MO 表示。自旋分辨的 `scf/ucphf.py` 显式打包两种自旋。各路径的源码阅读、执行和未追踪分支已分别列入覆盖台账。

## 尚未满足的硬门槛

完整上游文件执行的每个失败、跳过和超时都需保留。独立的计时 benchmark 使用上游原始 warmup 与 rounds 配置。单分子 A–D 已有 CUPTI activity 和板卡能耗，硬件级 achieved occupancy/FLOPs 受到性能计数器权限限制。完整上游论文的时间、编译 flags 和跨设备规模结论仍需各自可复核的证据。[设备活动与限制](../environment/gpu4pyscf-20261122/nsight-control/README.md)
