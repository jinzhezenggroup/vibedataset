# CP-001 结果

在 H₂ 的两份固定几何上，同身份 checkpoint 获准导入后，GQC 仍用目标哈密顿量求解。源密度满足电子数和占据约束，只说明它可以作初猜。这个区别在篡改源诊断的对照中直接可见。[预登记](../checkpoint_probe_protocol.md) · [第二次运行的原始数值和文件校验和](job-5382.json)

| 路径 | 核间距（Bohr） | 目标能量（Hartree） | SCF 迭代 | Fock 构建 |
|---|---:|---:|---:|---:|
| 单体系冷启动 | 1.4 | −1.116714325176 | 2 | 接口未报 |
| 同身份、原收敛密度 | 1.4 | −1.116714325176 | 2 | 3 |
| 同身份、非驻定密度，源能量写为 −100 | 1.4 | −1.116714325176 | 8 | 10 |
| 单体系冷启动 | 1.6 | −1.103140970811 | 2 | 接口未报 |
| 改变几何，显式允许热启动 | 1.6 | −1.103140970811 | 2 | 3 |

所有表中 GQC 结果均为已核验动态库的 CUDA RHF/STO-3G 中性单重态、球谐、FP64、direct 解。两次同身份导入均先返回 `pending_execute`。电子数减半后，即使元数据和文件校验都自洽，原生层仍以 `electron_count` 拒绝，拒绝前后重新导出的已有状态逐字节相同。默认几何不匹配和更换基组也被拒绝。两几何冷启动对 CPU PySCF 2.14.0 的最大能量差为 3.27×10⁻¹⁰ Hartree，最大笛卡尔力差为 1.28×10⁻⁹ Hartree/Bohr 以内。两步长中心差分的最大投影力误差为 7.26×10⁻⁷ Hartree/Bohr 以内。每个判断对应的输入、容差与观察值均可复查。[配置](../../../../../configs/checkpoint_probe.json) · [逐操作日志](job-5382-operations.jsonl.gz)

## 执行与成本

| 尝试 | Slurm 终态 | 程序时间 | GQC 求解 | PySCF SCF／梯度 | 观察范围 |
|---|---|---:|---:|---:|---|
| 传输目录失败 | 未提交 | 未计时 | 0 | 0／0 | scp 在调用 sbatch 前退出 |
| 5381 | COMPLETED，0:0，4 秒 | 3.310 秒 | 15 | 2／2 | 核对指定库文件，未测实际加载对象 |
| 5382 | COMPLETED，0:0，5 秒 | 4.389 秒 | 15 | 2／2 | 加载对象与指定文件 samefile，库哈希及 7 个 Python 模块均匹配 |

两个作业各申请 1 张 GPU、4 个 CPU、16 GiB，各含 6 次 prepare、3 次保存、2 次资产变换和 7 次导入，其中 3 次按预期拒绝。5382 另记录 1 次库加载。日志中每个 started 操作都有对应终态，两个作业各通过 36 项检查。输入与科学阈值相同，第二次运行用于补足库身份。Slurm 控制器保留了终态，集群关闭了 sacct 存储，实际 GPU 忙时、峰值内存和能耗未知。这组时间包含验证和反例，不能用来估计数据集加速。[传输失败回执](03e7ffaefdb8-checkpoint-20261117T181538Z-submission.json) · [5381](job-5381.json) · [5381 操作日志](job-5381-operations.jsonl.gz) · [5382](job-5382.json)

## 复现

在仓库根目录运行下面命令。n2 的既有运行环境见根目录 docs/N2_EXECUTION_CONTRACT.md。路径按提交和时间隔离，重复运行会产生新的 Slurm 作业。原运行目录及提交、传输、原始文件的 SHA-256 见随附回执。两个远程目录中的 14 个日志、环境或资产文件分别与取回副本校验过，输入驱动和配置与各自提交的 blob 字节一致。

```bash
set -euo pipefail
cp_sha=cfdc7ebcb83360d28db4a4c35b571794c0a34a7f
cp_run="vibedataset/runs/${cp_sha:0:12}-checkpoint-$(date -u +%Y%m%dT%H%M%SZ)"
cp_stage=$(mktemp -d)
git archive "$cp_sha" scripts/probe_gqc_checkpoint.py scripts/run_checkpoint_probe.slurm \
  configs/checkpoint_probe.json | tar -x -C "$cp_stage"
printf '%s\n' "$cp_sha" > "$cp_stage/PROJECT_COMMIT"
(cd "$cp_stage" && sha256sum scripts/* configs/* PROJECT_COMMIT > SHA256SUMS)
ssh n2 'sinfo -p main && squeue --me'
ssh n2 "mkdir -p vibedataset/runs && mkdir '$cp_run'"
scp -r "$cp_stage"/{scripts,configs,PROJECT_COMMIT,SHA256SUMS} "n2:$cp_run/"
ssh n2 "cd '$cp_run' && sbatch --parsable --output=slurm-%j.out --error=slurm-%j.err scripts/run_checkpoint_probe.slurm"
```

对返回的作业号查看 `scontrol show job` 及该目录 `outputs/job-<id>/run.json`、`checks.json` 和 `operations.jsonl`。源声明与实际库的对应来自部署记录，未从源码重建该库。科学结论限于两份测试几何的能量和力；极化率、Hessian、开放壳层及其他构建仍需各自的验证。
