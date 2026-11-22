#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:5090:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=22G
#SBATCH --time=01:25:00
set -euo pipefail
envdir=${GPU4PYSCF_ENV:?isolated 1.9.2 environment}
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
unset PYTHONPATH
out="$PWD/run-$SLURM_JOB_ID"
mkdir "$out"
export PAIR_OUTPUT="$out"
py="$envdir/bin/python"
"$py" - <<'PY' > "$out/identity.json"
import json, platform, os, subprocess, sys
import importlib.metadata as m
from pathlib import Path
import cupy, gpu4pyscf
from gpu4pyscf.lib import cutensor
from gpu4pyscf.scf import cphf
import hashlib
wheel = next(x for x in json.loads(Path("install.json").read_text())["install"] if x["metadata"]["name"].lower()=="gpu4pyscf-cuda12x")
sha = wheel["download_info"]["archive_info"]["hashes"]["sha256"]
assert sha == "519d78d412392ffa7ba73683742e01716ac2be303462c6b420b8712e003880fd"
assert gpu4pyscf.__version__ == "1.9.2" and cupy.cuda.runtime.getDeviceCount() == 1
source_hash = hashlib.sha256(Path(cphf.__file__).read_bytes()).hexdigest()
assert source_hash == "1010af1ff5cb62e424223e6c65bad9344e7a6e37bf6882ff574efddb9e2839de"
pci = cupy.cuda.Device().pci_bus_id
props=cupy.cuda.runtime.getDeviceProperties(0)
assert b"5090" in props["name"]
print(json.dumps(dict(wheel_sha256=sha, source_sha256=source_hash, pci=pci, gpu=props["name"].decode(),
    gpu4pyscf=gpu4pyscf.__version__, cupy=cupy.__version__, cublas=m.version("nvidia-cublas-cu12"), pyscf=m.version("pyscf"),
    cuda_runtime=cupy.cuda.runtime.runtimeGetVersion(), python=platform.python_version(), engine=cutensor.contract_engine,
    device_state=subprocess.check_output(["nvidia-smi","-i",pci,"--query-gpu=driver_version,memory.total,power.limit,clocks.max.sm,clocks.max.memory","--format=csv,noheader"],text=True).strip(),
    slurm_job=os.environ["SLURM_JOB_ID"]),indent=2))
PY
# The official package stays read-only; only a job-private copy receives the reversible patch.
site=$("$py" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
mkdir "$out/patched"
cp -a "$site/gpu4pyscf" "$out/patched/"
(cd "$out/patched" && patch --batch -p1 -i "$PWD/../../response-cache.patch" && patch --dry-run --batch -R -p1 -i "$PWD/../../response-cache.patch") > "$out/patch.log"
sha256sum "$out/patched/gpu4pyscf/scf/cphf.py" | cut -d' ' -f1 | grep -qx e945d59c4b19a5b183af2e4651caf2bb9276dc807079b8c060bb6490854a4d6a
printf 'A pilot started\n' >> "$out/attempts.txt"
"$py" run_gpu4pyscf_4arm_telemetry.py --manifest micro.json --arm A --out "$out/pilot" --source-commit "$PROJECT_SHA" --gpu4pyscf-source-commit 8536a80c1e03260aab030e108ef1d181a3709057
"$py" - <<'PY'
from pathlib import Path
import json,os,math
p=Path(os.environ["PAIR_OUTPUT"])/"pilot"
rows=[json.loads(s) for s in (p/"raw.jsonl").read_text().splitlines()]
assert len(rows)==3 and all(r["status"]=="accepted" and all(math.isfinite(v) for v in r["targets"].values())
    and r["response_metrics"]["residual_linf"] <= 1e-5 for r in rows)
PY
mkdir "$out/score-input"
for arm in A B C D; do
  printf '%s full started (51 requested)\n' "$arm" >> "$out/attempts.txt"
  args=(--arm "$arm" --manifest full.json --out "$out/$arm" --source-commit "$PROJECT_SHA" --gpu4pyscf-source-commit 8536a80c1e03260aab030e108ef1d181a3709057)
  if [[ $arm == B || $arm == D ]]; then
    PYTHONPATH="$out/patched" "$py" run_gpu4pyscf_4arm_telemetry.py "${args[@]}" --patch response-cache.patch
  else
    "$py" run_gpu4pyscf_4arm_telemetry.py "${args[@]}"
  fi
  cp "$out/$arm/raw.jsonl" "$out/score-input/raw-$arm.jsonl"
  printf '%s full finished\n' "$arm" >> "$out/attempts.txt"
done
printf 'official scorer started\n' >> "$out/attempts.txt"
"$py" score_gpu4pyscf_4arm.py --manifest full.json --raw-dir "$out/score-input" --out "$out/score.json"
printf 'official scorer finished\n' >> "$out/attempts.txt"
