# Issue #25 protocol

输入固定为 8 个有态留出 QM9 构型、历史文件和三类请求。四次重复、单线程
FP64、RHF/STO-3G、相同原点和 `vibedataset.discrete_response_error.v1` 质量
程序沿用 PR #24。生产进程无法访问 v2 oracle、目标真值或评分 JSON。独立分析器
在封存后读取历史 `two` 结果，只用于评分和比较。

独立手写模块只包含明确的 `xy`、`yz` 恢复恒等式以及普通 field/adjoint 回退。
它不调用候选 planner。`multi4` 在四个二值混合场的 15 个非空子集上逐项运行
精确有理数恢复和评分，最多使用三个独立行来恢复三维字段目标。第四列可以参与
候选和条件性排序，但不会增加字段空间的线性秩。

每条记录保存计划、恢复系数、输出误差、J/K、RHS、块数、输入/输出字节、wall
time、质量复核、失败和回退。`issue25_result.json` 另外汇总旧封存的 direct、
adjoint、two、hand、vectors 和 dense 成本，避免用不同分母混合历史生产费用。
