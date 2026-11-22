#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
set -euo pipefail
source ~/miniconda3/etc/profile.d/conda.sh
conda activate xtbflow-qc
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export OPENBLAS_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export MKL_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$HOME/vibedataset/runs/gpu4pyscf-v1.9.2-build-20261122"
VENV="$PWD/wheel-venv/bin/python"
"$VENV" - <<'PY'
import hashlib
import importlib.metadata as metadata
import json
import pathlib
import platform
import shutil
import subprocess
import sys

import cupy
import gpu4pyscf
import pyscf

wheel = pathlib.Path("gpu4pyscf_cuda12x-1.9.2-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl")
props = cupy.cuda.runtime.getDeviceProperties(0)
name = props["name"]
if isinstance(name, bytes):
    name = name.decode()
result = {
    "python": sys.version,
    "platform": platform.platform(),
    "gpu4pyscf": metadata.version("gpu4pyscf-cuda12x"),
    "cupy": cupy.__version__,
    "pyscf": pyscf.__version__,
    "device_count": cupy.cuda.runtime.getDeviceCount(),
    "device": name,
    "compute_capability": f"{cupy.cuda.Device(0).compute_capability}",
    "cuda_runtime_version": int(cupy.cuda.runtime.runtimeGetVersion()),
    "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    "wheel_filename": wheel.name,
}
result["nvidia_smi"] = subprocess.run(
    ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
    check=True,
    text=True,
    capture_output=True,
).stdout
nvcc = shutil.which("nvcc") or "/home/lhshen/miniconda3/pkgs/cuda-nvcc-tools-12.9.86-he02047a_2/bin/nvcc"
result["nvcc_path"] = nvcc
result["nvcc"] = subprocess.run([nvcc, "--version"], check=True, text=True, capture_output=True).stdout
print(json.dumps(result, sort_keys=True, indent=2))
PY
