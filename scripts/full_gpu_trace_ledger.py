#!/usr/bin/env python3
"""Seal native activity snapshots and replay a per-request timing, resource and quality ledger."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
import random
import statistics
from pathlib import Path
import tempfile

from summarize_request_traces import extract, summarize_file


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packed(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def compress(obj):
    return gzip.compress(
        (
            json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode(),
        mtime=0,
    )


def export(root, source, scores):
    blobs = {}
    for arm in "ABCD":
        for phase in ("cold", "warm"):
            before = source / arm / phase
            key = f"{arm}-{phase}"
            out = root / key
            out.mkdir(parents=True, exist_ok=False)
            with tempfile.TemporaryDirectory() as t:
                combined = Path(t) / "activities.json.gz"
                extract(before, combined)
                data = combined.read_bytes()
            parts = []
            for i, start in enumerate(range(0, len(data), 1024 * 1024)):
                block = data[start : start + 1024 * 1024]
                name = f"activities.{i:02d}.part"
                (out / name).write_bytes(block)
                parts.append(dict(file=name, bytes=len(block), sha256=sha(block)))
            raw = (before / "producer/raw.jsonl").read_bytes()
            (out / "scientific.jsonl.gz").write_bytes(gzip.compress(raw, mtime=0))
            (out / "storage.json.gz").write_bytes(
                compress(json.loads((before / "producer/storage.json").read_bytes()))
            )
            blobs[key] = dict(
                parts=parts, activity_sha256=sha(data), scientific_sha256=sha(raw)
            )
    for phase in ("cold", "warm"):
        (root / f"official-score-{phase}.json.gz").write_bytes(
            gzip.compress((scores / (phase + ".json")).read_bytes(), mtime=0)
        )
        (root / f"cpu-score-{phase}.json.gz").write_bytes(
            (source / f"independent-cpu-{phase}.json.gz").read_bytes()
        )
    (root / "parts.json").write_text(json.dumps(blobs, indent=2) + "\n")


def effects(runs, molecules, phase, seed):
    totals = {}
    for arm in "ABCD":
        rows = runs[f"{arm}-{phase}"]["requests"]
        totals[arm] = [
            math.fsum(
                row["timing"]["end_to_end_wall_seconds"]
                for row in rows
                if row["molecule"] == m
            )
            for m in molecules
        ]
    # Keep all trajectories from the same molecule in every resample.
    samples = {
        key: [] for key in ("A_over_C", "orchestration_s", "patch_s", "interaction_s")
    }
    ratios = [math.log(a / c) for a, c in zip(totals["A"], totals["C"])]
    contrasts = {"orchestration_s": [], "patch_s": [], "interaction_s": []}
    for a, b, c, d in zip(*(totals[k] for k in "ABCD")):
        contrasts["orchestration_s"].append(((c - a) + (d - b)) / 2)
        contrasts["patch_s"].append(((b - a) + (d - c)) / 2)
        contrasts["interaction_s"].append((d - b) - (c - a))
    n = len(ratios)
    rng = random.Random(seed)
    means = {
        "A_over_C": math.exp(math.fsum(ratios) / n),
        **{k: math.fsum(v) / n for k, v in contrasts.items()},
    }
    for _ in range(4000):
        ids = rng.choices(range(n), k=n)
        samples["A_over_C"].append(math.exp(math.fsum(ratios[i] for i in ids) / n))
        for k, values in contrasts.items():
            samples[k].append(math.fsum(values[i] for i in ids) / n)

    def quantile(values, p):
        point = p * (len(values) - 1)
        v = sorted(values)
        lo = math.floor(point)
        return v[lo] + (point - lo) * (v[math.ceil(point)] - v[lo])

    return {
        k: dict(
            estimate=means[k],
            molecule_bootstrap_95ci=[quantile(v, 0.025), quantile(v, 0.975)],
        )
        for k, v in samples.items()
    }


def ledger(root, manifest):
    seals = json.loads((root / "parts.json").read_bytes())
    outputs = {}
    summaries = {}
    by_name = {m["name"]: m for m in manifest["molecules"]}
    requests = [
        (m, q["id"])
        for m in by_name
        for q in sorted(manifest["request_trajectories"], key=lambda x: x["order"])
    ]
    shared_scorers = {}
    for phase in ("cold", "warm"):
        official = packed(root / f"official-score-{phase}.json.gz")
        cpu = packed(root / f"cpu-score-{phase}.json.gz")
        shared_scorers[phase] = dict(
            cpu_s=cpu["full_scorer_seconds"],
            official_gpu_s=official["elapsed_seconds"],
            rows=len(cpu["rows"]),
        )
        checks = {}
        for name, rec in (("official", official), ("independent_cpu", cpu)):
            ix = {(r["arm"], r["molecule"], r["trajectory"]): r for r in rec["rows"]}
            if (
                rec["manifest_sha256"] != manifest["manifest_sha256"]
                or len(ix) != len(rec["rows"])
                or set(ix) != {(a, *q) for a in "ABCD" for q in requests}
            ):
                raise ValueError("missing independent scorer rows")
            checks[name] = ix
        for arm in "ABCD":
            key = f"{arm}-{phase}"
            folder = root / key
            seal = seals[key]
            pieces = []
            for i, v in enumerate(seal["parts"]):
                if v["file"] != f"activities.{i:02d}.part":
                    raise ValueError("invalid activity part order")
                b = (folder / v["file"]).read_bytes()
                if len(b) != v["bytes"] or sha(b) != v["sha256"]:
                    raise ValueError("corrupt activity part")
                pieces.append(b)
            data = b"".join(pieces)
            if sha(data) != seal["activity_sha256"]:
                raise ValueError("corrupt activity stream")
            with tempfile.TemporaryDirectory() as t:
                source = Path(t) / "activity.gz"
                source.write_bytes(data)
                bounded = summarize_file(source, manifest, arm)
            raw = gzip.decompress((folder / "scientific.jsonl.gz").read_bytes())
            if (
                sha(raw) != seal["scientific_sha256"]
                or sha(raw) != cpu["input_files"][arm]
            ):
                raise ValueError("profile and CPU certifier did not see identical rows")
            src = json.loads(gzip.decompress(data))
            if (
                src["scientific_raw_sha256"] != sha(raw)
                or len(src["producer"]["timing_fields"]) != 14
            ):
                raise ValueError("missing timing schema or scientific linkage")
            stored = packed(folder / "storage.json.gz")
            counts = Counter()
            ledger_rows = []
            lines = raw.splitlines()
            events = {r["name"]: r for r in bounded["rows"]}
            if len(lines) != len(requests) or len(stored["rows"]) != len(requests):
                raise ValueError("truncated producer output")
            for line, k, v in zip(lines, requests, stored["rows"]):
                molecule, traj = k
                row = json.loads(line)
                if (
                    row["arm"] != arm
                    or (row["molecule"], row["trajectory"]) != k
                    or (v["molecule"], v["trajectory"]) != k
                    or v["bytes"] != len(line) + 1
                ):
                    raise ValueError("producer/storage identity mismatch")
                if not all(
                    f in row["timing"] for f in src["producer"]["timing_fields"]
                ):
                    raise ValueError("incomplete request timing")
                ev = events[f"request/{molecule}/{traj}"]
                g = checks["official"][(arm, *k)]
                q = checks["independent_cpu"][(arm, *k)]
                line_hash = q.get("raw_line_sha256")
                if line_hash is not None and line_hash != sha(line):
                    raise ValueError(
                        "independent physical certificate refers to a different row"
                    )
                if q["status"] == "accepted" and (
                    line_hash is None
                    or not q.get("metrics")
                    or not all(
                        math.isfinite(z) and 0 <= z <= cpu["threshold"]
                        for z in q["metrics"].values()
                    )
                ):
                    raise ValueError("accepted certificate failed its physical gates")
                times = row["timing"]
                ledger_rows.append(
                    dict(
                        molecule=molecule,
                        trajectory=traj,
                        producer_status=row["status"],
                        timing=times,
                        cp_kernel_launches=ev["kernel_launches"],
                        kernel_time_ns=ev["sum_kernel_ns"],
                        transfer_bytes=ev["transfer_bytes"],
                        transfer_ns=ev["sum_transfer_ns"],
                        cuda_event_seconds=ev["cuda_event_seconds"],
                        nvtx_wall_ns=ev["nvtx_wall_ns"],
                        peak_traced_allocation_bytes=ev[
                            "peak_traced_device_allocation_bytes"
                        ],
                        sampled_board_peak_bytes=ev["sampled_board_memory_peak_bytes"],
                        board_joules=ev["board_energy_joules"],
                        official_quality=g["status"],
                        cpu_quality=q["status"],
                        cpu_validation_seconds=q.get("validation_seconds"),
                        candidate_residual_linf=q.get("metrics", {}).get(
                            "candidate_physical_residual_linf"
                        ),
                        published_bytes=v["bytes"],
                        write_flush_ns=v["write_flush_ns"],
                        serialize_final_ns=v["serialize_ns"],
                    )
                )
                counts[(row["status"], g["status"], q["status"])] += 1
            outputs[key] = dict(
                requests=ledger_rows,
                scf=[e for e in bounded["rows"] if e["name"].startswith("scf/")],
                fsync_queue_ns=stored["queue_fsync_ns"],
            )
            summaries[key] = dict(
                requests=len(lines),
                quality={"/".join(k): v for k, v in counts.items()},
                summed_request_joules=math.fsum(r["board_joules"] for r in ledger_rows),
                summed_request_kernel_launches=sum(
                    r["cp_kernel_launches"] for r in ledger_rows
                ),
                summed_published_bytes=sum(r["published_bytes"] for r in ledger_rows),
                native_report_sha256=src["native_report_sha256"],
                sqlite_sha256=src["sqlite_sha256"],
                pci=bounded["pci"],
                cphf_sha256=src["observer"]["cphf_sha256"],
                queue_fsync_ns=stored["queue_fsync_ns"],
                median_request_producer_s=statistics.median(
                    r["timing"]["end_to_end_wall_seconds"] for r in ledger_rows
                ),
            )
    if len({v["pci"] for v in summaries.values()}) != 1:
        raise ValueError("mixed physical GPU assignment")
    return dict(
        schema="vibedataset.full_queue_profile.v1",
        manifest_sha256=manifest["manifest_sha256"],
        runs=summaries,
        independent_scorers_for_all_four_arms=shared_scorers,
        within_device_producer_effects={
            p: effects(outputs, list(by_name), p, manifest["protocol"]["seed"])
            for p in ("cold", "warm")
            if all(
                summaries[f"{arm}-{p}"]["quality"]
                == {"accepted/accepted/accepted": len(requests)}
                for arm in "ABCD"
            )
        },
        attained_occupancy=None,
        hardware_flop_count=None,
        standalone_jit_seconds=None,
        scope="cold/warm disk cache, fresh processes, per-request CUPTI activity and board energy. Queue fsync and fresh scorer elapsed are separately reported.",
    ), outputs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--extract", type=Path)
    p.add_argument("--scores", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--rows", type=Path, required=True)
    a = p.parse_args()
    if a.extract:
        if not a.scores:
            p.error("--scores is required for extraction")
        export(a.root, a.extract, a.scores)
    summary, rows = ledger(a.root, json.loads(a.manifest.read_bytes()))
    a.out.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    a.rows.write_bytes(compress(rows))


if __name__ == "__main__":
    main()
