#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G
#SBATCH --time=00:10:00
set -eu
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
unset PYTHONPATH
"${GPU4PYSCF_ENV:?}/bin/python" refine_raman_modes.py --protocol protocol.json --plan raman-refinement.json \
  --gpu-run "${1:?path to GPU Hessian run}" --out "refinement-$SLURM_JOB_ID"
