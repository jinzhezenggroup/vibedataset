#!/usr/bin/env python3
"""Check the bounded A/C GPU4PySCF phase telemetry receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    errors = []
    profiles = {}
    for arm in ("A", "C"):
        path = args.directory / f"profile-{arm}.json"
        if not path.exists():
            errors.append(f"missing {path}")
            continue
        document = json.loads(path.read_text())
        profiles[arm] = document
        if document.get("schema") != "vibedataset.gpu4pyscf_phase_profile_control.v2":
            errors.append(f"schema {arm}")
        if document.get("arm") != arm or document.get("molecule") != "qm9-000001":
            errors.append(f"identity {arm}")
        if len(document.get("rows", [])) != 3:
            errors.append(f"rows {arm}")
        if document.get("protocol", {}).get("precision") != "FP64":
            errors.append(f"precision {arm}")
        for row in document.get("rows", []):
            if not row.get("phase_seconds") or not row.get("gpu_event_seconds"):
                errors.append(f"timing {arm}:{row.get('trajectory')}")
    if set(profiles) == {"A", "C"}:
        if profiles["A"].get("manifest_sha256") != profiles["C"].get("manifest_sha256"):
            errors.append("manifest binding")
        c_rows = profiles["C"]["rows"]
        if c_rows[1].get("fields_reused") != ["x"] or c_rows[2].get("fields_computed"):
            errors.append("C reuse receipt")
    result = {"status": "passed" if not errors else "failed", "arms": sorted(profiles), "errors": errors}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
