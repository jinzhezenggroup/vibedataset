#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=00:30:00
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
set -euo pipefail
source ~/miniconda3/etc/profile.d/conda.sh
conda activate xtbflow-qc
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
cd "$HOME/vibedataset/runs/gpu4pyscf-v1.9.2-build-20261122"
wheel-venv/bin/python run_prepared_gpu4pyscf_processes.py \
  --manifest attribution-manifest.json \
  --molecules qm9-000009 qm9-000011 qm9-000017 \
  --out prepared-runtime/process-runtime.json
