# Psi4 的静态场响应与可复用的方向

对同一分子的静态偶极极化率，Psi4 1.10 已经用三个笛卡尔电场右端得到整个 3×3 张量。读出三个偶极分量共用每一个场方向的轨道响应。固定源码为 `f2492db10de56b30b188239bdc6b4cfbc4a23bd5`。这份审计追踪代码和已有测试输入，本轮没有安装或执行 Psi4。

## 从用户输入到物理算子

| 层次 | 固定版本的行为 |
|---|---|
| 参考态与扰动 | `run_scf_property` 识别线性响应属性，设置 SAVE_JK，计算参考波函数并把求解容差和迭代上限传入 `cpscf_linear_response`。`MintsHelper::ao_dipole` 产生 x、y、z 三份 AO 矩阵，驱动乘 −1，变换为 Coccᵀ (−μ) Cvir。RHF 为三个占虚矩阵，UHF 对每个场方向交替存入 α、β 两个矩阵。[属性入口](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/driver/procrouting/proc.py#L3161) · [AO 积分](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/libmints/mintshelper.cc#L1569) · [右端构造](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/driver/procrouting/response/scf_response.py#L119) |
| RHF 原生执行 | `RHF::cphf_Hx` 加总一电子 Fock 块作用和二电子响应。后者从试探占虚旋转构造左右系数，批量进入 JK，再按 HF/泛函返回对应占虚投影。缺少 JK 对象或传入错误形状会抛出异常。`cphf_solve` 用对角 Fock 差预处理，每轮只把仍活跃的 RHS 送入 Hx。它逐向量更新 CG 系数；把向量送入同一 C++ 调用不能直接推导每个 RHS 的 J/K 成本降为零。[一／二电子作用](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/libscf_solver/rhf.cc#L371) · [Hx 与迭代](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/libscf_solver/rhf.cc#L605) |
| UHF 原生执行 | `UHF::cphf_solve` 要求成对 α/β 向量，数目为奇数时拒绝。每对对应一个扰动。二电子部分构造两组试探密度并执行 JK；两自旋通过 Coulomb 项耦合，各有自身交换和适用的 XC 响应。每个方向用两个自旋块的合并残差更新活跃集。[自旋块及 JK](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/libscf_solver/uhf.cc#L518) · [CPHF](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/libscf_solver/uhf.cc#L748) |
| 张量与验收 | 一次 `cphf_solve` 得到各方向的解。对同一属性族，每个 i 方向左向量与每个 j 方向解取点积，RHF 系数 −4，UHF 逐自旋相加、系数 −2。一次请求偶极、四极和无迹四极会将各族 RHS 汇集后求解，再分别返回各族方阵。RHF/UHF 在达到迭代上限时仍能返回最后的向量，`cphf_converged_` 和高级别打印警告记录收敛状态；该 Python 收缩路径没有先判断此标志。不同实现的迭代残差和算子调用数需按各自定义比较。[张量收缩](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/driver/procrouting/response/scf_response.py#L156) · [RHF 终态](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/libscf_solver/rhf.cc#L837) · [UHF 终态](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/libscf_solver/uhf.cc#L1045) |

## 对额外观测量究竟可复用什么

低层 Python 暴露了 `cphf_solve` 和 `cphf_Hx`；前者把响应矩阵列表交还调用者。上游 Psi4NumPy 示例通过后者求三个场方向的解，再双循环生成九个张量分量。`scf-response1` 包含 RHF 水的多属性请求；`scf-response3` 同时包含水阳离子 UHF 参考和中性水 RHF/UHF 的一致性检查。这些是版本内可复核的测试规格。[低层绑定](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/export_wavefunction.cc#L337) · [可编辑的三方向示例](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/tests/psi4numpy/cphf/input.py#L35) · [RHF 测试](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/tests/scf-response1/input.dat#L11) · [UHF 测试](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/tests/scf-response3/input.dat#L22)

在零场固定几何、同一参考及可解的同一线性化方程下，沿 u 的响应是三个笛卡尔响应解的线性组合。对固定的一电子读出 O，其场导数可用 Tr(O δD) 得到。Mulliken 的具体读出已有源码依据：Psi4 在 AO 表示将两个自旋密度分别乘 S，再按原子累计对角线，净电荷等于核电荷减去人口数。在固定 AO 与核的电场扰动下，已有 δD 给出 δqₐ=−Σ_{μ∈A}(δD S)μμ，因而可与偶极共用同一轨道响应。这里只做了公式与源码对应。高层静态接口在各属性族内部收缩，直接返回张量；它没有在这个入口发布原子电荷的场响应、跨族混合张量或可跨记录恢复的轨道响应资产。若只保存九个偶极分量，其他一电子读出通常还需要占虚解或密度响应。[Mulliken 的实际定义](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/libmints/oeprop.cc#L1428)

同版本还有一个真实的跨观测量消费者。RHF 核 Hessian 路径按核坐标分批求 CPHF，写入 `Uai^A`；补入 overlap 变化形成 `Upi^A` 后，同时收缩三个偶极导数并供 Hessian 组装读取。这里的扰动是核坐标，偶极算符和核项的显式导数也参与计算。核坐标响应与均匀电场响应应使用不同资产身份。[求解与保存](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/scfgrad/response.cc#L2157) · [偶极导数](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/scfgrad/response.cc#L2193) · [Hessian 组装](https://github.com/psi4/psi4/blob/f2492db10de56b30b188239bdc6b4cfbc4a23bd5/psi4/src/psi4/scfgrad/response.cc#L2311)

RES-001 已知 x、y 响应时，再求 z 并对三个混合方向线性组合，是公平的手写基线。对每个新读出重复解一次 CPHF 会高估编译器收益。可比较的增量是自动判定已覆盖的扰动子空间、校验跨轮状态与真实残差、处理不匹配后的回退，并计入这些步骤之后实际执行的 J/K。该结论依赖相同方法/基组、几何、场算符、参考分支、占虚规范和数值精度。[RES-001 实测](../experiments/gqc_residual_response/README.md)
