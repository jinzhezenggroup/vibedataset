# RES-001　从存档态为新外场和新观测量生成剩余响应程序

预登记于 2026-11-18。首轮分子验证针对电子基态分支的静态线性响应。研究假设为，已验证的相同物理算子 A 下的解 X 满足 AX=B。当新外场含有既有扰动方向时，编译器只需求解已有方向张成空间以外的分量，同时保留密度对外场的隐式依赖。竞争解释为一个识别场方向的手写程序也能省下相同工作。项目不会把线性叠加或 Krylov 方法本身计为新发现。

## 目标、输入与范围

- 固定 GQC `2791504cc238fe83d328fc1718080642b288222a` 的完整树。已有资产为该树的 `tests/reference_data/posthf/{water,lih}.{json,npz}`。这两份是档案中具有多维占虚空间的中性闭壳层分子；水为 Cartesian、LiH 为 real spherical，均使用记录中的具体 STO-3G 壳和 Bohr 几何。读取 conventional RHF 分支、所有电子、FP64、无 DF/冻结芯，绑定轨道规范、归一化 AO 的 S/h/F/C/轨道能/占据及归档 AO ERI。H₂ 的占虚空间为一维，另一份带 f 壳档案为阳离子，均不计入本预登记范围。原存档制造开销不可从历史数据反推。
- 第一轮缺少电场响应，从该存档的零场 RHF 态计算并保存 x、y 两个单位方向的占虚响应解与其身份。这是现场生成的后续复用资产。第二轮请求方向 (1,1,0)、(1,0,1)、(0,1,1) 处对场强 t 在 t=0 的导数，方向按给出的分量使用、不另做单位归一化。每方向要求总偶极三分量及第一个原子 Mulliken 净电荷的响应。核静止，固定实验室坐标原点；偶极响应为原子单位，电荷响应为 e/原子单位电场。选取不同的观测量，使只保留上轮偶极标签的资产不足以直接推出所有请求。
- 同一验证样本的每条路径使用相同 C、积分、场耦合 h(t)=h(0)+t u·r、精度和公开门槛。GQC 的 `build_rhf_frame_response` 对轨道旋转导出 dD 及 −dFov 作用。生成 CPU TensorIR 执行 dD → J(dD)−K(dD)/2 → 占虚响应；新求解器调用 GQC `solve_many(strategy="blocked")`。按显式场方向做小空间精确有理消元，只生成未覆盖 RHS，以及组合已有/新解的 TensorIR 程序。末端从 dD 收缩观测算符。两个上游测试入口为 `tests/python/test_rhf_frame_response.py` 的 orbital action 检验和 `tests/python/test_response_krylov.py` 的多 RHS 例。在源码选择层 `common/specialization.py` 的既有 profile guard 负责实现适配，`automatic_artifacts.py` 查询原生执行回执，均不能据此认定有跨记录的响应充分性证明。
- 最强手写对照用相同条件验收 x/y 响应，仅求 z 并手写求和。无解资产的 GQC 对照用同一 blocked 算法一次提交三方向，并共享各物性的密度响应。普通完整方向缓存处理三个新方向均未命中。三条路径都重新检查最终三个真残差。独立解析对照采用 PySCF 2.14.0 的 CPHF；两步长 ±场重做同方法 RHF，给出完全自洽的中心差分。冻结密度会使这两类观测量的场导数为零，保留作错误对照。

## 推翻条件与成本

沿用归档零场设置，核对其 SHA、真实 AO 归一化和轨道方程；数值控制与阈值在 configs/gqc_residual_response.json。任一实际新增 SCF 未收敛、终态真残差超过 1e−10、与独立 CPHF 或直接 GQC 相差超过 1e−8，或任一步长的任一输出与自洽差分相差超过 1e−4，则该目标的精度判断失败。两类单位分别比较。检查与同标签但身份不同的资产，以及身份匹配、内容重新散列但物理残差错误的资产的拒绝及恢复。存档缺失或不被接受时重新规划剩余求解。记录三条可比路径的真实 GQC 算子调用次数（每次含一组 J/K）、求解 RHS 数、加载和残差复核、准备状态和存储字节、首次编译与重复执行成本。如原生 blocked 已很高效，或验证成本抵消部分收益，按实际差额报告。只报告本组 FP64／目标误差验收，不主张任意响应条件数下的误差界或普遍逐位完全一致。

完整 GQC 源码中参考态的生成、物理身份与扰动求解均可复查。[归档生成](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/tools/generate_posthf_references.py) · [TensorIR 轨道响应](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc_compiler/method/rhf_orbital_response.py) · [GQC blocked 解算](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1903) · [PySCF 无重叠扰动 CPHF](https://github.com/pyscf/pyscf/blob/c63a953ba603a5ad8c1d65d88da72aaf05ede4d8/pyscf/scf/cphf.py#L53)
