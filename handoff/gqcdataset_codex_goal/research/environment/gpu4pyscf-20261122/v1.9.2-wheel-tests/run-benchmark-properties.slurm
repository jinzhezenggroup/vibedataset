#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
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
$VENV -m pip install --no-deps pytest_benchmark-5.3.1-py3-none-any.whl
mkdir -p tag-tests/gpu4pyscf/tests
cp tag-tests/gpu4pyscf/tests/../properties/tests/../../tests/test_benchmark_properties.py tag-tests/gpu4pyscf/tests/test_benchmark_properties.py 2>/dev/null || true
cp 020_Vitamin_C.xyz tag-tests/gpu4pyscf/tests/020_Vitamin_C.xyz
$VENV -m pytest -q tag-tests/gpu4pyscf/tests/test_benchmark_properties.py --benchmark-disable -m "not slow and not high_memory" --maxfail=1
