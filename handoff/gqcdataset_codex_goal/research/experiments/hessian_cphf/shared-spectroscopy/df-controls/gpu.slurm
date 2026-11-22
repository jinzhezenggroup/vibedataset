#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=14G
#SBATCH --time=00:20:00
set -eu
unset PYTHONPATH
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1
"$GPU4PYSCF_ENV/bin/python" run_density_fitted_derivatives.py gpu --protocol protocol.json --out "df-$SLURM_JOB_ID"
