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
if [[ ${1:-} == counterbalanced ]]; then
    schedule=(cold planned planned cold)
else
    schedule=(cold planned)
fi
for index in "${!schedule[@]}"; do
    mode=${schedule[$index]}
    folder="$out/$mode"
    if (( ${#schedule[@]} == 4 )); then
        folder="$out/rep-$((index / 2 + 1))/$mode"
    fi
    mkdir -p "$(dirname "$folder")"
    if (( ${#schedule[@]} == 4 )); then
        export CUPY_CACHE_DIR="$out/cache-$index/cupy" CUDA_CACHE_PATH="$out/cache-$index/cuda"
        mkdir -p "$CUPY_CACHE_DIR" "$CUDA_CACHE_PATH"
    fi
    start_ns=$(date +%s%N)
    "$py" run_response_frontier.py --manifest manifest.json --protocol protocol.json --source raw-C.jsonl \
        --certificates certificates.json.gz --mode "$mode" --out "$folder"
    end_ns=$(date +%s%N)
    printf '%s %s %s %s\n' "$index" "$mode" "$start_ns" "$end_ns" >> "$out/process-wall-ns.txt"
done
date -u +%FT%TZ > "$out/finished"
