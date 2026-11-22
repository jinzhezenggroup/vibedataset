#!/usr/bin/env python3
"""Run the opt-in PreparedPropertyBatch serial/async-streams control.

The official GPU4PySCF SCF/CPHF producer is unchanged.  The async mode only
schedules independent same-bucket molecule chains on separate non-blocking
CuPy streams.  Requests for one molecule remain ordered so response assets are
never consumed before their producer request completes.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prepared_property_batch import PreparedPropertyBatch, PropertyIdentity, Request  # noqa: E402
from run_gpu4pyscf_4arm import (  # noqa: E402
    build_molecule,
    density_values,
    load_manifest,
    solve_fields,
    target_values,
)


def memory_snapshot(cupy) -> dict:
    free, total = cupy.cuda.runtime.memGetInfo()
    pool = cupy.get_default_memory_pool()
    return {
        "free_bytes": int(free),
        "total_bytes": int(total),
        "pool_used_bytes": int(pool.used_bytes()),
        "pool_total_bytes": int(pool.total_bytes()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--molecules", nargs="+", required=True)
    parser.add_argument("--mode", choices=("serial", "async_streams"), required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "async_streams" and args.workers < 2:
        raise ValueError("async_streams requires at least two workers")

    manifest = load_manifest(args.manifest)
    protocol = manifest["protocol"]
    by_name = {item["name"]: item for item in manifest["molecules"]}
    missing = [name for name in args.molecules if name not in by_name]
    if missing:
        raise ValueError(f"unknown molecules: {missing}")
    trajectories = sorted(manifest["request_trajectories"], key=lambda row: row["order"])

    import cupy
    from pyscf import gto
    from gpu4pyscf import scf
    from gpu4pyscf.scf import cphf

    molecules = {}
    requests = []
    request_info = {}
    for name in args.molecules:
        item = by_name[name]
        mol = build_molecule(gto, item, protocol)
        nao = int(mol.nao_nr())
        molecules[name] = {"item": item, "mol": mol, "nao": nao}
        identity = PropertyIdentity(
            protocol["method"],
            protocol["basis"],
            item["charge"],
            item["multiplicity"] - 1,
            protocol["basis_representation"],
            tuple(protocol["origin"]),
            protocol["unit"],
            item["member_sha256"],
        )
        for trajectory in trajectories:
            request_id = f"{name}:{trajectory['id']}"
            requests.append(Request(request_id, identity, nao, ("energy", "response")))
            request_info[request_id] = {"molecule": name, "trajectory": trajectory}

    batch = PreparedPropertyBatch(requests, resident=True, max_workspace_bytes=0).compile()
    assets = defaultdict(dict)
    states = {}
    streams = {}
    setup_receipts = {}
    producer_started = time.perf_counter()

    class Producer:
        def prepare_bucket(self, bucket, request_ids):
            started = time.perf_counter()
            names = sorted({request_info[request_id]["molecule"] for request_id in request_ids})
            workspace_nao = max(molecules[name]["nao"] for name in names)
            workspace = cupy.empty((workspace_nao, workspace_nao), dtype=cupy.float64)
            for name in names:
                mf = scf.RHF(molecules[name]["mol"])
                mf.conv_tol = protocol["conv_tol"]
                mf.max_cycle = protocol["max_cycle"]
                mf.kernel()
                if not mf.converged:
                    raise RuntimeError(f"SCF did not converge for {name}")
                states[name] = mf
                if args.mode == "async_streams":
                    streams[name] = cupy.cuda.Stream(non_blocking=True)
            state = {
                "bucket": bucket,
                "request_ids": request_ids,
                "molecule_names": names,
                "workspace_shape": list(workspace.shape),
                "workspace_bytes": int(workspace.nbytes),
                "workspace_resident": True,
                "setup_seconds": time.perf_counter() - started,
                "memory_after_setup": memory_snapshot(cupy),
                "workspace": workspace,
            }
            setup_receipts[bucket] = {key: value for key, value in state.items() if key != "workspace"}
            return state

        def run_request(self, request_id, state):
            info = request_info[request_id]
            name = info["molecule"]
            trajectory = info["trajectory"]
            mf = states[name]
            requested = list(trajectory["fields"])
            solve_names = [field for field in requested if field not in assets[name]]
            started = time.perf_counter()
            stream = streams.get(name)
            context = stream if stream is not None else cupy.cuda.get_current_stream()
            with context:
                response = None
                if solve_names:
                    response = solve_fields(
                        cupy,
                        cphf,
                        mf,
                        ["xyz".index(field) for field in solve_names],
                        protocol["response_tol"],
                        protocol["response_max_cycle"],
                        None,
                    )
                    assets[name].update(response["vectors"])
                vectors = {field: assets[name][field] for field in requested}
                targets = target_values(cupy, mf, vectors, trajectory["targets"])
                density_values(cupy, mf, vectors)
                sync_started = time.perf_counter()
                context.synchronize()
                synchronize_seconds = time.perf_counter() - sync_started
            return {
                "molecule": name,
                "trajectory": trajectory["id"],
                "fields_requested": requested,
                "fields_computed": solve_names,
                "fields_reused": [field for field in requested if field not in solve_names],
                "targets": targets,
                "response_seconds": None if response is None else response["seconds"],
                "operator_calls": 0 if response is None else response["operator_calls"],
                "operator_rows": 0 if response is None else response["operator_rows"],
                "residual_linf": None if response is None else response["residual_linf"],
                "host_to_device_bytes": 0 if response is None else response["host_to_device_bytes"],
                "device_to_host_bytes": 0 if response is None else response["device_to_host_bytes"],
                "request_seconds": time.perf_counter() - started,
                "synchronize_seconds": synchronize_seconds,
                "stream_id": int(stream.ptr) if stream is not None else 0,
                "memory_after_request": memory_snapshot(cupy),
            }

    producer = Producer()
    if args.mode == "serial":
        runtime = batch.execute(producer)
    else:
        runtime = batch.execute_async(producer, lambda request_id: request_info[request_id]["molecule"], args.workers)
    result = {
        "schema": "vibedataset.prepared_gpu4pyscf_runtime.v1",
        "status": "accepted" if not runtime["failures"] else "partial",
        "runtime_mode": args.mode,
        "max_workers": 1 if args.mode == "serial" else args.workers,
        "execution_mode": runtime.get("execution_mode", "serial"),
        "manifest_sha256": manifest["manifest_sha256"],
        "gpu4pyscf_source_commit": "5a717f899cb40d64a5799ef1df7e3626c505c3bd",
        "python": sys.version,
        "platform": platform.platform(),
        "protocol": protocol,
        "molecules": args.molecules,
        "nao_by_molecule": {name: molecules[name]["nao"] for name in args.molecules},
        "request_count": len(requests),
        "bucket_count": len(batch.buckets),
        "resident_bucket_setup_count": runtime["setup_count"],
        "serial_setup_count_reference": len(args.molecules),
        "setup_reduction_ratio_reference": runtime["setup_count"] / len(args.molecules),
        "async_group_count": runtime.get("group_count", len(args.molecules)),
        "scheduler_seconds": runtime.get("scheduler_seconds", 0.0),
        "setup_receipts": setup_receipts,
        "receipts": runtime["receipts"],
        "failures": runtime["failures"],
        "memory_at_end": memory_snapshot(cupy),
        "elapsed_seconds": time.perf_counter() - producer_started,
        "scientific_backend": "official GPU4PySCF; no fused or altered kernels",
        "workspace_semantics": "resident orchestration buffer, not a claim of shared GPU4PySCF operator assets",
        "limitations": [
            "The async mode overlaps independent molecule chains with non-blocking CuPy streams but keeps each molecule's response assets ordered.",
            "Ragged field lengths are scheduled as request metadata; no fused ragged CPHF kernel is claimed.",
            "No J/K fusion, mixed precision or cross-molecule operator-value reuse is enabled.",
            "The control uses one process, one CUDA context and three same-shape molecules.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "runtime_mode", "request_count", "bucket_count", "async_group_count", "elapsed_seconds")}, indent=2))


def sync(cupy) -> None:
    cupy.cuda.get_current_stream().synchronize()


if __name__ == "__main__":
    main()
