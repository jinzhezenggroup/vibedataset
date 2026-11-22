#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=03:00:00
set -euo pipefail
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
unset PYTHONPATH
py="$GPU4PYSCF_ENV/bin/python"
site=$("$py" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
out="$PWD/cost-$SLURM_JOB_ID"
mkdir "$out"
sha256sum *.py manifest.json middle-queue.jsonl response-cache.patch > "$out/inputs-sha256"
printf '%s\n' "$PROJECT_SHA" > "$out/project-commit"
date -u +%FT%TZ > "$out/started"
mode=${1:-full}
arms=(A D C B)
extra=()
if [[ $mode == pilot ]]; then arms=(A D); extra=(--pilot); fi
for arm in "${arms[@]}"; do
    start=$(date +%s%N)
    echo "$arm started $start" >> "$out/outer-ledger.txt"
    export CUPY_CACHE_DIR="$out/cache-$arm/cupy" CUDA_CACHE_PATH="$out/cache-$arm/driver"
    mkdir -p "$CUPY_CACHE_DIR" "$CUDA_CACHE_PATH"
    pkg=()
    if [[ $arm == B || $arm == D ]]; then
        dir="$out/patched-$arm";mkdir "$dir"
        cp -a "$site/gpu4pyscf" "$dir/"
        (cd "$dir" && patch --batch -p1 -i "$PWD/../../response-cache.patch" && patch --dry-run -R --batch -p1 -i "$PWD/../../response-cache.patch") > "$out/patch-$arm.log"
        pkg=("PYTHONPATH=$dir")
    fi
    echo "$arm backend-ready $(date +%s%N)" >> "$out/outer-ledger.txt"
    args=(--manifest manifest.json --queue middle-queue.jsonl --arm "$arm" --out "$out/$arm")
    env "${pkg[@]}" "$py" run_middle_full_cost.py produce "${args[@]}" "${extra[@]}" > "$out/produce-$arm.log" 2>&1
    echo "$arm producer-finished $(date +%s%N)" >> "$out/outer-ledger.txt"
    "$py" run_middle_full_cost.py certify "${args[@]}" "${extra[@]}" > "$out/score-$arm.log" 2>&1
    echo "$arm durable-labels $(date +%s%N)" >> "$out/outer-ledger.txt"
done
date -u +%FT%TZ > "$out/finished"
