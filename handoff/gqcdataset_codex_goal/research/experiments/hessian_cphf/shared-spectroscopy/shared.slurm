#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=20G
#SBATCH --time=00:50:00
set -eu
unset PYTHONPATH
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
out="$PWD/shared-$SLURM_JOB_ID"
mkdir "$out"
sha256sum *.py protocol.json > "$out/input-sha256"
printf '%s\n' "$PROJECT_SHA" > "$out/project-commit"
for mode in serial shared failures; do
    echo "$mode started $(date +%s%N)" >> "$out/process-wall.txt"
    "$GPU4PYSCF_ENV/bin/python" run_shared_spectroscopy.py --mode "$mode" --protocol protocol.json --out "$out/$mode" > "$out/$mode.log" 2>&1
    echo "$mode finished $(date +%s%N)" >> "$out/process-wall.txt"
done
date -u +%FT%TZ > "$out/finished"
