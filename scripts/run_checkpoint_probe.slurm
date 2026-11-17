#!/usr/bin/env bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:10:00
set -euo pipefail
source ~/miniconda3/etc/profile.d/conda.sh
conda activate xtbflow-qc
source ~/.config/n2-qc/runtime.env
export LD_LIBRARY_PATH="$GQC_OPENBLAS_DIR:$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export OPENBLAS_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export MKL_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export PYTHONDONTWRITEBYTECODE=1
export VIBEDATASET_CODE_SHA="$(cat PROJECT_COMMIT)"
sha256sum -c SHA256SUMS
"$GQC_PYTHON" scripts/probe_gqc_checkpoint.py \
  --config configs/checkpoint_probe.json --out "outputs/job-${SLURM_JOB_ID}"
