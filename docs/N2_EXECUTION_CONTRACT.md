# vibedataset 执行约定

## 服务器与运行环境

- 本地目录 `/home/lhshen/vibedataset` 用于开发；真实 GQC/GPU 计算在 `ssh n2`
  连接的 `node2` 执行。SSH 地址、账号、密钥由本机 SSH 配置提供，不复制凭据。
- 2026-11-18 已实测 SSH 成功、Slurm `main` 分区可用，节点配置
  `gpu:pro6000:4`；这是配置数量，不是实时空闲数量。提交前检查 `squeue`/`sinfo`。
- 同日通过远端 Python urllib 实测 GitHub、PyPI HTTPS 均返回 200。
  当前加载环境没有 `curl`，网络探测可用 Python；这不代表所有数据源均可达。
- 每项 GPU 计算经 Slurm，明确 CPU、内存、GPU 数量和有限时长。例如小型探针使用
  `srun --partition=main --gres=gpu:pro6000:1 --nodes=1 --ntasks=1
  --cpus-per-task=4 --mem=16G --time=00:10:00`。不改写 `CUDA_VISIBLE_DEVICES`。
- 复用远端已编译 GQC，不重复安装、升级或编译。在远端作业内加载：

  ```bash
  source ~/miniconda3/etc/profile.d/conda.sh
  conda activate xtbflow-qc
  source ~/.config/n2-qc/runtime.env
  export LD_LIBRARY_PATH="$GQC_OPENBLAS_DIR:$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
  export OPENBLAS_NUM_THREADS="$SLURM_CPUS_PER_TASK"
  export MKL_NUM_THREADS="$SLURM_CPUS_PER_TASK"
  # 在本项目独立执行目录，用 "$GQC_PYTHON" 调用实际驱动。
  ```

- `runtime.env` 仅在 n2 存在，提供 `GQC_PYTHON`、`GQC_OPENBLAS_DIR`、
  `GQC_NATIVE_LIBRARY`、`GQC_SOURCE_SHA`、`GQC_NATIVE_LIBRARY_SHA256`。
  Python 必须使用 `$GQC_PYTHON`，不能混用 `xtbflow` 的 Python 3.10。
  动态库需要现有 `scipy_openblas32` LP64 provider；缺库时先检查 loader 路径。
- 2026-11-18 实测：Python 3.11.17、generativeqc 0.1.0，包导入成功；
  源码声明 SHA `2bf3fd98da9c6cfba46ca83345e63e1d934e4780`；实际原生库 SHA256
  `67bc98a4549fe8854ed6ae65791c824024bd77a9e8e498c6891dea3b8de670c4`。
  本次仅检查连接、调度信息和导入，没有执行新的量化计算。

## GQC API 与验证边界

- API：`from generativeqc import Calculator`；`Calculator(...).singlepoint(
  atoms_bohr, charge=charge, multiplicity=multiplicity, properties=("energy", "forces"))`。
- 原生坐标为 Bohr，能量 Hartree，力 Hartree/Bohr。
  `BOHR_ANGSTROM = 0.529177210903`；Å 坐标除以此常数传入；原生力除以
  此常数得到 Hartree/Å。优化器所需梯度为负力。
- 输入必须显式给出电荷、多重度、坐标单位、方法和基组。检查 `result.converged`、
  `result.executed_backend` 和数值有限性；保留数组时复制，避免后续调用覆盖。
- 此构建有有限范围验证的 GPU 候选协议：`method="b3lyp-rks"`、
  `basis="def2-svp"`、`device="cuda"`、`precision="fp64"`、
  `basis_representation="spherical"`、`density_fitting="none"`，
  `max_iterations=150`、`energy_tolerance=1e-10`、`density_tolerance=1e-7`。
  历史通过范围主要是气相中性单重态小分子，不能直接推广到新分子类别或自旋态。
- 此构建 CUDA PBE/LDA/PBE0/r2SCAN/M06-2X 力曾验证失败；不能用于力标签、
  优化或动力学。def2-TZVP CUDA 力在已测分子上不支持；capabilities 标志不是数值验证。
- 新任务先做有界能量与力验证：至少两个步长的方向有限差分，以及适当的独立后端比较。
  GQC Hessian/频率/IRC 尚未由现有力验证获得资格；若用 PySCF 补做，必须标明后端。

## 项目隔离与可追溯性

- 在 n2 为 vibedataset 建独立执行/输出目录，以提交和运行 ID 区分；不覆盖 xtbflow
  工作树、共享 venv、缓存或历史计算。大型数据和运行产物不提交 Git。
- 记录输入与配置哈希、源码 SHA、实际库哈希、环境、Slurm job ID、调用数、
  耗时、收敛和失败状态。计算前记 started；重试保留原失败及消耗。
- 当前项目尚无计算驱动或数据协议；本文件是运行约定，不代表接入和科学验证已完成。

## 已阅读的复用来源

- `~/xtbflow/docs/GENERATIVEQC_BRIDGE.md` 与 `src/xtbflow/calculators/generativeqc.py`。
  该工作树有未提交修改，不能只用 HEAD SHA 代表这些内容。
- `n2-quantum-chemistry` 技能及 `references/runtime.md`、`qualification.md`。
- xtbflow 提交 `323fd156987322ed7181dd48b4fe514a162f702d` 中的
  `scripts/gqc_tautomer_pilot.py`；续算/参考检查提交
  `aad1b5362883c5c2364acd2eec5c6c1e90ff4d13` 可作为后续驱动参考。
