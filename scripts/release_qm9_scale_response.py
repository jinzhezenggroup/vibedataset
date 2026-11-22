#!/usr/bin/env python3
"""Publish complete request-level labels, reference certificates, attempts and storage costs."""

import argparse
from collections import Counter
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import tarfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def load(path):
    return json.loads(path.read_bytes())


def read_run(root, phase):
    result = {}
    runs = {}
    for logfile in sorted(root.glob(phase + "-*.jsonl")):
        records = [json.loads(line) for line in logfile.read_bytes().splitlines()]
        head, tail = records[0], records[-1]
        if head["event"] != "run-start" or tail["event"] != "run-finished":
            raise ValueError(f"unfinished shard: {logfile}")
        first = {r["request_id"]: r for r in records if r["event"] == "started"}
        terminal = {r["request_id"]: r for r in records if r["event"] == "finished"}
        expected = {
            f"qm9-scale-{i:06d}" for i in range(head["start"], head["stop"] + 1)
        }
        if (
            set(terminal) != expected
            or set(first) != expected
            or len(records) != 2 + 2 * len(expected)
            or set(result) & expected
        ):
            raise ValueError("duplicated or missing attempt")
        key = digest(logfile.read_bytes())
        runs[key] = dict(phase=phase, inputs=head, elapsed_s=tail["elapsed_seconds"])
        for req in expected:
            receipt = root / req / "receipt.json"
            r = load(receipt)
            if (
                r["run"] != logfile.name
                or first[req]["input_sha256"] != r["input_sha256"]
                or terminal[req]["status"] != r["status"]
            ):
                raise ValueError("terminal receipt identity mismatch")
            result[req] = (r, terminal[req], key, root / req)
    return result, runs


def collect(paths, phase):
    rows = {}
    runs = {}
    for path in paths:
        if not path.is_dir():
            raise ValueError(f"missing {phase} data: {path}")
        items, logs = read_run(path, phase)
        if rows.keys() & items.keys():
            raise ValueError("same request attempted twice in a single generation")
        rows.update(items)
        runs.update(logs)
    return rows, runs


def check_asset(row, folder):
    if row["status"] == "computed":
        asset = folder / "arrays.npz"
        if (
            asset.stat().st_size != row["arrays_bytes"]
            or digest(asset.read_bytes()) != row["arrays_sha256"]
        ):
            raise ValueError(f"corrupt array: {asset}")


def percentile(v, p):
    v = sorted(v)
    k = (len(v) - 1) * p
    return v[math.floor(k)] + (v[math.ceil(k)] - v[math.floor(k)]) * (k - math.floor(k))


def package(tar, dest, data):
    entry = tarfile.TarInfo(dest)
    entry.size = len(data)
    entry.mode = 0o644
    entry.mtime = 0
    tar.addfile(entry, io.BytesIO(data))


def write_outputs(a):
    protocol = load(a.protocol)
    seal = digest(a.protocol.read_bytes())
    geometry_bytes = a.geometries.read_bytes()
    if digest(geometry_bytes) != protocol["geometry_file_sha256"]:
        raise ValueError("geometry digest")
    geometry = json.loads(gzip.decompress(geometry_bytes))["rows"]
    frozen = [
        json.loads(x) for x in gzip.decompress(a.requests.read_bytes()).splitlines()
    ]
    expected = {r["request_id"] for r in frozen}
    if (
        len(geometry) != len(frozen)
        or len(expected) != len(frozen)
        or len(expected) != protocol["request_count"]
        or [r["request_id"] for r in geometry] != [r["request_id"] for r in frozen]
    ):
        raise ValueError("frozen denominator")
    refs, ref_runs = collect([a.references], "reference")
    candidates, gpu_runs = collect(a.primary, "produce")
    initial, score_runs = collect([a.scores], "score")
    if set(refs) != expected or set(candidates) != expected or set(initial) != expected:
        raise ValueError("incomplete primary campaign")
    generations = [(candidates, initial)]
    runs = {**ref_runs, **gpu_runs, **score_runs}
    for candidate_root, score_root in a.retry:
        cand, run = collect([Path(candidate_root)], "produce")
        scored, scorer = collect([Path(score_root)], "score")
        if set(cand) != set(scored) or set(cand) - expected:
            raise ValueError("incomplete retry coverage")
        generations.append((cand, scored))
        runs.update(run)
        runs.update(scorer)
    out = a.out
    out.mkdir(parents=True, exist_ok=False)
    ledger = []
    labels = []
    stats = Counter()
    reads = []
    worst = {}
    publish = []
    for request, item in zip(frozen, geometry):
        rid = request["request_id"]
        expected_input = request["input_sha256"]
        requested_geometry = {
            k: item[k]
            for k in ("request_id", "member_sha256", "atoms", "unit", "charge", "spin")
        }
        if (
            request["protocol_sha256"] != seal
            or request["member_sha256"] != item["member_sha256"]
            or expected_input
            != digest(encode(dict(geometry=requested_geometry, protocol_sha256=seal)))
        ):
            raise ValueError("request does not match its frozen input")
        ref, rf_end, ref_run, rf_dir = refs[rid]
        if ref["input_sha256"] != expected_input or ref["protocol_sha256"] != seal:
            raise ValueError("unrelated reference")
        check_asset(ref, rf_dir)
        attempts = []
        prior = None
        for index, (crow, srow) in enumerate(generations):
            if rid not in crow:
                continue
            if prior == "accepted":
                raise ValueError("accepted primary request was selected for retry")
            c, ct, cr, folder = crow[rid]
            q, qt, qr, qfolder = srow[rid]
            if any(
                r["request_id"] != rid
                or r["input_sha256"] != expected_input
                or r["protocol_sha256"] != seal
                for r in (c, q)
            ) or c["retry"] != (index > 0):
                raise ValueError("producer or independent scorer identity mismatch")
            check_asset(c, folder)
            decision = q["status"]
            if decision in ("accepted", "reject-and-recompute") and "errors" in q:
                if (
                    q["candidate_sha256"] != c["arrays_sha256"]
                    or q["reference_sha256"] != ref["arrays_sha256"]
                    or q["basis_parameters_sha256"] != c["basis_parameters_sha256"]
                    or ref["basis_parameters_sha256"] != c["basis_parameters_sha256"]
                ):
                    raise ValueError(
                        "certificate does not belong to the supplied arrays"
                    )
                errors = q["errors"]
                limits = protocol["maximum_absolute_error"]
                if set(errors) != set(limits) or not all(
                    math.isfinite(v) and v >= 0 for v in errors.values()
                ):
                    raise ValueError("incomplete or nonfinite quality evidence")
                failed = {k for k in limits if errors[k] > limits[k]}
                if failed != set(q["failed_gates"]) or (decision == "accepted") != (
                    not failed
                ):
                    raise ValueError("acceptance inconsistent with frozen tolerances")
                if decision == "accepted":
                    alpha = q["polarizability_au"]
                    oracle = q["reference_polarizability_au"]
                    if (
                        len(alpha) != 3
                        or len(oracle) != 3
                        or any(len(v) != 3 for v in alpha + oracle)
                        or not math.isclose(
                            max(
                                abs(x - y)
                                for xs, ys in zip(alpha, oracle)
                                for x, y in zip(xs, ys)
                            ),
                            errors["polarizability"],
                            abs_tol=1e-13,
                            rel_tol=1e-12,
                        )
                    ):
                        raise ValueError("invalid tensor certificate")
            elif decision == "accepted":
                raise ValueError("acceptance without physical evidence")
            attempts.append(
                dict(
                    generation=index,
                    producer_status=c["status"],
                    decision=decision,
                    rejected_gates=q.get("failed_gates", []),
                    reason=q.get("reason", c.get("reason")),
                    producer_job=runs[cr]["inputs"]["identity"]["slurm_job"],
                    producer_journal_sha256=cr,
                    scorer_journal_sha256=qr,
                    producer_array_sha256=c.get("arrays_sha256"),
                    errors=q.get("errors"),
                    producer_wall_s=ct["wall_seconds"],
                    scorer_wall_s=qt["wall_seconds"],
                    scf_s=c.get("scf_seconds"),
                    solve_and_verify_s=c.get("solve_and_check_seconds"),
                    readout_s=c.get("readout_seconds"),
                    prepare_s=c.get("prepare_seconds"),
                    serialize_and_store_s=c.get("serialize_store_seconds"),
                    producer_asset_bytes=c.get("arrays_bytes", 0),
                    producer_receipt_bytes=ct["receipt_bytes"],
                    scorer_receipt_bytes=qt["receipt_bytes"],
                    correction_history=c.get("retry_fp64_residual_history", []),
                )
            )
            publish.append((f"attempt-{index}/{rid}/producer", folder))
            publish.append((f"attempt-{index}/{rid}/scorer", qfolder))
            prior = decision
        publish.append((f"reference/{rid}", rf_dir))
        stats["requested"] += 1
        stats["attempts"] += len(attempts)
        stats["first_" + attempts[0]["decision"]] += 1
        stats["final_" + prior] += 1
        stats["recomputed_requests"] += int(len(attempts) > 1)
        stats["recomputations"] += len(attempts) - 1
        label = dict(
            request_id=rid,
            input_sha256=expected_input,
            geometry_member_sha256=item["member_sha256"],
            protocol_sha256=seal,
            disposition=prior,
            attempt_count=len(attempts),
            missing_label=prior != "accepted",
        )
        if prior == "accepted":
            label.update(
                basis_parameters_sha256=q["basis_parameters_sha256"],
                rhs_sha256=q["rhs_sha256"],
                operator_identity_sha256=digest(
                    encode(
                        {
                            "input": expected_input,
                            "basis": q["basis_parameters_sha256"],
                            "property": protocol["definition"],
                        }
                    )
                ),
                solution_sha256=q["candidate_amplitudes_sha256"],
                candidate_sha256=q["candidate_sha256"],
                independent_reference_sha256=q["reference_sha256"],
                polarizability_au=alpha,
                independent_polarizability_au=oracle,
                quality_errors=errors,
                orbital_gap_hartree=q["gap_hartree"],
                scorer_receipt_sha256=digest((qfolder / "receipt.json").read_bytes()),
            )
            for key, v in errors.items():
                if key not in worst or v > worst[key]["value"]:
                    worst[key] = dict(request_id=rid, value=v)
        labels.append(label)
        reads.append(
            sum(v["producer_wall_s"] + v["scorer_wall_s"] for v in attempts)
            + rf_end["wall_seconds"]
        )
        ledger.append(
            dict(
                request_id=rid,
                reference_journal_sha256=ref_run,
                cpu_reference_s=rf_end["wall_seconds"],
                cpu_reference_bytes=ref.get("arrays_bytes", 0),
                reference_receipt_bytes=rf_end["receipt_bytes"],
                attempts=attempts,
            )
        )
    for name, data in (("labels", labels), ("cost-and-failures", ledger)):
        (out / (name + ".jsonl.gz")).write_bytes(
            gzip.compress(b"".join(encode(r) + b"\n" for r in data), mtime=0)
        )
    (out / "runs.json.gz").write_bytes(gzip.compress(encode(runs), mtime=0))
    summary = dict(
        schema="vibedataset.certified_qm9_response_release.v1",
        protocol_sha256=seal,
        counts=dict(stats),
        input_geometry_sha256=digest(geometry_bytes),
        requests_sha256=digest(a.requests.read_bytes()),
        worst_accepted_errors=worst,
        median_total_request_work_s=percentile(reads, 0.5),
        p95_total_request_work_s=percentile(reads, 0.95),
        summed_request_work_s=math.fsum(reads),
        cost_semantics="sum of primary, retries, separate independent CPU reference and scoring; excludes scheduler queue waits, captures per-process startup in run journals; embedded JIT/transfers and future amortization are not separately identifiable",
        artifacts={p.name: digest(p.read_bytes()) for p in sorted(out.glob("*.gz"))},
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if a.raw_tar:
        with (
            a.raw_tar.open("xb") as fd,
            gzip.GzipFile(
                fileobj=fd, mode="wb", filename="", mtime=0, compresslevel=2
            ) as gz,
            tarfile.open(fileobj=gz, mode="w|") as tar,
        ):
            for name, folder in publish:
                for p in sorted(folder.iterdir()):
                    if p.name in ("arrays.npz", "receipt.json"):
                        package(tar, name + "/" + p.name, p.read_bytes())
            for f in sorted(out.iterdir()):
                package(tar, "release/" + f.name, f.read_bytes())
            for p in (a.requests, a.protocol, a.geometries):
                package(tar, "inputs/" + p.name, p.read_bytes())
            for key in sorted(runs):
                package(tar, "run-identities/" + key + ".json", encode(runs[key]))
        (out / "raw-bundle.json").write_text(
            json.dumps(
                dict(
                    filename=a.raw_tar.name,
                    bytes=a.raw_tar.stat().st_size,
                    sha256=digest(a.raw_tar.read_bytes()),
                ),
                indent=2,
            )
            + "\n"
        )
    print(json.dumps(summary["counts"]))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("geometries", "protocol", "requests", "references", "scores", "out"):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument(
        "--primary",
        nargs="+",
        type=Path,
        required=True,
        help="finished nonoverlapping GPU shard directories",
    )
    p.add_argument(
        "--retry",
        nargs=2,
        metavar=("PRODUCER_DIRECTORY", "SCORE_DIRECTORY"),
        action="append",
        default=[],
    )
    p.add_argument("--raw-tar", type=Path)
    write_outputs(p.parse_args())


if __name__ == "__main__":
    main()
