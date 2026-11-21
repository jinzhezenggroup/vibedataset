# vibedataset

**gqcdataset** 研究项目的远程仓库：研究如何复用已有量子化学信息，以明确的科学定义和质量要求补全数据，并保留能够支持后续扩展的资产。

## Codex 从这里开始

1. 读取根目录 [AGENTS.md](AGENTS.md)。
2. 读取 [Codex Goal 主任务](handoff/gqcdataset_codex_goal/CODEX_GOAL.md) 和 [交接导航](handoff/gqcdataset_codex_goal/README.md)。
3. 打开 [任务与依赖导航](handoff/gqcdataset_codex_goal/research/ISSUES.md) 及 [当前研究状态](handoff/gqcdataset_codex_goal/research/STATUS.md)。
4. 获取完整可用源码并固定版本，再依据实现和测试证据推进路线比较、实现与科学验证。

研究总目标和审查后的任务顺序见 [Goal #1](https://github.com/jinzhezenggroup/vibedataset/issues/1#issuecomment-6968146709)。PR #10 覆盖 #11–#13 的修订，PR #16 的盲验与资产证据已作为 #17–#19 的历史输入。当前科研顺序为 #17 → #19 → #18。[任务导航](handoff/gqcdataset_codex_goal/research/ISSUES.md)

## 已执行的补全工作

项目用有来源的历史标量或响应向量补全相同协议下的分子响应。17 个 QM9 候选对应 153 个唯一目标。用独立 AO 方程逐项验收后，108 项可发布，45 项保留缺基态的原因。在十个受控请求掩码上，普通块、已验收标量扣除、保留方向向量的后轮成本分别为 12,370、10,371、7,102 次 J/K。独立验收、历史生产与失败费用均可追溯。[v2 数据与精度](handoff/gqcdataset_codex_goal/research/experiments/cphf_v2/README.md) · [全部 153 项](handoff/gqcdataset_codex_goal/research/experiments/cphf_v2/response-labels.jsonl) · [命令行用法](handoff/gqcdataset_codex_goal/research/experiments/response_dataset_cli/README.md) · [研究结果与成本](handoff/gqcdataset_codex_goal/research/RESULTS.md)

在没有完整真值的补全入口中，程序用原生物理残差、读出算符和历史误差估计作决定，另一个进程再开封独立参照。11 个留出构型的 33 个请求有 24 项接受、9 项缺态。循环历史的三个新增目标可用两混合场恢复，留出集与手写路径同为 824 次后轮 J/K。质量验收已付过小型稠密矩阵时，直接解所需列更便宜。实际核查的外部资产没有提供兼容的旧标量和自然请求。两种资产场景及停止扩大范围的决定均已登记。[盲验 CLI](handoff/gqcdataset_codex_goal/research/experiments/target_quality/README.md) · [强基线与预算](handoff/gqcdataset_codex_goal/research/experiments/response_benefit/README.md) · [独立研究 PR](https://github.com/jinzhezenggroup/vibedataset/pull/16)

后续研究已完成。有限多混合场搜索与手写公式逐项等价，目标证书保留离散 SVD 入口但不升级为普适严格界，跨方法/基组/状态资产按科学身份分类并在不匹配时拒绝或重算。[#17 信息充分性](handoff/gqcdataset_codex_goal/research/experiments/information_sufficiency/README.md) · [#19 误差证书](handoff/gqcdataset_codex_goal/research/experiments/error_certificates/README.md) · [#18 跨协议边界](handoff/gqcdataset_codex_goal/research/experiments/cross_protocol/README.md)

复评后新增 #25–#27。独立手写基线与四列二值候选已运行，算子级证书已加入全空间探针，响应资产迁移已完成独立序列化重开和目标 CPHF 评分。[#25](handoff/gqcdataset_codex_goal/research/experiments/information_sufficiency/issue25/README.md) · [#26](handoff/gqcdataset_codex_goal/research/experiments/error_certificates/operator_probe/README.md) · [#27](handoff/gqcdataset_codex_goal/research/experiments/cross_protocol/response_migration/README.md)

新增 #31–#33 已完成。四臂 GPU4PySCF/GQC 归因、固定版本源码算法矩阵和带成本/覆盖/风险的目标相关 planner 均有独立复核。结果限定为 17 个 RHF/STO-3G 小分子和预登记请求轨迹。[四臂实验与 planner](handoff/gqcdataset_codex_goal/research/experiments/attribution_4arm/README.md) · [源码审计](handoff/gqcdataset_codex_goal/research/audits/SOURCE_AUDIT_32.md) · [算法矩阵](handoff/gqcdataset_codex_goal/research/audits/ALGORITHM_MATRIX.md)

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
| [开发资源清单](docs/DEVELOPMENT_RESOURCES.md) | GitHub 账号、CI、集群和后续资源边界 |
| [ChatGPT/Codex 中继流程](docs/CHATGPT_CODEX_RELAY_WORKFLOW.md) | 网页审核、Codex 执行、PR 回执和 merge queue 操作 |
| [下载重建版 ZIP](https://github.com/jinzhezenggroup/vibedataset/raw/refs/heads/main/downloads/gqcdataset_codex_goal_20261118_rebuilt.zip) | 初次重建的文字与工具快照；单独提供后来取得的两份历史 PDF |
| [ZIP SHA-256](https://github.com/jinzhezenggroup/vibedataset/blob/main/downloads/gqcdataset_codex_goal_20261118_rebuilt.zip.sha256) | 下载完整性校验 |

## 当前阶段

本次交接材料于 2026-11-18（Asia/Shanghai）根据当前可见对话重建，修复了初始化 README 指向不存在文件的问题。后来取得两份历史 PDF，已核对原始字节、页码及内容差异。用户已取消原 ZIP 的交付要求。[附件原件与核对记录](handoff/gqcdataset_codex_goal/attachments/README.md)

固定版本、逐文件清单、实际审读与运行证据见[来源索引](handoff/gqcdataset_codex_goal/research/SOURCE_INDEX.md)和[研究结果](handoff/gqcdataset_codex_goal/research/RESULTS.md)。

信息充分性、剩余科学程序生成、联合信息获取、目标质量控制、可持续扩展资产五条主线保持开放。历史 QMugs 四极矩、固定样本数和接口草案均为候选，后续路线依据源码与实验决定。

## 开发流程

工程改动遵循 issue → 隔离分支 → 可复现检查 → pull request → 规则集合并的流程。PR 模板要求记录科学身份、独立参照、失败行为、计算成本和持久资产。`main` 当前要求 `Response validation gate`，只允许通过 pull request 使用 squash 合并，并保留合并队列入口。[开发约定](CONTRIBUTING.md)

## 响应验证

在仓库根目录运行以下命令。每次使用新的输出目录，`checks.json` 会记录实际提交、环境、命令和退出状态。两个检查均可在 Linux CPU 上运行。

```bash
python3 scripts/check_response_ci.py archive --out .work/response-archive-01
```

新增研究归档检查可以在不安装科学依赖的 Python 环境中重放四臂记录、独立评分摘要和 planner 选择。

```bash
python3 scripts/check_attribution_ci.py --out .work/attribution-ci
```

归档检查仅用 Python 标准库，核对两套规划器的全部已登记组合、两批 v1 标签的逐字节重建、v2 的 153 项资格迁移表和独立复核费用，以及 17 个分子的两版规划成本与操作记录。它还在临时副本中故意破坏一份归档，要求重放因校验和错误而失败。

科学回归使用 Python 3.13、Git 和 C++ 编译器。在单独的 Python 环境中安装固定依赖后，运行同一入口的 `science` 模式。

```bash
python3.13 -m venv .work/response-science-env
.work/response-science-env/bin/python -m pip install --only-binary=:all: -r configs/response-science-requirements.txt
.work/response-science-env/bin/python scripts/check_response_ci.py science --out .work/response-science-01
```

科学回归会按仓库版本锁获取缺少的 GQC 与 PySCF 源码树，并为浅克隆取得旧 CLI 的固定提交。它实算直接／伴随响应、组合块和独立 CPHF，按冻结资格核对每个可计算目标、跳过的输入与退出码。CLI 测试覆盖历史来源、版本隔离、损坏的缓存、求解失败与 SQLite 回滚。每个 PR 的两项检查分别保存原始 JSON、JSONL 和命令日志。[工作流](.github/workflows/response.yml) · [CPU 依赖](configs/response-science-requirements.txt)

后续研究的归档层另从原始封存包重算 #14 两个分组的评分与成本，逐项核对 #15 的归档、强基线与请求概率区间。科学层在无目标表的来源目录中执行水分子盲生产和独立评分，并验证双场恒等式、历史误差传播和失效输入。
