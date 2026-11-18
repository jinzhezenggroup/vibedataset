# vibedataset

**gqcdataset** 研究项目的远程仓库：研究如何复用已有量子化学信息，以明确的科学定义和质量要求补全数据，并保留能够支持后续扩展的资产。

## Codex 从这里开始

1. 读取根目录 [AGENTS.md](AGENTS.md)。
2. 读取 [Codex Goal 主任务](handoff/gqcdataset_codex_goal/CODEX_GOAL.md) 和 [交接导航](handoff/gqcdataset_codex_goal/README.md)。
3. 打开 [任务与依赖导航](handoff/gqcdataset_codex_goal/research/ISSUES.md) 及 [当前研究状态](handoff/gqcdataset_codex_goal/research/STATUS.md)。
4. 获取完整可用源码并固定版本，再依据实现和测试证据推进路线比较、实现与科学验证。

研究总目标和审查后的任务顺序见 [Goal #1](https://github.com/jinzhezenggroup/vibedataset/issues/1#issuecomment-6968146709)。PR #10 的本轮修订覆盖 #11–#13，下一阶段的质量证据和真实资产收益分别由 #14、#15 跟踪。[任务导航](handoff/gqcdataset_codex_goal/research/ISSUES.md)

## 已执行的补全工作

项目用有来源的历史标量或响应向量补全相同协议下的分子响应。17 个 QM9 候选对应 153 个唯一目标。用独立 AO 方程逐项验收后，108 项可发布，45 项保留缺基态的原因。在十个受控请求掩码上，普通块、已验收标量扣除、保留方向向量的后轮成本分别为 12,370、10,371、7,102 次 J/K。独立验收、历史生产与失败费用均可追溯。[v2 数据与精度](handoff/gqcdataset_codex_goal/research/experiments/cphf_v2/README.md) · [全部 153 项](handoff/gqcdataset_codex_goal/research/experiments/cphf_v2/response-labels.jsonl) · [命令行用法](handoff/gqcdataset_codex_goal/research/experiments/response_dataset_cli/README.md) · [研究结果与成本](handoff/gqcdataset_codex_goal/research/RESULTS.md)

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

## 响应验证

在仓库根目录运行以下命令。每次使用新的输出目录，`checks.json` 会记录实际提交、环境、命令和退出状态。两个检查均可在 Linux CPU 上运行。

```bash
python3 scripts/check_response_ci.py archive --out .work/response-archive-01
```

归档检查仅用 Python 标准库，核对两套规划器的全部已登记组合、两批 v1 标签的逐字节重建、v2 的 153 项资格迁移表和独立复核费用，以及 17 个分子的两版规划成本与操作记录。它还在临时副本中故意破坏一份归档，要求重放因校验和错误而失败。

科学回归使用 Python 3.13、Git 和 C++ 编译器。在单独的 Python 环境中安装固定依赖后，运行同一入口的 `science` 模式。

```bash
python3.13 -m venv .work/response-science-env
.work/response-science-env/bin/python -m pip install --only-binary=:all: -r configs/response-science-requirements.txt
.work/response-science-env/bin/python scripts/check_response_ci.py science --out .work/response-science-01
```

科学回归会按仓库版本锁获取缺少的 GQC 与 PySCF 源码树，并为浅克隆取得旧 CLI 的固定提交。它实算直接／伴随响应、组合块和独立 CPHF，按冻结资格核对每个可计算目标、跳过的输入与退出码。CLI 测试覆盖历史来源、版本隔离、损坏的缓存、求解失败与 SQLite 回滚。每个 PR 的两项检查分别保存原始 JSON、JSONL 和命令日志。[工作流](.github/workflows/response.yml) · [CPU 依赖](configs/response-science-requirements.txt)
