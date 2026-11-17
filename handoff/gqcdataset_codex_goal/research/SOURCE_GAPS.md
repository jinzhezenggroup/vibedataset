# 源码与执行缺口（本轮实际接管）

2026-11-18（Asia/Shanghai）；关联 #2、#3、#4、#5、#9。
本表区别**完整 Git 树**、**论文实验发布物**与**可运行依赖闭包**。
`sources.lock.json` 的 acquired 仅覆盖其中明确列出的固定树和子模块；
不表示下表已解决，不支持任何新颖性或数值正确性结论。

## 原始实现和公开来源

| 对象 | 本轮查证的来源与观察 | 尚缺什么／下一步 |
|---|---|---|
| PhiSNet 原始实现 | [NeurIPS 官方页](https://papers.nips.cc/paper/2021/hash/78f1893678afbeaa90b1fa01b9cfb860-Abstract.html) 的 Supplemental 实际指向 14 页 PDF；[OpenReview](https://openreview.net/forum?id=auGY2UQfhSu) 返回浏览器验证页。搜索原作者与模型名未定位可确认的原始代码包。 | 保持原始实现未获取；nablaDFT 是单列适配实现。后续核对作者发布物／OpenReview 附件，不能把 PDF 当代码归档。 |
| dm-PhiSNet | [arXiv HTML v1](https://arxiv.org/html/2604.27256v1) 可读；本轮检索 github 链接只见 arXiv 页脚基础设施；[期刊 DOI](https://doi.org/10.1002/chem.71739) 在浏览工具访问失败。 | 期刊 SI、原始实现和公式—代码对应仍未取得。不可从缺代码推出无既有方法。 |
| IM-GNN | [MIR 官方论文页](https://www.mi-research.net/en/article/doi/10.1007/s11633-023-1443-7) 可读，但返回内容未给出作者代码链接；模型名＋作者＋github 搜索未得到可确认的原始实现。 | 检查可获取的全文／补充材料与作者项目；不用不同的 IMM-GNN、ImbGNN 或搜索聚合站替代。 |
| QPMA | 本轮 GitHub connector GET `https://api.github.com/repos/JeongminChae/QPMA` 仍返回 HTTP 404 / NOT_FOUND。 | 迁移、权限、删除原因未知；保留访问阻塞，沿论文和作者公开归档追踪。 |
| QMugs | [ETH 官方数据记录](https://www.research-collection.ethz.ch/entities/researchdata/d0e7d2fc-6fd2-43bc-bd68-8903470ad0ec) 搜索索引可定位；直接打开返回 403。[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9174255/) 返回验证页，Nature 正文重定向受限。 | 尚未获取实际波函数记录，未定位独立生成源码。后续沿官方 README／数据访问入口验证文件结构与许可；归档存在不算数据字段已核验。 |
| Δ-ML 原始工作 | [arXiv 1503.04987](https://arxiv.org/abs/1503.04987) 可读；本轮定向搜索未定位能确认对应原实验的代码。 | 查原作者归档和 SI；现代 Δ-learning 实现单列，不能替代原始版本。 |
| mlelec 论文版本 | [Materials Cloud v1](https://archive.materialscloud.org/records/4vezc-jtt98) 将 mlelec 列为软件，另列 1.1 GiB dataset.tar.xz 和 README；README 下载经签名重定向后在浏览工具失败。 | 当前默认分支已锁定，但论文分支／提交未确定；不能用 main 证明论文复现。固定树的 pyproject.toml 仍为 `license = TODO` 注释，未找到 LICENSE/COPYING。先解决授权和论文版本，再复用实现。 |
| ANI-1ccx | 获取的是目录中的数据支持仓库。 | 训练实现、NEUROCHEM、权重与现代 TorchANI 的版本关系仍待 #4/#5 审读；数据下载脚本不算训练链闭合。 |

以上检索均只是定位证据，未声称通读论文或补充材料。
本轮没有联系作者或发送邮件。

## 引用扩展

PhiSNet 作者方向的检索定位到
[Enhancing molecular dynamics with equivariant machine-learned densities 的作者发布 PDF](https://dft.uci.edu/pubs/BHVMBT26.pdf)，
其中 Code Availability 指向 `MihailBogojeski/equiv_dens_ml`。
已把该完整仓库作为独立的当前实现加入获取计划。它不是 PhiSNet 原始代码，
也不是 dm-PhiSNet 的实现。其论文版本、依赖和机制仍待审计。
另一条可继续核查的适配路线是
[deeperwin 原论文](https://proceedings.neurips.cc/paper_files/paper/2023/file/4b5721f7fcc1672930d860e0dfcfee84-Paper-Conference.pdf)
指向的 `mdsunivie/deeperwin`；本轮仅登记，未获取，不能作已审计对照。

## 源码树之外的对象

| 范围 | 已检查 | 处理方式与边界 |
|---|---|---|
| Git 子模块 | xTB 的 AUR 包装仓库；TREXIO 的教程与文档主题 | 读取 .gitmodules 后按父树 pin 获取；初始缺件清点、获取回执和最终递归清点均保留。不自动排除文档／测试支持。 |
| LFS | 每份清点递归检查固定树中 ≤1 KiB 的标准指针及内容哈希 | 汇总在锁文件。非典型指针、远端数据服务和下载脚本内容不在这个检查的保证内。 |
| LLVM 工作区换行 | 6 条初始 blob 差异，均有 `eol=crlf` 属性且实际字节恰为固定 blob 的 LF→CRLF 展开 | 保留原始差异，在 intake_review.json 逐文件解释，验证器重查；没有修改源码或隐藏缺件。 |
| GQC | 当前源码与 n2 声明源码分开；树内 generator、manifest、upstream、tests 和原生源码均已索引 | 不重编译。n2 导入和库哈希不是当前源码的执行证据，也不是可复现构建证明。可选 CUDA/CUTLASS/cuTENSOR 等 provider 需在选定执行路径后固定。 |
| xTBloom | pyproject.toml 的 `pre_parse = "fail_on_shallow"`；Eigen manifest 规定仅 WebAssembly FetchContent，含版本与 SHA256 | 当前完整树的历史仍为浅历史；构建前补足历史/tags。WebAssembly Eigen 与原生运行路径分开；没有因清点成功就安装或宣称可运行。 |
| PySCF | `pyscf/lib/CMakeLists.txt` 的 libcint/qcint、libxc 7.1.2、xcfun、可选 libxsmm/FFTW 等构建边 | 这些外部发布物未全部获取；必须在选定后端时按配置固定，不能把 PySCF 根树称为整个数值依赖闭包。 |
| xTB / tblite | `subprojects/*.wrap` 中的 mctc-lib、dftd4、multicharge、ddX 等 | wrap 文件已包含在树和哈希索引中，非 submodule 的外部下载不自动被递归 Git 获取；逐路径审计时继续固定。 |
| 学习／数据项目 | 全仓库保留已有文件，不加载 pickle、不执行下载器或训练代码 | 大数据、模型权重、原论文切分及外部补充代码另作资产；存在 URL 不代表已取得。 |
| 生成代码 | 生成规则和已跟踪生成结果均在全树索引 | 尚未运行生成器；不保证 release tarball、sdist 与 Git 树产物相同。 |

缺口的当前状态与重试成本以 `acquisition/` 回执为准；超时／失败不删除。
外部依赖闭包和论文版本尚未核完，#2 保持打开。已锁定的树可立即支撑 #3/#4/#5 的局部审读。

## 原交接附件

原 ZIP、`gptchataboutgqc.pdf`、`gqc_completion_design.pdf` 未提供原件，继续由 #9 跟踪。
仓库重建 ZIP 不是原件；本轮没有把缺失附件作为研究证据。
