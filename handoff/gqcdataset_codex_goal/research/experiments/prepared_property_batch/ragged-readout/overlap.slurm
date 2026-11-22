#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=18G
#SBATCH --time=00:20:00
set -euo pipefail
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
unset PYTHONPATH
out="$PWD/readout-trace-$SLURM_JOB_ID"
mkdir "$out"
for plan in queued during_solve; do
    mode=async_streams
    extra=()
    if [[ $plan == during_solve ]]; then extra=(--overlap-submission); fi
    dir="$out/$plan"
    mkdir "$dir"
    "$NSYS" profile --sample=none --cpuctxsw=none --trace=cuda,nvtx -o "$dir/trace" \
      "$GPU4PYSCF_ENV/bin/python" run_prepared_gpu4pyscf_async.py --manifest manifest.json \
      --molecules qm9-000003 qm9-000009 qm9-000011 qm9-000001 --workers 2 --batch-size 4 \
      --ragged --mode "$mode" "${extra[@]}" --out "$dir/producer.json" > "$dir/console.log" 2>&1
    "$NSYS" export --type sqlite --output "$dir/trace.sqlite" "$dir/trace.nsys-rep" >> "$dir/console.log" 2>&1
done
date -u +%FT%TZ > "$out/finished"
