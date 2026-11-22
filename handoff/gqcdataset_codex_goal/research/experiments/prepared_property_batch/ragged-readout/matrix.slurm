#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=20G
#SBATCH --time=00:55:00
set -euo pipefail
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
unset PYTHONPATH
py="$GPU4PYSCF_ENV/bin/python"
out="$PWD/matrix-$SLURM_JOB_ID"
mkdir "$out"
sha256sum *.py manifest.json > "$out/input-sha256"
printf '%s\n' "$PROJECT_SHA" > "$out/project-commit"
common=(--manifest manifest.json --molecules qm9-000003 qm9-000009 qm9-000011 qm9-000001 --workers 2 --batch-size 4)
run() {
    local name=$1
    shift
    local start end status
    start=$(date +%s%N)
    printf '%s started %s\n' "$name" "$start" >> "$out/process-wall.txt"
    set +e
    "$py" run_prepared_gpu4pyscf_async.py "${common[@]}" "$@" --out "$out/$name.json" > "$out/$name.log" 2>&1
    status=$?
    set -e
    end=$(date +%s%N)
    printf '%s finished %s %s\n' "$name" "$end" "$status" >> "$out/process-wall.txt"
    return "$status"
}
if [[ ${1:-} == pilot ]]; then
    run serial --mode serial
    run async-ragged --mode async_streams --ragged
else
    run serial --mode serial
    run async --mode async_streams
    run ragged --mode serial --ragged
    run async-ragged --mode async_streams --ragged
    run allocate --mode async_streams --ragged --no-resident
    run batch-one --mode async_streams --ragged --batch-size 1
    run single-rhs --mode async_streams --ragged --no-multi-rhs
    run no-asset --mode async_streams --ragged --no-asset-reuse
    run budget --mode async_streams --ragged --workspace-bytes 64
    run isolation --mode async_streams --ragged --fault qm9-000003:cycle-one=scf-fail \
        --fault qm9-000009:cycle-three=allocator-oom --fault qm9-000011:cross-three=unsupported
fi
date -u +%FT%TZ > "$out/finished"
