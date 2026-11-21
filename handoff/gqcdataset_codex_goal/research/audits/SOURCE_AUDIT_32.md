# 固定版本源码审计（Issue #32）

核对日期：2026-11-22。每一条观察来自仓库中固定 checkout 的实际路径和符号。`check_source_audit_32.py` 会校验路径、提交、许可证、符号和测试入口。索引、源码阅读、行为追踪和运行验证仍分开记账。

## 版本与边界

| 来源 | URL | commit | checkout | 许可证 | 子模块/LFS |
|---|---|---|---|---|---|
| `gqc` | https://github.com/jinzhezenggroup/generativeqc | `2791504cc238fe83d328fc1718080642b288222a` | `_references/gqc` | `LICENSE; THIRD_PARTY_NOTICES.md` | 0/0 |
| `gpu4pyscf` | https://github.com/pyscf/gpu4pyscf | `5a717f899cb40d64a5799ef1df7e3626c505c3bd` | `_references/gpu4pyscf` | `LICENSE` | 0/0 |
| `pyscfad` | https://github.com/fishjojo/pyscfad | `190fbb4670de4c989333a5eb49b401efd5395a3b` | `_references/pyscfad` | `pyscfadlib/LICENSE` | 0/0 |
| `pvmc` | https://github.com/RateTheory/PVMC | `0d3340644047abc727896753f48650f8c5205a89` | `_references/pvmc` | `LICENSE` | 0/0 |
| `hvmc` | https://github.com/RateTheory/HVMC | `389bc8abad78d574ae971289226a27c620a0c351` | `_references/hvmc` | `LICENSE` | 0/0 |
| `pymor` | https://github.com/pymor/pymor | `36a0035e180694c7ad4eb8f083d9f1d65ceb6f42` | `_references/pymor_2026_1` | `LICENSE.txt` | 0/0 |
| `qemfi` | https://github.com/SM4DA/QeMFi | `883eca5b12c96ca2248fddcc671fcd032696552a` | `_references/qemfi` | `LICENSE` | 0/0 |
| `openmdao` | https://github.com/OpenMDAO/OpenMDAO | `64175aa55fb541355b2fb279a6bcfde01e17a878` | `_references/openmdao_3_45_2` | `LICENSE.txt` | 0/0 |
| `cppad` | https://github.com/coin-or/CppAD | `5d51b2aa6d6874c8d561da298a90b3721550d45d` | `_references/cppad_2026` | `COPYING` | 0/0 |
| `multifidelity_gnn` | https://github.com/davidbuterez/multi-fidelity-gnns-for-drug-discovery-and-quantum-mechanics | `84ee8a280557d7fbc2ebd1042468e21ce8ea16c6` | `_references/multifidelity_gnn` | `LICENSE` | 0/0 |

所有 checkout 均来自 `research/sources.lock.json`。第三方树位于未跟踪 `_references/`，没有复制进发布包。论文版本、作者历史树、运行时二进制和外部数据不由本表替代。

## 关键行为观察

| ID | 源码行为 | 固定路径和符号 | 测试/运行证据 | 对本项目的边界 |
|---|---|---|---|---|
| `gqc-linear-problem` | Defines the operator and dimension identity for a response equation. | `src/response/linear_problem.hpp::class LinearResponseProblem` | `tests/python/test_response_problem.py`，Executable response-problem admission tests. | 可归入 #31 的官方/既有能力 |
| `gqc-solve-plan` | Stores GMRES options and response solve request metadata. | `src/response/solve.hpp::class ResponsePlan` | `tests/python/test_response_operator.py`，Operator setup and response shape checks. | 可归入 #31 的官方/既有能力 |
| `gqc-batch-plan` | Represents a prepared batch and its workspace accounting. | `src/response/solve.hpp::struct ResponseBatchPlan` | `tests/python/test_response_block_resident_cuda.py`，Batch/resident response path exercised. | 可归入 #31 的官方/既有能力 |
| `gqc-gmres-options` | Controls restart, true-residual cadence and reorthogonalization. | `src/response/native_gmres.hpp::struct GmresOptions` | `tests/python/test_response_krylov.py`，Krylov residual and failure cases. | 可归入 #31 的官方/既有能力 |
| `gqc-gmres-solve` | Performs matrix-free GMRES and accepts only a true residual. | `src/response/native_gmres.cpp::solve_gmres` | `tests/native/test_native_gmres.cpp`，Native convergence and refusal tests. | 可归入 #31 的官方/既有能力 |
| `gqc-resident-backend` | Keeps response workspace resident across actions and charges capacity. | `src/response/resident_krylov.hpp::class ResidentResponseBackend` | `tests/python/test_response_block_resident_cuda.py`，Resident path and workspace failures. | 可归入 #31 的官方/既有能力 |
| `gqc-recycle-space` | Publishes same-operator solved directions with generation and capacity checks. | `src/response/recycle.hpp::class ResponseRecycleSpace` | `tests/native/test_response_recycle_sdk.cpp`，Stale generation and dimension rejection. | 可归入 #31 的官方/既有能力 |
| `gqc-cuda-cpks-cache` | Caches exact CPKS operator images only under source/operator identity. | `src/response/cuda_cpks.hpp::class CudaCpksOperatorCache` | `tests/native/test_rhf_frame_recycle.cpp`，Same-operator response recycle. | 可归入 #31 的官方/既有能力 |
| `gqc-identity` | Binds geometry, reference and operator identity before reuse. | `src/hf/rhf_frame_identity.hpp::class RHFFrameIdentity` | `tests/python/test_geometry_response_reuse_cuda.py`，Wrong geometry/reference rejection. | 可归入 #31 的官方/既有能力 |
| `gqc-python-native` | Python entry point selects native sequence and records diagnostics. | `python/generativeqc/_response_native.py::def solve_sequence` | `tests/python/test_response_production_owner.py`，Production owner and receipts. | 可归入 #31 的官方/既有能力 |
| `gqc-failure` | Terminal failure preserves residual/work counters for fallback. | `src/response/resident_gmres.cpp::solve_gmres_resident` | `tests/python/test_resident_gmres_failures.py`，Failure and cleanup controls. | 可归入 #31 的官方/既有能力 |
| `gpu-cphf-entry` | Dispatches restricted CPHF with 2-D RHS and optional mo10 initial guess. | `gpu4pyscf/scf/cphf.py::def solve(` | `gpu4pyscf/properties/tests/test_polarizability.py`，Three-field polarizability regression. | 可归入 #31 的官方/既有能力 |
| `gpu-cphf-batch` | Shapes h1 as (nset,nvir,nocc) and sends all RHS through one Krylov call. | `gpu4pyscf/scf/cphf.py::def solve_nos1` | `gpu4pyscf/properties/tests/test_polarizability.py`，Multi-direction polarizability path. | 可归入 #31 的官方/既有能力 |
| `gpu-cphf-mo10` | Uses caller-provided first-order orbitals as the initial Krylov guess. | `gpu4pyscf/scf/cphf.py::x0 = mo10.reshape` | `gpu4pyscf/scf/cphf.py`，Source-level executable branch; GPU run in issue31. | 可归入 #31 的官方/既有能力 |
| `gpu-krylov` | Shared Krylov subspace, stable QR and callback, with explicit convergence failure. | `gpu4pyscf/lib/cupy_helper.py::def krylov` | `gpu4pyscf/lib/cupy_helper.py`，Pinned source plus issue31 GPU run. | 可归入 #31 的官方/既有能力 |
| `gpu-stable-qr` | Drops linearly dependent trial vectors under lindep. | `gpu4pyscf/lib/cupy_helper.py::def _stable_qr` | `gpu4pyscf/lib/cupy_helper.py`，Pinned source branch exercised by CPHF. | 可归入 #31 的官方/既有能力 |
| `gpu-polarizability-vind` | Builds the AO induced-potential map from orbital rotations. | `gpu4pyscf/properties/polarizability.py::def gen_vind` | `gpu4pyscf/properties/tests/test_polarizability.py`，Independent scorer uses this map. | 可归入 #31 的官方/既有能力 |
| `gpu-jk-response` | Returns the SCF response potential provider used by CPHF. | `gpu4pyscf/scf/hf.py::gen_response` | `gpu4pyscf/scf/hf.py`，Pinned source and GPU response run. | 可归入 #31 的官方/既有能力 |
| `pyscfad-implicit` | Wraps an implicit root and its derivative rule. | `pyscfad/implicit_diff.py::custom_root` | `tests/test_scf.py`，SCF differentiation tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `pyscfad-linear-solve` | AD-compatible sparse linear solve primitive. | `pyscfad/_src/scipy/sparse/linalg.py::def gmres` | `tests/test_backend.py`，Backend and derivative checks. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `pvmc-sampling` | Samples matrix/coordinate observations under a prescribed mask and density. | `ZCT.py::def zct` | `README.md`，Author workflow example, not a CPHF solver. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `pvmc-analysis` | Aggregates sampled matrix reconstruction results after the run. | `AnalyzeResults.py::def get_eigenvalue_matrix` | `README.md`，Post-processing example. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `hvmc-vmc` | Runs variational Monte Carlo and stores sampled configurations. | `vmc.py::def vmc` | `Examples/README`，Example workflow. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `hvmc-zct` | Uses observed row/coordinate sampling for matrix completion experiments. | `ZCT.py::def zct` | `Examples/ResultsZCT/README`，Stored result protocol. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `pymor-dwr` | Computes dual-weighted residual error estimates for a reduced model. | `src/pymor/reductors/dwr.py::def estimate_error` | `src/pymordemos/output_error_estimation_with_dwr.py`，DWR tests and demo. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `pymor-residual` | Builds residual operators and norms for model reduction. | `src/pymor/reductors/residual.py::class ResidualReductor` | `src/pymortests/algorithms/krylov.py`，Residual reductor tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `pymor-krylov` | Constructs a Krylov basis for operator reduction. | `src/pymor/algorithms/krylov.py::def rational_arnoldi` | `src/pymortests/algorithms/krylov.py`，Krylov algorithm tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `qemfi-model` | Fits low/high-fidelity data through a multi-fidelity statistical model. | `MFML/Model_MFML.py::class ModelMFML` | `MFML/LearningCurves.py`，Learning-curve evaluation. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `qemfi-cost` | Plots fidelity learning curves against measured computational time. | `MFML/TimeLC_plots.py::def plot_function` | `MFML/TimeLC_plots.py`，Cost/accuracy visualization. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `openmdao-coloring` | Stores graph coloring and sparsity information for derivative solves. | `openmdao/utils/coloring.py::class Coloring` | `openmdao/core/tests/test_coloring.py`，Coloring tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `openmdao-approx` | Schedules finite-difference or complex-step derivative approximations. | `openmdao/approximation_schemes/approximation_scheme.py::class ApproximationScheme` | `openmdao/core/tests/test_approx_derivs.py`，Approximation tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `openmdao-jacobian` | Owns assembled/approximated Jacobian subjacobians and derivative products. | `openmdao/jacobians/jacobian.py::class Jacobian` | `openmdao/jacobians/tests/test_jacobian.py`，Jacobian tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `cppad-forward-sparse` | Propagates forward-mode Jacobian sparsity through an AD tape. | `include/cppad/core/for_sparse_jac.hpp::ForSparseJac` | `test_more/general/sparse_jacobian.cpp`，Sparse Jacobian executable tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `cppad-reverse-sparse` | Propagates reverse-mode Jacobian sparsity. | `include/cppad/core/rev_sparse_jac.hpp::RevSparseJac` | `test_more/general/rev_sparse_jac.cpp`，Reverse sparse tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `cppad-checkpoint` | Encapsulates a function as an AD checkpoint with sparse derivative support. | `include/cppad/core/chkpoint_one/chkpoint_one.hpp::class checkpoint` | `test_more/general/chkpoint_one.cpp`，Checkpoint tests. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `mfgnn-low` | Trains a low-fidelity graph model before high-fidelity transfer. | `multifidelity_gnn/train/train_low_fidelity.py::def main` | `README.md`，Training workflow. | 外部参照或强基线，不能恢复同一 CPHF 标签 |
| `mfgnn-finetune` | Transfers a low-fidelity model to high-fidelity labels. | `multifidelity_gnn/train/train_fine_tune_high_fidelity.py::def main` | `README.md`，Fine-tuning workflow. | 外部参照或强基线，不能恢复同一 CPHF 标签 |

## 由源码得到的算法结论

- GPU4PySCF 的 CPHF 已接受二维 RHS、稳定 QR、共享 Krylov 子空间和 `mo10` 初猜。三方向极化率是原生多 RHS 强基线。
- GQC 已有真实残差门、resident workspace、recycle generation、operator/source identity 和 CUDA CPKS cache。新增 batch、recycle 或常驻显存本身不能被写成新贡献。
- PVMC/HVMC 的 `zct`/`vmc` 处理坐标或矩阵采样，评估依赖 `Xtrue` 或保存结果。它们不能替代同一 CPHF 方程的 exact/legal reuse。
- pyMOR DWR 提供 primal/dual residual 估计，OpenMDAO/CppAD 提供 coloring 和 forward/reverse sparse AD，QeMFi 与 multifidelity GNN 提供 fidelity/cost learning。它们只能作为目标误差、稀疏导数和多保真成本设计参照。

## 最小可运行验证

| 验证 | 命令/入口 | 结果 |
|---|---|---|
| 审计 ledger | `python3 scripts/check_source_audit_32.py` | 10 个来源、37 条观察通过路径/commit/许可证/符号/测试检查。 |
| GPU4PySCF CPHF | `scripts/run_gpu4pyscf_4arm.py`，n2 Slurm GPU | 17 个分子、3 条请求轨迹的 A–D 原始记录，独立 scorer 在封存后重算。 |
| GQC residual | `_references/gqc/tests/native/test_native_gmres.cpp` 与 `tests/python/test_response_krylov.py` | 固定源码中可见真实残差、失败和重启分支。 |
| DWR/稀疏参照 | pyMOR demo、OpenMDAO coloring tests、CppAD sparse tests | 只验证外部算法入口和边界，不把输出当作量化标签。 |

`scripts/run_algorithm_controls_32.py` 另外运行固定离散 DWR、错误协议拒绝、矩阵补全不可得、多保真差值、稀疏 coloring 和 forward/reverse pattern 控制。输出见 `algorithm_controls_32.json`。这些控制分别保留估计、统计差值和证据不可得语义。

审计结论只支持“现有实现能力及本项目增量的可检验分界”。是否存在归因收益由 Issue #31 的四臂原始 JSON 和独立评分决定。
