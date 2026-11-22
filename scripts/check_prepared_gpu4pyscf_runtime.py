#!/usr/bin/env python3
"""Independently compare serial and process-isolated prepared runtime receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", type=Path, required=True)
    parser.add_argument("--process", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target-tol", type=float, default=1e-5)
    args = parser.parse_args()
    serial = read(args.serial)
    process = read(args.process)
    serial_rows = {row["request_id"]: row for row in serial["receipts"]}
    process_rows = {row["request_id"]: row for row in process["receipts"]}
    errors = []
    if set(serial_rows) != set(process_rows):
        errors.append("request identity mismatch")
    target_differences = []
    residual_differences = []
    for request_id in sorted(serial_rows):
        left = serial_rows[request_id]["result"]
        right = process_rows[request_id]
        if tuple(left["fields_computed"]) != tuple(right["fields_computed"]):
            errors.append(f"{request_id}: fields_computed mismatch")
        for name, value in left["targets"].items():
            target_differences.append(abs(float(value) - float(right["targets"][name])))
        if left["residual_linf"] is not None and right["residual_linf"] is not None:
            residual_differences.append(abs(float(left["residual_linf"]) - float(right["residual_linf"])))
    max_target_difference = max(target_differences, default=0.0)
    max_residual_difference = max(residual_differences, default=0.0)
    if max_target_difference > args.target_tol:
        errors.append(f"max target difference {max_target_difference} > {args.target_tol}")
    if serial.get("status") != "accepted" or process.get("status") != "accepted":
        errors.append("runtime status")
    if serial.get("request_count") != 9 or process.get("receipt_count") != 9:
        errors.append("request count")
    if process.get("worker_count") != 3 or process.get("cuda_context_count") != 3:
        errors.append("process worker/context count")
    result = {
        "schema": "vibedataset.prepared_gpu4pyscf_runtime_check.v1",
        "status": "passed" if not errors else "failed",
        "serial_elapsed_seconds": serial.get("elapsed_seconds"),
        "process_isolated_elapsed_seconds": process.get("elapsed_seconds"),
        "process_over_serial_ratio": process.get("elapsed_seconds", 0.0) / serial.get("elapsed_seconds", 1.0),
        "request_count": len(process_rows),
        "max_target_difference": max_target_difference,
        "max_residual_difference": max_residual_difference,
        "process_count": process.get("worker_count"),
        "cuda_context_count": process.get("cuda_context_count"),
        "errors": errors,
        "limitations": [
            "This compares process-isolated receipts to a serial receipt. It does not establish a same-context stream speedup.",
            "Process startup and duplicated CUDA contexts are included in the process elapsed time.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit("; ".join(errors))


if __name__ == "__main__":
    main()
