#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:5090:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:45:00
set -euo pipefail
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
unset PYTHONPATH
py="$GPU4PYSCF_ENV/bin/python"
export VERIFIED_WHEEL_SHA256
VERIFIED_WHEEL_SHA256=$(sha256sum "$WHEEL_FILE" | cut -d' ' -f1)
list=${1:?list of scored, rejected request indices}
out="$PWD/retry-$SLURM_JOB_ID"
mkdir "$out"
cp "$list" "$out/indices.txt"
date -u +%FT%TZ > "$out/started"
printf '%s\n' "$PROJECT_SHA" > "$out/project-commit"
sha256sum *.py protocol.json geometries.json.gz "$list" > "$out/input-sha256"
repair=()
if [[ ${2:-} == full-fock ]]; then repair=(--full-fock-repair); fi
while read -r i; do
    [[ $i =~ ^[0-9]+$ ]] && (( i >= 1 && i <= 1000 )) || exit 2
    "$py" run_qm9_scale_response.py produce --protocol protocol.json --geometries geometries.json.gz --retry \
        --start "$i" --stop "$i" "${repair[@]}" --out "$out"
done < "$list"
date -u +%FT%TZ > "$out/finished"
