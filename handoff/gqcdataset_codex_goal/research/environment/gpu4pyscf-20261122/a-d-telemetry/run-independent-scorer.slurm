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
mkdir -p telemetry-score/input
for arm in A B C D; do
  cp "a-d-telemetry/$arm/raw.jsonl" "telemetry-score/input/raw-$arm.jsonl"
done
wheel-venv/bin/python score_gpu4pyscf_4arm.py \
  --manifest attribution-manifest.json \
  --raw-dir telemetry-score/input \
  --out telemetry-score/score.json \
  --target-tol 1e-5 \
  --image-tol 1e-5 \
  --residual-tol 1e-5
