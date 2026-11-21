# DUAL-001　QM9 构型上同一标量响应的直接与伴随求解

预登记日期为 2026-11-18。继承 RES-001/002 的有限基组 RHF/FP64 目标。在用户已授权的 n5 上，从预定的 8 个 QM9 分层分别选择最小档案 ID 的代表，按实际壳参数生成新的同协议参考态。已有 QM9 标量与几何各保留其原始身份。所有分层均保留，空层、参考态失败和不合格标量分别登记。先用已锁定 GQC 的水分子 fixture 做独立的编译／符号回归。该水例不加入外部队列统计。

## 方程和含义

外场为原子单位 F，固定核与 AO 基组、冻结芯数为零；h(F)=h(0)+F·r，原点取各自归档的实验室坐标零点。只支持常规实数闭壳层 RHF、占据在前的正交规范轨道。用 GQC 的旋转 X（K_ia=X_ia，K_ai=−X_ia）时，固定核下 dD=−2(C_o X C_vᵀ+C_v Xᵀ C_oᵀ)。物理响应算子 A=−dF_ov/dX，逐次执行编译的 dD、J(dD)−K(dD)/2 和 dF_ov 作用。每个笛卡尔外场 i 的右端 bᵢ=C_oᵀ rᵢ C_v。将每个读出写作 Lⱼ(D)=Tr(OⱼD)+核常量，生成其关于 X 的 TensorIR 转置作用得到 cⱼ；对称实 O 的独立公式为 cⱼ=−4 vec(C_oᵀOⱼC_v)。

| 读出 ID | 一电子算符 O 与常量 | 场导数单位 |
|---|---|---|
| q0 | −(P₀S+SP₀)/2，P₀ 指向归档中首个原子所属 AO，常量为该原子核电荷 | e/原子单位电场 |
| r2 | x²+y²+z²，全电子空间二阶矩 | Bohr²/原子单位电场 |
| zz | z²，全电子 z 二阶矩 | Bohr²/原子单位电场 |

每个请求 (i,j) 的同一目标为 Jᵢⱼ=cⱼᵀA⁻¹bᵢ=bᵢᵀA⁻ᵀcⱼ。实 canonical RHF 占虚空间内，轨道能隙作用自伴，库仑和交换在对称密度矩阵的 Frobenius 内积下自伴；从 X 到对称 dD 的映射及其转置给出 A 的对称性。因此读出与电场的右端可用同一次 GQC blocked Krylov 求解。本实验数值检查两个由固定种子 32417 产生的单位向量对的双线性点积，并比较每个编译读出 cotangent 与解析公式。实际 A 的谱条件、当前基组的实用精度和新颖性均不由这两个点积推出。三个读出均与电场偶极算符区分，真实对称结构可能让个别响应为零或右端相关，必须保留秩和分母。

## 路径、门槛与失败

- 所有策略同享 GQC 的原生多 RHS block，算子、真残差、FP64 无降精度。对照包括所有请求电场、所有请求读出两条 block 方案和外层选择的混合直接／伴随方案。新 RHS 使用 GQC block 已测的最终真残差，旧资产使用同一物理算子重新测量。只为本轮使用的旧端点付核验开销；损坏或不兼容的条目拒绝并补算。保存原始数值和验证状态，统计实际 J/K、不同 RHS、回退、编译、读写和时间。
- 必须核对 archive digest、实际科学身份（含轨道规范、积分/状态/基组/几何、方法、序和字段符号）、本轮右端身份与方向；维数相同不能取代上述检查。真残差阈值 1e−10，两对 scaled dot 及读出 VJP 误差分别须≤1e−10。block 相对／绝对容差 1e−12／1e−13。直接与伴随、独立 PySCF 2.14.0 CPHF 的同一标量差各须≤1e−8。零值仍须核对两条路径。
- 每个可用分子独立构造 PySCF 物理积分，零场从头验证目标分支，另对 x、y、z 各做 5e−4 和 2e−4 原子单位场正、负两侧完全重收敛的中心差分。SCF 能量／轨道梯度容差为 1e−13／1e−11，上限 150 次。每个步长的该标量差须≤1e−4（各自单位）；沿用此前预登记的量级。有限场超差、基态不一致、不收敛或数值失败保留全部记录及新增成本，不修上游或事后更改科学门槛。
- 只有通过全部适用科学检查的标量可作为已验证标签；其余保留 raw 和具体失败原因。缓存中的 X/Y 只是同一已验收响应问题的原始物理解，经残差检查后允许作中间量，每个电子观测量仍需单独通过独立验收。若完整直接或完整伴随享有更好的块秩／成本优势，按实际报告。对不同请求掩码及多轮调度的成本评价另行记录。

固定 GQC 版本为 `2791504cc238fe83d328fc1718080642b288222a`，PySCF 发布源码为 `c63a953ba603a5ad8c1d65d88da72aaf05ede4d8`。[GQC 分子轨道 JVP](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc_compiler/method/rhf_orbital_response.py) · [TensorIR 转置生成](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc_compiler/tensor/ad_program.py#L1251) · [GQC 多 RHS](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1903) · [独立 CPHF](https://github.com/pyscf/pyscf/blob/c63a953ba603a5ad8c1d65d88da72aaf05ede4d8/pyscf/scf/cphf.py#L53)
