#!/usr/bin/env bash
#SBATCH --job-name=vibedataset-energy
#SBATCH --partition=main
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --gres=gpu:5090:1
#SBATCH --time=00:10:00
#SBATCH --mail-type=NONE
set -euo pipefail
sha256sum -c SHA256SUMS
source scripts/activate_n5_gqc.sh
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export OPENBLAS_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export MKL_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export PYTHONDONTWRITEBYTECODE=1
VIBEDATASET_CODE_SHA=$(cat PROJECT_COMMIT)
export VIBEDATASET_CODE_SHA
nvidia-smi --query-gpu=name,compute_cap,driver_version,memory.total --format=csv,noheader
/usr/bin/time -p "$GQC_PYTHON" scripts/probe_n5_dataset_energy.py \
  --study handoff/gqcdataset_codex_goal/research/experiments/n5_dataset_energy/protocol.json \
  --inputs inputs --out "outputs/job-$SLURM_JOB_ID"
