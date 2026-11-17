# 部分标量历史下的 RHF 多右端求解

QM9 第 3 个分子的四条合格历史标量将三个对角目标压缩成两个物理右端。已有 CLI 把两列分成两次冷求解，各用 18 次 J/K。普通 GQC 一次求解三列，只用 22 次 J/K。固定源码表明，GQC 已能让不同右端共享同一组 Arnoldi 基。因而这个反例比较的是“选取哪些扰动方向”和“如何把它们组块”两个因素。该审计核对既有源码和回执，以下两列联合方案的性能仍待预登记实测。[历史 CLI 回执](../experiments/response_dataset_cli/history-verification.json) · [三列直接与伴随基线](../experiments/gqc_dual_response/oracles/qm9-000003.json)

## 固定 GQC 中实际共享的工作

核查提交 `2791504cc238fe83d328fc1718080642b288222a`。在 `solve_many(strategy="blocked")` 中，`ResponseProblem.validate_rhs` 接受相同响应问题下的有限实数列，并检查形状和可选扰动标签。`_block_solve` 为一次调用初始化同一个 basis。初始各列按顺序对已有列作两次修正 Gram–Schmidt，只有残量范数高于 breakdown 门槛才扩充初始基。对于确为线性相关的 RHS，仍保存每个原始右端的投影、解及真残差。一个块中的每列共用当前投影矩阵，各自求小型最小二乘。新的算子像只对当前基做投影；残差面板再作薄 QR 与小 SVD，保留超过阈值且容量容许的方向。此前已计算的基向量及投影列在本块内复用。[入口](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1702) · [输入契约](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_problem.py#L372) · [初始基](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1520) · [面板秩](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1423)

一次扩展对新基中的每一向量调用一次 `apply`。在这个检查点，所有原始 RHS 还各调用一次 `apply` 计算真实的 `b−Ax`，包括此前已过阈值的列。仅当全部满足各自的绝对或相对准则时整块通过；最后公布解时复用末次真残差。正常完成且初始秩非零时，每个检查点的算子次数等于这轮新基的列数加上原始 RHS 总数。各列的 `SolveResult.operator_actions` 都携带同一个整块累计值，应读一次 `MultiRHSResult.operator_actions`。返回的 `iterations` 按继续扩展时保留的新基列数累计，不能代替 J/K 或逐轮检查点数。`collect_basis=False` 省去对外公布诊断基，块内仍构建和使用它。本项目的 `MoleculeResponse.apply` 每次执行一个密度方向和一次 J/K 势构造。[扩展与真残差](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1599) · [公布与计数](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1659) · [分子算子](https://github.com/jinzhezenggroup/vibedataset/blob/dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a/scripts/probe_gqc_residual.py#L152)

每次新调用都会重新初始化块基。跨调用显式使用 `recycled` 时，GQC 走逐 RHS 求解及投影/回收路径，并校验问题身份和向量所属执行引擎。此处的两次 blocked 调用都未使用该路径。工作区字节或驻留向量槽不足可在首次物理算子动作前返回失败；零秩按每列 RHS 范数和目标判断；无可扩展方向且未收敛会给出 breakdown，耗尽迭代预算会给出相应原因。项目使用 `raise_on_failure=True`，已花动作仍属成本。CLI 遇到异常时回滚当次向量和标签，并记录模型的实际 J/K；某项标量独立资格失败还可触发普通路径重试。检查上游测试时，单位阵两列的固定断言为 4 次动作，含两次扩展及两次逐列残差；另有已回放的重复列与顺序、分块、回收三策略一致性用例。[失败与回收分支](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/python/generativeqc/response_solver.py#L1743) · [上游计数用例](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/tests/python/test_response_krylov.py#L286) · [既有执行回执](../experiments/response-dual-prior-coloring/verification.json) · [CLI 失败回执入口](https://github.com/jinzhezenggroup/vibedataset/blob/dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a/scripts/complete_response_dataset.py#L417)

## 36 和 22 的可核对分解

已有回执的 CLI 对应提交 `dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a`，脚本 SHA-256 为 `28256794651db5eac6a49c9bb4f393f513ae1b53689a191c19e6860efbc33de8`。同一 FP64 RHF/STO-3G 参考态有 5 个占据和 2 个虚轨道，响应空间维数 10。每次模型建立的 5 次 J/K 包含一次 Fock 核查和两对双线性检查。表中给出已记账的各次进程成本。[同态算子诊断](../experiments/gqc_dual_response/oracles/qm9-000003.json) · [请求和进程登记](../experiments/response_dataset_cli/verify_history.py)

| 进程与资产 | 响应块 | RHS | 准备 J/K | 当轮 J/K |
|---|---|---:|---:|---:|
| 产生四条历史标量 | q0、r2 两个普通伴随列同块 | 2 | 5 | 19 |
| 普通三轴求三个目标 | x、y、z 三个场同块 | 3 | 5 | 22 |
| 只导入上述四条历史标量 | 先单列 x+y+z，再单列 z | 2 | 5 | 18 + 18 = 36 |
| 导入全部六条合格非对角标量 | 单列 x+y+z | 1 | 5 | 18 |

四条历史分别为 y/q0、z/q0、x/r2、z/r2。项目的 `complete_missing` 先调用 `combined_field`，该函数以一列执行 `solve_many`；剩下 z/zz 再进入一次 `run_round`。该例的向量核验和普通重试都为零。两项解码和一项普通收缩均通过原有独立验收，逐项与普通三轴的差最大为 2.31×10⁻¹⁴，各自按目标原单位比较。三列直接基线记录的初始秩为 3。历史回执记录了整块动作总数，未给出各次扩展宽度。生产成本按共同历史另计；六条历史的产生另花 5 次准备与 22 次当轮 J/K。[既有分流与重试](https://github.com/jinzhezenggroup/vibedataset/blob/dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a/scripts/complete_response_dataset.py#L288) · [单列组合场](https://github.com/jinzhezenggroup/vibedataset/blob/dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a/scripts/gqc_dual_response.py#L250) · [完整结果](../experiments/response_dataset_cli/history-verification.json)

## 普通两方向强基线

设场方向 RHS 为 `b_x,b_y,b_z`，读出导数为 `c_j`，同一 RHF 响应算子为 `A`。记 `H(f,j)=c_jᵀ A⁻¹ b_f`。固定原点、单位、参考态和场约定后，可以在一次已有 GQC blocked 调用组成下列两列。选种只看历史标量的身份和资格，解码后仍按目标分别验收。

| 联合 RHS | 对两个可解码目标的操作 | 第三个目标 |
|---|---|---|
| `[b_x+b_y+b_z, b_z]` | 用第一列读 q0 和 r2，各减去已有的另外两轴 | 第二列读 zz |
| `[b_x+b_y, b_z]` | q0 减历史 y/q0 得 x/q0，r2 减历史 x/r2 得 y/r2。只需四项历史中的两项 | 第二列读 zz |
| `[b_x+b_y, c_zz]` | 前两项仍由第一列及两项已知量取得 | 用 z 的场 RHS 收缩第二列的伴随解 |

前两个场面板是可逆列换基。精确算术下每一级未截断块 Krylov 子空间相同，实际实现按每个右端的范数判停，还有秩阈值与浮点舍入。第三种需要正向和伴随使用同一算子；本项目在选定 RHF 规范下用两对确定性双线性探针核查自伴替换并保留独立参照。普通非自伴问题须按 `Aᵀ` 处理读出，不能沿用这一组块。当前 `run_round` 已可对任意所选普通场或读出端点拼列并一次求解，`combined_field` 支持任意三维场系数。将普通端点和组合场放在同一次求解只需调用方构造面板，上游求解器接口已具备该能力。上述布置各自实际 J/K、失败和墙时应由运行结果给出。[普通场与读出组块](https://github.com/jinzhezenggroup/vibedataset/blob/dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a/scripts/gqc_dual_response.py#L306) · [方程与同态核验](https://github.com/jinzhezenggroup/vibedataset/blob/dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a/scripts/gqc_dual_response.py#L175)

另一个信息条件是保留历史生产器已经算出的 q0、r2 完整伴随向量。后轮只要向量身份、内容和物理残差仍通过，x/q0、y/r2 便可直接点积，z/zz 仍需一个适用端点。应计入向量写入、读取和残差复核。此前另有“全部三轴向量已存”实测，三个对角请求使用 0 个新 RHS 和 3 次 J/K 复核。这项证据支持把向量留存列为单独资产策略；四标量历史实验没有把生产端数据库和向量一并带入新进程。[历史与向量用例](../experiments/response_dataset_cli/history-verification.json)
