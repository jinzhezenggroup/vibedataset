# n5 的 GQC 环境与跨节点状态恢复

在 n5 的项目目录中，`~/vibedataset/envs/gqc-2bf3fd98-cp313` 是本项目独立的 CPython 3.13.12 venv。GQC 源码部署声明为 `2bf3fd98da9c6cfba46ca83345e63e1d934e4780`，与 n2 CP-001 使用的构建相同。原生库 SHA-256 为 `67bc98a4549fe8854ed6ae65791c824024bd77a9e8e498c6891dea3b8de670c4`。Python 包由原 n2 安装中 1,560 个通过 RECORD 校验的文件重封装，授权与通知文件保留在包内。n5 单独安装了 PySCF 2.14.0、NumPy 2.4.6、LP64 OpenBLAS 和 CUDA 12.9 providers。[安装与执行凭据](../handoff/gqcdataset_codex_goal/research/environment/n5-20261118/)

SSH 别名为 `n5`，Slurm 节点名为 `node5`。2026-11-18 实测 main 分区配置 48 个 CPU、240000 MB 内存和一张 RTX 5090，计算能力为 12.0。系统默认 nvcc 是 12.4，项目的编译器路径指向已安装的 CUDA 12.9.1。使用 Slurm 分配 GPU 并在作业内加载环境。完整环境变量和已验证的作业参数均在仓库脚本中。[激活脚本](../scripts/activate_n5_gqc.sh) · [n5 作业脚本](../scripts/run_n5_checkpoint.slurm)

```bash
ssh n5 'sinfo -N -p main -o "%P %n %t %c %m %G" && squeue --me'
ssh n5
source ~/vibedataset/tools/activate_n5_gqc.sh
"$GQC_PYTHON" -c 'import importlib.metadata as m; print(m.version("generativeqc"), m.version("pyscf"))'
```

## 已验证的计算

Slurm 作业 2044 获得 1 张 RTX 5090、4 个 CPU 和 16 GiB 内存，终态 COMPLETED，退出码 0:0，运行 9 秒。首先在 n5 运行 CP-001 的两份 H₂ 几何、两种有限差分步长和本机 CPU PySCF 2.14.0 对照，36 项检查通过。随后在一个新进程中读入 n2 作业 5382 的 5,439 字节 checkpoint，验证两台节点实际加载的原生库 SHA-256 一致。GQC 导入后仍执行目标求解。[调度、哈希与逐项结果](../handoff/gqcdataset_codex_goal/research/environment/n5-20261118/job-2044.json)

| 项目 | 跨节点恢复结果 |
|---|---|
| 核间距 1.4 Bohr，RHF/STO-3G，FP64，direct，球谐，中性单重态 | −1.11671432517577 Hartree；2 次 SCF 迭代，3 次 Fock 构建，无冷启动回退 |
| 对 n2、n5 各自冷启动的能量差／最大力分量差 | 0 Hartree ／ 9.72×10⁻¹⁷ Hartree/Bohr 以内 |
| 对 n5 同协议 CPU PySCF 的差 | 能量 1.14×10⁻¹⁰ Hartree 以内，力 1.28×10⁻⁹ Hartree/Bohr 以内 |

CP-001 使用 15 次 GQC 求解和 PySCF SCF／梯度各 2 次，3 次预设错误导入均被拒绝。跨节点步骤另调用 1 次 GQC 求解。新增一次性投入包括 n2 CPU 封装约 62 秒、传送 wheel 约 263 秒、n5 科学及 CUDA 依赖安装分别约 8 和 31 秒、安装 GQC wheel 约 3.4 秒。n5 环境逻辑大小约 4.09 GB，安装包另占 0.87 GB。实际 GPU 忙时、峰值内存及能耗未采集。[部署记录](../handoff/gqcdataset_codex_goal/research/environment/n5-20261118/deployment.json) · [n2 封装记录](../handoff/gqcdataset_codex_goal/research/environment/n5-20261118/n2-pack.json)

作业 2044 的最初汇总引用了会被 GQC 原地更新的 Python 诊断字典，求解后把汇总中的导入前状态写成了 executed。导入完成时已经 fsync 的操作日志记录了 exact_restart 和 pending_execute，接下来的独立事件记录了求解。保留原始汇总，以该日志复核导入前状态，并在复现驱动中提前复制了状态值。实际求解、误差和计数均来自原作业。独立新 SSH 会话也已从持久入口加载 GQC、PySCF 和原生库，并执行了项目 venv 下的 CLI 版本查询。[导入与求解日志](../handoff/gqcdataset_codex_goal/research/environment/n5-20261118/job-2044-cross-operations.jsonl.gz) · [原始汇总](../handoff/gqcdataset_codex_goal/research/environment/n5-20261118/job-2044-cross.raw.json)

## 复现已登记作业

在本机仓库根目录执行下列命令。需能访问 n2 原始归档和 n5 的本项目环境。每次提交都会创建新的执行目录。下方使用已修正导入状态转录的 d00e0ff 驱动；原作业提交和输入文件哈希见作业 2044 的证据。

```bash
set -euo pipefail
project_sha=d00e0ff021687bb036db1c08dc0c38932f515cd5
stage=$(mktemp -d)
mkdir "$stage/inputs"
git archive "$project_sha" configs/checkpoint_probe.json scripts/activate_n5_gqc.sh \
  scripts/probe_gqc_checkpoint.py scripts/probe_n5_archive.py scripts/run_n5_checkpoint.slurm | tar -x -C "$stage"
git show "$project_sha:handoff/gqcdataset_codex_goal/research/experiments/checkpoint_probe/job-5382.json" > "$stage/inputs/n2-job-5382.json"
scp n2:vibedataset/runs/cfdc7ebcb833-checkpoint-20261117T182121Z/outputs/job-5382/source.vqcp "$stage/inputs/n2-source.vqcp"
printf '%s\n' "$project_sha" > "$stage/PROJECT_COMMIT"
(cd "$stage" && sha256sum configs/* scripts/* inputs/* PROJECT_COMMIT > SHA256SUMS)
run="vibedataset/runs/${project_sha:0:12}-cross-$(date -u +%Y%m%dT%H%M%SZ)"
ssh n5 "mkdir '$run'"
tar -C "$stage" -cf - . | ssh n5 "tar -xf - -C '$run'"
ssh n5 "cd '$run' && sbatch --parsable --mail-type=NONE --output=slurm-%j.out --error=slurm-%j.err scripts/run_n5_checkpoint.slurm"
```

使用返回的作业号查看 `scontrol show job`，并核对远端执行目录内的 `outputs/job-<id>/run.json`、`outputs/cross-<id>/result.json` 和两个 `operations.jsonl`。集群关闭了 sacct 存储。若 Slurm 控制器已清理作业，则用此处附带的调度回执核对本次运行。

## 重建同一二进制环境

运行材料（包括约 867 MB 的重封装 wheel）位于 n5 的 `~/vibedataset/artifacts/n2-gqc-2bf3fd98/`。大文件留在远端。重封装前逐文件验证了 n2 安装 RECORD 中的 SHA-256 和长度，保留持久化包内 CLI、生成器资源及原生共享库。完整 wheel 的 SHA-256 为 `2f98bb4c1b25706841cf0ae68b8c61b14cc212604dd728001f1b4cc065cbedeb`。原始 n2 包为源码构建后安装，重封装生成了新 wheel 的分发哈希。源码到原始二进制的可复现编译仍待单独验证。[封装程序](../scripts/pack_n5_runtime.py)

下列命令在 n5 上使用新的前缀。uv 使用现有用户安装。按需要将 `VIBEDATASET_N5_ENV` 指向新前缀再加载激活脚本。原包需要重新产生时，将封装脚本传至 n2 并在空目录执行 `source ~/.config/n2-qc/runtime.env`，再运行 `srun -p main -c 2 --mem=4G --time=00:15:00 "$GQC_PYTHON" pack_n5_runtime.py .`，校验传输两端的 wheel 与库。

```bash
set -euo pipefail
n5_prefix="$HOME/vibedataset/envs/gqc-2bf3fd98-rebuild-$(date -u +%Y%m%dT%H%M%SZ)"
n5_wheel="$HOME/vibedataset/artifacts/n2-gqc-2bf3fd98/generativeqc-0.1.0-py3-none-linux_x86_64.whl"
printf '%s  %s\n' 2f98bb4c1b25706841cf0ae68b8c61b14cc212604dd728001f1b4cc065cbedeb "$n5_wheel" | sha256sum -c -
~/.local/bin/uv venv --python ~/miniconda3/bin/python "$n5_prefix"
~/.local/bin/uv pip install --python "$n5_prefix/bin/python" "$n5_wheel" \
  numpy==2.4.6 scipy==1.18.1 h5py==3.16.0 pyscf==2.14.0 scipy-openblas32==0.3.34.0.0 \
  array-api-compat==1.16.0 typing-extensions==4.16.0 sccache==0.16.0 setuptools==84.2.1 \
  nvidia-cublas-cu12==12.9.2.10 nvidia-cusolver-cu12==11.7.5.82 nvidia-cusparse-cu12==12.5.10.65 \
  nvidia-cuda-runtime-cu12==12.9.79 nvidia-nvjitlink-cu12==12.9.86 nvidia-cuda-nvrtc-cu12==12.9.86
~/.local/bin/uv pip check --python "$n5_prefix/bin/python"
export VIBEDATASET_N5_ENV="$n5_prefix"
source ~/vibedataset/tools/activate_n5_gqc.sh
```

## 两次官方 QM9 队列作业

同一持久环境于 2026-11-18 顺序执行 2046 与 2047。首批 6 份 GQC 能量用 72 次 SCF 迭代、77 次 Fock 构建；留出的全部 11 份另用 139/141 次。各作业只有一批 GQC 系统调用，独立 CPU 参考态生产、收敛/稳定性拒绝与存储成本分别登记。两次均处理完所有分子后，因分别 2/3 个独立门槛失败返回 1；没有因这些状态重做上游精度。最终 12 对核验参考态可直接用于本地 GQC 编译的 CPU 响应。留出的 11 份中 8 对占 5,780,168 字节。[2046 与首批](../handoff/gqcdataset_codex_goal/research/experiments/qm9_response_assets/README.md) · [2047 与可下载资产](../handoff/gqcdataset_codex_goal/research/experiments/qm9_extension/README.md)

作业 2048 使用 n5 的 1 个 CPU 核独立复算水分子的部分标量响应，Slurm 成功退出、耗时 5 秒。此作业复用 2046 的水分子状态和持久科学环境，从固定的 GQC 编译器树生成并运行 CPU 核；未占用 GPU。相同精度下，单块合并的 2 RHS 用 20 次 J/K，分开调用用 36 次。[作业、版本和逐次物理调用](../handoff/gqcdataset_codex_goal/research/experiments/partial_response_blocks/n5/README.md)
