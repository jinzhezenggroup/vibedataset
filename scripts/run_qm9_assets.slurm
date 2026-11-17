#!/usr/bin/env bash
#SBATCH --job-name=vibedataset-qm9
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
/usr/bin/time -p "$GQC_PYTHON" scripts/build_qm9_assets.py --config configs/checkpoint_probe.json \
  --helpers upstream --cohort handoff/gqcdataset_codex_goal/research/experiments/qm9_response_assets/cohort.json \
  --out "outputs/job-$SLURM_JOB_ID"
