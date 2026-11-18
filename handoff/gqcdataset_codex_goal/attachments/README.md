# 历史附件与核对记录

2026-11-18（Asia/Shanghai）在用户本机找回两份与交接记录同名的 PDF，按本仓库交接材料的上传授权保存原始字节。复制后已用 cmp 与源文件逐字节比较，用 pdfinfo 核对页数并渲染查阅。44 页讨论的第 37 页列出三页设计稿的文件名及内容；设计稿三页均与该描述相符。最初重建版本未包含这两份文件。

| 原件 | 本机来源 | 字节 | 页数 | SHA-256 |
|---|---|---:|---:|---|
| [历史讨论](gptchataboutgqc.pdf) | 用户目录的同名 PDF | 1,626,624 | 44，A4 | `05247dbe0c78c4b90e9dd636240cd3e525477bf41a6da28a9200b84e7c2ea440` |
| [解耦架构与 QMugs 四极矩设计稿](gqc_completion_design.pdf) | 用户下载目录的同名 PDF | 695,606 | 3，A3 | `70835730ba363cea1a3e2d027c1be83a72f0f11bb437c82094974616476c94e2` |

### 与重建交接的差异

| 原始页码 | 从原件可确认的内容 | 对本项目的处理 |
|---|---|---|
| 讨论 1–10 | 已有信息可提供初猜、消除显式步骤，或进入剩余驻点/伴随方程。几何、状态和目标一致性及隐式响应均有条件 | 保留原研究问题。对静态物性、耦合场响应和统计预测分别登记。现有运行证据可逐项复核。[科学实验](../research/RESULTS.md) |
| 讨论 11–22 | 多种数据集、复用方式和预设的成本情景。性能比较来自历史引述及假设计算 | 重建保留了五条主线，未保留当时逐项表格。此处保留其上下文。历史速度与外推数字不进入本仓库实测统计 |
| 讨论 23–36 | 比较科学公式、程序生成、执行后端与调度。建议用成熟程序及 GQC 在相同复用计划下对照；列出多个数据集和样本规模 | 成本按求解、验收、读写和保存分别归因。QMugs、QH9、rMD17、SPICE 和样本数继续作为候选 |
| 讨论 37–44；设计第 1 页 | 明确拆分科学身份和执行身份。给出跨数据适配、状态、几何、响应/物性资产及缓存的接口草图 | 接口名属于历史设计。当前可执行入口、存储身份和门槛由本仓库源码及实测确定 |
| 设计第 2 页；讨论 39–41 | QMugs 存档态的 ωB97X-D/def2-SVP 四极矩候选，固定原点，合并 α/β 自旋密度并检查 Tr(DS)。无迹定义含 1/2，单位 e·a₀²，六个对称分量中五个独立。以同态 Psi4、矩阵法及分块收缩作对照 | 为此候选保留更完整的科学定义。现有 QM9 实验的电子二阶矩场导数与此性质分别命名 |
| 设计第 3 页；讨论 42–44 | 列出升阶重叠积分实现候选、primitive 归一化与收缩系数限制、坐标平移及 CPU 到 CUDA 验证顺序 | 作为待核验的实现提案保存。当前精度差异只记原始输入、差值与门槛，由用户决定对上游的反馈 |

### 原 ZIP 的查找与结项

查找期间未取得 `gqcdataset_codex_goal_20261118.zip` 的原始字节或散列。已查本机项目、用户目录的相应文件名与下载目录中的相关包，以及仓库发布入口。2026-10-29 的 `gqc_handover.zip` 含 8,810 个归档条目，顶层是早期 GQC 文档与 A100 包。另一个十月论文对话 ZIP 只有三个条目。两者都没有该原包或这两份 PDF 的同名成员。讨论第 37 页列出的另一个压缩包用于矢量图源。

2026-11-18 独立复查了远程 `main`（`de60ee4`）与研究分支（`db97afd`）可达的全部 72 个提交，以及当时 PR #10 的合并树，历史中唯一的 ZIP 对象是重建包 `466160579c927d79d0dfc12f3b263cf0809b60c4`。原 README 的下载路径在初始提交和当日 `main` 均返回 HTTP 404，GitHub 发布记录与 Actions 产物均为零，本机另查的 A100 备份 9,042 个条目也无原包文件名。[当时的研究树](https://github.com/jinzhezenggroup/vibedataset/tree/db97afd179bab1ab6ca06fefc69884dc86e8d014/downloads) · [初始 README](https://github.com/jinzhezenggroup/vibedataset/blob/8e329d573ce3cdc9210cdc9d2d1766940cfa7d1c/README.md#L20) · [官方发布](https://github.com/jinzhezenggroup/vibedataset/releases)

到研究提交 `64c5bfab3e6b4d2382c9878a48d76c4e6e59f9b7` 再查两条已公布分支的全部 98 个可达提交，仍只检出重建包的同一 Git 对象。本机可读的下载及回收站目录中未见以原名开头的完整、重名或部分下载。另核对了 n2 的项目目录 `~/vibedataset`，精确文件名命中为 0，遍历错误为 0。原包的 SHA-256 和内部清单均未知。

2026-11-18，用户明确确认原 ZIP 不再需要，按 #9 的验收条件结束原包追踪。两份历史 PDF 的原件及散列见上表。[重建 ZIP 与校验文件](../../../downloads/) · [资料 issue #9](https://github.com/jinzhezenggroup/vibedataset/issues/9)

在仓库根目录可运行以下检查。

```bash
sha256sum handoff/gqcdataset_codex_goal/attachments/*.pdf
pdfinfo handoff/gqcdataset_codex_goal/attachments/gptchataboutgqc.pdf
pdfinfo handoff/gqcdataset_codex_goal/attachments/gqc_completion_design.pdf
```
