#!/usr/bin/env python3
"""Compare matching PySCF and GPU4PySCF Hessian controls elementwise."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


PAIRINGS = (
    ("h2o", "h2o-rhf"),
    ("nh3", "nh3-rhf"),
)


def flatten(value: Any) -> list[float]:
    if isinstance(value, list):
        result: list[float] = []
        for child in value:
            result.extend(flatten(child))
        return result
    return [float(value)]


def digest(values: list[float]) -> str:
    payload = json.dumps(values, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def load_rows(path: Path, name_key: str) -> dict[str, dict[str, Any]]:
    document = json.loads(path.read_text())
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{path} has no rows array")
    result = {}
    for row in rows:
        name = row.get(name_key)
        if not isinstance(name, str):
            raise ValueError(f"{path} contains a row without {name_key}")
        result[name] = row
    return result


def compare(cpu: dict[str, Any], gpu: dict[str, Any], max_abs_tolerance: float) -> dict[str, Any]:
    cpu_values = flatten(cpu.get("hessian_values"))
    gpu_values = flatten(gpu.get("hessian_values"))
    if len(cpu_values) != len(gpu_values):
        raise ValueError(f"shape mismatch: {len(cpu_values)} versus {len(gpu_values)} values")
    deltas = [left - right for left, right in zip(cpu_values, gpu_values)]
    max_abs = max((abs(delta) for delta in deltas), default=0.0)
    rms = math.sqrt(sum(delta * delta for delta in deltas) / len(deltas)) if deltas else 0.0
    cpu_shape = cpu.get("hessian_shape")
    gpu_shape = gpu.get("hessian_shape")
    accepted = (
        cpu.get("status") == "accepted"
        and gpu.get("scf_hessian_status") == "accepted"
        and cpu_shape == gpu_shape
        and max_abs <= max_abs_tolerance
    )
    return {
        "cpu_name": cpu["name"],
        "gpu_name": gpu["name"],
        "shape": cpu_shape,
        "elements": len(cpu_values),
        "cpu_hessian_sha256": cpu.get("hessian_sha256"),
        "gpu_hessian_sha256": gpu.get("hessian_sha256"),
        "cpu_value_digest": digest(cpu_values),
        "gpu_value_digest": digest(gpu_values),
        "energy_abs_diff_hartree": abs(float(cpu["energy_hartree"]) - float(gpu["energy_hartree"])),
        "max_abs_hessian_diff": max_abs,
        "rms_hessian_diff": rms,
        "max_abs_tolerance": max_abs_tolerance,
        "status": "accepted" if accepted else "reject-and-recompute",
    }


def compare_finite_difference(
    analytic: dict[str, Any], finite_difference: dict[str, Any], max_abs_tolerance: float
) -> dict[str, Any]:
    analytic_values = flatten(analytic.get("hessian_values"))
    finite_difference_values = flatten(finite_difference.get("hessian_values"))
    if len(analytic_values) != len(finite_difference_values):
        raise ValueError(
            "finite-difference shape mismatch: "
            f"{len(analytic_values)} versus {len(finite_difference_values)} values"
        )
    deltas = [left - right for left, right in zip(analytic_values, finite_difference_values)]
    max_abs = max((abs(delta) for delta in deltas), default=0.0)
    rms = math.sqrt(sum(delta * delta for delta in deltas) / len(deltas)) if deltas else 0.0
    accepted = (
        analytic.get("status") == "accepted"
        and finite_difference.get("status") == "accepted"
        and analytic.get("hessian_shape") == finite_difference.get("hessian_shape")
        and max_abs <= max_abs_tolerance
    )
    return {
        "analytic_name": analytic["name"],
        "finite_difference_step_bohr": finite_difference["protocol"]["step_bohr"],
        "shape": analytic.get("hessian_shape"),
        "elements": len(analytic_values),
        "analytic_hessian_sha256": analytic.get("hessian_sha256"),
        "finite_difference_hessian_sha256": finite_difference.get("hessian_sha256"),
        "max_abs_hessian_diff": max_abs,
        "rms_hessian_diff": rms,
        "max_abs_tolerance": max_abs_tolerance,
        "status": "accepted" if accepted else "reject-and-recompute",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", type=Path, required=True)
    parser.add_argument("--gpu", type=Path, required=True)
    parser.add_argument("--cpu-rks", type=Path)
    parser.add_argument("--finite-difference", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-abs-tolerance", type=float, default=1e-7)
    parser.add_argument("--rks-max-abs-tolerance", type=float, default=1e-5)
    args = parser.parse_args()

    cpu_rows = load_rows(args.cpu, "name")
    gpu_rows = load_rows(args.gpu, "name")
    comparisons = []
    for cpu_name, gpu_name in PAIRINGS:
        if cpu_name not in cpu_rows or gpu_name not in gpu_rows:
            raise ValueError(f"missing paired row {cpu_name}/{gpu_name}")
        comparisons.append(compare(cpu_rows[cpu_name], gpu_rows[gpu_name], args.max_abs_tolerance))
    finite_difference = None
    if args.finite_difference is not None:
        finite_difference_document = json.loads(args.finite_difference.read_text())
        finite_difference = compare_finite_difference(
            cpu_rows["h2o"], finite_difference_document, args.max_abs_tolerance
        )
    rks_comparison = None
    if args.cpu_rks is not None:
        rks_rows = load_rows(args.cpu_rks, "name")
        if "h2o-rks" not in rks_rows or "h2o-rks" not in gpu_rows:
            raise ValueError("missing H2O/RKS pair")
        rks_comparison = compare(rks_rows["h2o-rks"], gpu_rows["h2o-rks"], args.rks_max_abs_tolerance)
    result = {
        "schema": "vibedataset.hessian_cphf.cpu_gpu_crosscheck.v1",
        "protocol": {
            "cpu": "PySCF RHF analytic relaxed Hessian/CPKS",
            "gpu": "GPU4PySCF RHF analytic relaxed Hessian/CPKS",
            "basis": "sto-3g",
            "geometry_unit": "Bohr",
            "precision": "FP64",
            "scf_tol": 1e-10,
            "pairings": [[cpu_name, gpu_name] for cpu_name, gpu_name in PAIRINGS],
        },
        "inputs": {
            "cpu": str(args.cpu),
            "gpu": str(args.gpu),
            "cpu_rks": str(args.cpu_rks) if args.cpu_rks else None,
            "finite_difference": str(args.finite_difference) if args.finite_difference else None,
        },
        "comparisons": comparisons,
        "rks_comparison": rks_comparison,
        "finite_difference": finite_difference,
        "status": "accepted"
        if all(item["status"] == "accepted" for item in comparisons)
        and (rks_comparison is None or rks_comparison["status"] == "accepted")
        and (finite_difference is None or finite_difference["status"] == "accepted")
        else "reject-and-recompute",
        "limitations": [
            "H2O/RHF and NH3/RHF use a 1e-7 elementwise tolerance. H2O/RKS(B3LYP) uses the separately recorded CPU RKS control and its 1e-5 tolerance when provided.",
            "This is an elementwise micro-control and does not replace a VeloxChem cross-check.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "comparisons": len(comparisons)}, indent=2))


if __name__ == "__main__":
    main()
