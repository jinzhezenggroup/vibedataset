# n5 独立复算 QM9 第 3 号水分子的部分标量响应

Slurm 作业 2048 使用 node5 的 1 个 CPU、4 GiB 内存，5 秒完成，退出码 0。此次求解使用 GQC 源码树 `2791504cc238fe83d328fc1718080642b288222a` 的原生 CPU TensorIR 和 block GMRES。本次分配仅占 CPU，RTX 5090 由调度器另行分配。固定 RHF/STO-3G 基态源于此前 n5 作业 2046，独立 CPHF 和两步长自洽有限场使用原已发布参照。所有策略共享同一模型建立及一份实产生的四标量历史。每个新块均从零开始。[预登记](../protocol.md) · [Slurm 原始记录](slurm-accounting.txt) · [参考态](../../qm9_response_assets/qm9-000003.json) · [独立参照](../../gqc_dual_response/oracles/qm9-000003.json)

| 实际操作 | 新 RHS | 块内算子扩展 | 块内逐列真残差 | 其他 J/K | 合计 J/K |
|---|---:|---:|---:|---:|---:|
| 共享模型建立与算子核验 | 0 | 0 | 0 | 5 | 5 |
| 四个已知标量的生产，伴随 q0、r2 同块 | 2 | 9 | 10 | 0 | 19 |
| 普通 x、y、z 三列同块 | 3 | 10 | 12 | 0 | 22 |
| 分开求 x+y+z，再求 z | 2 | 18 | 18 | 0 | 36 |
| x+y+z 与 z 同块 | 2 | 10 | 10 | 0 | 20 |
| x+y 与 z 同块 | 2 | 10 | 10 | 0 | 20 |
| x+y 与伴随 zz 同块 | 2 | 10 | 10 | 0 | 20 |
| x+y+z 与伴随 zz 同块 | 2 | 10 | 10 | 0 | 20 |
| 读取生产阶段保留的 q0、r2 两个伴随向量，再求 z | 1 | 9 | 9 | 2 | 20 |

四个历史值来自实际求得的 y/q0、z/q0、x/r2、z/r2。它们逐项通过全部独立门槛，写盘 2,040 字节，再按散列和目标身份读入。三轴组合每个待解码目标扣除两项。二轴组合只需 y/q0 或 x/r2 中对应的一项。GQC FP64 原生减法与独立手写扣除逐项核对。另实写 1,756 字节的两个伴随向量，保留向量的路径按每个向量实付一次残差检查。其余策略的求解只使用标量。历史批中的读出和此次三个目标共用同一参考态、AO 约定、响应算子、单位和原点。[实际历史](history.json) · [向量](producer-vectors.json) · [分步结果](result.json)

普通三列的四轮基扩展宽度为 3、3、3、1，每轮做 3 次真残差检查。分开的两个单列各有 9 轮，每轮各有一次扩展与检查。四种两列联合求解均为五轮，每轮扩展 2 次并检查 2 个右端。因此同块将 36 次降至 20 次，普通同块参照是 22 次。在这个水分子上，缩短组合场至两轴减少了标量依赖，J/K 与三轴组合相同。保留两个生产向量的总边际成本也为 20 次。六种标量路径的 18 次输出比较覆盖同样三个物理目标。每次均通过原独立验收，与同节点直接求解的最大分量差为 2.665×10⁻¹⁴，各按原单位。保存向量路径的三个输出也通过门槛。联合和分开方案实测物理残差不超过 4.64×10⁻¹⁴。[逐块与逐列结果](result.json) · [独立复核程序](verify.py)

所有 10 个阶段共 182 次 J/K，含共享建模 5 次，历史生产 19 次，以及每条对照实际消耗。模型建立 2.663 秒含五个原生核的首次装载和本次编译。两个原生标量解码核准备另用 0.969 秒。驱动总计 3.771 秒。该单次、带动作位置记录的墙时不构成稳定速度估计。Slurm 没有启用 accounting storage，控制器留下了分配与终态，实际峰值内存与能耗未计量。[事件日志](events.jsonl) · [原生库身份](runtime-libraries.json)

## 复查与重放

在仓库根目录可用标准库重新核查原始 SHA-256、7 个已执行原生库的文件身份、前后期 J/K、18 个输出及历史标量扣除的数值关系。

```bash
python3 handoff/gqcdataset_codex_goal/research/experiments/partial_response_blocks/n5/verify.py
```

n5 已有本次的隔离目录 `~/vibedataset/runs/plan004-n5-20261118` 与持久源码 `~/vibedataset/sources/gqc-2791504cc238`。本次使用既有 CPython 3.13.12、NumPy 2.4.6、PySCF 2.14.0、SciPy 1.18.1，系统 c++ 11.4、项目私有 sccache 0.16.0，并将 BLAS/OMP 限制为单线程。该源码经 Git 树校验，共 15,690 个文件。驱动固定项目 `dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a` 的三个辅助模块，通过不同于主项目联合面板入口的调用方直接执行同一上游 `solve_many`。5 个计算核和 2 个解码核的实际共享库哈希均已取回。[远端驱动](independent.py) · [作业脚本](run.slurm)

```bash
ssh n5 'cd ~/vibedataset/runs/plan004-n5-20261118 && sbatch --parsable --output=slurm-%j.out --error=slurm-%j.err driver/run.slurm'
```

新目录的相对布局如下。可由固定版本重新创建，也可核对已有部署。源归档和分发环境取得的成本独立于本次水分子响应求解。GQC 动作只能在同一物理问题内组块。伴随一列复用同一算子依赖本次经核验的 RHF 自伴规范。[共享基的固定源码审计](../../../audits/partial-response-blocks.md)

```text
_references/gqc/           固定的完整 GQC Git 树
bin/sccache                0.16.0
input/qm9-000003.json      qm9_response_assets 中的元数据
input/qm9-000003.npz       qm9_response_assets 中的 FP64 数组
input/oracle.json          gqc_dual_response/oracles/qm9-000003.json
scripts/                   固定的 gqc_dual_response.py、probe_gqc_residual.py、gqc_residual_plan.py
driver/                    本目录中的 independent.py 和 run.slurm
```
