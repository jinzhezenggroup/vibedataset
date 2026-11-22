#!/usr/bin/env python3
"""Summarize matched A-D telemetry and the separate physical scorer receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path


ARMS = ("A", "B", "C", "D")
METRICS = (
    "end_to_end_wall_seconds",
    "prepare",
    "environment_startup",
    "data_read",
    "h2d",
    "scf_fock",
    "cp_hf_gmres",
    "property_readout",
    "physical_residual",
    "serialization",
    "retry",
    "fallback",
    "operator_rows",
    "rhs_columns",
    "host_to_device_bytes",
    "device_to_host_bytes",
)


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def geometric_mean(values: list[float]) -> float:
    positive = [value for value in values if value > 0]
    return math.exp(sum(math.log(value) for value in positive) / len(positive)) if positive else 0.0


def bootstrap_median(values: list[float], seed: int = 20261122, rounds: int = 4000) -> list[float]:
    rng = random.Random(seed)
    estimates = []
    for _ in range(rounds):
        sample = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(statistics.median(sample))
    estimates.sort()
    low = int(0.025 * (len(estimates) - 1))
    high = int(0.975 * (len(estimates) - 1))
    return [estimates[low], estimates[high]]


def row_metrics(row: dict) -> dict[str, float]:
    timing = row["timing"]
    response = row["response_metrics"]
    return {
        "end_to_end_wall_seconds": float(timing["end_to_end_wall_seconds"]),
        "prepare": float(timing["prepare"] or 0.0),
        "environment_startup": float(timing["environment_startup"] or 0.0),
        "data_read": float(timing["data_read"] or 0.0),
        "h2d": float(timing["h2d"] or 0.0),
        "scf_fock": float(timing["scf_fock"] or 0.0),
        "cp_hf_gmres": float(timing["cp_hf_gmres"] or 0.0),
        "property_readout": float(timing["property_readout"] or 0.0),
        "physical_residual": float(timing["physical_residual"] or 0.0),
        "serialization": float(timing["serialization"] or 0.0),
        "retry": float(timing["retry"] or 0.0),
        "fallback": float(timing["fallback"] or 0.0),
        "operator_rows": float(response.get("operator_rows", 0)),
        "rhs_columns": float(len(row["fields_computed"])),
        "host_to_device_bytes": float(response.get("host_to_device_bytes", 0)),
        "device_to_host_bytes": float(response.get("device_to_host_bytes", 0)),
    }


def paired_effect(left: dict[tuple[str, str], dict], right: dict[tuple[str, str], dict], metric: str) -> dict:
    differences = [left[key][metric] - right[key][metric] for key in sorted(left)]
    ratios = [left[key][metric] / right[key][metric] for key in sorted(left) if right[key][metric] > 0]
    return {
        "paired_median_difference": statistics.median(differences),
        "paired_bootstrap_95ci": bootstrap_median(differences),
        "geometric_mean_ratio": geometric_mean(ratios),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw = {arm: load_rows(args.root / "raw" / arm / "raw.jsonl") for arm in ARMS}
    score = json.loads(args.score.read_text())
    scored = score["rows"]
    score_by_key = {(row["arm"], row["molecule"], row["trajectory"]): row for row in scored}
    request_metrics = {
        arm: {(row["molecule"], row["trajectory"]): row_metrics(row) for row in rows}
        for arm, rows in raw.items()
    }
    molecule_metrics = {}
    for arm in ARMS:
        grouped = {}
        for key, metrics in request_metrics[arm].items():
            grouped.setdefault(key[0], {metric: 0.0 for metric in METRICS})
            for metric in METRICS:
                grouped[key[0]][metric] += metrics[metric]
        molecule_metrics[arm] = grouped

    summary = {
        "schema": "vibedataset.gpu4pyscf_4arm_telemetry_summary.v1",
        "manifest_sha256": raw["A"][0]["input_sha256"],
        "arms": {},
        "paired_effects": {},
        "scorer": {
            "rows": len(scored),
            "accepted": sum(row["status"] == "accepted" for row in scored),
            "reject_and_recompute": sum(row["status"] != "accepted" for row in scored),
            "max_target_error": max(row["max_target_error"] for row in scored),
            "max_operator_image_error": max(row["max_operator_image_error"] for row in scored),
            "max_ao_density_error": max(row["max_ao_density_error"] for row in scored),
            "max_oracle_residual": max(row["oracle_residual_linf"] for row in scored),
            "score_elapsed_seconds": score["elapsed_seconds"],
            "operator_image_diagnostic": {
                "max_error": max(row["max_operator_image_error"] for row in scored),
                "rows_over_1e-5": sum(row["max_operator_image_error"] > 1e-5 for row in scored),
                "rows_over_1e-5_by_arm": {
                    arm: sum(row["arm"] == arm and row["max_operator_image_error"] > 1e-5 for row in scored)
                    for arm in ARMS
                },
                "included_in_acceptance": False,
                "reason": "The existing independent scorer accepts on target, density and oracle residual gates. The image value is retained as a diagnostic because its MO-gauge interpretation is not a settled acceptance predicate.",
            },
        },
        "unknowns": [
            "compile_jit is not exposed by the official Python API",
            "independent scorer is a separate process and is not included in producer wall time",
            "kernel launch count, occupancy, FLOPs, CUPTI/Nsight and energy were not collected",
            "operator-image diagnostic is retained but is not used as a quality acceptance gate",
        ],
    }
    for arm in ARMS:
        rows = raw[arm]
        totals = {metric: sum(row_metrics(row)[metric] for row in rows) for metric in METRICS}
        quality = [score_by_key[(arm, row["molecule"], row["trajectory"])] for row in rows]
        summary["arms"][arm] = {
            "rows": len(rows),
            "failed": sum(row.get("status") != "accepted" for row in rows),
            "scorer_accepted": sum(row["status"] == "accepted" for row in quality),
            "totals": totals,
            "molecule_count": len(molecule_metrics[arm]),
            "molecule_wall_seconds": molecule_metrics[arm],
            "patch_sha256": json.loads((args.root / "raw" / arm / "run.json").read_text()).get("patch_sha256"),
        }
    for left, right, label in (("A", "C", "official_native_over_gqc"), ("B", "A", "patch_native_over_official_native"), ("D", "C", "patch_gqc_over_official_gqc")):
        summary["paired_effects"][label] = {
            metric: paired_effect(molecule_metrics[left], molecule_metrics[right], metric)
            for metric in METRICS
        }
    interaction = {}
    for metric in METRICS:
        values = [
            (molecule_metrics["D"][key][metric] - molecule_metrics["B"][key][metric])
            - (molecule_metrics["C"][key][metric] - molecule_metrics["A"][key][metric])
            for key in sorted(molecule_metrics["A"])
        ]
        interaction[metric] = {
            "paired_median_difference": statistics.median(values),
            "paired_bootstrap_95ci": bootstrap_median(values),
        }
    summary["paired_effects"]["interaction_(D-B)-(C-A)"] = interaction
    summary["source_sha256"] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for arm in ARMS
        for path in sorted((args.root / "raw" / arm).glob("*.json*"))
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"status": "accepted", "rows": len(scored), "accepted": summary["scorer"]["accepted"]}, indent=2))


if __name__ == "__main__":
    main()
