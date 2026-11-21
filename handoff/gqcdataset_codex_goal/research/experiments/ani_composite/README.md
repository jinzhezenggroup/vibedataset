# CBS-001 真实缺失与一个被否决的复用路径

发布标签缺失的 323 行，其七个必需分量也全部缺失。其余 34 行的七个分量及发布标签全部存在。GQC TensorIR 按登记的复合能量公式执行，和独立手写公式在 34 行上逐值相符，但两条路径相对发布值均有 0.0225864–0.0356659 Hartree 的绝对差。预登记上限为 10⁻⁸ Hartree。本切片可以验证表达式，却没有一行新增合格的 CCSD(T)*/CBS 标签。[协议](../ani_composite_protocol.md) · [汇总](summary.json) · [357 行可查结果](observations.json.gz)

| 观测 | 结果 |
|---|---|
| 原样查询已有 CC 标签 | 34/357；保留为发布值 |
| 七个分量存在、CC 标签缺失 | 0/357 |
| 七个分量全缺、CC 标签缺失 | 323/357 |
| 可执行 H、H+M 和最终公式的行数 | 各 34；中间量只按各自的具名公式解释 |
| GQC 同一行三个输出联合／分开执行 | 510／1,054 个实际生成快照的节点，含常数和输入；输出逐位相同 |
| GQC 与同公式手写 FP64 的最大差 | 0 Hartree；手写的联合求值也可共享中间量 |
| 本轮新增量化作业、可认定省下的真实发布标签重算 | 均为 0 |

原论文式 (1)–(3) 与补充材料第 3 页表 3 均已核对，七个字段对应 T/Q Hartree–Fock、T/Q 的 MP2 相关能和三个指定基组/PNO 阈值的相关能。文章给出 α=5.46、β=3.05。表中字段身份与代码相符。已固定的作者 Git 树包含数据读取器，未取得生成发布标签的逐行 ORCA 输入、输出和实际组装代码；现有证据不足以解释偏差来源。保留原阈值与原始值，没有反向拟合参数。此项记录同时约束手写与 GQC 路径。[论文](https://doi.org/10.1038/s41597-020-0473-z) · [作者补充材料](https://static-content.springer-cdn.net/esm/art%3A10.1038%2Fs41597-020-0473-z/MediaObjects/41597_2020_473_MOESM1_ESM.pdf) · [原始发布](https://doi.org/10.6084/m9.figshare.10047041.v1)

## 复现与成本

在根目录使用固定的 GQC 源码树和装有 NumPy 2.5.5、h5py 3.16.0、fsspec 2026.9.0 的 Python。下列离线命令读取仓库内 7,232 字节的 CC0 分量包，验证容器、列、坐标引用与发布标签的哈希，并重新执行全部判断。退出码 1 表示科学验收未通过，标准输出仍是完整结果。核对 JSON 时，耗时随执行环境变化。

```bash
out=handoff/gqcdataset_codex_goal/research/experiments/ani_composite
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/_references/gqc/python" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .work/audit-venv/bin/python scripts/probe_ani_composite.py "$out"
```

从官方发布重新取得小包可运行 `.work/audit-venv/bin/python scripts/fetch_ani_composite.py .work/ani-refetch`。首次确定样本的 HDF5 分块缓存累计请求 148,373,504 字节，耗时 663.64 秒。已知分组名后提取七个分量及参照，累计请求 5,242,880 字节，耗时 25.07 秒；只验证所读切片。所有求值使用 GQC 的 NumPy CPU 解释器，计时含调试快照。保存的脚本、逐行结果与源数据下载成本足以区分代数节点共享、参考协议差异、量化求解缺失。[分量与校验回执](fetch.json) · [初始数据清点](../../assets/ani-v1-slice.json)
