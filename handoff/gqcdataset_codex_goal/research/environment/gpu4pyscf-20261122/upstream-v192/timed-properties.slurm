#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=40G
#SBATCH --time=02:00:00
set -euo pipefail
root=$PWD; out="$root/timing-$SLURM_ARRAY_JOB_ID-$SLURM_ARRAY_TASK_ID"
mkdir "$out"
readarray -t planned < properties-nodeids.txt
node=${planned[$SLURM_ARRAY_TASK_ID]}
printf '%s\n' "$node" > "$out/nodeid.txt"
date -u +%FT%TZ > "$out/started"
cd "$root/tree"
export PYTHONPATH="$PWD:$root/benchmark-metadata/site" OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
py="$GPU4PYSCF_ENV/bin/python"
"$py" - <<'PY' > "$out/environment.json"
import cpuinfo,cupy,gpu4pyscf,pyscf,json,os,importlib.metadata as m
from gpu4pyscf.scf import cphf
from pathlib import Path
import hashlib
print(json.dumps(dict(gpu4pyscf=gpu4pyscf.__version__,pyscf=pyscf.__version__,cupy=cupy.__version__,driver=cupy.cuda.runtime.driverGetVersion(),
    gpu=cupy.cuda.runtime.getDeviceProperties(0)["name"].decode(),pci=cupy.cuda.Device().pci_bus_id,
    cphf_sha256=hashlib.sha256(Path(cphf.__file__).read_bytes()).hexdigest(),benchmark=m.version("pytest-benchmark"),
    py_cpuinfo=m.version("py-cpuinfo"),slurm_job=os.environ["SLURM_JOB_ID"])))
PY
set +e
"$py" -m pytest -v -ra --benchmark-json="$out/benchmark.json" --benchmark-save-data --junitxml="$out/junit.xml" "$node" > "$out/pytest.log" 2>&1
rc=$?
set -e
printf '%s\n' "$rc" > "$out/exit.txt"
date -u +%FT%TZ > "$out/finished"
exit "$rc"
