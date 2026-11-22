#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:10:00
set -eu
d="$PWD/counters-$SLURM_JOB_ID"
mkdir "$d"
unset PYTHONPATH
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
"$NCU" --version > "$d/version.txt"
grep RmProfilingAdminOnly /proc/driver/nvidia/params > "$d/driver-policy.txt"
set +e
"$NCU" --kernel-name 'regex:rys_k_.*' --launch-count 1 \
  --metrics sm__warps_active.avg.pct_of_peak_sustained_active,smsp__sass_thread_inst_executed_op_dfma_pred_on.sum \
  --export "$d/first-rys" "$GPU4PYSCF_ENV/bin/python" run_gpu4pyscf_4arm.py --manifest manifest.json --arm A \
  --out "$d/producer" --source-commit "$PROJECT_SHA" --gpu4pyscf-source-commit 8536a80c1e03260aab030e108ef1d181a3709057 \
  > "$d/console.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$d/exit.txt"
exit "$rc"
