# gqcdataset Codex 交接导航

本目录提供可以直接交给 Codex 执行的研究目标、工作约定、源码目录、验证要求和证据模板。日期：2026-11-18（Asia/Shanghai）。

**这是依据当前可见对话重建的版本。原 ZIP 与两份原始 PDF 未取得。** 具体来源和恢复边界见 [PROVENANCE.md](PROVENANCE.md)，附件缺口见 [attachments/README.md](attachments/README.md)。

## Codex 阅读顺序

1. 仓库根目录 [AGENTS.md](../../AGENTS.md)。
2. [CODEX_GOAL.md](CODEX_GOAL.md)：总体任务与第一轮交付要求。
3. [项目背景](docs/PROJECT_CONTEXT.md) 与 [研究命题](docs/RESEARCH_CHARTER.md)：用户已确定的要求、五条开放主线、历史候选和未证实能力。
4. [完整源码审计协议](docs/SOURCE_AUDIT_PROTOCOL.md) 与 [源码目录](sources/CATALOG.md)。
5. [阶段路线与验收](docs/ROADMAP_AND_ACCEPTANCE.md)、[科学验证框架](docs/VALIDATION_FRAMEWORK.md)。
6. [当前状态](research/STATUS.md) 与 [issue 导航](research/ISSUES.md)：从已满足依赖的最早未完成任务开始。

## 文件职责

| 文件或目录 | 用途 |
|---|---|
| `CODEX_GOAL.md` | 可直接用作 Codex Goal 的完整任务说明 |
| `docs/PROJECT_CONTEXT.md` | 项目背景、已有认识与未决问题 |
| `docs/RESEARCH_CHARTER.md` | 五条开放主线、竞争解释、可证伪问题 |
| `docs/SOURCE_AUDIT_PROTOCOL.md` | 完整获取、版本锁、覆盖台账、行为证据与运行验证 |
| `docs/ROADMAP_AND_ACCEPTANCE.md` | 阶段依赖、产物和结项条件 |
| `docs/VALIDATION_FRAMEWORK.md` | 科学身份、标签语义、响应、质量、基线、失败与成本 |
| `sources/CATALOG.md` / `catalog.json` | 人可读与机器可读的公开入口起始目录 |
| `sources/CODE_GAPS.md` | 原始实现、访问和版本缺口 |
| `templates/` | 仓库审计、主张证据、源码覆盖、版本锁、假设、实验与决策模板 |
| `tools/inventory_sources.py` | 只清点已有本地 Git checkout 的工具；索引不等于阅读 |
| `research/` | 当前状态、任务导航和后续实际审计/实验记录 |
| `attachments/README.md` | 缺失原件的显式记录 |

目录当前包括 38 个研究／软件条目、31 个不同的可访问仓库；32 个条目已核实仓库入口（部分共用单仓库），另 5 个条目待定位原始代码，1 个论文给出的源码地址当前访问失败。全部完整源码获取与审计均尚未执行。当前公开入口计数不是原 ZIP 清单的逐条恢复证明。

## 路径与证据管理

本目录内的 `research/`、`sources/`、`templates/` 等路径均相对此交接目录。实际实现代码可以按最终路线放入仓库合适的位置。完整第三方源码默认保存在仓库未跟踪的 `_references/`；提交来源锁、审计证据、复现命令与必要脚本。

模板中的空列表和空表头表示待填写，不表示工作完成。后续每项结论应追溯至固定版本、代码/论文、实际命令和结果。保留未知、失败和负结果。

原始 PDF 缺件不阻塞公开源码调研。后续取得原件时应记录哈希并核对差异，不覆盖后来已确认的研究要求。
