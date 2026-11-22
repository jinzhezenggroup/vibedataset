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
MODE="${MODE:?MODE must be serial or async_streams}"
OUT="$PWD/prepared-runtime/$MODE.json"
mkdir -p "$PWD/prepared-runtime"
wheel-venv/bin/python run_prepared_gpu4pyscf_async.py \
  --manifest attribution-manifest.json \
  --molecules qm9-000009 qm9-000011 qm9-000017 \
  --mode "$MODE" \
  --workers 2 \
  --out "$OUT"
