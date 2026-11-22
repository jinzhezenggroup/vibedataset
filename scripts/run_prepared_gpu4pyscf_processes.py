#!/usr/bin/env python3
"""Run ordered response chains in isolated GPU4PySCF worker processes.

This is a separate opt-in runtime from the same-context stream experiment. Each
molecule worker owns a CUDA context and executes its three response requests in
order. The parent retains the PreparedPropertyBatch bucket/DAG identity and
merges only completed, identity-bound receipts.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as multiprocessing
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from prepared_property_batch import PreparedPropertyBatch, PropertyIdentity, Request  # noqa: E402


def worker(payload: dict) -> dict:
    import cupy
    import numpy as np
    from pyscf import gto
    from gpu4pyscf import scf
    from gpu4pyscf.properties import polarizability
    from gpu4pyscf.scf import cphf
    from run_gpu4pyscf_4arm import build_molecule, density_values, solve_fields, target_values, measured_prepared_backend

    cupy.cuda.Device(0).use()
    protocol = payload["protocol"]
    item = payload["item"]
    mol = build_molecule(gto, item, protocol)
    mf = scf.RHF(mol)
    mf.conv_tol = protocol["conv_tol"]
    mf.max_cycle = protocol["max_cycle"]
    setup_started = time.perf_counter()
    mf.kernel()
    cupy.cuda.get_current_stream().synchronize()
    if not mf.converged:
        raise RuntimeError(f"SCF did not converge for {item['name']}")
    setup_seconds = time.perf_counter() - setup_started
    assets = {}
    receipts = []
    for trajectory in payload["trajectories"]:
        requested = list(trajectory["fields"])
        solve_names = [field for field in requested if field not in assets]
        started = time.perf_counter()
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
            assets.update(response["vectors"])
        vectors = {field: assets[field] for field in requested}
        targets = target_values(cupy, mf, vectors, trajectory["targets"])
        densities = density_values(cupy, mf, vectors)
        cupy.cuda.get_current_stream().synchronize()
        receipts.append({
            "request_id": f"{item['name']}:{trajectory['id']}",
            "molecule": item["name"],
            "trajectory": trajectory["id"],
            "fields_requested": requested,
            "fields_computed": solve_names,
            "fields_reused": [field for field in requested if field not in solve_names],
            "targets": targets,
            "response_vectors": {name: np.asarray(value, dtype=np.float64).reshape(-1).tolist() for name, value in vectors.items()},
            "response_densities": {name: np.asarray(value, dtype=np.float64).reshape(-1).tolist() for name, value in densities.items()},
            "response_seconds": None if response is None else response["seconds"],
            "operator_calls": 0 if response is None else response["operator_calls"],
            "operator_rows": 0 if response is None else response["operator_rows"],
            "residual_linf": None if response is None else response["residual_linf"],
            "host_to_device_bytes": 0 if response is None else response["host_to_device_bytes"],
            "device_to_host_bytes": 0 if response is None else response["device_to_host_bytes"],
            "request_seconds": time.perf_counter() - started,
            "pid": __import__("os").getpid(),
        })
    free, total = cupy.cuda.runtime.memGetInfo()
    return {
        "backend_identity": measured_prepared_backend(),
        "molecule": item["name"],
        "pid": __import__("os").getpid(),
        "setup_seconds": setup_seconds,
        "request_count": len(receipts),
        "receipts": receipts,
        "memory_free_bytes": int(free),
        "memory_total_bytes": int(total),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--molecules", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    protocol = manifest["protocol"]
    from pyscf import gto
    from run_gpu4pyscf_4arm import build_molecule

    by_name = {item["name"]: item for item in manifest["molecules"]}
    trajectories = sorted(manifest["request_trajectories"], key=lambda row: row["order"])
    payloads = []
    requests = []
    for name in args.molecules:
        item = by_name[name]
        payloads.append({"item": item, "protocol": protocol, "trajectories": trajectories})
        nao = int(build_molecule(gto, item, protocol).nao_nr())
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
            requests.append(Request(f"{name}:{trajectory['id']}", identity, nao, ("energy", "response")))
    batch = PreparedPropertyBatch(requests, resident=True, max_workspace_bytes=0).compile()
    started = time.perf_counter()
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=len(payloads)) as pool:
        worker_results = pool.map(worker, payloads)
    receipts = [receipt for result in worker_results for receipt in result["receipts"]]
    order = {f"{name}:{trajectory['id']}": index for index, (name, trajectory) in enumerate((name, trajectory) for name in args.molecules for trajectory in trajectories)}
    receipts.sort(key=lambda receipt: order[receipt["request_id"]])
    if not worker_results or any(w["backend_identity"] != worker_results[0]["backend_identity"] for w in worker_results):
        raise ValueError("prepared workers report different backend identities")
    result = {
        "schema": "vibedataset.prepared_gpu4pyscf_process_runtime.v1",
        "status": "accepted" if len(receipts) == len(requests) else "partial",
        "runtime_mode": "process_isolated",
        "execution_mode": "spawned-worker-chains",
        "manifest_sha256": manifest["manifest_sha256"],
        **worker_results[0]["backend_identity"],
        "python": sys.version,
        "platform": platform.platform(),
        "molecules": args.molecules,
        "request_count": len(requests),
        "receipt_count": len(receipts),
        "bucket_count": len(batch.buckets),
        "resident_bucket_setup_count": len(batch.buckets),
        "worker_count": len(worker_results),
        "cuda_context_count": len(worker_results),
        "same_physical_gpu": True,
        "elapsed_seconds": time.perf_counter() - started,
        "worker_results": worker_results,
        "receipts": receipts,
        "failures": [],
        "scientific_backend": "official GPU4PySCF; no fused or altered kernels",
        "planner": batch.to_dict(),
        "limitations": [
            "Each worker owns a separate CUDA context on one physical GPU. This is not a same-context stream runtime.",
            "Process startup, context creation and duplicated resident state are included in elapsed_seconds.",
            "No cross-molecule operator-value reuse or fused ragged kernel is claimed.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "request_count", "receipt_count", "bucket_count", "worker_count", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
