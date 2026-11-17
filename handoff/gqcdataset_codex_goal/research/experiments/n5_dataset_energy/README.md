# N5-DS-001 的新能量标签

n5 在 QCFractal 固定快照的 13 条单点输入上补出了 13 个合格的 RHF 总能量标签。它们对应 5 个精确的量化目标。用 `source_path` 与源归档联结，读取 CSV 的 `gqc_rhf_sto3g_direct_fp64_total_energy_hartree` 列。完整记录含有序核、精确坐标、基组及电子态身份、源状态、全部执行路径和逐行独立对照。[可直接联结的 CSV](labels.csv) · [科学身份和逐行数值](labels.json) · [原始输入清单](protocol.json)

| 分子 | 源记录数 | 新总能量（Hartree，表中显示至 12 位小数） |
|---|---:|---:|
| H₂O | 6 | −74.963023162664 |
| C₆H₆ | 4 | −227.890603485051 |
| C₂H₅F | 1 | −175.750706500210 |
| H₂ | 1 | −1.116714325176 |
| H₂O₂ | 1 | −148.748994849063 |

这批 QCFractal 测试记录含同一几何的不同源协议。水的两条原始失败记录分别因源基组查找失败和源 SCF 未收敛而缺少结果。新列依据其完整输入几何和新协议求解，保留两项原错误及其来源。源文件中的 DFT、UFF 能量、梯度、Hessian 等继续按其原定义解释。[资产来源与字段说明](../../DATASET_ASSETS.md)

## 求解工作与精度

| 实际执行路径 | GQC execute 次数 | 物理体系求解数 | SCF 迭代 | Fock 构建 | 本次路径耗时（秒） |
|---|---:|---:|---:|---:|---:|
| 逐行冷启动 | 13 | 13 | 120 | 131 | 1.867 |
| 普通字典去重，逐个唯一目标冷启动 | 5 | 5 | 47 | 50 | 0.387 |
| 相同键去重，一次原生 GQC 批处理 | 1 | 5 | 47 | 50 | 0.355 |

普通字典已省去 8 个重复体系求解和 81 次 Fock 构建。把 5 个唯一目标放进一个原生批次后，入口从 5 次减到 1 次，Fock 构建数与字典相同。重复来自同一新协议下完全相同的几何、基组/态和计算控制；这份测试夹具的重复率不能直接用于估算其他数据集的节省比例。

三条 GQC 路径每行两两比较，最大差为 1.71×10⁻¹³ Hartree 以内。用 GQC 基组包内的指数和系数，在每个唯一几何独立完成 CPU PySCF 2.14.0 conventional RHF 计算；三条 GQC 路径对参考的最大差为 1.91×10⁻¹² Hartree 以内。全部 13 行满足预登记的 2×10⁻⁹ 和 2×10⁻⁸ Hartree 容差。未经四舍五入的能量、数值差与所有 5 个参考值可在 JSON 中重查。[协议](PROTOCOL.md) · [按策略统计与参考数值](result.json)

Slurm 作业 2045 在 n5 的 RTX 5090 上以 COMPLETED、0:0 结束，分配 1 GPU、4 CPU、16 GiB 共 5 秒；驱动进程壁钟 5.02 秒。验证本身实际运行 19 次 GQC execute，共请求 23 个体系，且进行了 5 次独立 PySCF 求解。分项另包括读取/解压 0.007 秒、运行库与科学身份核验 1.159 秒、CPU 参考 0.243 秒、输入及脚本传输 1.631 秒。沿用已建的 n5 环境，其一次性成本在环境报告中。三条路径按预定顺序各运行一次，时间含首次运行和缓存状态影响。44 个日志操作均有起止事件。集群关闭 sacct，实际 GPU 忙时、峰值内存与能耗未知。[调度与哈希](job-2045.json) · [原始操作日志](operations.jsonl.gz) · [环境及一次性部署成本](../../environment/n5-20261118/deployment.json)

## 复现

从项目根目录用 bash 运行。需要已完成源码接管的 QCFractal 固定 checkout、n5 的项目环境及现有 SSH 别名。新作业使用独立目录。输入文件在 Slurm 作业内再次对预登记的长度和 SHA-256 校验。

```bash
set -euo pipefail
project_sha=6ab9a0ae6a474ec20077df93c55aa3543ebb426b
upstream_sha=4ec1ed623f82536076c069dd65a4eb132969d9ed
study=handoff/gqcdataset_codex_goal/research/experiments/n5_dataset_energy/protocol.json
stage=$(mktemp -d)
mkdir "$stage/inputs"
git archive "$project_sha" scripts/activate_n5_gqc.sh scripts/probe_gqc_checkpoint.py \
  scripts/probe_n5_dataset_energy.py scripts/run_n5_dataset_energy.slurm \
  configs/checkpoint_probe.json "$study" | tar -xf - -C "$stage"
mapfile -t fixtures < <(jq -r '.input_manifest[].path' "$stage/$study")
git -C _references/qcfractal archive "$upstream_sha" "${fixtures[@]}" | tar -xf - -C "$stage/inputs"
printf '%s\n' "$project_sha" > "$stage/PROJECT_COMMIT"
(cd "$stage" && sha256sum PROJECT_COMMIT scripts/* configs/* "$study" \
  inputs/qcarchivetesting/qcarchivetesting/qcschema_v1_data/*.xz > SHA256SUMS)
run="vibedataset/runs/${project_sha:0:12}-dataset-$(date -u +%Y%m%dT%H%M%SZ)"
ssh n5 'sinfo -N -p main && squeue --me'
ssh n5 "mkdir '$run'"
tar -C "$stage" -cf - . | ssh n5 "tar -xf - -C '$run'"
ssh n5 "cd '$run' && sbatch --parsable --mail-type=NONE --output=slurm-%j.out --error=slurm-%j.err scripts/run_n5_dataset_energy.slurm"
```

用作业号查看 `scontrol show job` 和 `outputs/job-<id>/{labels.json,result.json,operations.jsonl}`。CSV 是核验过的 JSON 结果的扁平投影，文件路径取自 protocol.json，写出的每个键和二进制浮点值均从 CSV 回读核对。普通字典去重是此试验的强基线。这里验证了目标身份判定和原生批处理在这 13 条记录中的作用；含不同几何、态分支或实际基组参数的工作量另行实测。
