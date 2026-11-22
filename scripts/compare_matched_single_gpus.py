#!/usr/bin/env python3
"""Compare A/B/C/D within each device using complete matched molecule trajectories."""

import argparse
import gzip
import hashlib
import json
import math
import random
import statistics
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def lines(path):
    return [
        json.loads(line) for line in gzip.decompress(path.read_bytes()).splitlines()
    ]


def percentile(values, p):
    ordered = sorted(values)
    position = p * (len(ordered) - 1)
    lo, hi = math.floor(position), math.ceil(position)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def effect(left, right, seed):
    logs = [math.log(x / y) for x, y in zip(left, right)]
    rng = random.Random(seed)
    samples = [
        math.exp(math.fsum(rng.choices(logs, k=len(logs))) / len(logs))
        for _ in range(4000)
    ]
    return {
        "geometric_mean": math.exp(math.fsum(logs) / len(logs)),
        "molecule_paired_bootstrap_95ci": [
            percentile(samples, 0.025),
            percentile(samples, 0.975),
        ],
    }


def cpu_quality(root, manifest, expected):
    record = json.loads(gzip.decompress((root / "cpu-ao-score.json.gz").read_bytes()))
    rows = record["rows"]
    keys = {(r["arm"], r["molecule"], r["trajectory"]) for r in rows}
    expected_keys = {(arm, *key) for arm in "ABCD" for key in expected}
    if (
        record["manifest_sha256"] != manifest["manifest_sha256"]
        or keys != expected_keys
        or len(rows) != len(keys)
        or record["threshold"] != 1e-5
        or record["pyscf"] != "2.14.0"
    ):
        raise ValueError("unmatched independent CPU scorer")
    raw_hashes = {}
    for arm in "ABCD":
        raw = gzip.decompress((root / f"raw-{arm}.jsonl.gz").read_bytes())
        if hashlib.sha256(raw).hexdigest() != record["input_files"][arm]:
            raise ValueError("CPU scorer received different raw output")
        for line in raw.splitlines():
            item = json.loads(line)
            raw_hashes[arm, item["molecule"], item["trajectory"]] = hashlib.sha256(
                line
            ).hexdigest()
    accepted = [r for r in rows if r["status"] == "accepted"]
    for row in accepted:
        if (
            row["raw_line_sha256"]
            != raw_hashes[row["arm"], row["molecule"], row["trajectory"]]
            or not row.get("metrics")
            or any(
                not math.isfinite(x) or x > record["threshold"]
                for x in row["metrics"].values()
            )
        ):
            raise ValueError("invalid accepted physical certificate")
    controls = record["negative_controls"]
    if set(controls) != {
        "truncated_density",
        "nan_density",
        "wrong_finite_density",
        "wrong_readout",
        "wrong_unit",
        "wrong_rhs",
    } or any(v["status"] != "reject-and-recompute" for v in controls.values()):
        raise ValueError("missing physical negative controls")
    return dict(
        scored=len(rows),
        accepted=len(accepted),
        rejected=len(rows) - len(accepted),
        seconds=record["full_scorer_seconds"],
        physical_controls_rejected=len(controls),
        maximum_accepted_candidate_residual=max(
            (r["metrics"]["candidate_physical_residual_linf"] for r in accepted),
            default=None,
        ),
    )


def device(root, manifest):
    identity = read(root / "identity.json")
    score = json.loads(gzip.decompress((root / "score.json.gz").read_bytes()))
    names = [m["name"] for m in manifest["molecules"]]
    requests = [
        r["id"]
        for r in sorted(manifest["request_trajectories"], key=lambda r: r["order"])
    ]
    expected = [(name, request) for name in names for request in requests]
    scores = {(r["arm"], r["molecule"], r["trajectory"]): r for r in score["rows"]}
    if (
        score["manifest_sha256"] != manifest["manifest_sha256"]
        or len(scores) != len(score["rows"])
        or set(scores) != {(a, *key) for a in "ABCD" for key in expected}
    ):
        raise ValueError("incomplete or unmatched independent scorer")
    cpu = cpu_quality(root, manifest, expected)
    totals = {}
    times = {}
    eligible = cpu["rejected"] == 0
    for arm in "ABCD":
        run = read(root / f"run-{arm}.json")
        rows = lines(root / f"raw-{arm}.jsonl.gz")
        if (
            run["arm"] != arm
            or run["manifest_sha256"] != manifest["manifest_sha256"]
            or run["record_count"] != len(rows)
            or [(r["molecule"], r["trajectory"]) for r in rows] != expected
            or any(
                r["arm"] != arm
                or r["protocol"] != manifest["protocol"]
                or r["input_sha256"] != manifest["manifest_sha256"]
                for r in rows
            )
        ):
            raise ValueError(f"{identity['gpu']}/{arm}: unmatched inputs")
        registered = (
            "dad0f28af59dc9dca2fc3c0c78f73920ae4f5593bc2d50408fc02153293679d5"
            if arm in "BD"
            else None
        )
        if (
            run["patch_sha256"] != registered
            or run["device"]["cuda_name"] != identity["gpu"]
            or run["gpu4pyscf_source_commit"]
            != "8536a80c1e03260aab030e108ef1d181a3709057"
            or not run["blind"]
            or run["oracle_loaded"]
            or run["scorer_loaded"]
        ):
            raise ValueError("backend/device identity")
        wall = [r["timing"]["end_to_end_wall_seconds"] for r in rows]
        if any(not math.isfinite(x) or x <= 0 for x in wall):
            raise ValueError("invalid producer wall time")
        failures = sum(r["status"] != "accepted" for r in rows)
        rejected = sum(scores[(arm, *key)]["status"] != "accepted" for key in expected)
        if failures != run["failed_count"]:
            raise ValueError("inconsistent producer failure count")
        eligible = eligible and not failures and not rejected
        times[arm] = [
            math.fsum(x for row, x in zip(rows, wall) if row["molecule"] == name)
            for name in names
        ]
        totals[arm] = dict(
            requested=len(rows),
            produced=len(rows) - failures,
            failures=failures,
            scorer_rejected=rejected,
            request_wall_sum_s=math.fsum(wall),
            median_request_s=statistics.median(wall),
            p95_request_s=percentile(wall, 0.95),
            producer_elapsed_s=run["elapsed_seconds"],
            producer_rate_rows_per_s=len(rows) / run["elapsed_seconds"],
        )
    pairs = {}
    if eligible:
        for base, other in (("A", "C"), ("B", "A"), ("D", "C")):
            pairs[f"{base}/{other}"] = effect(
                times[base], times[other], manifest["protocol"]["seed"]
            )
    return dict(
        identity=identity,
        rows_scored=len(scores),
        quality_eligible=bool(eligible),
        arms=totals,
        within_device_molecule_time_ratios=pairs,
        fresh_scorer_seconds=score["elapsed_seconds"],
        independent_cpu=cpu,
        max_target_error=max(
            (
                row["max_target_error"]
                for row in scores.values()
                if row.get("max_target_error") is not None
            ),
            default=None,
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    manifest = read(args.manifest)
    body = dict(manifest)
    seal = body.pop("manifest_sha256")
    if (
        hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        != seal
    ):
        raise ValueError("manifest seal")
    boards = {
        name: device(args.root / name, manifest) for name in ("rtx5090", "pro6000")
    }
    one, two = [value["identity"] for value in boards.values()]
    for key in (
        "wheel_sha256",
        "source_sha256",
        "gpu4pyscf",
        "cupy",
        "cublas",
        "pyscf",
        "cuda_runtime",
        "python",
        "engine",
    ):
        if one[key] != two[key]:
            raise ValueError(f"unmatched runtime field: {key}")
    if one["gpu"] == two["gpu"]:
        raise ValueError("expected two different GPU models")
    result = dict(
        schema="vibedataset.single_gpu_pairs.v1",
        manifest_sha256=seal,
        boards=boards,
        scope="one run per arm per device; molecules are resampled as complete three-request blocks",
        metric="producer request wall, including allocated setup and SCF but excluding the fresh scorer and final publication",
        bootstrap_unit="molecule",
        bootstrap_rounds=4000,
        seed=manifest["protocol"]["seed"],
        ten_x_producer_threshold_met=all(
            b["quality_eligible"]
            and b["within_device_molecule_time_ratios"]["A/C"]["geometric_mean"] >= 10
            for b in boards.values()
        ),
    )
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                n: b["within_device_molecule_time_ratios"].get("A/C")
                for n, b in boards.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
