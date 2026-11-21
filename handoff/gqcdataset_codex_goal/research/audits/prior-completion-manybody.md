# 既有片段结果如何补全指定相互作用能

MolSSI QCManyBody 从同一套片段单点结果装配多体展开（MBE）、裸基组（NoCP）和反平衡修正（CP）等不同目标。这里取得 v0.8.0 全树，提交为 `90273ab21e4f824b286d55411666394c80cf2472`，共 108 个跟踪项，BSD-3-Clause，无子模块和 LFS 指针。仓库的 CITATION 将该实现关联到 2024 年的 JCP 论文。v0.8.0 发布于 2026 年，原论文具体提交仍待核实。[发行记录](https://github.com/MolSSI/QCManyBody/releases/tag/v0.8.0) · [版本内论文映射](https://github.com/MolSSI/QCManyBody/blob/90273ab21e4f824b286d55411666394c80cf2472/CITATION.cff) · [原论文](https://doi.org/10.1063/5.0231843)

## 目标定义决定哪些分量需要计算

`build_nbody_compute_list` 为每个模型层级和 BSSE 方案生成 (real fragments, basis fragments) 的集合。NoCP 在各片段自身的基组中计算；CP 单体保留完整簇的基函数，把环境核改成 ghost。全阶相互作用能由一个完整簇和多个单体直接确定。显式请求 `supersystem_ie_only` 时，中间阶二体明细可以省去。若要求那些明细，程序仍需对应分量。跨 CP 和 NoCP 的任务集合取并集，完整簇能量只需求一次。这是在相同物理目标上化简的已发布实现。[任务生成与并集](https://github.com/MolSSI/QCManyBody/blob/90273ab21e4f824b286d55411666394c80cf2472/qcmanybody/builder.py#L87)

`ManyBodyCore.iterate_molecules` 在当前分子内去除重复任务，将基组片段与实核片段的差集送入 `get_fragment`，保留当前坐标帧。`analyze` 和 `sum_cluster_data` 按标签加减已有能量；标量求和用 `math.fsum`。梯度、Hessian 容器按基组中心而非仅实核位置填入超分子布局，调用者必须供应同阶、同物理定义的分量导数。请求的能量分量缺少一项会触发查找失败。接口对同一标签收到的标量无法自行重建分量的出处。[枚举](https://github.com/MolSSI/QCManyBody/blob/90273ab21e4f824b286d55411666394c80cf2472/qcmanybody/core.py#L238) · [分量求和](https://github.com/MolSSI/QCManyBody/blob/90273ab21e4f824b286d55411666394c80cf2472/qcmanybody/utils.py#L178) · [组装](https://github.com/MolSSI/QCManyBody/blob/90273ab21e4f824b286d55411666394c80cf2472/qcmanybody/core.py#L526)

QCFractal 在另一个已锁定的完整仓库 `4ec1ed623f82536076c069dd65a4eb132969d9ed` 里使用这套机制。`initialize_service` 保存 cluster 对应的 molecule_id、模型层、实片段和基组片段；`iterate_service` 将单点规格 ID、分子 ID 和 `find_existing` 传给单点记录入口，回收已完成子计算中的 `return_energy` 再组装。单点 SQL 去重分支按 `specification_id, molecule_id` 查重。本轮实测外部调用者的轻量分量档案，数据库服务仅核查实现。[服务初始化和组装](https://github.com/MolSSI/QCFractal/blob/4ec1ed623f82536076c069dd65a4eb132969d9ed/qcfractal/qcfractal/components/manybody/record_socket.py#L134) · [单点去重](https://github.com/MolSSI/QCFractal/blob/4ec1ed623f82536076c069dd65a4eb132969d9ed/qcfractal/qcfractal/components/singlepoint/record_socket.py#L444)

## 同协议的实算对照

MB-001 使用一个固定 He/H₂/H₂O 簇、CPU PySCF 2.14.0、球谐 FP64 RHF/STO-3G；预先指定能量一致容差 1×10⁻¹⁰ Hartree。直接编写超分子四项式，独立生成核、ghost 和基组，算得 CP 相互作用能 0.000594532364730 Hartree，NoCP 为 0.000453241039281 Hartree。下面每条路径的新 SCF 次数来自逐调用日志，重复参考与对照均计入总数。[预登记](../experiments/prior-completion-manybody/protocol.md) · [机器结果](../experiments/prior-completion-manybody/result.json) · [34 次 SCF 开始与终态](../experiments/prior-completion-manybody/scf.jsonl)

| 路径 | 产出 | 新 SCF 次数 | 准确性及已有资产 |
|---|---|---:|---|
| 独立手写最小联合公式 | CP、NoCP 最终能量 | 7 | 一个超分子，为两种定义各算三个单体 |
| QCManyBody 普通全阶联合计划 | 最终量和二体明细 | 13 | 两个最终量与手写值之差在本次显示精度内为 0 |
| QCManyBody 仅最终量联合计划 | CP、NoCP 最终能量 | 7 | 最大差 1.43×10⁻¹⁴ Hartree 以内 |
| 第一轮仅 NoCP | NoCP 最终能量 | 4 | 4 份分量写入档案 |
| 第二轮加入 CP | CP 最终能量 | 3 | 命中完整簇，须计算 3 个含 ghost 的单体 |
| 第三轮重取两者 | 两种最终能量 | 0 | 7 项命中，最大差同上 |

各阶段共 34 次尝试，均收敛；实存 7 个分量 JSON 合计 2,577 字节。协议字典、本地环境、运行脚本和日志另行保留。两轮分别查询的 4+3 次与强手写联合基线的 7 次相同。13 次路径另外生成了中间阶明细，比较省掉的工作时须明确这一差别。单次小体系计时仅作复现记录。[驱动与输入](../experiments/prior-completion-manybody/probe.py)

**反例。** 用裸单体的标量替换 CP 单体值并沿用 CP 标签，程序仍完成组装，但目标偏差达到 1.413×10⁻⁴ Hartree。挪动一个水分子的 H 原子后，四个 CP 局部标签全部相同，基于实际几何和 ghost 中心构造的四个分量身份全部变化。单独删除一个必要的 CP 单体会触发 `KeyError`。这三例分别检验身份错配、跨记录失效和数据缺项。上游 6 个水三聚体存档回归用例也已运行，包含三种修正下的能量、梯度和 Hessian 组装；导数输入是既有分量导数，本次没有计算新的分子响应。[上游用例](https://github.com/MolSSI/QCManyBody/blob/90273ab21e4f824b286d55411666394c80cf2472/qcmanybody/tests/test_core_singlelevel.py#L11) · [测试回执](../experiments/prior-completion-manybody/upstream-tests.txt)

## 对 GQC 的强基线

依赖消除须先与按目标显式裁剪的 QCManyBody 以及手写四项式比。跨记录复用还要和保存一致规格分量的缓存比较。此实验确定了官方实现可以省去哪些逐项单点；任何 GQC 增量都还要展示超出这两种基线的计算减少，并保持目标协议、误差和失败记录。这里的 7 次等价并未建立新的 GQC 优势。

在仓库根目录复现，先按源码计划获取两个参考树。设置 PYTHONPATH 后直接运行所锁定 QCManyBody 源码，安装同版本 wheel 供依赖和版本元信息使用。

```bash
uv venv --python 3.13 .work/prior-completion/venv
uv pip install --python .work/prior-completion/venv/bin/python qcmanybody==0.8.0 qcelemental==0.51.4 pyscf==2.14.0 numpy==2.5.5 scipy==1.18.1 pytest==9.2.0 zstandard==0.25.0
export PYTHONPATH="$PWD/_references/qcmanybody" PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
.work/prior-completion/venv/bin/python -m pytest -q --import-mode=importlib -p no:cacheprovider _references/qcmanybody/qcmanybody/tests/test_core_singlelevel.py::test_h2o_trimer_single
.work/prior-completion/venv/bin/python handoff/gqcdataset_codex_goal/research/experiments/prior-completion-manybody/probe.py .work/prior-completion/new-run
```
