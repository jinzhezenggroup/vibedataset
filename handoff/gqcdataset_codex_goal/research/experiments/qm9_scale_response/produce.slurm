#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:5090:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
set -euo pipefail
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
unset PYTHONPATH
py="$GPU4PYSCF_ENV/bin/python"
export VERIFIED_WHEEL_SHA256
VERIFIED_WHEEL_SHA256=$(sha256sum "$WHEEL_FILE" | cut -d' ' -f1)
args=(--geometries geometries.json.gz --protocol protocol.json)
out="$PWD/produce-$SLURM_JOB_ID"
mkdir "$out"
date -u +%FT%TZ > "$out/started"
nvidia-smi --query-gpu=name,driver_version,pci.bus_id,power.limit --format=csv > "$out/device.csv"
printf '%s\n' "$PROJECT_SHA" > "$out/project-commit"
sha256sum run_qm9_scale_response.py run_gpu4pyscf_4arm.py protocol.json geometries.json.gz > "$out/inputs.sha256"
if [[ ${1:-} == pilot ]]; then
    for index in 1 501 1000; do
        "$py" run_qm9_scale_response.py produce "${args[@]}" --out "$out" --start "$index" --stop "$index"
    done
else
    start=$((1 + SLURM_ARRAY_TASK_ID * SHARD_SIZE))
    stop=$((start + SHARD_SIZE - 1))
    if ((stop > 1000)); then stop=1000; fi
    "$py" run_qm9_scale_response.py produce "${args[@]}" --out "$out" --start "$start" --stop "$stop"
fi
date -u +%FT%TZ > "$out/finished"
