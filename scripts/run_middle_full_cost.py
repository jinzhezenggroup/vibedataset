#!/usr/bin/env python3
"""Produce, physically score and durably publish the frozen six-pass request queue."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np

from build_benchmark_contract import geometry_hash
from run_gpu4pyscf_4arm import build_molecule, load_manifest
from run_gpu4pyscf_4arm_telemetry import (
    density_values,
    memory_snapshot,
    solve_response,
    target_values,
)


QUEUE_SHA = "321e1db971d74d2643712396746282a90aadba32096daf7d9635fc214cb8b989"
OFFICIAL = "1010af1ff5cb62e424223e6c65bad9344e7a6e37bf6882ff574efddb9e2839de"
PATCHED = "e945d59c4b19a5b183af2e4651caf2bb9276dc807079b8c060bb6490854a4d6a"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def flush(handle, row):
    handle.write(encode(row) + b"\n")
    handle.flush()
    os.fsync(handle.fileno())


def produce(args, manifest, items, queue):
    import cupy as cp
    from gpu4pyscf import scf
    import gpu4pyscf
    from gpu4pyscf.properties import polarizability
    from gpu4pyscf.scf import cphf
    from pyscf import gto

    patch = args.arm in "BD"
    cache_class = None
    if patch:
        from gpu4pyscf.lib.response_cache import ResponseOperatorCache

        cache_class = ResponseOperatorCache
    solver = sha(Path(cphf.__file__).read_bytes())
    if (
        solver != (PATCHED if patch else OFFICIAL)
        or gpu4pyscf.__version__ != "1.9.2"
        or cp.cuda.runtime.getDeviceCount() != 1
    ):
        raise ValueError("arm or allocated GPU mismatch")
    protocol = manifest["protocol"]
    states = {}
    assets = {}
    caches = {}
    ledger = []
    begin = time.perf_counter()
    known = {
        (tuple(t["fields"]), tuple(t["targets"])): t
        for t in manifest["request_trajectories"]
    }
    with (
        (args.out / "attempts.jsonl").open("xb") as j,
        (args.out / "scientific.jsonl").open("xb") as raw,
    ):
        for request in queue:
            tick = time.perf_counter()
            rid, name = request["request_id"], request["name"]
            m = items[name]
            flush(j, dict(request_id=rid, event="started", unix_time=time.time()))
            row = dict(
                request_id=rid,
                arm=args.arm,
                molecule=name,
                qm9_id=m["qm9_id"],
                protocol=protocol,
                input_sha256=manifest["manifest_sha256"],
                queue_repeat=request["queue_repeat"],
            )
            times = dict(
                prepare_s=0.0,
                scf_s=0.0,
                retry_s=0.0,
                fallback_s=0.0,
                compile_jit_s=None,
            )
            try:
                check = time.perf_counter()
                fields = request["fields"]
                targets = request["targets"]
                trajectory = known[(tuple(fields), tuple(targets))]
                if (
                    request["geometry_hash"] != geometry_hash(m)
                    or request["atomic_numbers"] != m["atomic_numbers"]
                    or request["coordinates_bohr"] != m["coordinates_bohr"]
                    or request["charge"] != m["charge"]
                    or request["spin"] != m["multiplicity"] - 1
                    or request["convergence"]
                    != {
                        "response": protocol["response_tol"],
                        "scf": protocol["conv_tol"],
                    }
                    or any(
                        request[k] != protocol[k]
                        for k in (
                            "basis",
                            "method",
                            "precision",
                            "origin",
                            "unit",
                            "basis_representation",
                        )
                    )
                    or request["source_kind"] != "controlled-request"
                    or rid
                    != f"middle-{request['queue_repeat']:02d}-{name}-{trajectory['id']}"
                ):
                    raise ValueError("queue protocol mismatch")
                times["protocol_match_s"] = time.perf_counter() - check
                if name not in states:
                    prepare = time.perf_counter()
                    mol = build_molecule(gto, m, protocol)
                    mf = scf.RHF(mol)
                    mf.conv_tol = protocol["conv_tol"]
                    mf.max_cycle = protocol["max_cycle"]
                    times["prepare_s"] = time.perf_counter() - prepare
                    sc = time.perf_counter()
                    mf.kernel()
                    cp.cuda.Stream.null.synchronize()
                    times["scf_s"] = time.perf_counter() - sc
                    if not mf.converged:
                        raise RuntimeError("SCF did not converge")
                    states[name] = mf
                    caches[name] = cache_class() if cache_class else None
                    assets[name] = {}
                mf = states[name]
                reuse = assets[name] if args.arm in "CD" else {}
                missing = [f for f in fields if f not in reuse]
                solve = time.perf_counter()
                stats = None
                if missing:
                    stats = solve_response(
                        cp,
                        cphf,
                        polarizability,
                        mf,
                        ["xyz".index(f) for f in missing],
                        protocol["response_tol"],
                        protocol["response_max_cycle"],
                        caches[name],
                    )
                    reuse.update(stats["vectors"])
                times["solve_path_s"] = time.perf_counter() - solve
                vectors = {f: cp.asarray(reuse[f]) for f in fields}
                readout = time.perf_counter()
                values = target_values(cp, mf, vectors, targets)
                dm = density_values(cp, mf, vectors)
                cp.cuda.Stream.null.synchronize()
                times["readout_d2h_s"] = time.perf_counter() - readout
                row.update(
                    status="accepted",
                    trajectory=trajectory["id"],
                    fields_requested=fields,
                    fields_computed=missing,
                    fields_reused=[f for f in fields if f not in missing],
                    operator_calls=stats["operator_calls"] if stats else 0,
                    operator_rows=stats["operator_rows"] if stats else 0,
                    physical_check_preconditioned_linf=stats["residual_linf"]
                    if stats
                    else None,
                    targets=values,
                    response_densities={f: m.ravel().tolist() for f, m in dm.items()},
                )
            except (KeyError, ValueError, RuntimeError, MemoryError) as exc:
                row.update(status="failed", reason=type(exc).__name__ + ": " + str(exc))
            serial = time.perf_counter()
            payload = encode(row) + b"\n"
            times["serialize_s"] = time.perf_counter() - serial
            store = time.perf_counter()
            raw.write(payload)
            raw.flush()
            os.fsync(raw.fileno())
            times["candidate_write_fsync_s"] = time.perf_counter() - store
            memory = memory_snapshot(cp)
            ledger.append(
                dict(
                    request_id=rid,
                    molecule=name,
                    repeat=request["queue_repeat"],
                    candidate_sha256=sha(payload.rstrip(b"\n")),
                    candidate_bytes=len(payload),
                    phases=times,
                    memory=memory,
                    wall_s=time.perf_counter() - tick,
                )
            )
            flush(j, dict(request_id=rid, event="finished", status=row["status"]))
    (args.out / "producer-ledger.json.gz").write_bytes(
        gzip.compress(encode(ledger), mtime=0)
    )
    return dict(
        solver_sha256=solver,
        compiled_package=gpu4pyscf.__version__,
        gpu=cp.cuda.runtime.getDeviceProperties(0)["name"].decode(),
        pci=cp.cuda.Device().pci_bus_id,
        retained_scf_states=len(states),
        producer_path_s=time.perf_counter() - begin,
        raw_sha256=sha((args.out / "scientific.jsonl").read_bytes()),
        candidate_rows=len(ledger),
    )


def certify(args, manifest, items, queue):
    from score_ao_density_response import reference, score

    exp = args.out
    refs = {}
    ref_cost = {}
    labels = []
    start = time.perf_counter()
    by_id = {t["id"]: t for t in manifest["request_trajectories"]}
    science = (exp / "scientific.jsonl").read_bytes()
    observed = science.splitlines()
    ledger = json.loads(gzip.decompress((exp / "producer-ledger.json.gz").read_bytes()))
    if len(observed) != len(queue) or len(ledger) != len(queue):
        raise ValueError("producer denominator")
    for raw, plan, entry in zip(observed, queue, ledger):
        row = json.loads(raw)
        name = plan["name"]
        rid = plan["request_id"]
        if (
            row["request_id"] != rid
            or row["molecule"] != name
            or row["arm"] != args.arm
            or entry["candidate_sha256"] != sha(raw)
            or entry["request_id"] != rid
        ):
            raise ValueError("misbound candidate")
        if name not in refs:
            t = time.perf_counter()
            refs[name] = reference(items[name], manifest["protocol"])
            ref_cost[name] = time.perf_counter() - t
        t = time.perf_counter()
        quality = (
            score(row, by_id[row["trajectory"]], manifest, refs[name])
            if row["status"] == "accepted"
            else dict(status="reject-and-recompute", reason=row["reason"])
        )
        labels.append(
            dict(
                request_id=rid,
                repeat=plan["queue_repeat"],
                molecule=name,
                status=quality["status"],
                quality=quality,
                geometry_sha256=plan["geometry_hash"],
                candidate_sha256=sha(raw),
                validation_s=time.perf_counter() - t,
                targets=row.get("targets") if quality["status"] == "accepted" else None,
            )
        )
    data = gzip.compress(b"".join(encode(r) + b"\n" for r in labels), mtime=0)
    with (exp / "published.jsonl.gz").open("xb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    with (exp / "scientific.jsonl.gz").open("xb") as out:
        out.write(gzip.compress(science, mtime=0))
        out.flush()
        os.fsync(out.fileno())
    return dict(
        counts=dict(Counter(l["status"] for l in labels)),
        fresh_reference_seconds=ref_cost,
        independent_scorer_and_publication_s=time.perf_counter() - start,
        labels_sha256=sha(data),
        label_bytes=len(data),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("produce", "certify"))
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--queue", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--arm", choices=list("ABCD"), required=True)
    p.add_argument("--pilot", action="store_true")
    a = p.parse_args()
    tick = time.perf_counter()
    m = load_manifest(a.manifest)
    data = a.queue.read_bytes()
    if sha(data) != QUEUE_SHA:
        raise ValueError("wrong frozen queue")
    planned = [json.loads(l) for l in data.splitlines()]
    if len(planned) != 306 or len({v["request_id"] for v in planned}) != 306:
        raise ValueError("invalid 306-row queue")
    if a.pilot:
        planned = planned[:3]
    items = {v["name"]: v for v in m["molecules"]}
    validation = time.perf_counter() - tick
    if a.mode == "produce":
        a.out.mkdir(parents=True, exist_ok=False)
    result = (produce if a.mode == "produce" else certify)(a, m, items, planned)
    result.update(
        mode=a.mode,
        arm=a.arm,
        input_validation_s=validation,
        worker_total_s=time.perf_counter() - tick,
        queue_sha256=QUEUE_SHA,
        manifest_sha256=m["manifest_sha256"],
        code_sha256=sha(Path(__file__).read_bytes()),
        job=os.environ["SLURM_JOB_ID"],
    )
    with (a.out / (a.mode + ".json")).open("xb") as f:
        flush(f, result)


if __name__ == "__main__":
    main()
