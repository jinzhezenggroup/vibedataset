# gqcdataset 当前状态

更新时间：2026-11-18（Asia/Shanghai）。本轮从交接提交
`de60ee48eb7e567b494c558daeba85a8e1aff400` 开始，工作分支
`codex/source-intake-20261118`。完整记录：[INTAKE.md](INTAKE.md)。

可审查提交：[baea1aa](https://github.com/jinzhezenggroup/vibedataset/commit/baea1aa547d74a367224bfb44e179eaaf072eab6)；
[草稿 PR #10](https://github.com/jinzhezenggroup/vibedataset/pull/10)。尚未合入 main。

## 已完成的可审查增量

- [x] 读取根约定、交接 Goal、来源、科学约束与远程 #1/#2；核对本地真实状态。
- [x] 保留接管前未跟踪的 n2 运行约定与环境记录，字节散列核对一致。
- [x] 获取起始目录 31 个不同仓库的完整所选 Git 树；AIRS、LLVM 均为全仓库，未稀疏获取。
- [x] 额外固定历史 GQC 运行源码和新增 `equiv_dens_ml` 参照，共 33 份根树快照。
- [x] 固定 commit/tree、许可文件、子模块、LFS、浅历史与范围；xTB/TREXIO 子模块已补齐。
- [x] 建立 252,312 条文件覆盖记录、压缩完整库存、来源锁和显式复核记录。
- [x] 验证库存散列、逐文件覆盖、Git pin/干净状态及阅读标记来源；解释并重查 LLVM 的 6 条 CRLF 差异。
- [x] n2 只读导入及实际库哈希复核；未提交计算、未改动共享环境。
- [x] 开始 GQC checkpoint 局部审读，形成 [源码记录](audits/gqc-intake.md) 和 [claims.csv](claims.csv)。

**阅读/追踪/运行的真实计数：** 全文件已读 3，完整行为追踪 0，第三方测试／科学计算执行 0。
清点脚本和台账检查的运行不计入科学执行。没有速度、力误差或创新成立结论。

## Issue 状态

| Issue | 当前状态 | 下一步／未完成原因 |
|---|---|---|
| #1 总 Goal | 进行中 | 完成的是接管增量，研究目标未完成 |
| #2 完整源码接管 | 进行中 | 固定树与覆盖已建立；论文版本、原始实现缺件和关键外部依赖闭包仍需追踪 |
| #3 GQC/xTBloom | 部分开始 | 3 个 GQC 文件已全读，部分测试和 C ABI 已查看；追完原生状态验收、SCF、响应及 xTBloom 批处理，开展有界判别验证 |
| #4 相近实现 | 输入已部分就绪 | 完整树可用，尚未形成机制审计和强基线结论 |
| #5 数据资产 | 来源定位开始 | 尚未获取并核验代表性波函数／数据记录，不能声称字段已验证 |
| #6 五主线比较 | 待关键证据 | 不预选 QMugs、四极矩、固定样本量或唯一课题 |
| #7/#8 实现与评价 | 待路线与科学门槛 | 未进行科研实验、训练或性能比较 |
| #9 原附件 | 未解决 | 原 ZIP 和两份 PDF 仍无原件，不阻塞公开源码审读 |

## 主要证据与边界

- [源码锁](sources.lock.json)、[快照索引](SOURCE_INDEX.md)、[完整覆盖表](source_coverage.csv)、[台账验证](ledger_validation.json)。
- [缺口与访问证据](SOURCE_GAPS.md)：6 个原始代码/资产入口未解决；mlelec 许可与论文版本未确定。
- GQC 当前树 `2791504cc238fe83d328fc1718080642b288222a` 与 n2 声明源码
  `2bf3fd98da9c6cfba46ca83345e63e1d934e4780` 分开记录。
- n2 实测库 SHA256 为 `67bc98a4549fe8854ed6ae65791c824024bd77a9e8e498c6891dea3b8de670c4`；
  该一致性不构成新数值验证或当前源码的可复现构建证明。
- 所有 checkout 的 Git 历史为 shallow。特别是 xTBloom 打包显式要求完整历史，取得文件树不能直接推导可构建。

继续推进已满足依赖的源码审读与资产核查；以实际证据更新 issue，不因“已下载”关闭要求阅读或运行的任务。
