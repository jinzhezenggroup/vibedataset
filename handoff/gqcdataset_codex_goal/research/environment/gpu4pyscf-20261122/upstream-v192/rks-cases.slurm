#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=01:45:00
set -euo pipefail
root=$PWD
out="$root/case-$SLURM_ARRAY_JOB_ID-$SLURM_ARRAY_TASK_ID"
mkdir "$out"
readarray -t cases < rks-nodeids.txt
node=${cases[$SLURM_ARRAY_TASK_ID]}
printf '%s\n' "$node" > "$out/nodeid.txt"
date -u +%FT%TZ > "$out/started"
cp -a --reflink=auto tree "$out/tree"
cd "$out/tree"
export PYTHONPATH="$PWD:$root/basis-dependency/site" OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
set +e
timeout -k 30s 95m "$GPU4PYSCF_ENV/bin/python" -m pytest -v -ra --benchmark-disable --junitxml="$out/junit.xml" "$node" > "$out/pytest.log" 2>&1
status=$?
set -e
printf '%s\n' "$status" > "$out/exit.txt"
date -u +%FT%TZ > "$out/finished"
exit "$status"
