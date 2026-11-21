# Issue #26 protocol

生产器固定 `qm9-000003` 的源元数据与数组散列、GQC `2791504cc238fe83d328fc1718080642b288222a`、
RHF/STO-3G、FP64、原点和 `vibedataset.discrete_response_error.v1`。探针向量在
生产启动前固定。封存输出不含完整目标参照。

评分器重新读取同一源资产，构建新的 GQC `DualResponseModel`，重新生成全空间
标准基、随机、RHS 和近奇异探针。它只比较算子、矩阵和探针，不读取 CPHF oracle。
近奇异和非对称控制使用预登记的合成系统或矩阵扰动，专门检查残差-only 和错误
稳定性因子能否被击穿。

证书状态只在以下条件同时满足时为 `accepted`：全空间装配与原生作用的误差低于
`1e-10`、随机和 RHS 探针一致、近奇异探针一致、矩阵对称性可解释。任何算子
不一致都返回 `evidence_unavailable`，不直接发布目标值。
