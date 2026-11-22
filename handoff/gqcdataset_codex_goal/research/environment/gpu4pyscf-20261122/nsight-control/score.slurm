#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:08:00
set -eu
unset PYTHONPATH
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
src=${1:?matrix output directory}
out="score-$SLURM_JOB_ID"
mkdir "$out"
for state in cold warm; do
  mkdir "$out/$state"
  for arm in A B C D; do
    cp "$src/$arm/$state/producer/raw.jsonl" "$out/$state/raw-$arm.jsonl"
  done
  "$GPU4PYSCF_ENV/bin/python" score_gpu4pyscf_4arm.py --manifest manifest.json --raw-dir "$out/$state" --out "$out/$state.json"
done
