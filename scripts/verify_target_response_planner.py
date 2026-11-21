#!/usr/bin/env python3
"""Replay planner objective and verify no scorer/oracle leakage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def objective(cost, storage, risk, probability):
    return (cost["seconds"] + 2e-7 * cost["operator_rows"] + 1e-9 * cost["host_device_bytes"]
            + probability * storage * 1e-8 + 1e3 * risk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--planner", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.planner.read_text())
    failures = []
    for decision in result["decisions"]:
        if decision.get("domain") != "in-domain":
            selected = decision["selected"]
            if selected["policy"] != "reject-and-recompute":
                failures.append("OOD policy was not reject-and-recompute")
            continue
        candidates = decision["candidates"]
        for candidate in candidates:
            expected = objective(candidate["cost"], candidate["storage_bytes"], candidate["risk"], candidate["future_request_probability"])
            if abs(expected - candidate["objective"]) > 1e-12:
                failures.append(f"objective mismatch {candidate['molecule']} {candidate['distribution']} {candidate['policy']}")
            if candidate["oracle_loaded"] or candidate["scorer_loaded"]:
                failures.append("truth leakage flag set")
        minimum = min(candidates, key=lambda row: (row["objective"], row["policy"]))
        if decision["selected"]["policy"] != minimum["policy"]:
            failures.append(f"selection mismatch {decision['molecule']} {decision['distribution']}")
    if result.get("oracle_loaded") or result.get("scorer_loaded"):
        failures.append("planner-level truth leakage flag set")
    if failures:
        raise SystemExit("\n".join(failures))
    summary = {"status": "passed", "decisions": len(result["decisions"]), "candidates": result["candidate_count"], "ood_decisions": sum(row.get("domain") != "in-domain" for row in result["decisions"]), "external_inventory_cases": result.get("ood_inventory_count", 0)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
