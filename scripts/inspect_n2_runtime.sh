#!/usr/bin/env bash
# Read-only identity/import check. No Calculator and no GPU calculation.
set -euo pipefail
source ~/miniconda3/etc/profile.d/conda.sh
conda activate xtbflow-qc
source ~/.config/n2-qc/runtime.env
export LD_LIBRARY_PATH="$GQC_OPENBLAS_DIR:$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$GQC_PYTHON" - <<'PY'
import datetime
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from pathlib import Path
import generativeqc

def command(argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    return {"command": argv, "returncode": p.returncode,
            "stdout": p.stdout, "stderr": p.stderr}

lib = Path(os.environ['GQC_NATIVE_LIBRARY'])
actual = hashlib.sha256(lib.read_bytes()).hexdigest()
report = {
    "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "host": platform.node(), "python": platform.python_version(),
    "generativeqc_version": importlib.metadata.version('generativeqc'),
    "import_succeeded": True,
    "declared_source_sha": os.environ['GQC_SOURCE_SHA'],
    "declared_native_library_sha256": os.environ['GQC_NATIVE_LIBRARY_SHA256'],
    "actual_native_library_sha256": actual,
    "library_hash_matches_declaration": actual == os.environ['GQC_NATIVE_LIBRARY_SHA256'],
    "openblas_directory_exists": Path(os.environ['GQC_OPENBLAS_DIR']).is_dir(),
    "scheduler": [command(['sinfo', '-p', 'main', '-o', '%P %a %l %D %G %t']),
                  command(['squeue', '--me', '-o', '%i %P %j %T %M %D'])],
    "qc_calls": 0, "gpu_jobs_submitted": 0,
    "scope": "Read-only import, file hash and scheduler observation; no numerical validation.",
}
print(json.dumps(report, indent=2))
PY
