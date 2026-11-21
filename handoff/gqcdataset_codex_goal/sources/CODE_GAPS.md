# 源码、版本和访问缺口

日期：2026-11-18。本表记录当前交接时的真实缺口。缺少原始代码、访问失败、版本未锁定分别处理；任何一项都不能推出“前人没有实现”。

此表保留交接发布时的记录；接管后的实际尝试、已解决项与剩余范围见
[research/SOURCE_GAPS.md](../research/SOURCE_GAPS.md)，版本见 [sources.lock.json](../research/sources.lock.json)。

## 已识别的具体缺口

| 条目 | 已核实的一手证据 | 当前缺口 | Codex 下一步 | 对结论的影响 |
|---|---|---|---|---|
| PhiSNet 原始实现 | [NeurIPS 原论文](https://papers.nips.cc/paper/2021/hash/78f1893678afbeaa90b1fa01b9cfb860-Abstract.html)；[nablaDFT 适配说明](https://github.com/AIRI-Institute/nablaDFT/blob/main/nablaDFT/phisnet/README.md) | OpenReview 页面本轮出现验证页；未取得原始补充代码包 | 查原论文/补充附件/作者公开归档，记录包散列与许可；单独比较适配版 | 可讨论论文能力，不能声称完成原始实现审计 |
| dm-PhiSNet | [arXiv](https://arxiv.org/abs/2604.27256)；[期刊 DOI](https://doi.org/10.1002/chem.71739) | 未定位独立原始仓库，预印本与期刊版需核对 | 查期刊代码可用性、补充材料及作者公开入口；对比密度规范与解析修正公式 | 学习初猜与约束修正已有直接先例；不能据代码缺口宣称创新空白 |
| IM-GNN | [MIR 官方论文](https://www.mi-research.net/en/article/doi/10.1007/s11633-023-1443-7) | 未定位作者原始代码 | 查正文、补充材料、作者公开项目；不能误用名称近似的 IMM-GNN | 缺失标签插补与伪标签筛选必须保留为相邻路线 |
| QPMA | [原论文 V 节](https://arxiv.org/html/2212.05469v2)明确给出 [源码地址](https://github.com/JeongminChae/QPMA) | 本轮 GitHub API 返回 404；可能涉及迁移、权限或删除，原因未定 | 追踪作者主页、论文新版本与正式公开归档；保留访问时间/错误，不绕过权限 | 理论与论文结果可审读；复现状态必须写 unavailable，不能写不存在 |
| QMugs | [原论文](https://www.nature.com/articles/s41597-022-01390-7)和[开放全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9174255/) | 未取得实际数据归档，未定位独立生成源码仓库 | 沿论文 Data Records/正式归档获取小规模代表性记录与下载说明；核实实际波函数字段 | “保存波函数”不自动证明任意目标均可直接补全 |
| Δ-ML 原始工作 | [原论文](https://arxiv.org/abs/1503.04987) | 未定位原始实验实现 | 查作者公开代码、补充材料和原数据；现代通用实现只能作另一个基线 | 低层结果加学习修正不属于本项目独创 |
| ANI-1ccx 训练链 | [论文](https://www.nature.com/articles/s41467-019-10827-4)；[数据支持仓库](https://github.com/aiqm/ANI1x_datasets) | 数据读取代码不等于完整训练和主动采样实现 | 追踪原训练发布路径、权重、NEUROCHEM/现代 TorchANI 对应关系；分别记录 | 不能把已有数据访问能力写成完整复现实验 |
| Suman 2025 / mlelec | [Materials Cloud](https://archive.materialscloud.org/records/4vezc-jtt98)列出[mlelec](https://github.com/curiosity54/mlelec) | 论文对应分支/提交未锁定 | 对照论文归档 README、qm7 等分支和历史提交固定版本 | main 分支存在不能证明论文实验已经复现 |

## 已发现的目录／版本注意事项

- GQC 的已核实仓库名是 [jinzhezenggroup/generativeqc](https://github.com/jinzhezenggroup/generativeqc)，默认分支在本轮为 master；仍须核实所选提交的实际能力。
- [QCFractal](https://github.com/MolSSI/QCFractal) 根目录包含 qcfractal 和 qcportal。QCPortal 客户端与服务端在同一主仓库，历史独立仓库不能取代当前完整代码树。
- [TREXIO tools README](https://github.com/TREX-CoE/trexio_tools/blob/master/README.md)说明 PySCF↔TREXIO 转换已迁往 [pyscf-forge](https://github.com/pyscf/pyscf-forge)。审计转换器必须跟进实际依赖。
- [AIRS](https://github.com/divelab/AIRS)包含 QHNet 和 QH9；[nablaDFT](https://github.com/AIRI-Institute/nablaDFT)有相关适配实现。作者原始版本与适配版应分别登记。
- QeMFi 的历史名称为 CheMFi；以[论文](https://www.nature.com/articles/s41597-024-04247-3)指向的 [SM4DA/QeMFi](https://github.com/SM4DA/QeMFi)作为起点，并单独记录历史归档及 fork。
- Halide 与 MLIR 是不同项目。可比较算法/调度分离与多层 IR 思想，不应把它们写成同一项目的直接版本演化。

## 所有条目共有的未完成事项

本轮只核实入口并建立问题清单，没有获取完整源码树、锁定论文 SHA、清点子模块/LFS、执行测试或复现实验。许可、依赖版本、编译条件、数据下载条款及样本可用性均须在实际获取时核查。源码和模型权重、训练数据各自的许可不能混为一谈。

若暂时无法获得直接相关实现，应继续可以进行的审读和独立对照，同时在路线比较中降低相应判断的确定性。需要联系作者时先准备问题与证据；是否发送由项目已有授权决定，不能自动向外部联系人发信。

