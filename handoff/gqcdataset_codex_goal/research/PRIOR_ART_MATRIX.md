# 数据补全相关实现按机制比较

工程目标是让 GQC 在同一物理定义、精度与收敛要求下执行剩余科学程序。下表以已取得的源码与实跑边界区分哪些操作能直接省略；它也是后续声称方法增量时要越过的基线。

| 已有实现 | 输入、确实省略的工作 | 质量、失效与比较方式 |
|---|---|---|
| MolSSI QCManyBody v0.8.0 | 给定片段、实核/ghost 基组与 BSSE 目标，生成分量并集；全阶最终相互作用能可裁剪只为明细所需的任务。三轮 NoCP、追加 CP、重复取两者实际新增 4、3、0 次 RHF | 同目标最小手写联合公式也只用 7 个分量，错误 ghost 身份仍能组装出错误标量。普通含二体明细方案的 13 次工作包含额外目标。[源码与实验](audits/prior-completion-manybody.md) |
| Schofield 等原作者 v1.0.0 属性插补 | 从部分已给的性质/缺失掩码或结构预测缺列；训练权重可复用，不需执行电子结构求解。原作者 property-only 分支显式为缺失项赋 embedding | 预测属于统计标签。所有性质遮蔽且不输入结构时，多个不同分子具有同一输入；即使学习器运行成功也不能在任意精度下恢复各自的物理值。[论文权重与实跑反例](audits/prior-completion-imputation.md) · [模型](https://github.com/Savoie-Research-Group/mol_prop_imputation/blob/386217f233f5607a6c69e09c8bd9375fbde06444/random_drop_prop2prop/model_random_drop.py) |
| GQC checkpoint 与 xTBloom | 接纳兼容密度初猜，或维持整批计算上下文、工作区与上次态。目标态仍执行 SCF/SCC，可以只省部分迭代和准备操作 | 源诊断不能替代新目标验收，批次失败区分逐项结果与整批后续资格。[原生路径、拒绝与执行](FOUNDATION_CAPABILITIES.md) |
| PySCF、Psi4、TREXIO-tools | 固定态算符收缩、逐壳表示转换、投影初猜均有现有实现。档案的元数据容许确定轴次序时，手写转换足以复现偶极 | AO 归一化/自旋/占据与原点都可能改变目标。转换正确仍不能省略响应。实跑 3 份存档与跨基组初猜。[逐项目路径](audits/pyscf-and-archives.md) |
| GQC 驻点编译与 PySCFAD | 编译器按 R(x,q)=0 生成偏导与伴随右端，或以 SCF 固定点 VJP 求隐式导数。可以使用已知前向态，导数仍需物理转置作用与源参数依赖 | GQC 五个代数用例已运行。PySCFAD 源码已有专用线性求解；冻结密度的场导数对照可排除错误依赖删除。[GQC 编译](audits/gqc.md) · [PySCFAD 实现](audits/pyscf-and-archives.md) |
| QCFractal、AiiDA | QCFractal 单点 `find_existing` 按 spec/molecule 查已有记录，AiiDA 在同类节点散列候选上检查 `is_valid_cache`。两者可复用完全相同的工作 | 多个名字相似或使用相同计算程序不构成同一科学目标。这两条数据库路径读到核心选择分支；本轮无数据库吞吐测试。[QCFractal](https://github.com/MolSSI/QCFractal/blob/4ec1ed623f82536076c069dd65a4eb132969d9ed/qcfractal/qcfractal/components/singlepoint/record_socket.py#L444) · [AiiDA](https://github.com/aiidateam/aiida-core/blob/31c1dcf5936359c7eaaebaeb335dabe141dfb40e/src/aiida/orm/nodes/caching.py#L142) |
| QCDB 组合计算与 ANI 作者读取器 | `cbs` 先去重，再仅在 energy 分支按同基组、VARH 返回量覆盖关系删除可被上级方法提供的工作。ANI 读取器实际对请求字段做联合掩码 | 组合方法的身份和外推协议必须吻合；CBS-001 得到了可执行公式和错误接受的实证边界。尚未运行 QCDB 的外部求解器。[QCDB](https://github.com/qcdb/qcdb/blob/d9e156ef8b313ac0633211fc6b841f84a3ddde24/qcdb/driver/cbs_driver.py#L978) · [ANI 的实验结果](experiments/ani_composite/README.md) |
| SchNOrb、多保真 GNN、PVMC | SchNOrb 的 Hamiltonian head 对原子间及在位块拼接并对称化 H/S。多保真 GNN 从低保真 checkpoint 初始化并对高保真标签微调。PVMC 用核矩阵特征分解与插值项更新缺失矩阵条目并重置观测条目 | 均为局部实现审读，未训练或复现论文性能。对相同研究目标，可比较预测后再求解、学习近似与仅作 seed 三种语义；预测不能算作精确量化调用的成功。PVMC 的 `row_interpolation` 使用选中列，实验必须计入这些观测。[SchNOrb](https://github.com/atomistic-machine-learning/SchNOrb/blob/38cb268ea431b46e3b2088dda48bcd1983462ff5/src/schnorb/model.py#L335) · [多保真 GNN](https://github.com/davidbuterez/multi-fidelity-gnns-for-drug-discovery-and-quantum-mechanics/blob/84ee8a280557d7fbc2ebd1042468e21ce8ea16c6/multifidelity_gnn/train/train_fine_tune_high_fidelity.py#L148) · [PVMC](https://github.com/RateTheory/PVMC/blob/0d3340644047abc727896753f48650f8c5205a89/pvmc_step.m) |
| GQC TensorIR 自身的通用优化 | 节点内容散列包含类型/对称性，Program 只执行可达输出。`optimize.py` 已有 exact CSE、死节点消除、受限常量折叠 | 这些已有机制构成编译后端基线。CBS-001 的联合节点减少由原生图共享实现，即使执行更少节点，也未使一个缺失发布标签通过验收。[Program](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc_compiler/tensor/program.py#L158) · [优化器](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc_compiler/tensor/optimize.py#L479) |

目录之外纳入了直接插补及多体分量复用两个项目，并固定实际使用的 PySCF、Psi4 和默认 libcint 发布源码。论文映射未确定的当前树只作为该版本行为的证据。已按分子响应任务补齐 Psi4 从 Python 到原生 CPHF 的调用链，并实跑整组三轴预取、手写与 GQC 多 RHS 的公平对照。随后进一步核查了下列方法。[Psi4 源码](audits/prior-completion-response.md) · [实测](experiments/gqc_residual_multiround/README.md) · [覆盖表](source_coverage.csv) · [来源缺口](SOURCE_GAPS.md)

## 新取得的作者源码与运行基线

| 固定实现 | 源码追踪与实测 | 对 GQC 的约束 |
|---|---|---|
| OpenMDAO 3.45.2、CppAD 与 pyMOR 2026.1 | 比较稀疏 Jacobian 正/反向、代入着色及输出误差的对偶解；错误地把请求掩码当结构零在受控稠密矩阵上产生 165 的最大绝对偏差，已知其余 30 项时单种子和扣除恢复到舍入误差 | 最少端点、着色和已知值代入均有成熟先例；应报告分子实际 J/K。[着色与代码](audits/response-dual-prior-coloring.md) · [对偶与估计](audits/response-dual-prior-adjoint.md) |
| PySCF 2.14.0 MP2 梯度、GQC 原生 blocked/recycled | 实际 MP2 水的九个核梯度分量共用一个 CPHF 右端，另计显式核导数；GQC 的多 RHS、未收敛回收、跨身份拒绝测试已执行 | 伴随复用已有化学先例，RHS 更少仍可能花更多算子作用。[源到运行](audits/response-dual-prior-adjoint.md) |
| mlelec 论文相关归档与单独 qm7 Git 树 | 在作者归档代码和规定环境重跑两份几何，有场阶段各做四次对角化和零次诱导势更新；与自洽响应的差异在甲烷和水分别为 1.120365 和 1.504074 原子单位 | 固定零场有效 Hamiltonian、受监督性质模型和耦合响应各自登记。归档的代码与分支的训练入口也有实际差异。[版本、原始执行和差值](audits/mlelec-archive.md) |
| dm-PhiSNet 第一作者历史树、PhiSNet 后续适配、DelFTa v1 | 完整取得三棵树；历史训练与密度/物性分析有源可查。另核查六个原始发布位置 | 五个原始实现位置仍待补齐，作者历史代码与确切论文 commit 分列。没有运行这些模型的训练。[逐原始来源及证据](audits/intake-originals.md) |

GQC 固定版本的 block GMRES 在同一调用内合并初始残差子空间，同时逐列计算真实残差；分开调用会重复建立子空间。n5 独立对四种两列组合逐次追踪了基扩展和真残差检查。水分子中均为 10 次扩展及 10 次复核。[固定源码与运行跟踪](audits/partial-response-blocks.md) · [n5 对照](experiments/partial_response_blocks/n5/README.md)

## 独立 Hessian 与光谱参考（#40）

VeloxChem 的解析 RHF Hessian 通过核坐标 CPHF 解组装二阶导数。水、氨、氢化锂的 261 个笛卡尔分量已与官方 GPU4PySCF 1.9.2 对照。水的 Raman 去偏振比触发了实际重算，同一几何三个模式的极化率方向导数在两个步长下独立通过。此处执行的是 VeloxChem CPU 发行包。论文所用 GPU CPKS 另有性能实验边界。[固定源码、数值与回执](experiments/hessian_cphf/cross-engine/README.md) · [VeloxChem 的二阶导数论文](https://doi.org/10.1021/acs.jpca.5c04510)

GPU4PySCF 1.9.0 与 1.9.2 的官方 CUDA-12 wheel 上游发布作业现在可按 tag、运行 ID、容器 digest 和实际 CMake 配置追踪，两者均禁用 multigrid V2。PySCF 2.14 的七个固定上游 CPU 测试文件覆盖 RHF/UHF SCF 和梯度、RHF/UHF/RKS Hessian，共 138 个通过、18 个跳过。独立的项目响应标签、GPU4PySCF 示例及 GQC 论文水簇计时保留各自的协议和分母。[上游编译记录](environment/gpu4pyscf-20261122/upstream-v192/wheel-build-provenance.json) · [CPU 测试原始结果](environment/gpu4pyscf-20261122/upstream-v192/pyscf-cpu/receipt.json)
