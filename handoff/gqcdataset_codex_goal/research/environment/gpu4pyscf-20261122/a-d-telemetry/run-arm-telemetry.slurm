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
ARM="${ARM:?ARM must be A, B, C or D}"
PYTHON="$PWD/wheel-venv/bin/python"
OUT="$PWD/a-d-telemetry/$ARM"
mkdir -p "$OUT"
if [[ "$ARM" == "B" || "$ARM" == "D" ]]; then
  export PYTHONPATH="$PWD/patched-site${PYTHONPATH:+:$PYTHONPATH}"
  "$PYTHON" "$PWD/run_gpu4pyscf_4arm_telemetry.py" \
    --manifest "$PWD/attribution-manifest.json" \
    --arm "$ARM" \
    --out "$OUT" \
    --source-commit "231ad366852259b447abb0cfe1157074b2174707" \
    --gpu4pyscf-source-commit "8536a80c1e03260aab030e108ef1d181a3709057" \
    --patch "$PWD/gpu4pyscf-response-cache.patch"
else
  "$PYTHON" "$PWD/run_gpu4pyscf_4arm_telemetry.py" \
    --manifest "$PWD/attribution-manifest.json" \
    --arm "$ARM" \
    --out "$OUT" \
    --source-commit "231ad366852259b447abb0cfe1157074b2174707" \
    --gpu4pyscf-source-commit "8536a80c1e03260aab030e108ef1d181a3709057"
fi
