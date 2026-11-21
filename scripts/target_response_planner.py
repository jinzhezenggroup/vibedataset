#!/usr/bin/env python3
"""Cost/coverage/risk planner for protocol-preserving response increments.

The planner reads only the sealed request manifest and raw arm costs.  It never
loads scorer output, response truth, or an oracle.  Its decisions are therefore
replayed independently by ``verify_target_response_planner.py`` before the
four-arm records are scored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


POLICIES = ("native-field", "gqc-assets", "vector-precompute", "dense-prefetch", "reject-and-recompute")
DISTRIBUTIONS = {
    "short-queue": {"cycle-one": 1.0},
    "mixed-targets": {"cycle-one": 0.25, "cycle-three": 0.5, "cross-three": 0.25},
    "near-full-coverage": {"cycle-one": 0.1, "cycle-three": 0.7, "cross-three": 0.2},
}
PROBABILITIES = (0.2, 0.5, 0.9)


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def row_cost(row: dict) -> dict[str, float]:
    response = row.get("response_metrics") or {}
    vector_bytes = sum(len(values) * 8 for values in row.get("response_vectors", {}).values())
    density_bytes = sum(len(values) * 8 for values in row.get("response_densities", {}).values())
    return {
        "operator_rows": float(response.get("operator_rows", 0)),
        "quality_rows": float(response.get("quality_operator_rows", 0)),
        "seconds": float(response.get("seconds", 0.0)),
        "host_device_bytes": float(response.get("host_to_device_bytes", 0) + response.get("device_to_host_bytes", 0)),
        "vector_bytes": vector_bytes,
        "density_bytes": density_bytes,
    }


def plus(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    return {key: a[key] + b[key] for key in a}


def zero() -> dict[str, float]:
    return {"operator_rows": 0.0, "quality_rows": 0.0, "seconds": 0.0, "host_device_bytes": 0.0, "vector_bytes": 0.0, "density_bytes": 0.0}


def build_ood_cases(manifest: dict) -> list[dict]:
    cases = []
    for item in manifest["molecules"]:
        xyz = item["coordinates_bohr"]
        centroid = [sum(row[index] for row in xyz) / len(xyz) for index in range(3)]
        stretched = [
            [round(centroid[index] + 1.15 * (coord[index] - centroid[index]), 12) for index in range(3)]
            for coord in xyz
        ]
        compressed = [
            [round(centroid[index] + 0.85 * (coord[index] - centroid[index]), 12) for index in range(3)]
            for coord in xyz
        ]
        cases.append({"molecule": item["name"], "case": "geometry-stretched-1.15", "coordinates_bohr": stretched, "target_protocol": manifest["protocol"], "disposition": "refine-required", "risk": 0.02})
        cases.append({"molecule": item["name"], "case": "geometry-compressed-0.85", "coordinates_bohr": compressed, "target_protocol": manifest["protocol"], "disposition": "refine-required", "risk": 0.02})
    cases.extend([
        {"molecule": "qm9-000003", "case": "basis-6-31g-star", "target_protocol": {**manifest["protocol"], "basis": "6-31g*"}, "disposition": "reject-and-recompute", "risk": 0.0},
        {"molecule": "qm9-000003", "case": "method-b3lyp", "target_protocol": {**manifest["protocol"], "method": "B3LYP"}, "disposition": "reject-and-recompute", "risk": 0.0},
        {"molecule": "qm9-000002", "case": "open-shell-doublet", "target_protocol": {**manifest["protocol"], "multiplicity": 2}, "disposition": "reject-and-recompute", "risk": 0.0},
    ])
    return cases


def objective(cost: dict[str, float], storage: float, risk: float, probability: float) -> float:
    # Coefficients are fixed before reading any scorer output.  Time is the
    # primary currency, transfer/validation are charged in seconds-equivalent,
    # storage is charged at 1e-8 s/byte, and risk is a hard penalty.
    return (cost["seconds"] + 2e-7 * cost["operator_rows"] + 1e-9 * cost["host_device_bytes"]
            + probability * (storage * 1e-8) + 1e3 * risk)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ood-inventory", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    inventory_path = args.ood_inventory or args.manifest.parent / "ood_inventory.json"
    inventory = json.loads(inventory_path.read_text()) if inventory_path.exists() else {"rows": []}
    rows_a = {(row["molecule"], row["trajectory"]): row for row in read_rows(args.raw_dir / "raw-A.jsonl")}
    rows_c = {(row["molecule"], row["trajectory"]): row for row in read_rows(args.raw_dir / "raw-C.jsonl")}
    molecule_names = [item["name"] for item in manifest["molecules"]]
    decisions = []
    frontier = []
    for molecule in molecule_names:
        all_cost = zero()
        gqc_cost = zero()
        full_storage = 0.0
        for trajectory in ("cycle-one", "cycle-three", "cross-three"):
            all_cost = plus(all_cost, row_cost(rows_a[(molecule, trajectory)]))
            gqc_cost = plus(gqc_cost, row_cost(rows_c[(molecule, trajectory)]))
        unique = rows_c[(molecule, "cycle-three")]["response_vectors"]
        full_storage = sum(len(values) * 8 for values in unique.values())
        dense_storage = 9 * 8
        for distribution, weights in DISTRIBUTIONS.items():
            selected = [name for name, weight in weights.items() if weight > 0]
            for probability in PROBABILITIES:
                candidates = []
                native = zero()
                gqc = zero()
                for trajectory in selected:
                    native = plus(native, row_cost(rows_a[(molecule, trajectory)]))
                    gqc = plus(gqc, row_cost(rows_c[(molecule, trajectory)]))
                # These are declared policy costs.  No target values enter the
                # choices.  vector/dense policies charge full prefetch and
                # storage even when the request distribution is sparse.
                policy_costs = {
                    "native-field": (native, 0.0, 0.0, len(selected) / 3),
                    "gqc-assets": (gqc, full_storage, 0.005, min(1.0, len(selected) / 3 + 0.25)),
                    "vector-precompute": (gqc, full_storage, 0.002, 1.0),
                    "dense-prefetch": (all_cost, dense_storage, 0.001, 1.0),
                    "reject-and-recompute": (zero(), 0.0, 0.0, 0.0),
                }
                for policy in POLICIES:
                    cost, storage, risk, coverage = policy_costs[policy]
                    score = objective(cost, storage, risk, probability)
                    candidate = {
                        "molecule": molecule,
                        "domain": "in-domain",
                        "distribution": distribution,
                        "future_request_probability": probability,
                        "policy": policy,
                        "coverage": coverage,
                        "risk": risk,
                        "objective": score,
                        "cost": cost,
                        "storage_bytes": storage,
                        "oracle_loaded": False,
                        "scorer_loaded": False,
                    }
                    candidates.append(candidate)
                    frontier.append(candidate)
                selected_candidate = min(candidates, key=lambda row: (row["objective"], row["policy"]))
                decisions.append({"molecule": molecule, "domain": "in-domain", "distribution": distribution, "future_request_probability": probability, "selected": selected_candidate, "candidates": candidates})
    for case in build_ood_cases(manifest):
        for probability in PROBABILITIES:
            selected = {
                "molecule": case["molecule"],
                "domain": "ood",
                "case": case["case"],
                "future_request_probability": probability,
                "selected": {"policy": "reject-and-recompute", "disposition": case["disposition"], "coverage": 0.0, "risk": case["risk"], "objective": 1000.0 * case["risk"], "oracle_loaded": False, "scorer_loaded": False},
                "target_protocol": case["target_protocol"],
                "coordinates_bohr": case.get("coordinates_bohr"),
            }
            decisions.append(selected)
    for case in inventory["rows"]:
        for probability in PROBABILITIES:
            decisions.append({
                "molecule": case["case_id"],
                "domain": "external-ood-inventory",
                "future_request_probability": probability,
                "selected": {
                    "policy": "reject-and-recompute",
                    "disposition": case["disposition"],
                    "coverage": 0.0,
                    "risk": 0.0,
                    "objective": 0.0,
                    "oracle_loaded": False,
                    "scorer_loaded": False,
                },
                "source_relpath": case["source_relpath"],
                "source_sha256": case["source_sha256"],
                "protocol_status": case["protocol_status"],
            })
    result = {
        "schema": "vibedataset.target_response_planner.v1",
        "manifest_sha256": manifest["manifest_sha256"],
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "objective": {"time_weight": 1.0, "operator_row_weight": 2e-7, "transfer_byte_weight": 1e-9, "storage_byte_weight": 1e-8, "risk_weight": 1000.0},
        "policy_names": list(POLICIES),
        "distribution_names": list(DISTRIBUTIONS),
        "request_count": len(decisions),
        "candidate_count": len(frontier),
        "ood_inventory_count": len(inventory["rows"]),
        "decisions": decisions,
        "negative_boundary": "OOD geometry is refine-required. Basis, method and multiplicity changes are reject-and-recompute.",
        "oracle_loaded": False,
        "scorer_loaded": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
