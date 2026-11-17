# GQC 的初猜、目标求解与导数依赖

## 两个固定版本

数值探针使用 n2 构建，部署声明的源码为 `2bf3fd98da9c6cfba46ca83345e63e1d934e4780`，实际 CDLL 的 SHA-256 为 `67bc98a4549fe8854ed6ae65791c824024bd77a9e8e498c6891dea3b8de670c4`。当前上游树为 `2791504cc238fe83d328fc1718080642b288222a`，本轮对该树执行了 CPU 方程编译器测试。两者各有独立库存和证据。[来源锁](../sources.lock.json) · [接管时的阅读记录](gqc-intake.md)

## 从密度文件到新目标

| 运行版本的源码路径与符号 | 实际决策与可观测后果 |
|---|---|
| `python/generativeqc/checkpoint.py` 的 `load_checkpoint`、`_restore_states` | 核对源坐标散列、有序核、模型、基组/表示、提供方与数值控制。相同身份接受密度；只改几何或控制须显式允许热启动。读入的能量、残差和迭代数属于源诊断。[实现](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/python/generativeqc/checkpoint.py#L633) |
| `generativeqc_batch_restore_hf_warm_states` → HF 方法适配器 → `FleetPlan::restore_warm_states` | C ABI 先按 prepared topology 查每个描述符与尺寸，再复制候选。Fleet 把记录中的源坐标作用于原子，逐项验证后才清设备旧 seed 并交换有效项。物理验证失败时不会提前替换当前状态。[C ABI](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/src/api/c_api_batch.cpp#L746) · [HF 适配](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/src/methods/hf_method.cpp#L361) · [Fleet](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/src/scf/fleet.cpp#L674) |
| `validate_hf_warm_density_cuda` → `validate_hf_warm_density` → `validate_seed` | 读取源几何 AO overlap。RHF 要求正偶数电子、单重态，检查密度的有限性、对称性、Tr(DS) 及 S½DS½ 的占据区间。此处调用 ensemble 验收，未要求给定 Fock 与密度对易，也未求物性误差界。[CUDA 入口](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/src/scf/cuda/warm_density.cpp#L28) · [overlap](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/src/scf/rhf.cpp#L1212) · [度量验收](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/src/scf/solver/proposal_control.cpp#L25) |
| `FleetPlan::execute` → `run_rhf_cuda_bucket_cached` → `execute_hf_cuda_bucket_driver` | 从保留对象取密度作为初猜，在目标几何进入 CUDA HF driver，取得新结果和状态。Fleet 有按项冷启动重试路径，本次有效种子的结果均报告未回退。[调度](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/src/scf/fleet.cpp#L350) · [执行](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/src/scf/cuda/rhf_bucket.cpp#L567) |

CP-001 在 H₂ 上比较了冷启动、同身份收敛密度、同身份非驻定密度和改变几何的热启动。源能量写成 −100 Hartree 后，目标仍经过 8 次迭代，在 1.4 Bohr 得到 −1.116714325176 Hartree。已分开保存原生拒绝、批结果、独立参考和两步长力检查。上游也有篡改源诊断的测试，该科学问题已有直接先例。[CP-001 数值与成本](../experiments/checkpoint_probe/README.md) · [上游测试](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/tests/python/test_checkpoint.py#L470)

## 已知状态的导数

当前树的 `StationaryProblem` 声明目标 E、残差 R、独立状态坐标、规范及源参数。对 R(x,q)=0，`compile_stationary` 构造 L=E+λᵀR，生成 −Eₓ、Lₓ、Lq。使用者须解 Rₓᵀλ=−Eₓ，并接回上游参数的导数；在固定 x 处执行 E 只能给出偏导。状态已知与 λ 已知是两种资产。自动生成隐式算子对未打包的耦合状态有显式拒绝。CPU 上实跑 5 个上游用例，覆盖标量重求解有限差分、非对称转置作用、耦合参数权重与拒绝。该测试用例提供线性求解器，未调用分子哈密顿量。[编译器](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc_compiler/method/stationary.py#L525) · [测试](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/tests/python/test_stationary_problem.py#L96) · [执行记录](../experiments/gqc-stationary-cpu.json)

闭壳层 RHF/CPKS 的 `ResponseProblem` 绑定参考态、占虚布局、规范、算子和模型。`_BaseResponseOperator._base_action` 将旋转量映为 AO 密度变化，经 Coulomb/exchange 及适用的 XC 核产生诱导 Fock，再加上轨道能隙项。求解器提供真残差检查。这里追踪到算子接口；本次尚未在分子上贯通该响应路径。RHF 能量/力一致性只支持 CP-001 中已经比较的输出。[身份](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_problem.py#L170) · [算子](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_operator.py#L167) · [求解器](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1237)

精度模块 `EmpiricalHFEstimator.predict` 有训练域门槛，显式检查基组族、后端、AO 度量条件数、能隙、电子数等，对能量和力返回 `EvidenceKind.EMPIRICAL`。其源码域要求 conventional Cartesian RHF，CP-001 的 spherical 设置不能直接套用该校准。本轮实跑 18 个上游合成用例，检查超域拒绝、holdout 失配与证据分类。真实分子校准仍待独立验证。[测试输出](../experiments/gqc-estimator-cpu.json) [域门槛与预测](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/accuracy_estimator.py#L119)

编译器用例可在装有 NumPy 和 pytest 的本地 Python 中复现。固定源码树位置与顶层协议相同。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/_references/gqc/python" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m pytest -q -p no:cacheprovider \
  _references/gqc/tests/python/test_stationary_problem.py \
  -k 'nonvariational_scalar_sign or nonsymmetric_coupled_state_and_parameter_weights or automatic_implicit_dispatch_rejects_unpacked_coupled_states or declared_stationary_state_dispatches_generic_implicit_plan'
```
