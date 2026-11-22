#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=18G
#SBATCH --time=00:35:00
set -euo pipefail
arms=( "$@" )
[[ ${#arms[@]} -gt 0 ]] || exit 2
tool=${NSYS:?absolute path to the Nsight Systems executable}
envroot=${GPU4PYSCF_ENV:?official wheel environment}
dir="$PWD/trace-$SLURM_JOB_ID"
mkdir "$dir"
for arm in "${arms[@]}"; do
  mkdir "$dir/$arm"
  args=(--arm "$arm" --manifest "$PWD/manifest.json" --source-commit "$PROJECT_SHA")
  pkg=()
  if [[ $arm == B || $arm == D ]]; then
    args+=(--patch "$PWD/response-cache.patch")
    pkg=("PYTHONPATH=${PATCHED_SITE:?isolated B/D backend}")
  fi
  "$tool" --version > "$dir/nsys-version.txt"
  for state in cold warm; do
    out="$dir/$arm/$state"
    mkdir "$out"
    date -u +%FT%TZ > "$out/started"
    env -i HOME="$HOME" USER="$USER" PATH="$envroot/bin:/usr/bin:/bin" LANG=C.UTF-8 \
      CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:?}" OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4 \
      SLURM_JOB_ID="$SLURM_JOB_ID" CUPY_CACHE_DIR="$dir/$arm/cupy-cache" CUDA_CACHE_PATH="$dir/$arm/driver-cache" \
      "${pkg[@]}" "$tool" profile --sample=none --cpuctxsw=none --trace=cuda,nvtx --cuda-memory-usage=true \
      -o "$out/trace" "$envroot/bin/python" trace_gpu4pyscf_requests.py "${args[@]}" --out "$out/producer" \
      > "$out/console.log" 2>&1
    "$tool" export --type sqlite --output "$out/trace.sqlite" "$out/trace.nsys-rep" >> "$out/console.log" 2>&1
    date -u +%FT%TZ > "$out/finished"
  done
done
