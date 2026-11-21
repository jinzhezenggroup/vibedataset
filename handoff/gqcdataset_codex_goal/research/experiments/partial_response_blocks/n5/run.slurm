#!/usr/bin/env bash
#SBATCH --partition=main
#SBATCH --job-name=plan004-blocks
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --ntasks=1
set -euo pipefail
project_dir=$SLURM_SUBMIT_DIR
cd "$project_dir"
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export PATH="$project_dir/bin:$PATH"
export GENERATIVEQC_JIT_SCCACHE_ROOT="$HOME/vibedataset/sc-$SLURM_JOB_ID"
export CUDA_VISIBLE_DEVICES=""
python_bin="$HOME/vibedataset/envs/gqc-2bf3fd98-cp313/bin/python"
srun --ntasks=1 --cpus-per-task=1 "$python_bin" driver/independent.py --project "$project_dir" --out "job-$SLURM_JOB_ID"
