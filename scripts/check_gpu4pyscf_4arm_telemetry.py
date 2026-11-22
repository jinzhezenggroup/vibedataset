#!/usr/bin/env python3
"""Validate the request-level A-D telemetry receipt without a scorer oracle."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


TIMING_FIELDS = {
    "prepare",
    "environment_startup",
    "data_read",
    "compile_jit",
    "warmup",
    "h2d",
    "scf_fock",
    "cp_hf_gmres",
    "property_readout",
    "physical_residual",
    "independent_scorer",
    "serialization",
    "retry",
    "fallback",
}
ARMS = ("A", "B", "C", "D")
REQUESTS = {
    "cycle-one": ("x",),
    "cycle-three": ("x", "y", "z"),
    "cross-three": ("x", "z"),
}


def read_json(path: Path):
    return json.loads(path.read_text())


def finite_or_null(value) -> bool:
    return value is None or isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True, help="directory containing raw/A through raw/D")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = read_json(args.manifest)
    expected_rows = [(molecule["name"], request["id"]) for molecule in manifest["molecules"] for request in sorted(manifest["request_trajectories"], key=lambda row: row["order"])]
    errors: list[str] = []
    arms: dict[str, dict] = {}
    for arm in ARMS:
        directory = args.root / "raw" / arm
        run = read_json(directory / "run.json")
        rows = [json.loads(line) for line in (directory / "raw.jsonl").read_text().splitlines() if line.strip()]
        if len(rows) != len(expected_rows):
            errors.append(f"{arm}: row count {len(rows)} != {len(expected_rows)}")
        observed_ids = [(row.get("molecule"), row.get("trajectory")) for row in rows]
        if observed_ids != expected_rows:
            errors.append(f"{arm}: molecule/request order mismatch")
        if run.get("record_count") != len(rows) or run.get("failed_count") != 0:
            errors.append(f"{arm}: run receipt count or failure denominator mismatch")
        arm_times = []
        for index, row in enumerate(rows):
            if row.get("status") != "accepted":
                errors.append(f"{arm}[{index}]: status {row.get('status')}")
            if row.get("input_sha256") != manifest["manifest_sha256"]:
                errors.append(f"{arm}[{index}]: manifest identity")
            timing = row.get("timing", {})
            if not TIMING_FIELDS.issubset(timing):
                errors.append(f"{arm}[{index}]: missing timing fields")
            if any(not finite_or_null(timing.get(field)) for field in TIMING_FIELDS):
                errors.append(f"{arm}[{index}]: invalid timing value")
            wall = timing.get("end_to_end_wall_seconds")
            known = timing.get("known_seconds")
            unattributed = timing.get("unattributed_seconds")
            if not all(finite_or_null(value) for value in (wall, known, unattributed)):
                errors.append(f"{arm}[{index}]: invalid timing totals")
            elif known is not None and wall is not None and known > wall + 1e-6:
                errors.append(f"{arm}[{index}]: known timing exceeds end-to-end wall time")
            elif wall is not None and known is not None and unattributed is not None and abs(unattributed - max(0.0, wall - known)) > 1e-6:
                errors.append(f"{arm}[{index}]: unattributed timing mismatch")
            arm_times.append(float(wall or 0.0))
            requested = tuple(row.get("fields_requested", ()))
            computed = tuple(row.get("fields_computed", ()))
            reused = tuple(row.get("fields_reused", ()))
            if arm in ("A", "B") and (computed != requested or reused):
                errors.append(f"{arm}[{index}]: native field disposition")
            if arm in ("C", "D"):
                expected = REQUESTS[row["trajectory"]]
                expected_computed = expected if row["trajectory"] == "cycle-one" else ("y", "z") if row["trajectory"] == "cycle-three" else ()
                expected_reused = () if row["trajectory"] == "cycle-one" else ("x",) if row["trajectory"] == "cycle-three" else ("x", "z")
                if requested != expected or computed != expected_computed or reused != expected_reused:
                    errors.append(f"{arm}[{index}]: planner field disposition")
        arms[arm] = {
            "rows": len(rows),
            "failed": int(run.get("failed_count", -1)),
            "elapsed_seconds": run.get("elapsed_seconds"),
            "request_wall_seconds": sum(arm_times),
            "device": run.get("device"),
            "patch_sha256": run.get("patch_sha256"),
        }
    if arms["A"]["patch_sha256"] is not None or arms["C"]["patch_sha256"] is not None:
        errors.append("A/C must not report a patch hash")
    if not arms["B"]["patch_sha256"] or arms["B"]["patch_sha256"] != arms["D"]["patch_sha256"]:
        errors.append("B/D patch hashes do not match")
    result = {
        "schema": "vibedataset.gpu4pyscf_4arm_telemetry_check.v1",
        "status": "passed" if not errors else "failed",
        "manifest_sha256": manifest["manifest_sha256"],
        "timing_fields": sorted(TIMING_FIELDS),
        "arms": arms,
        "errors": errors,
        "limitations": [
            "compile_jit and independent_scorer remain explicit null phases in producer rows",
            "This checker validates receipt structure and bounded field reuse, not physical target correctness",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit("; ".join(errors))


if __name__ == "__main__":
    main()
