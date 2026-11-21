#!/usr/bin/env python3
"""Rebuild the attribution table and paired effects from raw four-arm JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from pathlib import Path


ARMS = ("A", "B", "C", "D")


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def geom(values):
    positive = [float(value) for value in values if float(value) > 0]
    return math.exp(sum(math.log(value) for value in positive) / len(positive)) if positive else 0.0


def bootstrap_ci(values, seed=20261122, rounds=4000):
    values = [float(value) for value in values]
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    estimates = []
    for _ in range(rounds):
        sample = [values[rng.randrange(len(values))] for _ in values]
        estimates.append(statistics.median(sample))
    estimates.sort()
    return [estimates[int(0.025 * (len(estimates) - 1))], estimates[int(0.975 * (len(estimates) - 1))]]


def metrics(row):
    response = row.get("response_metrics") or {}
    return {
        "rhs_columns": len(row["fields_computed"]),
        "operator_rows": int(response.get("operator_rows", 0)),
        "quality_operator_rows": int(response.get("quality_operator_rows", 0)),
        "response_seconds": float(response.get("seconds", 0.0)),
        "host_to_device_bytes": int(response.get("host_to_device_bytes", 0)),
        "device_to_host_bytes": int(response.get("device_to_host_bytes", 0)),
        "scf_cycles": int(row.get("scf_cycles", 0)),
        "molecule_seconds": float(row.get("molecule_seconds", 0.0)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--negative-controls", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raw = {arm: rows(args.raw_dir / f"raw-{arm}.jsonl") for arm in ARMS}
    scored = json.loads(args.score.read_text())["rows"]
    score_by_key = {(row["arm"], row["molecule"], row["trajectory"]): row for row in scored}
    summary = {"schema": "vibedataset.attribution_4arm.summary.v1", "arms": {}, "paired_effects": {}, "negative_controls": json.loads(args.negative_controls.read_text())}
    by_key = {arm: {(row["molecule"], row["trajectory"]): row for row in raw[arm]} for arm in ARMS}
    for arm in ARMS:
        totals = {key: 0.0 for key in metrics(raw[arm][0])}
        for row in raw[arm]:
            for key, value in metrics(row).items():
                totals[key] += value
        last_cache = raw[arm][-1].get("cache")
        quality = [score_by_key[(arm, row["molecule"], row["trajectory"])] for row in raw[arm]]
        summary["arms"][arm] = {
            "rows": len(raw[arm]),
            "totals": totals,
            "median_molecule_seconds": statistics.median(row["molecule_seconds"] for row in raw[arm]),
            "geometric_mean_molecule_seconds": geom(row["molecule_seconds"] for row in raw[arm]),
            "max_target_error": max(row["max_target_error"] for row in quality),
            "accepted": sum(row["status"] == "accepted" for row in quality),
            "reject_and_recompute": sum(row["status"] != "accepted" for row in quality),
            "backend_cache_final": last_cache,
        }
    metrics_to_compare = ("rhs_columns", "operator_rows", "quality_operator_rows", "response_seconds", "molecule_seconds", "host_to_device_bytes", "device_to_host_bytes")
    for left, right, label in (("C", "A", "gqc_minus_native_official"), ("B", "A", "modified_minus_official_native"), ("D", "C", "modified_minus_official_gqc")):
        effect = {}
        for metric in metrics_to_compare:
            differences = []
            ratios = []
            for key in sorted(by_key[left]):
                l = metrics(by_key[left][key])[metric]
                r = metrics(by_key[right][key])[metric]
                differences.append(l - r)
                if r > 0:
                    ratios.append(l / r)
            effect[metric] = {"paired_median_difference": statistics.median(differences), "paired_bootstrap_95ci": bootstrap_ci(differences), "geometric_mean_ratio": geom(ratios)}
        summary["paired_effects"][label] = effect
    interaction = {}
    for metric in metrics_to_compare:
        values = []
        for key in sorted(by_key["A"]):
            a = metrics(by_key["A"][key])[metric]
            b = metrics(by_key["B"][key])[metric]
            c = metrics(by_key["C"][key])[metric]
            d = metrics(by_key["D"][key])[metric]
            values.append((d - b) - (c - a))
        interaction[metric] = {"paired_median_difference": statistics.median(values), "paired_bootstrap_95ci": bootstrap_ci(values)}
    summary["paired_effects"]["interaction_(D-B)-(C-A)"] = interaction
    summary["source_sha256"] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(args.raw_dir.glob("raw-*.jsonl"))}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
