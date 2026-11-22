#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=18G
#SBATCH --time=00:35:00
set -eu
out="$PWD/tests-$SLURM_JOB_ID"
mkdir "$out"
cd tree
export PYTHONPATH="$PWD" OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
py="$GPU4PYSCF_ENV/bin/python"
"$py" - <<'PY' > "$out/identity.json"
import json,hashlib,platform
from pathlib import Path
import importlib.metadata as md
import cupy,pyscf,gpu4pyscf
from gpu4pyscf.scf import cphf
from gpu4pyscf.lib import cutensor
assert Path(cphf.__file__).resolve().parent.parent == Path.cwd()/"gpu4pyscf"
assert gpu4pyscf.__version__ == md.version("gpu4pyscf-cuda12x") == "1.9.0"
w=json.loads(Path("../wheel.json").read_text())
assert hashlib.sha256((Path("..")/w["filename"]).read_bytes()).hexdigest()==w['digests']['sha256']
print(json.dumps(dict(version=gpu4pyscf.__version__,wheel_sha256=w['digests']['sha256'],cphf_sha256=hashlib.sha256(Path(cphf.__file__).read_bytes()).hexdigest(),python=platform.python_version(),cupy=cupy.__version__,pyscf=pyscf.__version__,engine=cutensor.contract_engine,gpu=cupy.cuda.runtime.getDeviceProperties(0)["name"].decode(),cuda_runtime=cupy.cuda.runtime.runtimeGetVersion()),indent=2))
PY
tests=(gpu4pyscf/scf/tests/test_cphf.py gpu4pyscf/properties/tests/test_polarizability.py gpu4pyscf/properties/tests/test_ir_intensity.py gpu4pyscf/properties/tests/test_raman_intensity.py)
sha256sum "${tests[@]}" > "$out/test-sha256.txt"
date -u +%FT%TZ > "$out/started"
set +e
"$py" -m pytest -v -ra --junitxml="$out/junit.xml" "${tests[@]}" > "$out/pytest.log" 2>&1
rc=$?
set -e
printf '%s\n' "$rc" > "$out/exit.txt"
exit "$rc"
