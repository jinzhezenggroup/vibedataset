#!/usr/bin/env python3
"""Probe process-isolated GPU4PySCF concurrency on one CUDA device."""

from __future__ import annotations

import argparse
import json
import multiprocessing as multiprocessing
import platform
import time
from pathlib import Path


def worker(payload: dict) -> dict:
    import cupy
    from pyscf import gto
    from gpu4pyscf import scf

    cupy.cuda.Device(0).use()
    symbols = {1: "H", 6: "C", 7: "N", 8: "O", 9: "F"}
    atoms = [(symbols[z], tuple(coords)) for z, coords in zip(payload["atomic_numbers"], payload["coordinates_bohr"])]
    mol = gto.M(
        atom=atoms,
        unit="Bohr",
        basis=payload["basis"],
        charge=payload["charge"],
        spin=payload["multiplicity"] - 1,
        cart=False,
        verbose=0,
    )
    mf = scf.RHF(mol).set(conv_tol=payload["conv_tol"], max_cycle=payload["max_cycle"])
    started = time.perf_counter()
    energy = mf.kernel()
    cupy.cuda.get_current_stream().synchronize()
    return {
        "molecule": payload["name"],
        "converged": bool(mf.converged),
        "energy": float(energy),
        "seconds": time.perf_counter() - started,
        "pid": __import__("os").getpid(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--molecules", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    protocol = manifest["protocol"]
    selected = {row["name"]: row for row in manifest["molecules"]}
    payloads = []
    for name in args.molecules:
        item = selected[name]
        payloads.append({**item, **{key: protocol[key] for key in ("basis", "conv_tol", "max_cycle")}})
    started = time.perf_counter()
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=len(payloads)) as pool:
        results = pool.map(worker, payloads)
    result = {
        "schema": "vibedataset.gpu4pyscf_process_concurrency_probe.v1",
        "status": "accepted" if all(row["converged"] for row in results) else "failed",
        "manifest_sha256": manifest["manifest_sha256"],
        "molecules": args.molecules,
        "process_count": len(payloads),
        "device_count": 1,
        "python": __import__("sys").version,
        "platform": platform.platform(),
        "elapsed_seconds": time.perf_counter() - started,
        "results": results,
        "limitations": [
            "This probes independent SCF processes only. It does not prove a safe multi-process response runtime.",
            "Each process owns a separate CUDA context on the same physical GPU.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "process_count", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
