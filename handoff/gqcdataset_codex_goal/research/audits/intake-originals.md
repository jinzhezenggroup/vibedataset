# 六项原始来源核查

检索日期为 2026-11-18（Asia/Shanghai）。本次找到了 dm-PhiSNet 第一作者名下可取得的历史实现，另固定了 PhiSNet 的 CasNet 后续适配与 QMugs 作者团队的 DelFTa 论文版本。三棵树共 302 个跟踪文件，完整清点均通过，子模块和标准 LFS 指针计数均为零。本次未运行这些项目的训练或预测。所有页面、补充文件、API 查询、时间、返回码、文件大小和散列见机器证据。[核查回执](../acquisition/originals-evidence-20261118.json)

| 原始问题 | 现有材料 | 仍待获取或验证 |
|---|---|---|
| PhiSNet 2021 | 会议论文与补充 PDF、arXiv v2 的排版源包、两条独立的后续代码来源 | 投稿原始模型代码包及字节身份 |
| dm-PhiSNet 2026 | 第一作者历史仓库的训练、解析层、数据生成与评估代码，190 个文件 | 作者将论文实验明确绑定到某个提交、对应权重和训练库、代码许可 |
| IM-GNN | 期刊 15 页 PDF、方法与参数、作者/实验室公开仓库目录 | 作者原始实现或软件归档 |
| QPMA | arXiv v2 正文明确给出的唯一 QPMA 仓库地址。GitHub 和 Software Heritage 地址核查 | 可访问的原实现、迁移地址或归档版本 |
| QMugs | 出版商刊出的 Code availability、ETH 数据 DOI 及许可元数据、下游 DelFTa 论文源码 | 原始数据集生成工作流的独立版本和实际 ETH 波函数样本 |
| 2015 Δ-ML | ACS 的正式 SI，作者公开数据目录及其对三个数据集的用途说明 | 支撑 2015 年训练、预测和评测的源代码版本 |

## PhiSNet 和 dm-PhiSNet

**PhiSNet。** NeurIPS 页面给出正文、补充 PDF 及 OpenReview。实际取得的正文和补充各 14 页，补充 PDF 没有嵌入附件。arXiv 2106.02347v2 的源包有 29 个文件（13 PDF、9 SVG、4 TeX、2 BBL、1 STY），提供论文和图的源文件。OpenReview 对此 forum 的 API 请求返回 403 ChallengeRequiredError。原始投稿附加物仍未逐字节核查。后续若恢复常规访问，应直接核对该投稿的 supplemental artifact 及其许可。[会议官方页](https://proceedings.neurips.cc/paper/2021/hash/78f1893678afbeaa90b1fa01b9cfb860-Abstract.html) · [补充 PDF](https://proceedings.neurips.cc/paper/2021/file/78f1893678afbeaa90b1fa01b9cfb860-Supplemental.pdf) · [arXiv 源包](https://arxiv.org/src/2106.02347v2) · [OpenReview](https://openreview.net/forum?id=auGY2UQfhSu)

nablaDFT 的训练说明注明基于原作者代码并链接 OpenReview。另一次独立核查取得了完整的 CasNet PhiSNet fork，固定提交 `398f215554146069a386809a4bd3bed83eddf87a`，61 个文件，含 train.py、test.py、推理、数据转换和配置。README 标明其 CasNet 用途，仓库历史另有后续损失实现改动。两个派生项目都可用于比较具体实现。均未找到可证明其整树与 2021 原始发行物相同的版本关系。新 fork 树中没有识别到 LICENSE/COPYING，完整源码只保存在未跟踪 checkout。[nablaDFT 说明](https://github.com/AIRI-Institute/nablaDFT/blob/67ca402809806e5dd55095e1f095ec9b2683ac41/nablaDFT/phisnet/README.md) · [CasNet 派生说明](https://github.com/marquetand/phisnet_fork/blob/398f215554146069a386809a4bd3bed83eddf87a/README.md)

**dm-PhiSNet。** 通过第一作者名下账号的公开仓库及提交历史定位 `zyyr17/dm-nn-so3-analytic`。提交作者署名 Zuriel Yescas，仓库描述、密度矩阵解析细化、具体数据生成器和论文方法一致。默认分支 HEAD `54a566de8ef854a5e62fb434a41b509e1cf44185` 的树为空，提交记录明确删除项目文件。实际固定并清点其直接父提交 `eb365d3e4d0e85ccf89740e5fad26970591c5b16`，树 `85ace16af649d2ed6af3efb44c17f7c79df1f154`，日期为 2025-10-03。它早于 arXiv v1 与 2026-10-09 的期刊记录。部署说明、env.yml、训练、结构生成、评估脚本和示例输入均可读，未找到代码许可文件。原仓库没有把此提交标为论文版。预印本 v1 的排版源包只有 7 个文件，期刊网页请求返回 403 验证页面。仍要将论文的 SI、实际权重与训练数据库关联到具体提交。[作者仓库历史](https://github.com/zyyr17/dm-nn-so3-analytic/commits/main/) · [固定历史树](https://github.com/zyyr17/dm-nn-so3-analytic/tree/eb365d3e4d0e85ccf89740e5fad26970591c5b16) · [预印本](https://arxiv.org/abs/2604.27256) · [期刊记录](https://doi.org/10.1002/chem.71739)

在该历史树中，模型调用 `AnalyticLayer.forward`。该层检查输入有限性并对称化。只有提供重叠矩阵且启用 downstream mode，才用 Tr(PS) 重新缩放并进入 AO 度量 McWeeny 迭代。受限分支先将自旋求和密度除以 2，迭代后乘回 2，再作一次迹缩放。基准函数 `evaluate_dm_guess` 的预测分支把原始或迹校正密度作为 `kernel(dm0=...)` 的初猜，在相应的密度拟合 PBE 协议下重新求解。可见解析约束、初猜和目标态收敛是不同步骤。示例 args.txt 指名的 nitrate 库、best checkpoint 在 190 个跟踪文件中缺失。本次没有由这些源码测量精度、加速或态响应。[解析层](https://github.com/zyyr17/dm-nn-so3-analytic/blob/eb365d3e4d0e85ccf89740e5fad26970591c5b16/source/base_model/nn/modules/analytic_layer.py#L123) · [网络调用](https://github.com/zyyr17/dm-nn-so3-analytic/blob/eb365d3e4d0e85ccf89740e5fad26970591c5b16/source/base_model/nn/neural_network.py#L571) · [对照函数](https://github.com/zyyr17/dm-nn-so3-analytic/blob/eb365d3e4d0e85ccf89740e5fad26970591c5b16/source/model_assesment/test.py#L331)

## IM-GNN 和 QPMA

**IM-GNN。** 从 MIR 出版商原文页进入其正式 PDF，HTTP 200，1,447,414 字节，15 页（含期刊附页），无嵌入附件。第 5.1.3 节给出实现参数，论文给出分子—任务二部图、缺失边预测以及基于 MC-dropout 不确定性选取伪标签的机制。PDF 的 URI 注释中包括 Tox21 数据入口，未出现模型仓库/软件归档链接。核查 FenyuHu 公开仓库（GraphAIR、H-GCN-IJCAI19）、CRIPAC-DIG 当时的 39 个公开项目，并以题名和 IM-GNN 加 molecular 定向检索，未定位可确认的作者实现。论文算法和参数可以指导后续严格区分复现与原代码，不能据此给其实际运行行为记账。[出版商原文](https://www.mi-research.net/en/article/doi/10.1007/s11633-023-1443-7) · [正式 PDF](https://www.mi-research.net/en/article/pdf/preview/10.1007/s11633-023-1443-7.pdf) · [作者目录](https://api.github.com/users/FenyuHu/repos?per_page=100) · [实验室目录](https://api.github.com/orgs/CRIPAC-DIG/repos?per_page=100)

**QPMA。** 本机从 arXiv v2 的第 V 节再次核到作者明确写出的 `JeongminChae/QPMA`。已认证 GitHub API 对该地址返回 404。作者公开目录的 6 个项目中没有该名称。Software Heritage 的 exact-origin API 同样返回 404 NotFoundExc，DataCite 同题名查询仅返回预印本 DOI。正文另引的 VMC 是独立基线。迁移、权限或删除的具体原因仍未知。后续可对照 IEEE 最终版的补充文件或作者公开的正式归档标识。[论文第 V 节](https://arxiv.org/html/2212.05469v2) · [文中代码地址](https://github.com/JeongminChae/QPMA) · [作者公开项目](https://api.github.com/users/JeongminChae/repos?per_page=100) · [Software Heritage 原址查询](https://archive.softwareheritage.org/api/1/origin/https://github.com/JeongminChae/QPMA/get/)

## QMugs 和 2015 年的 Δ-ML

**QMugs。** 正式 JATS 正文的 Code availability 给出 Python 3.7.7、RDKit 2020.03.3、GFN2-xTB 6.3.1、Psi4 1.3.2、可视化软件和 rclone WebDAV 1.54.0。该段两个软件链接指向 RDKit、rclone 项目主页。Data Records 指向 ETH Library Collection。除结构/汇总数据外，论文描述用 100 份约 50 GB 的 `wfns_xx.tar.gz` 保存 NumPy 波函数文件，并用 `tarball_assignment.csv` 标明分子归属。DataCite DOI 元数据含 CC BY-SA 3.0 和 ETH handle，`contentUrl` 为空。对数据 DOI 请求在最终页面收到 HTTP 403，既有 ETH item/bundles API 核查记录为 429。尚未在此核查中取得并验证一条实际 ETH wavefunction 记录或独立的 QMugs 生成器。可复查 ETH DOI 元数据和归档的 README/映射表，再选择真实成员验证字段。[正文与 Code availability](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9174255/fullTextXML) · [ETH 数据 DOI](https://doi.org/10.3929/ethz-b-000482129) · [DataCite 元数据](https://api.datacite.org/dois/10.3929/ethz-b-000482129)

QMugs 第一作者的公开仓库包含 `cisert/delfta`，GitHub 指向上游 `josejimenezluna/delfta`。作者注明 DelFTa 论文用 v1.0.0。已取得此 tag 的完整树 `5635b514067b229227e27143cd87e0ad5057388e`，51 个跟踪文件，根目录 AGPL-3.0。源码 `DelftaCalculator.predict` 在相应模式下运行 GFN2-xTB、推理并把校正加回低层结果，另有失败分子处理。模型、normalizers 和训练/测试资产通过 download.py 所列外部归档提供，未执行下载器或训练。这里固定的是已发表的 QMugs 下游 Δ-QML 对照。该软件训练自 QMugs，2015 年 Δ-ML 的训练版本另行追踪。[版本说明](https://github.com/josejimenezluna/delfta/blob/5635b514067b229227e27143cd87e0ad5057388e/README.md) · [实现](https://github.com/josejimenezluna/delfta/blob/5635b514067b229227e27143cd87e0ad5057388e/delfta/calculator.py#L483) · [依赖资产](https://github.com/josejimenezluna/delfta/blob/5635b514067b229227e27143cd87e0ad5057388e/delfta/download.py) · [DelFTa 论文](https://doi.org/10.1039/D2CP00834C)

**2015 Δ-ML。** ACS Figshare 对应的唯一 SI 是 `ct5b00099_si_001.pdf`，版本 1、文件 3801826，384,114 字节，实测 MD5 `0e2865b967befc890b7f2b4e9cf5bbe7` 等于发布值。实际渲染并检查全部 3 页、正文和 PDF 附件表。内容为核岭回归公式、交叉验证伪代码及示意图、Coulomb matrix 表示、系统偏差和表格。嵌入附件数为 0，链接为文献与通信地址。此 SI 没有可执行源码。PDF 在 ACS 归档按 CC BY-NC 4.0 发布。[正式 SI 与许可](https://doi.org/10.1021/acs.jctc.5b00099.s001) · [Figshare 单文件清单](https://api.figshare.com/v2/articles/2167927) · [论文](https://doi.org/10.1021/acs.jctc.5b00099)

第一作者的研究组数据页把 134k PM7/B3LYP 数据、6,095 个异构体的关联能数据、9,868 个非对映体的迁移测试与此论文相连。本轮按该页原链接读取：134k 下载返回 404，另两个旧主机链接在 TLS 握手时断开。网页提供实验数据描述。未找到原始 KRR 训练/评测仓库。作者公开 GitHub 项目、ACS 的 SI API 和相关 DOI 查询的检索边界均有记录。现代 DelFTa 和明确自称 reproduction 的仓库须另记，不据此推断历史实现或性能。[作者数据页](https://www.tifrh.res.in/~ramakrishnan/?page_id=66) · [原论文](https://arxiv.org/abs/1503.04987)

## 对 issue #2 验收的影响

| Issue 原文验收项 | 本次核查能证明的范围与余项 |
|---|---|
| 每个纳入对象都有明确版本与角色，或具证据的访问阻塞；重要缺口有继续处理方式。 | 六项均有可追溯调查路径，新增树的作者、时间关系和角色已区分。dm-PhiSNet 的历史实现原可获取，原刊版本和权重仍未绑定。其余五项保留原始代码缺口。 |
| 已获取对象的源码、测试、构建、生成器和必要外部对象范围清楚，完整性检查可重做。 | 三份完整 Git 树、逐文件库存及获取回执已生成，外部训练库、模型、服务和许可限制已注明。原始论文包、训练所需文件未验收为可运行发布物。 |
| 获取/索引/阅读/追踪/运行状态独立，完整文件集合与未读范围可检查。 | 向中央台账提供 302 条库存输入和 7 条显式 blob 审读记录，其中仅 analytic_layer.py 登记全文件已读。本次无第三方训练/评测执行。最终以中央锁和逐文件核验的同一版本输出为准。 |
| 后续审计能定位到确定提交；本任务未解决的源码缺口持续跟踪。 | 三个 pin 和来源证据可直接引用。待中央来源锁为 dm-PhiSNet 登记历史版本和剩余缺口，给其余五项保留证据链接，并重跑全项目库存验证。 |

这些判断覆盖本次六项排查和新增三树，issue #2 的全局验收还应结合中央锁、其他新来源及最终验证输出。
