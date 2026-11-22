#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=40G
#SBATCH --time=04:00:00
set -euo pipefail
mode=${1:?specify collect, properties, suite or retry}
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONUNBUFFERED=1
work=$PWD
runtime=${GPU4PYSCF_ENV:?set GPU4PYSCF_ENV to the matched wheel virtual environment}
out="$work/$mode-$SLURM_JOB_ID"
mkdir "$out"
cd "$work/tree"
if [[ $mode == suite ]]; then
    # Some upstream tests write relative input/temporary files.
    cp -a --reflink=auto . "$out/tree"
    cd "$out/tree"
fi
export PYTHONPATH="$PWD"
printf '%s\n' "$SLURM_JOB_ID" > "$out/job-id"
"$runtime/bin/python" - <<'PY' > "$out/identity.json"
from importlib import metadata
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import cupy
import gpu4pyscf
from gpu4pyscf.scf import cphf
path = Path(cphf.__file__)
assert path.resolve().parent.parent == Path.cwd() / 'gpu4pyscf'
packages = ('gpu4pyscf-cuda12x', 'pyscf', 'cupy-cuda12x', 'nvidia-cublas-cu12', 'gpu4pyscf-libxc-cuda12x', 'pytest', 'pytest-benchmark')
identity = {dist: metadata.version(dist) for dist in packages}
assert identity['gpu4pyscf-cuda12x'] == gpu4pyscf.__version__ == '1.9.2'
props = cupy.cuda.runtime.getDeviceProperties(0)
print(json.dumps(dict(packages=identity, python=sys.version, num_devices=cupy.cuda.runtime.getDeviceCount(),
    device=props['name'].decode(), cuda_runtime=cupy.cuda.runtime.runtimeGetVersion(),
    driver=subprocess.check_output(['nvidia-smi','--query-gpu=driver_version','--format=csv,noheader'],text=True).splitlines()[0],
    cphf_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), wheel_build_flags=None,
    omp_threads=os.environ['OMP_NUM_THREADS']), indent=2))
PY
case "$mode" in
collect) flags=(--collect-only -q gpu4pyscf) ;;
properties) flags=(-v gpu4pyscf/tests/test_benchmark_properties.py --benchmark-json="$out/benchmark.json") ;;
retry)
    target=${2:?supply test file relative to upstream}
    [[ "$target" =~ ^gpu4pyscf/([a-zA-Z_0-9]+/)*test_[a-zA-Z_0-9]+\.py$ ]] || exit 2
    flags=(-q -ra --benchmark-disable "$target")
    ;;
suite)
    shard=${SLURM_ARRAY_TASK_ID:-0}
    count=${SLURM_ARRAY_TASK_COUNT:-1}
    mapfile -t files < <(find gpu4pyscf -type f -name 'test_*.py' | LC_ALL=C sort)
    date -u +%FT%TZ > "$out/started"
    for ((i=shard; i<${#files[@]}; i+=count)); do
        target=${files[$i]}
        logfile="$out/${target//\//_}"
        printf '%s\n' "$target" >> "$out/dispatched.txt"
        date -u +%FT%TZ > "$logfile.started"
        set +e
        timeout -k 30s 45m "$runtime/bin/python" -m pytest -q -ra --benchmark-disable \
            --junitxml="$logfile.xml" "$target" > "$logfile.log" 2>&1
        rc=$?
        set -e
        printf '%s %s\n' "$rc" "$target" >> "$out/exits.txt"
    done
    date -u +%FT%TZ > "$out/finished"
    exit 0
    ;;
*) exit 2 ;;
esac
printf '%s\n' "-m" "pytest" "${flags[@]}" > "$out/argv.txt"
date -u +%FT%TZ > "$out/started"
set +e
"$runtime/bin/python" -m pytest "${flags[@]}" --junitxml="$out/junit.xml" > "$out/pytest.log" 2>&1
rc=$?
set -e
printf '%s\n' "$rc" > "$out/exit.txt"
date -u +%FT%TZ > "$out/finished"
exit "$rc"
