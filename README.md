# vibedataset

**gqcdataset** 研究项目的远程仓库：研究如何复用已有量子化学信息，以明确的科学定义和质量要求补全数据，并保留能够支持后续扩展的资产。

## Codex 从这里开始

1. 读取根目录 [AGENTS.md](AGENTS.md)。
2. 读取 [Codex Goal 主任务](handoff/gqcdataset_codex_goal/CODEX_GOAL.md) 和 [交接导航](handoff/gqcdataset_codex_goal/README.md)。
3. 打开 [任务与依赖导航](handoff/gqcdataset_codex_goal/research/ISSUES.md) 及 [当前研究状态](handoff/gqcdataset_codex_goal/research/STATUS.md)。
4. 获取完整可用源码并固定版本，再依据实现和测试证据推进路线比较、实现与科学验证。

**总任务：[Goal #1](https://github.com/jinzhezenggroup/vibedataset/issues/1)。第一项执行任务：[#2 完整源码接管](https://github.com/jinzhezenggroup/vibedataset/issues/2)。** 后续依赖和验收已写入各 issue，当前共 9 个 issues。

## 已执行的补全工作

项目已交付基于 GQC 科学编译器的分子响应补全工具。给定有来源的历史标量或已保存的响应向量，工具生成剩余物理求解，并记录每个结果的独立验收与实际计算量。n5 已建成持久环境并实算全部 17 个符合筛选规则的 QM9 分子，153 个新目标含 37 个可发布数值。外推同算子对照中，24 项恢复将后续 J/K 从 1,000 减为 518；发布路径的收益取决于实际已有的合格信息。[153 行派生数据](handoff/gqcdataset_codex_goal/research/experiments/qm9_extension/response-labels.jsonl) · [命令行与历史文件用法](handoff/gqcdataset_codex_goal/research/experiments/response_dataset_cli/README.md) · [研究结果与成本](handoff/gqcdataset_codex_goal/research/RESULTS.md) · [n5 环境](docs/N5_GQC.md)

## 材料入口

| 材料 | 作用 |
|---|---|
| [完整交接目录](handoff/gqcdataset_codex_goal/) | Goal、背景、研究主线、阶段验收、模板与工具 |
| [源码与文献目录](handoff/gqcdataset_codex_goal/sources/CATALOG.md) | 38 个研究／软件条目、31 个可访问仓库的起始清单 |
| [机器可读目录](handoff/gqcdataset_codex_goal/sources/catalog.json) | 逐项入口状态、来源及审计问题 |
| [完整源码审计协议](handoff/gqcdataset_codex_goal/docs/SOURCE_AUDIT_PROTOCOL.md) | 获取、索引、阅读、行为追踪、运行验证分别记账 |
| [研究路线与验收](handoff/gqcdataset_codex_goal/docs/ROADMAP_AND_ACCEPTANCE.md) | 可并行任务、阶段依赖和证据门槛 |
| [科学验证框架](handoff/gqcdataset_codex_goal/docs/VALIDATION_FRAMEWORK.md) | 状态/标签语义、响应、质量证据、强基线与全成本 |
| [材料来源与恢复边界](handoff/gqcdataset_codex_goal/PROVENANCE.md) | 本次重建来源、缺件和后续核对方法 |
| [下载重建版 ZIP](https://github.com/jinzhezenggroup/vibedataset/raw/refs/heads/main/downloads/gqcdataset_codex_goal_20261118_rebuilt.zip) | 初次重建的文字与工具快照；单独提供后来取得的两份历史 PDF |
| [ZIP SHA-256](https://github.com/jinzhezenggroup/vibedataset/blob/main/downloads/gqcdataset_codex_goal_20261118_rebuilt.zip.sha256) | 下载完整性校验 |

## 当前阶段

本次交接材料于 2026-11-18（Asia/Shanghai）根据当前可见对话重建，修复了初始化 README 指向不存在文件的问题。后来取得两份历史 PDF，已核对原始字节、页码及内容差异。用户已取消原 ZIP 的交付要求。[附件原件与核对记录](handoff/gqcdataset_codex_goal/attachments/README.md)

固定版本、逐文件清单、实际审读与运行证据见[来源索引](handoff/gqcdataset_codex_goal/research/SOURCE_INDEX.md)和[研究结果](handoff/gqcdataset_codex_goal/research/RESULTS.md)。

信息充分性、剩余科学程序生成、联合信息获取、目标质量控制、可持续扩展资产五条主线保持开放。历史 QMugs 四极矩、固定样本数和接口草案均为候选，后续路线依据源码与实验决定。
