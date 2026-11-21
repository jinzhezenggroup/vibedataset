# 量化学伴随、正对偶降阶与 Krylov 回收

## 一次轨道弛豫求解给出整个 MP2 梯度

Handy 与 Schaefer 在 1984 年已讨论用与扰动方向无关的方程计算相关波函数能量导数。PySCF 2.14.0 的受限 MP2 梯度入口给出具体实现。它先根据相关密度等中间量形成一个占虚右端 Xvo，`_response_dm1` 让轨道旋转生成试探密度，调用 HF 有效势（J/K）并投影回占虚空间，用 CPHF 求出 dvo，填入弛豫一阶密度。后续各原子和三坐标分量共用这份密度，并各自计算核积分导数和 overlap 等显式项。这相当于闭壳层实轨道下求解同一个性质侧 Z-vector。对于一般非对称响应算子，对偶方程须使用转置作用。源码固定为 `c63a953ba603a5ad8c1d65d88da72aaf05ede4d8`。[原论文](https://doi.org/10.1063/1.447489) · [单右端与梯度组装](https://github.com/pyscf/pyscf/blob/c63a953ba603a5ad8c1d65d88da72aaf05ede4d8/pyscf/grad/mp2.py#L137) · [响应核](https://github.com/pyscf/pyscf/blob/c63a953ba603a5ad8c1d65d88da72aaf05ede4d8/pyscf/grad/mp2.py#L268) · [CPHF](https://github.com/pyscf/pyscf/blob/c63a953ba603a5ad8c1d65d88da72aaf05ede4d8/pyscf/scf/cphf.py#L46)

在不对称 H₂O 固定几何上执行全电子 RHF/MP2、STO-3G、FP64、无密度拟合，9 个笛卡尔梯度分量只进入了一次轨道弛豫 CPHF，右端形状为 2 个虚轨道 × 5 个占轨道。保持同一方向，对 ±0.001、±0.0003 Bohr 重新求 RHF 和 MP2 能量；将 dvo 清零作为错误对照。两个运行使用同样的真实响应残差门槛 2×10⁻⁷ 和投影梯度容差 2×10⁻⁶ Hartree/Bohr。

| Krylov 线性相关阈值 | 诱导势调用（另有一次残差核查） | 最大分量方程残差 | 两步长梯度误差（Hartree/Bohr） | 验收 |
|---|---:|---:|---:|---|
| 发布默认 1×10⁻¹³ | 5 | 1.317×10⁻⁶ 以内 | 7.54×10⁻⁸、2.09×10⁻⁸ 以内 | 残差超限 |
| 补充运行 1×10⁻²⁴ | 6 | 2.39×10⁻⁹ 以内 | 6.01×10⁻⁸、5.57×10⁻⁹ 以内 | 通过 |

物理残差是 max|Δε·dvo + V(dvo) + Xvo|。PySCF 的 Krylov 可在新方向范数平方低于线性相关阈值时停止。因此第一行的能量差分吻合与独立残差超限能够同时发生。补充运行只更改内部线性相关阈值，保留原门槛；两次均保留，合计 10 次几何 RHF/MP2 能量、2 个正常全梯度和 2 个去掉弛豫的梯度。去掉弛豫后的方向误差约 2.245×10⁻³ Hartree/Bohr。[默认结果](../experiments/response-dual-prior-coloring/mp2-default.json) · [补充结果](../experiments/response-dual-prior-coloring/mp2-tightened.json) · [Krylov 停止条件](https://github.com/pyscf/pyscf/blob/c63a953ba603a5ad8c1d65d88da72aaf05ede4d8/pyscf/lib/linalg_helper.py#L1293)

## 用正、对偶基和条件性控制标量误差

pyMOR 的 `DWRCoerciveRBReductor` 对可强制的线性稳态模型及线性读出分别建立正向基和每个输出的对偶基，投影正向残差供输出修正。实现采用负的读出作为对偶右端，残差符号与之配套。`CorrectedOutputFunctional.apply` 实际求解降阶对偶方程，再收缩残差；`estimate_output_error` 组合正、对偶残差估计，正向因子使用可提供的 coercivity 下界。若用 Aᵀz=c、r=b−A x̂ 约定，修正量为 ẑᵀr，而剩余误差为 (c−Aᵀẑ)ᵀA⁻¹r。在欧氏度量和已证明的最小奇异值正下界 γ 下，其绝对值至多 ‖c−Aᵀẑ‖₂‖r‖₂/γ。将该边界用于化学响应，尚须对实际算子、态和度量证明相应下界。固定 pyMOR 2026.1.1 `36a0035e180694c7ad4eb8f083d9f1d65ceb6f42`，518 个跟踪项，BSD-2-Clause，捆绑依赖许可另列。[理论来源](https://doi.org/10.1137/1.9781611974829.ch2) · [投影、对偶与校正](https://github.com/pymor/pymor/blob/36a0035e180694c7ad4eb8f083d9f1d65ceb6f42/src/pymor/reductors/dwr.py#L116) · [输出估计](https://github.com/pymor/pymor/blob/36a0035e180694c7ad4eb8f083d9f1d65ceb6f42/src/pymor/reductors/dwr.py#L226) · [coercivity 因子](https://github.com/pymor/pymor/blob/36a0035e180694c7ad4eb8f083d9f1d65ceb6f42/src/pymor/reductors/coercive.py#L86)

三维 SPD 控制样例的真实最小特征值为 1。只保留一个正向基和每个读出的一个对偶基，第一项由 2 校正到真实 10/3；第二项由 0 校正到 1.5，真值为 17/6。使用 α=1 时第二项估计值约 3.606，覆盖实际误差 4/3；故意传入 α=1000 时估计约 0.003606，覆盖失败。此版本对于普通双输出 NumPy 矩阵，自动构建默认双向量的分支将一行数组交给要求首轴为输出维数的向量空间，实测抛出 AssertionError。使用其正式 `dual_foms` 参数显式提供两套对偶方程后完成两组运行。该实验限定在三维模型；没有建立任何分子的误差证书。[可复现数据与反例](../experiments/response-dual-prior-coloring/pymor.json) · [作者示例](https://github.com/pymor/pymor/blob/36a0035e180694c7ad4eb8f083d9f1d65ceb6f42/src/pymordemos/output_error_estimation_with_dwr.py)

## GQC 直接从已有实现继承的部分

锁定 GQC 当前树的 `solve_many` 已支持 sequential、blocked、recycled。blocked 对 RHS 块做秩分解、共同构建搜索子空间并重新应用算子检验残差；recycled 则先检验问题身份和资源所有者，为新 RHS 投影初猜，完成求解后更新可用空间。回收基可以帮助原先未完整求解的方向；保存完整正解或对偶解还可在相同问题上直接收缩，二者的离线生成、存储、重验和在线算子成本均应计入。没有新的性能比较时，不能从“减少了 RHS”推出物理 J/K 一定下降。[GQC blocked](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1464) · [GQC 单 RHS 回收](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1237) · [GQC 多 RHS 入口](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1702)

本轮实跑 3 个 GQC 上游用例，分别验证多 RHS/秩亏一致性、不收敛求解不污染回收和旧算子身份拒绝/显式传输。OpenMDAO 的总导数正/反向联合着色综合用例也实际通过，CppAD 的正反 sparse_jac 原生示例正常完成。它们提供正确性与竞争能力证据，无法给出其他代码在特定 GQC 分子批次上的墙时。[执行与失败回执](../experiments/response-dual-prior-coloring/verification.json) · [着色与请求集的独立数值对照](response-dual-prior-coloring.md)
