# QM9 独立队列的 RHF 参考态

完整 QM9 归档中的 133,885 个数值 ID 均出现一次。按预登记规则有 17 个合格候选，8 个预定分层中 6 个有成员。n5 对 6 个代表执行了原生 GQC CUDA 冷启动 RHF，保存了 4 个经过独立核验、可供 GQC 响应编译器读取的闭壳层参考态。其余 2 个代表保留在运行结果和下游分母中。[选样和门槛](PROTOCOL.md) · [全部候选 ID、来源及坐标](cohort.json) · [逐成员结果与资产清单](index.json)

## 源记录和筛选

发布包为 Figshare collection 978904 v5 中的成员 1057646 v2，成员 DOI 为 `10.6084/m9.figshare.978904_D12`。官方 API 给出的文件 ID 3195389，文件名 `dsgdb9nsd.xyz.tar.bz2`。测得 86,144,227 字节，MD5 `ad1ebd51ee7f5b3a6e32e974e5d54012` 与发布者一致，SHA-256 为 `3a63848ac80691bdb8d41834b575afad345b9300d7a2db0c38adb7f6eaa8360c`。数据、README 和质量标志清单的正式发布许可均为 CC0。作者 README 将每原子 XYZ 坐标标为 Å；新计算保留原子次序与坐标系，并换算为 Bohr。[官方发布成员 v2](https://api.figshare.com/v2/articles/1057646/versions/2) · [README v1](https://api.figshare.com/v2/articles/1057641/versions/1) · [作者的几何一致性清单 v1](https://api.figshare.com/v2/articles/1057644/versions/1)

逐个文件读取原子数和符号以选择 1–2 个或恰为 3 个非氢原子的分子，在两组内依 F、O、N、CH 优先级互斥分类。两组含 F 类都为空。该范围外有 133,868 个分子。遍历中没有解析失败，17 个合格候选均不在作者标出的 3,054 个几何识别不一致 ID 内。分层人数、选中的最小 ID、压缩包内成员名与字节 SHA 均在 cohort.json 中；其余源 DFT 数据未参与选样和计算。[原始研究](https://www.nature.com/articles/sdata201422)

| 非氢数／元素类别 | 候选数 | 选中 ID | AO 数 | n5 GQC 总能量（Eh） | 可供响应使用的状态 |
|---|---:|---:|---:|---:|---|
| 1–2 / F | 0 | — | — | — | 空层 |
| 1–2 / O | 3 | 3 | 7 | −74.963808669284 | 通过 |
| 1–2 / N | 2 | 2 | 8 | −55.454741646953 | 通过 |
| 1–2 / CH | 3 | 1 | 9 | −39.726596858839 | 通过 |
| 3 / F | 0 | — | — | — | 空层 |
| 3 / O | 5 | 11 | 19 | −150.944577886833 | 独立 PySCF 的第 100 次迭代仍未达预登记收敛门槛 |
| 3 / N | 1 | 10 | 18 | −130.270808375973 | 通过 |
| 3 / CH | 3 | 9 | 19 | −114.445379683388 | PySCF 内部稳定性通过，外部稳定性检查失败 |

## 状态、质量与成本

GQC 固定 CUDA 构建在 RTX 5090 上以同一批次求解了 6 个中性单重态 RHF/STO-3G 气相全电子能量。CPU PySCF 2.14.0 用 GQC 基组包的逐元素实际指数和系数独立求同一目标，在该态生成 S/h/F/C/轨道能/占据及完整四指标 AO ERI。记录的是固定分子结构上的 RHF 结果。参考态存档生产后端为 PySCF。GQC 运行版源码另有 `export_rhf` 工具，从原生密度生成主机上的 canonical snapshot；该实现对超过 12 个 AO 的输入显式拒绝，也会重新计算其所需物理 Fock。本次没有调用该导出工具。[运行版本导出实现](https://github.com/jinzhezenggroup/generativeqc/blob/2bf3fd98da9c6cfba46ca83345e63e1d934e4780/tools/generativeqc_posthf/export.py#L31)

4 个通过项对独立能量的最大差为 4.55×10⁻¹³ Eh 以内，真实 Fock 从 h/ERI/密度重建的最大分量差为 8.89×10⁻¹⁵ Eh 以内。除此之外核验 CᵀSC、电子数、FDS−SDF、能隙，以及 PySCF RHF 内/外局部稳定性（Davidson 3 根，求解容差 1e−7）。即使某个能量在两后端间接近，也不能替代驻点或分支检验。ID 11 的未收敛能量保留，ID 9 的外部不稳定单列。本地用当前固定 GQC 的 `fixture_snapshot` 和 PySCF 逐个重建状态身份、S 与 AO ERI，4 份身份全部匹配，S 最大差 5.56×10⁻¹⁷ 以内，ERI 最大差 0。[状态诊断与所有能量](index.json) · [调度、文件校验与消费端复核](job-2046.json)

| 项目 | 实耗或计数 |
|---|---:|
| 主压缩包获取与字节校验 | 20.848 秒 |
| 缓存文件校验／全包解压和分层 | 0.202／26.600 秒 |
| n5 GQC 批次／物理体系 | 1／6 |
| GQC SCF 迭代／Fock 构建 | 72／77 |
| PySCF SCF 尝试／迭代 | 6／362，含失败 |
| PySCF 内/外稳定性成对执行、完整积分/态生成 | 各 5 次 |
| 产出经核验的 JSON + NPZ | 4 对，共 602,811 字节 |
| 4 组浮点数组的未压缩有效载荷 | 961,520 字节 |
| n5 GQC 批次墙钟／全部资产生产计时 | 1.414／4.450 秒 |
| 启动 Python 至退出的墙钟／Slurm 作业时间 | 5.46／6 秒，1 GPU、4 CPU、16 GiB |

每份存档的实际耗时与字节数单列在 index.json 的对应行中。n5 作业 2046 在全部代表处理后返回 1:0，因为两个成员未通过预登记门槛。33 个操作都有开始/结束日志。逻辑失败包括求解器返回数值后的收敛与稳定性检查；因此操作返回并不充分证明资格。原始输入、结果、部分发布文件和调度输出保留在 n5 执行目录。伴随元数据的网络时间及 GPU 实际忙时、峰值内存、能耗均未测量。[逐操作日志](operations.jsonl.gz) · [n5 部署及一次性成本](../../environment/n5-20261118/deployment.json)

## 直接读取或重建

在本机仓库根目录，完整资产已随此研究记录提交。读取 `index.json` 的 8 行，只对 `status == "verified"` 的行加载其 `metadata_file` 和 `array_file`。对完整分母的报告应包括其他行。元数据的 `inputs` 保存逐原子、逐壳的指数和系数，波函数以单位自重叠的实球谐 AO 和电子空间占据 2/0 表示，ERI 为 chemists 顺序。用 `numpy.load(..., allow_pickle=False)` 读取 conventional_S、conventional_h、conventional_F、conventional_C、conventional_eps、conventional_occ 和 ao。每数组内容、元数据及完整文件均有 SHA。下游可调用 GQC 工具的 `fixture_snapshot(meta, arrays)`；它会校验轨道和态依赖。[该固定版本的构造函数](https://github.com/jinzhezenggroup/generativeqc/blob/2791504cc238fe83d328fc1718080642b288222a/tools/generativeqc_posthf/fixtures.py)

重新验证官方数据与队列，使用 Python 3.10+ 和本机磁盘缓存。选择名单可通过 `strata`、文件散列和分母比较，日期与耗时为新观测。

```bash
python3 scripts/select_qm9_assets.py --cache .work/qm9_source --out .work/qm9_response_assets/cohort.json
```

复现 n5 计算时使用已登记队列。下列命令只将执行所需的、来自已锁定完整源码树的测试辅助模块复制到该作业的隔离目录。

```bash
set -euo pipefail
project_sha=e04a1e94dc8483c00ecc1c8b06c96cef65c5b654
gqc_sha=2791504cc238fe83d328fc1718080642b288222a
cohort=handoff/gqcdataset_codex_goal/research/experiments/qm9_response_assets/cohort.json
stage=$(mktemp -d)
mkdir "$stage/upstream"
git archive "$project_sha" scripts/activate_n5_gqc.sh scripts/probe_gqc_checkpoint.py \
  scripts/build_qm9_assets.py scripts/run_qm9_assets.slurm configs/checkpoint_probe.json "$cohort" | tar -xf - -C "$stage"
git -C _references/gqc archive "$gqc_sha" LICENSE tools/__init__.py tools/generate_validation_references.py \
  tools/generativeqc_validation/{__init__,fixtures}.py \
  tools/generativeqc_posthf/{__init__,reference,fixtures,conventions}.py | tar -xf - -C "$stage/upstream"
printf '%s\n' "$project_sha" > "$stage/PROJECT_COMMIT"
(cd "$stage" && sha256sum PROJECT_COMMIT scripts/* configs/* "$cohort" upstream/LICENSE \
  upstream/tools/*.py upstream/tools/*/*.py > SHA256SUMS)
run="vibedataset/runs/${project_sha:0:12}-qm9-$(date -u +%Y%m%dT%H%M%SZ)"
ssh n5 'sinfo -p main && squeue --me'
ssh n5 "mkdir '$run'"
tar -C "$stage" -cf - . | ssh n5 "tar -xf - -C '$run'"
ssh n5 "cd '$run' && sbatch --parsable --mail-type=NONE --output=slurm-%j.out --error=slurm-%j.err scripts/run_qm9_assets.slurm"
```

检查对应 Slurm 作业号，以及 `outputs/job-<id>/index.json`、每个通过项的存档文件和 `operations.jsonl`。执行顺序、独立验证成本、失败和原始文件字节都可用本目录的回执核对。
