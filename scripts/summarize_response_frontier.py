#!/usr/bin/env python3
"""Validate the full 15-case denominator and summarize archived CPU/GPU measurements."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path


def read(p):
    return json.loads(p.read_bytes())


def session(directory, spec):
    score = read(directory / "independent.json")
    cases = [c["id"] for c in spec["cases"]]
    expected = {(mode, case) for mode in spec["modes"] for case in cases}
    rows = {(r["mode"], r["case"]): r for r in score["rows"]}
    if set(rows) != expected or len(rows) != len(score["rows"]):
        raise ValueError("independent score denominator")
    result = {}
    for mode in spec["modes"]:
        records = []
        quality = []
        storage = 0
        run = read(directory / mode / "run.json")
        if (
            run["mode"] != mode
            or run["cases"] != len(cases)
            or (mode == "cold" and run["source_raw_sha256"] is not None)
        ):
            raise ValueError("producer identity")
        for case in spec["cases"]:
            p = directory / mode / (case["id"] + ".json.gz")
            data = gzip.decompress(p.read_bytes())
            raw = json.loads(data)
            cert = rows[mode, case["id"]]
            if hashlib.sha256(data).hexdigest() != cert["candidate_sha256"]:
                raise ValueError("independent score linked to different raw output")
            unavailable = case["change"] == "open-shell"
            if cert["status"] != (
                "evidence-unavailable" if unavailable else "accepted"
            ):
                raise ValueError("scope or certificate mismatch")
            if not unavailable:
                limits = spec["limits"]
                errors = cert["errors"]
                for metric, gate in (
                    ("physical_residual_linf", "cpu_residual_linf"),
                    ("reference_residual_linf", "cpu_oracle_linf"),
                    ("ao_linf", "ao_linf"),
                    ("tangent_linf", "ao_linf"),
                    ("readout_linf", "readout_linf"),
                    ("readout_vs_density", "readout_linf"),
                ):
                    if (
                        not math.isfinite(errors[metric])
                        or errors[metric] > limits[gate]
                    ):
                        raise ValueError("failed physical gate")
            if mode == "planned":
                expected_action = {
                    "exact": "direct_reuse",
                    "split-valence": "refine_required",
                    "hybrid-functional": "refine_required",
                }.get(case["change"], "reject-and-recompute")
                if raw["action"] != expected_action or (
                    expected_action == "direct_reuse"
                    and raw["attempted_target_solves"] != 0
                    or expected_action != "direct_reuse"
                    and not unavailable
                    and raw["attempted_target_solves"] < 1
                ):
                    raise ValueError("missing actual disposition or target solve")
            records.append(raw)
            quality.append(cert)
            storage += p.stat().st_size
        accepted = [r for r in quality if r["status"] == "accepted"]
        result[mode] = dict(
            requested=len(quality),
            quality=dict(Counter(r["status"] for r in quality)),
            solver_rows=sum(r.get("solver_operator_rows", 0) for r in records),
            actions=dict(Counter(r["action"] for r in records)),
            max_absolute_cpu_readout_error=max(
                r["errors"]["readout_linf"] for r in accepted
            ),
            physical_residual_max=max(
                r["errors"]["physical_residual_linf"] for r in accepted
            ),
            max_condition=max(r["condition"] for r in accepted),
            elapsed_in_process_s=run["elapsed_seconds"],
            bytes_serialized=storage,
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    spec = read(a.root / "protocol.json")
    pairs = a.root / "counterbalanced"
    report = dict(
        schema="vibedataset.bounded_frontier_summary.v1",
        pilot=session(a.root / "pilot", spec),
        pairs=[session(pairs / f"rep-{i}", spec) for i in (1, 2)],
    )
    lines = (pairs / "process-wall-ns.txt").read_text().splitlines()
    if len(lines) != 4:
        raise ValueError("incomplete order comparison")
    for index, line in enumerate(lines):
        i, mode, start, end = line.split()
        if (
            int(i) != index
            or mode != ("cold", "planned", "planned", "cold")[index]
            or int(end) <= int(start)
        ):
            raise ValueError("invalid external process envelope")
        report["pairs"][index // 2][mode]["external_wall_seconds"] = (
            int(end) - int(start)
        ) / 1e9
    a.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
