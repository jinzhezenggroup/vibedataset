# Issue #25 独立手写基线与四列搜索

本轮固定 PR #24 使用的 8 个有态留出构型、四次重复、`cycle-one`、
`cycle-three`、`cross-three` 三个请求场景和同一生产/评分分离。生产进程只读取
零场、历史资产、请求和质量程序，不读取目标参照。[协议](protocol.md) · [逐项结果](issue25_result.json)

## 独立手写基线

`independent_hand_plans.py` 独立写出 `U=x+y`、`V=y+z` 的恢复式，没有导入候选
planner 的 `hand()` 或 `compile_plan()`。本轮分别运行 `hand_field_independent`
和 `hand_adjoint_independent`。每个方法覆盖 96 条未来记录，所有输出均接受、
没有回退，独立手写计划本身 96/96 与模块定义一致。

| 新执行方法 | 后轮 J/K | RHS | 块数 | wall time | 接受输出 |
|---|---:|---:|---:|---:|---:|
| `multi4` | 8,592 | 160 | 96 | 18.905 s | 96/96 |
| 独立手写 field | 9,344 | 192 | 96 | 13.778 s | 96/96 |
| 独立手写 adjoint | 9,176 | 192 | 96 | 13.538 s | 96/96 |

`multi4` 的 96 条记录与旧封存 `two` 的恢复式、J/K、RHS 和输出逐项一致。
独立手写路线在 `cycle-three` 中复现相同双场公式，在 `cycle-one` 和
`cross-three` 中按独立代码回退到普通 field/adjoint 端点。与旧 `two` 的最大
输出差为 `6.15×10⁻¹²`，全部低于目标预算。

## 四列候选

`multi4` 枚举四个登记混合场 `xy,yz,xz,xyz` 的全部非空子集，共 15 个候选。
在三个场景中，四列搜索和三列搜索的选择、得分和恢复式完全相同：

| 场景 | 候选数 | 选中列 | 四列与三列选择 |
|---|---:|---|---|
| `cycle-one` | 15 | `x` | 相同 |
| `cycle-three` | 15 | `xy,yz` | 相同 |
| `cross-three` | 15 | `xy,z` | 相同 |

四列候选已进入实际 `multi4` 执行入口。未选候选的可恢复性、恢复系数和评分
在执行前逐项计算，物理运行使用排序后唯一的最优计划。结果支持的范围是四个
二值混合场的有限候选域，不延伸到实系数、自适应响应子空间或任意冗余方向。

## 强基线和成本范围

旧封存强基线继续提供普通 primal/adjoint、完整向量和已付矩阵后的稠密策略。
本轮新运行保存输入/输出字节、块数、RHS、J/K、wall time、质量复核和失败回退。
最大观察相消比为 `1,215.7`，全部新运行没有失败或回退。

结论限定为：在 15 个二值候选和三个冻结请求场景中，独立手写基线没有显示
自动方案之外的新科学能力。GQC 的贡献继续限定为科学身份绑定、程序生成、
执行和证据不足时回退。

## 复现

```bash
e=handoff/gqcdataset_codex_goal/research/experiments/information_sufficiency
.work/response-checks-env/bin/python "$e/analyze_issue25.py"
```

物理重放使用 `response_benefit/run.py` 的过滤入口和同一单线程 GQC/PySCF 环境，
输出封存于本目录的压缩资产中。
