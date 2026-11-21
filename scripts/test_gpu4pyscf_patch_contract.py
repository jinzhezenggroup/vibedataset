#!/usr/bin/env python3
"""Apply and reverse the Issue #31 GPU4PySCF patch in a tiny source copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("_references/gpu4pyscf"))
    parser.add_argument("--patch", type=Path, default=Path("handoff/gqcdataset_codex_goal/research/experiments/attribution_4arm/patches/gpu4pyscf-response-cache.patch"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.source_root = args.source_root.resolve()
    args.patch = args.patch.resolve()
    args.out = args.out.resolve()
    original = args.source_root / "gpu4pyscf/scf/cphf.py"
    if not original.exists():
        raise SystemExit(f"missing source checkout {original}")
    with tempfile.TemporaryDirectory(prefix="gpu4pyscf-patch-contract-") as directory:
        root = Path(directory)
        target = root / "gpu4pyscf/scf/cphf.py"
        target.parent.mkdir(parents=True)
        shutil.copy2(original, target)
        original_hash = digest(target)
        subprocess.check_call(["patch", "-p1", "-i", str(args.patch)], cwd=root, stdout=subprocess.DEVNULL)
        patched_hash = digest(target)
        cache = root / "gpu4pyscf/lib/response_cache.py"
        if not cache.exists() or "class ResponseOperatorCache" not in cache.read_text():
            raise SystemExit("patch did not add ResponseOperatorCache")
        if "backend_cache" not in target.read_text():
            raise SystemExit("patch did not expose backend_cache")
        subprocess.check_call(["patch", "-p1", "-R", "-i", str(args.patch)], cwd=root, stdout=subprocess.DEVNULL)
        if digest(target) != original_hash or cache.exists():
            raise SystemExit("patch reverse did not restore source")
    result = {"status": "passed", "source_sha256": original_hash, "patched_sha256": patched_hash, "patch_sha256": digest(args.patch)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
