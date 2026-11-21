# Issue #17 目标相关信息充分性

本轮把“自动规划是否超出手写线性叠加”作为可证伪问题。输入固定为 PR #16
已经封存的 8 个有态留出构型、循环历史和三项目标请求，保留缺态构型在原
分母中的 `evidence_unavailable` 记录。[协议](protocol.md) · [逐项结果](result.json)

## 结果

有限 `multi` 搜索遍历 14 个一至三混合场候选。在 `cycle-one`、`cycle-three`
和 `cross-three` 三个登记掩码上，选出的计划与 `two` 的列、系数和恢复恒等式
完全相同。循环三目标的计划为

```text
x/q0 = xy/q0 - H(y/q0)
y/r2 = yz/r2 - H(z/r2)
z/zz = yz/zz - xy/zz + H(x/zz)
```

新的物理重放只读生产输入，不读独立目标真值。8 个留出构型、4 次重复、32
条完整记录全部满足以下逐项等价：

| 项目 | `multi` 与已验证 `two` |
|---|---:|
| 恢复式和列 | 32/32 |
| 原生 J/K、RHS、质量复核成本 | 32/32 |
| 输出值、单位、目标身份和误差证据 | 32/32 |
| 回退和失败 | 0 |

三项请求去重后是 24 个目标。`multi` 的后轮成本为 3,296 次 J/K、64 个
RHS 和 32 个块，逐项输出与已验证 `two` 相同。包括 160 个历史块、8 个模型
准备和 32 个后轮的封存运行共 18,680 次 J/K，实际封存墙时 56.21 秒。后轮
非预热运行的中位数为 0.146 秒，旧 `two` 重放为 0.181 秒，差异来自独立进程
的编译缓存和系统状态，不能作为方法收益。所有接受项继续满足原有离散响应
证据门槛，结果值与独立封存方案逐项相同。

## 反例和边界

- 水的开发正例仍为普通三场 22 次 J/K、双场 20 次，3 个 RHS 降为 2 个。
- 氨的开发反例仍为 30 次 J/K 变为 31 次，RHS 从 3 变为 2。这个反例说明
  RHS 减少不等于算子工作减少。
- 只给 `y/q0` 时，`x/q0` 的目标行不在历史张成空间中，规划器必须新增
  `x` 方向。`x/r2` 也不能使用跨读出的 `y/q0` 做扣除。
- 17 个有限恢复记录中，恢复矩阵的谱条件上界最高为 4.899，观察到的最大
  相消比为 1,215.7。目标误差仍须按系数和历史误差传播，不能只检查残差。

## 结论

在本协议、当前请求和有限候选空间内，没有发现自动机制超出手写公式的科学
能力。GQC 的新增价值是保留科学身份、生成可执行剩余程序、执行物理复核和
在证据不足时回退。线性恢复本身归为已有 superposition/coloring 的工程继承。
这项负结果不支持跨方法、跨基组或自然请求分布的推广，重新开启条件是取得
协议一致的真实历史资产和请求流，或在新的物理范围中观察到经过完整成本核算
且能超出手写强基线的目标相关判据。

## 复现

```bash
e=handoff/gqcdataset_codex_goal/research/experiments/information_sufficiency
.work/response-checks-env/bin/python "$e/analyze.py"
.work/response-checks-env/bin/python handoff/gqcdataset_codex_goal/research/experiments/response_benefit/check_algebra.py
python3 handoff/gqcdataset_codex_goal/research/experiments/response_benefit/verify.py
```

新重放资产的 `manifest.json` 绑定了 `assets.tar.gz`、事件日志、质量代码和
运行协议的散列。完整的源实验仍保留在 `response_benefit/evidence/`，便于核对
旧 `two` 结果的独立验收。

## Issue #25 后续复评

独立手写模块在 8 个留出构型、四次重复和三个场景上运行了 96 条记录。field
手写和 adjoint 手写分别为 9,344 和 9,176 次后轮 J/K，`multi4` 为 8,592 次，
全部 96 条输出通过，没有回退。四个混合场的 15 个非空子集已纳入枚举，三个
场景的 `multi4` 选择均与三列搜索相同。[独立结果](issue25/README.md) · [分析器](analyze_issue25.py)
