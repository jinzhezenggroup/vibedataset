# 算法对照矩阵（Issue #32）

矩阵依据固定版本源码审计表 [SOURCE_AUDIT_32.md](SOURCE_AUDIT_32.md)。`exact/legal reuse`、目标导向近似、统计补全、多保真预测和 AD/编译器的输入、输出和证据语义分开记录。

| 路线 | 最近邻实现 | 直接可恢复的标签 | 失败/边界 | #31 四臂归属 | 本项目可检验量 |
|---|---|---|---|---|---|
| 同算子精确复用 | GQC `ResponseRecycleSpace`、`CudaCpksOperatorCache`、GPU4PySCF `mo10` | 在几何、方法、基组、状态、算子、AO/MO 约定和容差完全一致时，可复用响应向量或作为初猜 | identity、generation、dimension、true residual 任一不符即拒绝或重算。`mo10` 本身只是初猜 | GQC 资产层在 C/D。GPU4PySCF 官方初猜在 A/B | AO 密度、目标标量、独立真残差、重算成本和命中条件 |
| 目标导向近似 | pyMOR DWR、GQC 残差/对偶/SVD 入口 | 可给出固定离散问题上的误差估计或接受决定 | 离散算子一致不等于连续物理模型一致。证书覆盖不足时必须 `evidence-unavailable` | 独立 scorer 与 C/D 的质量门 | 误接受、误拒绝、覆盖率、证书成本和近奇异控制 |
| 原生多 RHS / Krylov | GPU4PySCF `cphf.solve_nos1`、`cupy_helper.krylov` | 同一 CPHF 方程上同时求多个响应列 | 已是官方强基线。RHS 数少不等于端到端更快 | A/B 官方后端基线。B 的改动不能把此能力重新命名 | operator actions、Fock/JK 代理计数、墙时、GPU 传输和误差 |
| 矩阵/坐标补全 | PVMC/HVMC `zct`、`vmc` | 在矩阵结构或采样模型假设下预测缺项 | 依赖观测掩码、结构假设和 `Xtrue` 评估，不能恢复同一 CPHF 响应标签 | 外部辅助，不属于 A–D | 只作为负/边界参照，保留目标标签不等价 |
| 统计多保真预测 | QeMFi `ModelMFML`、multifidelity GNN low/high/fine-tune | 预测高保真统计量或 fidelity difference | 训练/推理成本、分布漂移和不确定性必须计入。预测值不是目标协议求解结果 | 外部辅助，不属于 A–D | label error、calibration、训练/推理、数据选择和 OOD 风险 |
| 稀疏导数/编译器 AD | OpenMDAO coloring、CppAD forward/reverse sparse/checkpoint、PySCFAD implicit diff | 稀疏 Jacobian/JVP/VJP 或隐式导数 | 稀疏模式和导数定义不等于 CPHF 物理身份。forward/reverse fallback 需计费 | 外部算法参照。若用于 B/D，必须单列后端因子 | JVP/VJP 误差、颜色数、回退、编译和验证成本 |
| GQC 目标相关 planner | 本项目新增编排。输入历史资产、请求序列和成本模型，输出复用/新 RHS/拒绝 | 同协议目标请求的响应列和标量，带独立质量证据 | 不得读取未来真值。跨协议只允许初猜/精修/拒绝分类 | C 为官方后端，D 为官方后端加 patch | 四臂主效应、交互效应、cost–coverage–risk frontier |
| GPU4PySCF backend patch | 本项目 `response_cache.py` 的 exact operator-image cache | 不改变物理标签，只复用同一 FP64 operator image | 仅接受完整字节相同的输入。缓存未命中仍调用官方 map | B 为 native+patch，D 为 GQC+patch | cache hit/miss、operator rows、AO 误差、端到端墙时 |

## 四臂能力映射

| 能力 | A 原生/官方 | B 原生/魔改 | C GQC/官方 | D GQC/魔改 |
|---|---:|---:|---:|---:|
| GPU4PySCF SCF/CPHF | ✓ | ✓ | ✓ | ✓ |
| 官方二维 RHS/Krylov | ✓ | ✓ | ✓ | ✓ |
| exact backend operator-image cache |  | ✓ |  | ✓ |
| 历史响应资产身份与请求规划 |  |  | ✓ | ✓ |
| 生产进程读取评分真值 |  |  |  |  |
| 独立 scorer 重建目标和残差 | 封存后统一执行 | 封存后统一执行 | 封存后统一执行 | 封存后统一执行 |

## 研究边界

“批处理”“Krylov”“recycle”“常驻 GPU”“AD”“矩阵补全”和“多保真预测”均已有固定版本实现。四臂实验只把 **目标相关请求规划/资产身份** 与 **最小后端 exact-image cache** 作为可归因因素，任何收益都要由配对原始记录、AO/目标误差和完整成本共同证明。
