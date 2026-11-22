#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:15:00
set -eu
unset PYTHONPATH
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
"$GPU4PYSCF_ENV/bin/python" run_shared_spectroscopy.py --protocol protocol.json --mode shared --seal-response --out "cartesian-$SLURM_JOB_ID"
