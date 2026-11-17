#!/usr/bin/env bash
#SBATCH --job-name=vibedataset-cp-n5
#SBATCH --partition=main
#SBATCH --gres=gpu:5090:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:10:00
#SBATCH --mail-type=NONE
set -euo pipefail
sha256sum -c SHA256SUMS
source scripts/activate_n5_gqc.sh
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export OPENBLAS_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export MKL_NUM_THREADS="$SLURM_CPUS_PER_TASK"
VIBEDATASET_CODE_SHA=$(cat PROJECT_COMMIT)
export VIBEDATASET_CODE_SHA
nvidia-smi --query-gpu=name,compute_cap,driver_version,memory.total --format=csv,noheader
"$GQC_PYTHON" scripts/probe_gqc_checkpoint.py --config configs/checkpoint_probe.json \
  --out "outputs/job-$SLURM_JOB_ID"
"$GQC_PYTHON" scripts/probe_n5_archive.py --config configs/checkpoint_probe.json \
  --local-probe "outputs/job-$SLURM_JOB_ID" --source-report inputs/n2-job-5382.json \
  --checkpoint inputs/n2-source.vqcp --out "outputs/cross-$SLURM_JOB_ID"
