# 目标误差、稳定性与观测量门槛

固定离散方程 A x=b、读出 q=wᵀx。候选 x̃ 的缺陷 r=b−A x̃ 给出 q−q̃=wᵀA⁻¹r。在欧氏范数下，用经论证的 γ≤σmin(A) 可给出 ||w||₂||r||₂/γ 的代数上界。使用近似对偶 ỹ 时，中心修正为 ỹᵀr，余项至多 ||w−Aᵀỹ||₂||r||₂/γ。有限精度的操作、测得的奇异值和电子态本身各有独立的误差来源。对组合减法还要加入每个历史操作数误差乘其系数绝对值，以及浮点求和消减。只保存历史数值会丢失这项依据。[原协议与误差类型](../experiments/response_quality_prior/protocol.md)

## 可从源码复用的机制

| 实现 | 固定实现、前提及失效行为 |
|---|---|
| pyMOR 2026.1.1 | DWRCoerciveRBReductor 将每个输出的转置方程分别投影。CorrectedOutputFunctional.apply 求降阶对偶，作用于投影后的正向残差。DWRCoerciveRBEstimator.estimate_output_error 将正向估计与各输出对偶残差估计相乘，CoerciveRBEstimator.estimate_error 按调用者给的 coercivity_estimator 作除法。数学模型须提供有效的稳定性因子。[正对偶构造和投影](https://github.com/pymor/pymor/blob/36a0035e180694c7ad4eb8f083d9f1d65ceb6f42/src/pymor/reductors/dwr.py#L118) · [输出估计](https://github.com/pymor/pymor/blob/36a0035e180694c7ad4eb8f083d9f1d65ceb6f42/src/pymor/reductors/dwr.py#L231) · [因子来源](https://github.com/pymor/pymor/blob/36a0035e180694c7ad4eb8f083d9f1d65ceb6f42/src/pymor/reductors/coercive.py#L86) |
| GQC | ErrorEvidence 绑定预定、实算与比较模型、范围和单位。AccuracyAssessment.outcomes 区分参照差与经验估计；公开 BOUND 需要已实现的特定物性证明。EmpiricalHFEstimator.predict 对域外特征抛错，能量／力训练包络只给估计；evaluate_holdout 检查训练族泄漏及误覆盖。响应 blocked solve 单独核对每个 RHS 的真实残差与算子调用。将这些接口迁到外场电荷与二阶矩时，须另建其 w、状态及目标误差证据。[证据类型](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/accuracy.py#L259) · [校准域与外推](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/accuracy_estimator.py#L193) · [原生块](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1464) |
| PySCF 2.14.0 | MP2 梯度中的 _response_dm1 形成读出侧右端、诱导密度和有效势，CPHF 解进入弛豫密度并供多个坐标使用。既有实测已含冻结态负例。对于本项目的外场读出，Krylov 的返回值须再检查物理残差和读出精度。不同读出若需不同对偶，须逐个承担相应成本。[弛豫密度](https://github.com/pyscf/pyscf/blob/c63a953ba603a5ad8c1d65d88da72aaf05ede4d8/pyscf/grad/mp2.py#L268) · [分子参照审计](response-dual-prior-adjoint.md) · [v2 复核](../experiments/cphf_v2/README.md) |

## 可复现的误接受

在预登记的三维系统中，候选满足 1e−10 的朴素物理残差门槛，实际残差为 2.91×10⁻¹¹。但目标沿近奇异方向，绝对误差为 1/4。用固定版 pyMOR 及同一 1e−8 目标门槛得到下表。[输入、实现与原始读数](../experiments/response_quality_prior/pymor.json)

| 对偶空间 | 提供的稳定性因子 | 修正输出 | 数值误差估计 | 实际绝对误差 | 决定 |
|---|---:|---:|---:|---:|---|
| 未包含第二坐标 | 2⁻³³（真实下界） | 0 | 0.25 | 0.25 | 拒绝 |
| 未包含第二坐标 | 1（刻意过大） | 0 | 2.91×10⁻¹¹ | 0.25 | 误接受 |
| 包含第二坐标 | 2⁻³³ 或 1 | 0.25 | 0 | 0 | 接受，精确对偶恰能给出正确修正 |

准确的单个读出可能掩盖错误稳定性因子。在分子任务中须报告因子的来源及适用范围，还须计入准备对偶或估计条件性的费用。GQC 的 21 个已有测试同时复核了经验估计的域、证据身份、留出误覆盖和真实块残差计数。三维对照使用 0.78 秒墙时，上游测试使用 0.96 秒，两者均无分子 SCF 或 J/K 工作。[命令、版本与测试结果](../experiments/response_quality_prior/verification.json) · [原始 pyMOR 日志](../experiments/response_quality_prior/pymor.log.gz)
