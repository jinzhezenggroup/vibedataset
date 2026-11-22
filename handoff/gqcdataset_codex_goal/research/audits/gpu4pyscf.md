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

该执行集是项目按固定合同重放的官方后端 baseline。v1.9.0/v1.9.2 的源码 tag 已取得并完成 license、测试和 benchmark inventory，但 n2 当前可执行二进制是 GPU4PySCF 1.8.1。对 v1.9.2 的隔离 CMake 构建已提交 15 次有限尝试，均停在工具链配置阶段，最终失败为 CMake 无法解析 nvcc implicit link line，原始 job 5550 日志和 build receipt 见 [v1.9.2-build-attempt.json](../environment/gpu4pyscf-20261122/v1.9.2-build-attempt.json)。因此 tag-specific execution 尚未声称完成。上游完整 benchmark suite、CUPTI/Nsight trace、能耗和论文版本映射仍是未知项，在 [baseline.json](../environment/gpu4pyscf-20261122/baseline.json) 中明确记录。不能把文件索引或项目 baseline 写成完整上游论文复现。

## 与四臂的映射

| 能力 | A | B | C | D |
|---|---:|---:|---:|---:|
| 官方 GPU4PySCF SCF/CPHF | ✓ | ✓ | ✓ | ✓ |
| 官方二维 RHS/Krylov | ✓ | ✓ | ✓ | ✓ |
| exact operator-image patch |  | ✓ |  | ✓ |
| GQC request/asset planner |  |  | ✓ | ✓ |
| 独立 scorer | 封存后统一执行 | 封存后统一执行 | 封存后统一执行 | 封存后统一执行 |

## 尚未满足的硬门槛

匹配 1.9.x 二进制环境下的 tag-specific suite、完整上游 benchmark、两份论文 release 映射、CUPTI/Nsight 原始 trace 和多设备公平基线仍未取得。Issue #36 的源码路径、两个官方 tags 和项目 baseline 已可复查，但这些缺口不能在 #34 的 10× claim 中被隐藏。
