#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=18G
#SBATCH --time=00:50:00
set -euo pipefail
unset PYTHONPATH
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
py="$GPU4PYSCF_ENV/bin/python"
out="$PWD/frontier-$SLURM_JOB_ID"
mkdir "$out"
printf '%s\n' "$PROJECT_SHA" > "$out/project-commit"
sha256sum *.py protocol.json manifest.json raw-C.jsonl certificates.json.gz > "$out/input-sha256"
for mode in cold planned; do
    "$py" run_response_frontier.py --manifest manifest.json --protocol protocol.json --source raw-C.jsonl \
        --certificates certificates.json.gz --mode "$mode" --out "$out/$mode"
done
date -u +%FT%TZ > "$out/finished"
