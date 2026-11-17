# n2 与 GenerativeQC 使用说明

核对日期：2026-11-18。来源为本机 xtbflow 项目说明、实际适配器、2026-11-14 的计算技能记录及本次服务器只读检查。

## 连接与网络

本机执行 `ssh n2`，实际主机返回 `node2`。现有 SSH 配置使用端口 22，未观察到 ProxyJump、ProxyCommand 或端口转发配置；复用本机别名即可，不复制私钥或凭据到项目。

本次在 n2 用 Python urllib 访问 `https://github.com` 返回 HTTP 200，未观察到常见 HTTP/HTTPS/ALL_PROXY 环境变量。n2 没有 curl，也未找到 rg；网络检查可使用 Python，远端文件搜索用 grep/find。Git 版本为 2.34.1。

HTTPS 首页可达不等于服务器已经具有本项目 GitHub SSH 仓库权限。需要拉取时单独核对 `git ls-remote git@github.com:jinzhezenggroup/vibedataset.git`；也可从本地传送已记录提交的代码快照。不要假设远端 `~/xtbflow` 本身是 Git 仓库。

## 已确认环境

- Slurm 分区 `main` 可用，节点 GRES 为 `gpu:pro6000:4`；单作业按需要申请，例如一张卡 `gpu:pro6000:1`。本次检查时当前用户队列为空，不代表资源始终空闲。
- `~/.config/n2-qc/runtime.env` 已存在，提供 GQC 解释器、OpenBLAS 目录和构建身份。
- `GQC_PYTHON` 返回 Python 3.11.17，generativeqc 包存在，OpenBLAS 目录存在。
- 配置声明源码 SHA：`2bf3fd98da9c6cfba46ca83345e63e1d934e4780`。
- 本次实际计算的 `libgenerativeqc.so` SHA-256：`67bc98a4549fe8854ed6ae65791c824024bd77a9e8e498c6891dea3b8de670c4`，与历史验证一致。
- 历史构建为 CUDA 12.9 / sm_120，使用 RTX PRO 6000 Blackwell；本次未重新运行 GPU 计算或验证 GPU 型号。

`xtbflow` 是 Python 3.10 的数据处理/RDKit 环境；GQC 使用基于 `xtbflow-qc` 的独立 Python 3.11 venv。激活 Conda 后仍须调用 `$GQC_PYTHON`。

## 作业环境模板

下列片段放在 n2 的 Slurm 作业内。执行目录、输入、输出、驱动参数需按本项目实际任务填写；当前尚未创建计算驱动。

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate xtbflow-qc
source ~/.config/n2-qc/runtime.env
export LD_LIBRARY_PATH="$GQC_OPENBLAS_DIR:$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export OPENBLAS_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export MKL_NUM_THREADS="$SLURM_CPUS_PER_TASK"
# cd 到按本项目提交建立的独立执行目录
# "$GQC_PYTHON" <本项目驱动> <显式输入与输出参数>
```

小探针的资源示例：`srun --partition=main --gres=gpu:pro6000:1 --nodes=1 --ntasks=1 --cpus-per-task=4 --mem=16G --time=00:10:00`。正式运行使用有限时长的 sbatch，保存 `%j` 日志和作业最终退出状态。所有 GPU 探针也在 Slurm 内执行。

不能只激活 Conda 后运行默认 python。已有启动失败曾由缺少 `libscipy_openblas.so` 引起，解决方法是加入已有 LP64 OpenBLAS 目录，无须重新编译。

## GQC 原生 API

下面是调用片段，symbols、coordinates_angstrom、charge、multiplicity 均须来自明确的输入。

```python
from generativeqc import Calculator

BOHR_ANGSTROM = 0.529177210903
calc = Calculator(
    method="b3lyp-rks", basis="def2-svp", device="cuda",
    precision="fp64", basis_representation="spherical",
    density_fitting="none", max_iterations=150,
    energy_tolerance=1e-10, density_tolerance=1e-7,
)
atoms_bohr = [(s, tuple(v / BOHR_ANGSTROM for v in xyz))
              for s, xyz in zip(symbols, coordinates_angstrom)]
result = calc.singlepoint(atoms_bohr, charge=charge,
                          multiplicity=multiplicity,
                          properties=("energy", "forces"))
```

原生坐标为 Bohr、能量为 Hartree、力为 Hartree/Bohr。转换为 Hartree/Å 时力除以 `BOHR_ANGSTROM`；优化器若以 Bohr 工作，梯度为负力。检查 `converged`、`executed_backend` 和输出有限性；跨下一次原生调用保存数组时先复制。

## 已知科学限制

以下是历史同一动态库的验证结论，本次未重跑：

- CUDA B3LYP/def2-SVP、spherical、FP64、无 density fitting，在若干小型中性单重态有机体系上通过能量/有限差分力/PySCF 对照，可作为新项目小规模验证的起点。
- CUDA LDA/PBE/PBE0/r2SCAN 的历史力测试失败；CUDA M06-2X/def2-SVP 也有显著力错误。能量通过或 capabilities 声称支持 forces，均不能代替力验证。
- CUDA def2-TZVP 在已测分子上因梯度积分仅支持 s/p/d 而报错。
- GQC 原生 Hessian/IRC 尚未由上述力验证覆盖。历史频率验证使用 CPU PySCF，不能标为 GQC 频率结果。
- 新元素、电荷、自旋、方法、基组或新构建均需重新选择适合的验证样本，不将历史通过外推为通用准确性。

## 后续可参考的本地资料

- `~/xtbflow/AGENTS.md`、`docs/ENVIRONMENT_N2.md`、`docs/CODEX_TOOL_MEMORY.md`
- `~/xtbflow/src/xtbflow/calculators/generativeqc.py`
- `~/xtbflow/docs/GENERATIVEQC_BRIDGE.md`（较早的按方法力诊断）
- `~/xtbflow/.codex-worktrees/gqc-tautomer-20261114/scripts/gqc_tautomer_pilot.py`
- 同一 worktree 的 `docs/evidence/gqc_tautomer_20261114/RESULTS_ZH.md`
- `~/xtbflow/.codex-worktrees/qc-campaign-20261114/docs/research/QC_CAMPAIGN_20261114.md`

本次仅检查连接、网络、文件和软件身份，没有提交计算作业、安装软件或修改 xtbflow。
