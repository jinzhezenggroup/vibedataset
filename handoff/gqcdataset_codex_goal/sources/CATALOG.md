# 源码与文献起始目录

日期：2026-11-18。此目录依据当前可见讨论重建，并核实公开入口；不是下载失败 ZIP 的逐字副本。

**历史入口快照：** 下文“本轮”及 `catalog.json` 的 not_acquired/空 pin 表示交接发布时的状态。
后续真实接管状态以 [来源锁](../research/sources.lock.json)、[快照索引](../research/SOURCE_INDEX.md)
和 [STATUS](../research/STATUS.md) 为准。同一项目可有多个版本，不把运行源码和当前源码压成一个 pin。

## 本轮完成到哪里

共 38 个研究／软件条目、31 个不同的可访问仓库入口；完整源码树获取 **0**，完整源码审计 **0**。仓库入口核实使用 GitHub 元数据；论文对应关系使用官方论文、作者仓库及正式归档。所有条目的 `source_status` 都是 `not_acquired`，所有 `pinned_commit` 都为空。详见可机读的 [catalog.json](catalog.json)。

`verified_entry` 仅表示入口已核实；`paper_verified_code_pending` 表示论文已核实但代码定位未完成；`paper_verified_source_unavailable` 表示原文提供地址而本轮访问失败。后两类需要查阅 [CODE_GAPS.md](CODE_GAPS.md)。这些状态都不支持“前人没有该能力”的结论。

## 使用规则

1. P0 是最先审读的直接依据；P1 是强基线和重要相邻路线；P2 是编译背景。优先级控制审读顺序，不豁免相关源码获取和覆盖记录。
2. 每个选定版本获取完整源码树，含测试、构建配置、生成器、示例、基准、所需子模块和真实 LFS 对象；固定完整 SHA。共享单仓库只获取一次，不以两个子目录伪装成两个独立仓库。
3. 论文版本、当前主分支、作者实现、适配版与 fork 分别标记；目录中的默认分支只是本轮元数据，不是论文版本锁定。
4. 从“输入及科学语义—实现—失败行为—测试/基准”追踪关键主张，再做必要验证。获取、索引、阅读、行为追踪和运行验证分别记账。
5. 本目录不是穷尽查新。沿文献和依赖扩展，同时为每条候选机制建立有边界的审计任务，避免把无限查新当成研究推进。

## 科学编译与工作基础

| ID / 工作 | 优先级 | 源码入口 | 本轮状态 |
|---|---|---|---|
| `gqc` — GenerativeQC / GQC | P0 | [jinzhezenggroup/generativeqc](https://github.com/jinzhezenggroup/generativeqc) | `verified_entry` |
| `xtbloom` — xTBloom | P0 | [jinzhezenggroup/xtbloom](https://github.com/jinzhezenggroup/xtbloom) | `verified_entry` |

### GenerativeQC / GQC

审计问题：科学图、求解器、自动微分与执行计划如何解耦？ 已知电子态数值能在哪层替代求解，同时保留隐式导数？ 目标精度、误差证据和实际后端支持的边界是什么？

版本与边界：仓库元数据确认当前名称 generativeqc，默认分支 master；旧材料中的 GQC 是项目简称。官网深层文档作为继续核查入口；本轮不把 README 的全部能力视为源码验证结果。

一手入口：[1](https://github.com/jinzhezenggroup/generativeqc) · [2](https://qc.jinzhezeng.group/en/latest/developer/compiler_architecture.html) · [3](https://qc.jinzhezeng.group/en/latest/developer/stationary_problem.html)。

### xTBloom

审计问题：异构批次、持久上下文与密度热启动的兼容条件是什么？ 单分子失败是否隔离，哪些资源实际被复用？

版本与边界：需要用实现及失败测试核实批处理设计，性能不能从接口存在推断。

一手入口：[1](https://github.com/jinzhezenggroup/xtbloom)。

## 量化后端与强基线

| ID / 工作 | 优先级 | 源码入口 | 本轮状态 |
|---|---|---|---|
| `pyscf` — PySCF | P0 | [pyscf/pyscf](https://github.com/pyscf/pyscf) | `verified_entry` |
| `pyscfad` — PySCFAD | P0 | [fishjojo/pyscfad](https://github.com/fishjojo/pyscfad) | `verified_entry` |
| `gpu4pyscf` — GPU4PySCF | P1 | [pyscf/gpu4pyscf](https://github.com/pyscf/gpu4pyscf) | `verified_entry` |
| `psi4` — Psi4 | P0 | [psi4/psi4](https://github.com/psi4/psi4) | `verified_entry` |
| `qcdb` — QCDB | P1 | [qcdb/qcdb](https://github.com/qcdb/qcdb) | `verified_entry` |
| `xtb` — xTB | P1 | [grimme-lab/xtb](https://github.com/grimme-lab/xtb) | `verified_entry` |
| `tblite` — tblite | P1 | [tblite/tblite](https://github.com/tblite/tblite) | `verified_entry` |
| `dxtb` — dxtb | P1 | [grimme-lab/dxtb](https://github.com/grimme-lab/dxtb) | `verified_entry` |

### PySCF

审计问题：档案加载、密度初猜、一次电子性质后处理分别调用什么？ 响应、梯度和基组变换的依赖是什么？

一手入口：[1](https://github.com/pyscf/pyscf)。

### PySCFAD

审计问题：迭代展开与隐式微分各覆盖哪些方法？ 用存档状态替代前向求解时怎样保留导数语义？

一手入口：[1](https://github.com/fishjojo/pyscfad)。

### GPU4PySCF

审计问题：预热、密度拟合、数据传输与后处理成本怎样计入比较？ 可比较的性质/方法/精度范围是什么？

一手入口：[1](https://github.com/pyscf/gpu4pyscf)。

### Psi4

审计问题：波函数序列化、oeprop 密度选择、CBS 去重如何实现？ 固定态后处理和目标协议重收敛的差别在哪里？

版本与边界：官网路径是重点审计入口；直接复用与组合计算应成为强基线。

一手入口：[1](https://github.com/psi4/psi4) · [2](https://psicode.org/psi4manual/master/oeprop.html) · [3](https://psicode.org/psi4manual/master/api/psi4.driver.cbs.html)。

### QCDB

审计问题：跨程序模型/单位/计算协议如何表达？ 组合计算和底层调用的可复用性边界是什么？

一手入口：[1](https://github.com/qcdb/qcdb)。

### xTB

审计问题：GFN 方法状态、重启和性质接口保存哪些信息？ 作为低保真信息时如何记录与目标 DFT 的区别？

一手入口：[1](https://github.com/grimme-lab/xtb)。

### tblite

审计问题：库级状态和结果接口如何组织？ 参数、模型身份、梯度和响应支持有哪些条件？

一手入口：[1](https://github.com/tblite/tblite)。

### dxtb

审计问题：可微 xTB 的求解/响应/缓存接口如何实现？ 批量、自动微分和数值收敛如何共同验收？

一手入口：[1](https://github.com/grimme-lab/dxtb)。

## 档案、工作流与状态

| ID / 工作 | 优先级 | 源码入口 | 本轮状态 |
|---|---|---|---|
| `qcfractal` — QCFractal / QCPortal / QCArchive | P0 | [MolSSI/QCFractal](https://github.com/MolSSI/QCFractal) | `verified_entry` |
| `qcengine` — QCEngine | P1 | [MolSSI/QCEngine](https://github.com/MolSSI/QCEngine) | `verified_entry` |
| `qcelemental` — QCElemental | P0 | [MolSSI/QCElemental](https://github.com/MolSSI/QCElemental) | `verified_entry` |
| `aiida` — AiiDA | P1 | [aiidateam/aiida-core](https://github.com/aiidateam/aiida-core) | `verified_entry` |
| `trexio` — TREXIO | P0 | [TREX-CoE/trexio](https://github.com/TREX-CoE/trexio) | `verified_entry` |
| `trexio_tools` — TREXIO tools | P0 | [TREX-CoE/trexio_tools](https://github.com/TREX-CoE/trexio_tools) | `verified_entry` |
| `pyscf_forge` — PySCF forge（TREXIO 适配依赖） | P1 | [pyscf/pyscf-forge](https://github.com/pyscf/pyscf-forge) | `verified_entry` |

### QCFractal / QCPortal / QCArchive

审计问题：单点记录如何保存波函数、规格、错误与溯源？ 任务去重与数据集条目身份如何区分？

版本与边界：本轮已读取根目录，qcfractal 与 qcportal 同在此主仓库；不要把历史独立 QCPortal 仓库当当前完整实现。

一手入口：[1](https://github.com/MolSSI/QCFractal) · [2](https://github.com/MolSSI/QCFractal/tree/main/qcportal) · [3](https://docs.qcarchive.molssi.org/user_guide/records/singlepoint.html)。

### QCEngine

审计问题：跨后端驱动、失败分类与资源配置如何定义？ 结果缓存依赖由谁负责？

一手入口：[1](https://github.com/MolSSI/QCEngine)。

### QCElemental

审计问题：模型、分子、单位、基组与 provenance 如何表达？ 现有模式对中间状态和精度证据有哪些约束？

一手入口：[1](https://github.com/MolSSI/QCElemental)。

### AiiDA

审计问题：内容哈希缓存怎样判定等价，如何失效？ 相同计算复用与不同资产的信息充分性有何边界？

一手入口：[1](https://github.com/aiidateam/aiida-core) · [2](https://aiida.readthedocs.io/projects/aiida-core/en/stable/topics/provenance/caching.html)。

### TREXIO

审计问题：实际基组、AO/MO、密度和多体状态保存什么？ 模式合法性与物理正确性分别在哪里检验？

一手入口：[1](https://github.com/TREX-CoE/trexio) · [2](https://trex-coe.github.io/trexio/lib.html)。

### TREXIO tools

审计问题：转换器如何处理轨道顺序、球谐/笛卡尔与归一化？ 现有检查工具能验证什么物理一致性？

版本与边界：本轮 README 指明 PySCF↔TREXIO 转换已移至 pyscf-forge；原包叙述需随源码版本更新。

一手入口：[1](https://github.com/TREX-CoE/trexio_tools) · [2](https://github.com/TREX-CoE/trexio_tools/blob/master/README.md)。

### PySCF forge（TREXIO 适配依赖）

审计问题：PySCF↔TREXIO 转换现在位于何处，覆盖哪些态？ 转换与 round-trip 测试是否足以支撑目标物性不变？

版本与边界：由 TREXIO tools 当前 README 追踪得到的实际依赖，不能仅审读旧转换器。

一手入口：[1](https://github.com/pyscf/pyscf-forge) · [2](https://github.com/TREX-CoE/trexio_tools/blob/master/README.md)。

## 电子态学习与可微混合计算

| ID / 工作 | 优先级 | 源码入口 | 本轮状态 |
|---|---|---|---|
| `schnorb` — SchNOrb | P1 | [atomistic-machine-learning/SchNOrb](https://github.com/atomistic-machine-learning/SchNOrb) | `verified_entry` |
| `qhnet` — QHNet | P1 | [divelab/AIRS](https://github.com/divelab/AIRS) | `verified_entry` |
| `qh9` — QH9 | P1 | [divelab/AIRS](https://github.com/divelab/AIRS) | `verified_entry` |
| `mlelec` — Suman 等 2025 / mlelec | P0 | [curiosity54/mlelec](https://github.com/curiosity54/mlelec) | `verified_entry` |
| `phisnet` — PhiSNet 原始工作 | P0 | 见下方官方来源与代码缺口 | `paper_verified_code_pending` |
| `nabladft` — nablaDFT 与 PhiSNet/QHNet 适配版 | P1 | [AIRI-Institute/nablaDFT](https://github.com/AIRI-Institute/nablaDFT) | `verified_entry` |
| `dm_phisnet` — dm-PhiSNet（2026） | P0 | 见下方官方来源与代码缺口 | `paper_verified_code_pending` |

### SchNOrb

审计问题：Hamiltonian/overlap 预测如何变成物性和 SCF 初猜？ 数据划分、分子范围和状态校正怎样影响收益？

一手入口：[1](https://github.com/atomistic-machine-learning/SchNOrb)。

### QHNet

审计问题：等变矩阵预测、AO 约定和下游计算如何衔接？ 原始代码与其他数据集适配版有哪些变化？

版本与边界：AIRS 为主仓库；已核实 OpenDFT/QHNet 目录入口。获取全树后标出重点模块，不能把局部抓取称为完整源码。

一手入口：[1](https://github.com/divelab/AIRS/tree/main/OpenDFT/QHNet)。

### QH9

审计问题：静态/动态划分和 Hamiltonian 数据生成协议是什么？ 复用同一分子构型信息是否造成评估泄漏？

版本与边界：本轮 QHBench README 明确链接 QH9 子目录；与 QHNet 共用一个仓库，不能按两个独立仓库计数。

一手入口：[1](https://github.com/divelab/AIRS/tree/main/OpenDFT/QHBench/QH9) · [2](https://github.com/divelab/AIRS/blob/main/OpenDFT/QHBench/README.md)。

### Suman 等 2025 / mlelec

审计问题：学习 Hamiltonian 与 PySCFAD 的端到端接口怎样实现？ 小表示基匹配大基组目标的模型身份、响应与泛化如何验证？

版本与边界：Materials Cloud 官方记录明确将 mlelec 列为对应软件。需对照论文归档与 qm7 等分支，不能默认 main 就是论文实验版本。

一手入口：[1](https://github.com/curiosity54/mlelec) · [2](https://archive.materialscloud.org/records/4vezc-jtt98) · [3](https://arxiv.org/abs/2504.01187)。

### PhiSNet 原始工作

审计问题：原始补充材料是否包含代码、权重与许可？ 波函数预测、迁移学习与热启动已有能力如何界定？

版本与边界：原论文入口已核实；OpenReview 本轮要求浏览器验证，原始代码包尚未取得。nablaDFT 的适配版单列，不能替代原始实现审计。

一手入口：[1](https://papers.nips.cc/paper/2021/hash/78f1893678afbeaa90b1fa01b9cfb860-Abstract.html) · [2](https://openreview.net/forum?id=auGY2UQfhSu)。

### nablaDFT 与 PhiSNet/QHNet 适配版

审计问题：适配版本的批处理、数据范围、状态约定如何改变？ 现有数据可否支撑跨构型、跨分子、缺物性评估？

版本与边界：PhiSNet 子目录 README 明确称基于作者代码；应同时保存适配记录和上游来源。

一手入口：[1](https://github.com/AIRI-Institute/nablaDFT) · [2](https://github.com/AIRI-Institute/nablaDFT/blob/main/nablaDFT/phisnet/README.md) · [3](https://pubs.rsc.org/en/content/articlehtml/2022/cp/d2cp03966d)。

### dm-PhiSNet（2026）

审计问题：解析约束与 SCF 初猜收益如何实现与计时？ 自旋求和密度的幂等系数、purification 公式及实际代码是否一致？ 一步力与完整目标态力是否具有相同定义？

版本与边界：已核实论文与 2026-10 期刊版本入口；本轮未定位独立原始仓库。必须核对预印本、期刊版、补充材料，不能把未找到代码解释为未实现。

一手入口：[1](https://arxiv.org/abs/2604.27256) · [2](https://arxiv.org/html/2604.27256v1) · [3](https://doi.org/10.1002/chem.71739)。

## 多保真、主动采样与缺失标签

| ID / 工作 | 优先级 | 源码入口 | 本轮状态 |
|---|---|---|---|
| `ani1` — ANI-1 数据支持仓库 | P1 | [isayev/ANI1_dataset](https://github.com/isayev/ANI1_dataset) | `verified_entry` |
| `ani1x_ccx` — ANI-1x / ANI-1ccx 数据及迁移学习路线 | P1 | [aiqm/ANI1x_datasets](https://github.com/aiqm/ANI1x_datasets) | `verified_entry` |
| `torchani` — TorchANI | P1 | [aiqm/torchani](https://github.com/aiqm/torchani) | `verified_entry` |
| `qemfi` — QeMFi（原 CheMFi） | P1 | [SM4DA/QeMFi](https://github.com/SM4DA/QeMFi) | `verified_entry` |
| `multifidelity_gnn` — 多保真 GNN 迁移学习 | P1 | [davidbuterez/multi-fidelity-gnns-for-drug-discovery-and-quantum-mechanics](https://github.com/davidbuterez/multi-fidelity-gnns-for-drug-discovery-and-quantum-mechanics) | `verified_entry` |
| `im_gnn` — IM-GNN 缺失标签插补 | P0 | 见下方官方来源与代码缺口 | `paper_verified_code_pending` |
| `delta_ml` — Δ-machine learning | P1 | 见下方官方来源与代码缺口 | `paper_verified_code_pending` |

### ANI-1 数据支持仓库

审计问题：数据读取脚本与生成/训练实现的边界是什么？ 主动学习样本选择能否作为数据集级获取策略基线？

版本与边界：已读 README：此仓库提供 ANI-1 数据访问支持；不把它写成 ANI-1ccx 完整训练实现。

一手入口：[1](https://github.com/isayev/ANI1_dataset) · [2](https://arxiv.org/abs/1801.09319)。

### ANI-1x / ANI-1ccx 数据及迁移学习路线

审计问题：低/高层标签的对应、缺失结构和训练划分是什么？ 原始迁移训练代码、数据读取脚本、现代实现如何分别锁定？

版本与边界：此入口核实为数据支持仓库；原论文训练发布路径需继续追踪，不能仅有数据读入脚本就宣称复现训练。

一手入口：[1](https://github.com/aiqm/ANI1x_datasets) · [2](https://www.nature.com/articles/s41467-019-10827-4)。

### TorchANI

审计问题：预训练、微调、集成不确定性和数据接口能支持哪些对照？ 当前版本与原始 ANI 论文实现有何差别？

一手入口：[1](https://github.com/aiqm/torchani)。

### QeMFi（原 CheMFi）

审计问题：多保真标签、真实计算时间与采样策略如何配对？ 构建学习曲线时是否计入所有层级的标注成本？

版本与边界：论文 Code availability 指向 SM4DA/QeMFi；历史 CheMFi 命名与作者 fork 应分开记录。

一手入口：[1](https://github.com/SM4DA/QeMFi) · [2](https://www.nature.com/articles/s41597-024-04247-3) · [3](https://zenodo.org/records/13925688)。

### 多保真 GNN 迁移学习

审计问题：低保真预训练、目标微调与缺失标签掩码怎样组合？ QMugs 划分和总训练成本如何核实？

版本与边界：仓库 README 将其标为 Transfer learning with graph neural networks for improved molecular property prediction in the multi-fidelity setting 的对应源码。

一手入口：[1](https://github.com/davidbuterez/multi-fidelity-gnns-for-drug-discovery-and-quantum-mechanics)。

### IM-GNN 缺失标签插补

审计问题：分子—任务二部图如何表示已知/缺失标签？ 不确定性筛选伪标签的校准与下游评价如何避免泄漏？

版本与边界：已核实官方论文页；本轮未定位作者原始代码。不混淆名字近似但不同的 IMM-GNN。

一手入口：[1](https://www.mi-research.net/en/article/doi/10.1007/s11633-023-1443-7)。

### Δ-machine learning

审计问题：低层计算与学习修正的总成本、适用范围和误差怎么比较？ 哪些补全收益已经由 Δ-learning 解释？

版本与边界：已核实原论文；原始实现、数据及后续复现代码需继续定位，不以现代同类包冒充原始实现。

一手入口：[1](https://arxiv.org/abs/1503.04987) · [2](https://doi.org/10.1021/acs.jctc.5b00099)。

## 结构化矩阵补全

| ID / 工作 | 优先级 | 源码入口 | 本轮状态 |
|---|---|---|---|
| `hvmc` — HVMC | P1 | [RateTheory/HVMC](https://github.com/RateTheory/HVMC) | `verified_entry` |
| `pvmc` — PVMC | P1 | [RateTheory/PVMC](https://github.com/RateTheory/PVMC) | `verified_entry` |
| `vmc` — VMC / algebraic variety models | P1 | [gregongie/vmc](https://github.com/gregongie/vmc) | `verified_entry` |
| `qpma` — QPMA / 带侧信息的列采样矩阵近似 | P1 | 见下方官方来源与代码缺口 | `paper_verified_source_unavailable` |

### HVMC

审计问题：反应路径 Hessian 特征值矩阵的缺失模式是什么？ 随机单元素采样与真实可执行计算单位如何对应？

版本与边界：官方 README 说明 vmc.py 改编自 gregongie/vmc。

一手入口：[1](https://github.com/RateTheory/HVMC) · [2](https://doi.org/10.1063/5.0018326)。

### PVMC

审计问题：多项式侧信息如何影响列采样？ 恢复矩阵误差如何传递到自由能与反应速率？

版本与边界：README 区分 MATLAB 补全与 Python 后处理；需一并获取和审读。

一手入口：[1](https://github.com/RateTheory/PVMC)。

### VMC / algebraic variety models

审计问题：代数簇约束、优化器和缺失掩码的适用条件是什么？ 原始 MATLAB 与 HVMC/PVMC 适配版有何变化？

一手入口：[1](https://github.com/gregongie/vmc) · [2](https://arxiv.org/abs/1703.09631)。

### QPMA / 带侧信息的列采样矩阵近似

审计问题：谱误差保证要求哪些侧信息、秩和采样条件？ 理论条件能否对应真实 QC 计算单位？

版本与边界：论文 V 节明确给出 JeongminChae/QPMA，但本轮 GitHub API 返回 404；这是访问缺口，不是没有源码的证据。

一手入口：[1](https://arxiv.org/abs/2212.05469) · [2](https://arxiv.org/html/2212.05469v2) · [3](https://github.com/JeongminChae/QPMA)。

## 编译与程序专门化背景

| ID / 工作 | 优先级 | 源码入口 | 本轮状态 |
|---|---|---|---|
| `halide` — Halide | P2 | [halide/Halide](https://github.com/halide/Halide) | `verified_entry` |
| `mlir` — MLIR / LLVM project | P2 | [llvm/llvm-project](https://github.com/llvm/llvm-project) | `verified_entry` |

### Halide

审计问题：算法/调度分离、缓存、阶段化与成本模型有什么可迁移机制？ 哪些想法属于已有编译优化，不能作为本项目首创？

一手入口：[1](https://github.com/halide/Halide)。

### MLIR / LLVM project

审计问题：多层 IR、合法化、依赖分析及变换验证如何组织？ 科学身份与误差证据需要哪些领域特定语义？

版本与边界：MLIR 位于 LLVM 单仓库，完整源码获取和阅读覆盖需诚实区分；不把 Halide 叙述为直接演化成 MLIR 的同一项目。

一手入口：[1](https://github.com/llvm/llvm-project)。

## 现实数据候选

| ID / 工作 | 优先级 | 源码入口 | 本轮状态 |
|---|---|---|---|
| `qmugs` — QMugs | P0 | 见下方官方来源与代码缺口 | `paper_verified_code_pending` |

### QMugs

审计问题：波函数归档中实际有哪些矩阵与基组/方法身份？ 档案后处理与目标协议重收敛分别支持什么标签？ 真实缺失、构型分组和质量筛选能否形成可信评价？

版本与边界：论文确认提供 DFT 密度和轨道矩阵；仍需下载实际记录核查。未定位独立生成源码仓库；不是既定首个实验或固定四极矩任务。

一手入口：[1](https://www.nature.com/articles/s41597-022-01390-7) · [2](https://pmc.ncbi.nlm.nih.gov/articles/PMC9174255/)。

## 交给 Codex 的首轮输出

更新源码锁文件与逐目录覆盖记录；将本目录的“入口已核实”推进到实际获取和审读。对每个会影响路线判断的能力提供固定版本、源文件/符号、相关测试、已运行结果或明确未运行原因。不要从本目录生成虚构的 commit SHA、审读结论或性能结论。

