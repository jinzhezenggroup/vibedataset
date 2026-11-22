# GPU4PySCF/PySCF 源码与官方基线审计（Issue #36）

核对日期：2026-11-22。GPU4PySCF 固定为 `5a717f899cb40d64a5799ef1df7e3626c505c3bd`，PySCF 固定为 `c63a953ba603a5ad8c1d65d88da72aaf05ede4d8`。完整 checkout、构建文件和测试树在 `_references/`，版本锁已在 `sources.lock.json`。逐文件覆盖见 [gpu4pyscf_source_coverage.csv](gpu4pyscf_source_coverage.csv)。

## 行为追踪

- `gpu4pyscf/scf/cphf.py::solve` 和 `solve_nos1` 接受二维 RHS，内部调用 `cupy_helper.krylov`。`mo10` 是初始猜测，不是科学身份证明。
- `gpu4pyscf/lib/cupy_helper.py::krylov` 用 stable QR 组织共享 Krylov 空间，`max_cycle`、`lindep` 和 true convergence failure 都是官方路径。
- `gpu4pyscf/properties/polarizability.py::gen_vind` 将 MO 旋转映射为 AO induced potential，`eval_polarizability` 当前入口只接受 restricted RHF。B3LYP/RKS 与 UHF 扩展控制因此保留拒绝/重算。
- `gpu4pyscf/scf/hf.py::gen_response` 提供 SCF response potential。`cusolver.py`、`cutensor.py` 负责后端库加载和张量收缩，不能被当作 GQC planner 能力。
- PySCF `scf/cphf.py`、`ucphf.py`、`lib/linalg_helper.py` 以及 gradient/Hessian 路径提供 CPU 交叉参照。它们的固定态、响应、梯度和 Hessian 语义分开记录。

## 执行证据

项目官方 baseline A 在 n2 GPU 实跑 17 个分子、三条 RHF/STO-3G 轨迹，`runs/run-A.json` 保存 Python、GPU、CuPy、输入 hash 和 blind flags，`raw/raw-A.jsonl` 保存 51 条请求级记录。固定 checkout 的 GPU4PySCF `test_polarizability.py` 也在同一 n2 GPU 环境执行，7 tests passed、1 skipped，退出码 0，原始日志保存在 `environment/gpu4pyscf-20261122/upstream-polarizability-pytest.log`。IR/Raman upstream files 另行执行，8 passed、2 skipped、1 failed。失败是 `test_pcm_not_supported` 传入 `hessian_obj=None` 后先触发 AttributeError，已保留为 upstream failure receipt。独立 scorer 在新进程中用官方 GPU4PySCF 重建 204 条 A–D 记录，`score.json` 保存目标、AO density 和残差门。

该执行集是项目按固定合同重放的官方后端 baseline。上游完整 benchmark suite、CUPTI/Nsight trace、能耗和论文对应的 v1.9.0/v1.9.2 release tag 在当前 checkout 中没有建立。它们在 [baseline.json](../environment/gpu4pyscf-20261122/baseline.json) 明确标为 unknown 或 unavailable。不能把文件索引或项目 baseline 写成完整上游论文复现。

## 与四臂的映射

| 能力 | A | B | C | D |
|---|---:|---:|---:|---:|
| 官方 GPU4PySCF SCF/CPHF | ✓ | ✓ | ✓ | ✓ |
| 官方二维 RHS/Krylov | ✓ | ✓ | ✓ | ✓ |
| exact operator-image patch |  | ✓ |  | ✓ |
| GQC request/asset planner |  |  | ✓ | ✓ |
| 独立 scorer | 封存后统一执行 | 封存后统一执行 | 封存后统一执行 | 封存后统一执行 |

## 尚未满足的硬门槛

完整上游 benchmark suite、两份论文 release、CUPTI/Nsight 原始 trace 和多设备公平基线仍未取得。Issue #36 的源码路径和项目官方基线已可复查，但这些缺口不能在 #34 的 10× claim 中被隐藏。
