# 首轮源码接管：范围、证据和复现

2026-11-18，基于交接提交 `de60ee48eb7e567b494c558daeba85a8e1aff400`，
分支 `codex/source-intake-20261118`。本轮推进 #2，并开始 #3 的一条局部审读。

## 实际完成的增量

- 起始目录 31 个不同仓库的**完整所选 Git 树**已获取，包括整个 AIRS 和整个 LLVM 项目，未做 sparse checkout。
- 额外固定 n2 声明的 GQC 历史源码，并沿作者论文新增 `equiv_dens_ml` 参照：共 33 份根树快照。
- xTB 的一个子模块、TREXIO 的两个子模块均按父树提交取得并递归清点。
- 全部 252,312 条文件记录进入覆盖台账；此分母按快照计数，两个 GQC 版本中的同名文件分别计入。
- 全文件阅读记录仅 **3** 条；完整行为追踪 **0**，第三方测试／科学计算执行 **0**。
- n2 只读导入与动态库实际哈希核验通过；未安装、升级、编译或提交计算作业。

`acquired` 的范围仅为锁定 Git 树及其子模块。源码树之外的外部数值依赖、
论文版本和原始实现缺件仍未闭合，详见 [SOURCE_GAPS.md](SOURCE_GAPS.md)。
#2 保持打开；不能把本轮写成完整源码审计或科研验证完成。

## 可审查入口

| 产物 | 说明 |
|---|---|
| [sources.lock.json](sources.lock.json) | 完整 commit/tree、角色、许可文件、浅历史、子模块、LFS、范围和缺口 |
| [SOURCE_INDEX.md](SOURCE_INDEX.md) | 每个快照的简明入口、文件数和固定版本 |
| [source_coverage.csv](source_coverage.csv) | 完整逐文件覆盖；子模块文件使用其自己的 commit；未读范围不隐藏 |
| `inventories/*.json.gz` | 无损压缩的全树文件/字节/哈希证据；SHA256 在锁文件内 |
| [intake_review.json](intake_review.json) | 绑定 commit 的完整性复核、绑定 blob 的阅读记录、LLVM 换行例外证据 |
| `acquisition/` | started、命令、时间、返回码与输出；初始子模块缺件清点也保留 |
| [ledger_validation.json](ledger_validation.json) | 全覆盖、哈希、状态来源、Git pin 和干净工作树一致性检查结果 |
| `environment/` | 本地初始状态／保全散列，以及 n2 实际检查结果 |
| [audits/gqc-intake.md](audits/gqc-intake.md) | checkpoint 局部源码记录，未执行项和下一条行为链 |

每个库存 JSON 保留脚本原始检查字段，只把本地绝对 `repository_path` 改成项目相对路径，
并明确记载这种路径规范化。gzip 固定 mtime=0；解压内容和压缩对象均有 SHA256。
未压缩工作副本不进 Git；第三方 checkout、训练数据和计算产物也不进 Git。

LLVM 的 6 条 blob 差异没有被删除：其 Git 属性指定 CRLF，
逐文件验证工作区恰等于固定 blob 的 LF→CRLF 展开。它们保留在原清点中，
锁文件单列已解释的完整性提示；验证器重新检查属性、blob 和实际字节。
没有为消除告警而改写上游文件。

## 在干净 checkout 中复现

从项目根目录运行（Python ≥3.10、Git、网络）。获取工具拒绝覆盖已有 checkout；
已有目录应先检查并选择另一工作区，不执行自动删除或 reset。

```bash
python3 handoff/gqcdataset_codex_goal/tools/acquire_sources.py \
  --plan handoff/gqcdataset_codex_goal/research/acquisition_plan.json
git -C _references/xtb -c protocol.file.allow=never submodule update --init --recursive --depth=1
git -C _references/trexio -c protocol.file.allow=never submodule update --init --recursive --depth=1
python3 handoff/gqcdataset_codex_goal/tools/inventory_sources.py _references/xtb \
  --recurse-submodules --json handoff/gqcdataset_codex_goal/research/inventories/xtb.json
python3 handoff/gqcdataset_codex_goal/tools/inventory_sources.py _references/trexio \
  --recurse-submodules --json handoff/gqcdataset_codex_goal/research/inventories/trexio.json
python3 handoff/gqcdataset_codex_goal/tools/build_source_ledger.py
python3 handoff/gqcdataset_codex_goal/tools/verify_source_ledger.py
```

计划中的当前版本已冻结成实际取得的完整 SHA，不在复现时追踪移动的 HEAD。
重新清点会产生新的时间戳／库存散列；文件 blob 和工作区字节才是比较内容的依据。
人工复核绑定 commit，阅读记录绑定 blob；发生变化时不能自动沿用旧记录。
生成覆盖表只合并这些显式记录，不把清点提升为阅读。

只读环境检查：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 n2 'bash -s' < scripts/inspect_n2_runtime.sh
```

它只加载已有配置、导入 GQC、计算已有库散列并查询 Slurm；不调用 Calculator。
原始检查中 `main` 为空闲、当前用户队列为空，仅表示该时间点，不保证未来资源。

## 仍待推进

1. #2：固定论文分支/归档，沿关键执行路径补齐外部源码及测试资产；mlelec 许可待查。
2. #3：从 checkpoint 进入原生状态验收、SCF 和响应消费者；对 xTBloom 进入批处理／失败隔离路径。
3. #4/#5：对已锁定强基线和数据接口按文件审读，获取有代表性的实际资产；本轮未核验波函数字段。
4. #6：只有关键源码、资产和对照证据齐备后才比较并选择路线。

本轮保留接管前本地 n2 约定的完整字节，合并到项目文档中；未修改 xtbflow。
原始交接 `MANIFEST.json` 与下载 ZIP 仍表示历史发布快照，未把本轮研究记录冒充原包内容。
