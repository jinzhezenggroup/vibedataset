# 源码与执行缺口（本轮实际接管）

2026-11-18（Asia/Shanghai）。完整 Git 树、论文发布归档与可运行依赖的证据分别登记。Git 版次、论文归属、外部模型和数据的可获取性可逐项检查。[版本锁](sources.lock.json) · [完整快照索引](SOURCE_INDEX.md)

## 起始目录中的六个原始来源

| 对象 | 已经取得或证实 | 尚缺什么及可行的复查入口 |
|---|---|---|
| PhiSNet | 会议正文和补充各 14 页，arXiv 源包是论文及图件。nablaDFT 适配和 CasNet fork 均已取得。 | 2021 原始软件包及其字节身份仍未知。OpenReview 的正常请求遇到验证页，可在恢复访问时核对投稿附件。[会议页](https://proceedings.neurips.cc/paper/2021/hash/78f1893678afbeaa90b1fa01b9cfb860-Abstract.html) |
| dm-PhiSNet | 第一作者仓库的空 HEAD 之前保留完整历史树 `eb365d3e4d0e85ccf89740e5fad26970591c5b16`。190 个文件含数据生成、解析约束、训练和初猜评估。 | 这个 2025 年提交与 2026 论文的精确版本关系、权重、训练库及代码许可仍缺。期刊页面返回 403，可待公开 SI 或作者发布版本核实。[历史树](https://github.com/zyyr17/dm-nn-so3-analytic/tree/eb365d3e4d0e85ccf89740e5fad26970591c5b16) |
| IM-GNN | 出版商 15 页正式 PDF 记载了图结构、缺失边预测、MC-dropout、设置和参数。论文链接、作者和实验室公开仓库清点均有回执。 | 未定位原作者软件归档。可检查后续刊方补充材料与作者公开项目。[正式 PDF](https://www.mi-research.net/en/article/pdf/preview/10.1007/s11633-023-1443-7.pdf) |
| QPMA | arXiv v2 指名的代码地址在 GitHub 和 Software Heritage 精确原址查询均返回 404。 | 原因和迁移地址未知。可查 IEEE 最终稿补充材料及作者发表的新归档号。[论文第 V 节](https://arxiv.org/html/2212.05469v2) |
| QMugs | 刊行正文的 Code availability 给出生成所用工具版本。ETH 元数据给出数据 DOI 和 CC BY-SA 3.0。取得下游 DelFTa 作者论文版。 | 生成工作流没有独立版本，ETH 入口返回 403/429。正文描述的波函数包仍需用实际成员验证。重试 README、分子分包索引和选定条目。[期刊 JATS](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9174255/fullTextXML) · [ETH 数据 DOI](https://doi.org/10.3929/ethz-b-000482129) |
| 2015 Δ-ML | ACS Figshare 仅列一份 384,114 字节的三页补充 PDF。其发布 MD5 与实测一致，含交叉验证伪代码，无嵌入源码。 | 未定位原始训练和评测源码。作者旧数据链接分别返回 404 或 TLS 握手失败，可按作者数据页复查。[ACS 补充归档](https://doi.org/10.1021/acs.jctc.5b00099.s001) |

六项均保留具体来源、访问结果和继续检查方式。dm-PhiSNet 的作者历史实现已经取得，另五项保留原始实现位置缺口。[完整核查](audits/intake-originals.md) · [请求回执与散列](acquisition/originals-evidence-20261118.json)

## 已定位来源的版本与依赖

| 对象 | 已核查与剩余范围 |
|---|---|
| mlelec | Materials Cloud v1 明确链接 `qm7` 分支与论文。另锁定该分支的 129 文件树、主分支，以及有 915 个文件的正式归档。归档 DOI 适用 CC BY 4.0，两个 Git 树没有显式代码许可。归档未给出精确 Git 提交，归档脚本与当前固定分支有独立字节身份。用归档脚本验证了有限场范围，权重与 ML 训练未运行。[正式审计](audits/mlelec-archive.md) · [官方记录](https://archive.materialscloud.org/records/4vezc-jtt98) |
| ANI-1ccx | 已取得数据支持仓库，按论文公式复算作者数据切片。作者仓库未给出可确认的 CC 标签逐行组装源码。NEUROCHEM、权重、现代 TorchANI 与原论文训练版本的关系待核。[复算](experiments/ani_composite/README.md) |
| OpenMDAO、CppAD、pyMOR | 已锁定三个发布树，分别审读并运行双向着色、部分 Jacobian、目标导向误差估计的对照。稀疏请求与结构零的区别、pyMOR 的稳定性常数条件，以及分子自洽响应的适用边界见审计。[着色](audits/response-dual-prior-coloring.md) · [伴随](audits/response-dual-prior-adjoint.md) |

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
| GQC | 当前树、n2/n5 归档 wheel 对应源码和实际原生库身份分开留存。已在固定当前树运行 TensorIR 原生 CPU 编译，在 n5 通过 Slurm 使用归档版 CUDA 原生库。 | 完整工具链和可选 provider 的依赖闭包仍取决于后端。测量和误差范围按具体执行资产核对。[CPU 实验](experiments/gqc_residual_multiround/README.md) · [n5 参考态](experiments/qm9_response_assets/README.md) |
| xTBloom | pyproject.toml 的 `pre_parse = "fail_on_shallow"`；Eigen manifest 规定仅 WebAssembly FetchContent，含版本与 SHA256 | 已补全历史/tags，保持原 pin，按本地 LP64 provider 从源码构建并运行 CPU CTest。CUDA 数值路径与 WebAssembly Eigen 仍需独立验证。[CPU 实跑](audits/xtbloom.md) |
| PySCF | `pyscf/lib/CMakeLists.txt` 的 libcint/qcint、libxc 7.1.2、xcfun、可选 libxsmm/FFTW 等构建边 | 另已固定 v2.14.0 及其默认构建选择的 libcint v6.1.3 全树；AD-001 校验实际 Python 源码与 libcgto 身份，未从源码重建 wheel。其他外部发布物仍待核验。 |
| xTB / tblite | `subprojects/*.wrap` 中的 mctc-lib、dftd4、multicharge、ddX 等 | wrap 文件已包含在树和哈希索引中，非 submodule 的外部下载不自动被递归 Git 获取；逐路径审计时继续固定。 |
| 学习／数据项目 | 原接管阶段仅获取源码。此后按发布身份定向取得少量 ANI、Schofield 等人的权重和数据，记录切片/哈希；后者以 weights_only 加载一次作者模型 | 大数据、模型权重、原论文切分及外部补充代码另作资产；存在 URL 不代表已取得。 |
| 生成代码 | 生成规则和已跟踪生成结果均在全树索引 | 实际运行过的生成器见对应实验。逐项目重建生成产物、核对 release tarball 或 sdist 与 Git 树内容仍须独立验证。 |

获取回执保留了重试和失败。mol_prop_imputation v1.0.0、QCManyBody v0.8.0、Psi4 v1.10、PySCF v2.14.0 与 libcint v6.1.3 都有独立固定树。QCManyBody 的 2024 论文原始提交仍未确定。上表各余项可在相应的后续科学审计中继续推进。[获取回执](acquisition/) · [中央历史审读记录](intake_review.json)

## 原交接附件

历史讨论和设计稿两份 PDF 已找回原始字节并校验。原交接 ZIP 的原始字节和散列仍缺，由独立附件任务跟踪。[附件核验](../attachments/README.md)
