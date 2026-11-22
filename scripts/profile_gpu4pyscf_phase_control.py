#!/usr/bin/env python3
"""Phase and CUDA-memory telemetry for a bounded GPU4PySCF control.

The control profiles one sealed manifest molecule in a fresh process. It is a
measurement receipt for the available phases, not a replacement for the full
A-D profiling matrix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np


FIELD_INDEX = {"x": 0, "y": 1, "z": 2}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text())
    encoded = dict(manifest)
    observed = encoded.pop("manifest_sha256")
    actual = hashlib.sha256(json.dumps(encoded, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != observed:
        raise ValueError(f"manifest hash mismatch: {actual} != {observed}")
    return manifest


def build_molecule(gto, item: dict, protocol: dict):
    symbols = {1: "H", 6: "C", 7: "N", 8: "O", 9: "F"}
    atoms = [(symbols[z], tuple(coords)) for z, coords in zip(item["atomic_numbers"], item["coordinates_bohr"])]
    return gto.M(
        atom=atoms,
        unit="Bohr",
        basis=protocol["basis"],
        charge=item["charge"],
        spin=item["multiplicity"] - 1,
        cart=False,
        verbose=0,
    )


def memory_snapshot(cupy) -> dict:
    free, total = cupy.cuda.runtime.memGetInfo()
    pool = cupy.get_default_memory_pool()
    pinned = cupy.get_default_pinned_memory_pool()
    return {
        "free_bytes": int(free),
        "total_bytes": int(total),
        "pool_used_bytes": int(pool.used_bytes()),
        "pool_total_bytes": int(pool.total_bytes()),
        "pinned_free_blocks": int(pinned.n_free_blocks()),
    }


def timed_gpu(cupy, callback):
    started = time.perf_counter()
    event_start = cupy.cuda.Event()
    event_end = cupy.cuda.Event()
    event_start.record()
    result = callback()
    event_end.record()
    event_end.synchronize()
    wall_seconds = time.perf_counter() - started
    gpu_seconds = float(cupy.cuda.get_elapsed_time(event_start, event_end)) / 1000.0
    return result, wall_seconds, gpu_seconds


def solve_response(cupy, cphf, polarizability, mf, field_indices, tol, max_cycle):
    mo_coeff = cupy.asarray(mf.mo_coeff)
    mo_occ = cupy.asarray(mf.mo_occ)
    mo_energy = cupy.asarray(mf.mo_energy)
    mocc = mo_coeff[:, mo_occ > 0]
    mvir = mo_coeff[:, mo_occ == 0]
    with mf.mol.with_common_orig((0.0, 0.0, 0.0)):
        h1 = cupy.asarray(mf.mol.intor("int1e_r"))
    h1ai_all = -cupy.einsum("au,dui->dai", mvir.conj().T, cupy.einsum("duv,vi->dui", h1, mocc))
    h1ai = h1ai_all[field_indices]
    fvind = polarizability.gen_vind(mf, mo_coeff, mo_occ, with_nlc=True)
    counters = {"operator_calls": 0, "operator_rows": 0}

    def counted(mo1):
        counters["operator_calls"] += 1
        counters["operator_rows"] += int(mo1.shape[0])
        return fvind(mo1)

    from gpu4pyscf.scf import cphf as cphf_module

    mo1, _ = cphf_module.solve(
        counted,
        mo_energy,
        mo_occ,
        h1ai,
        max_cycle=max_cycle,
        tol=tol,
        verbose=0,
    )
    e_a = mo_energy[mo_occ == 0]
    e_i = mo_energy[mo_occ > 0]
    e_ai = 1.0 / (e_a[:, None] - e_i)
    base = h1ai * -e_ai
    residual_image = fvind(mo1)
    residual = mo1 + residual_image * e_ai - base
    residual_linf = float(cupy.max(cupy.abs(residual)).item())
    return mo1, counters, residual_linf, int(mo1.nbytes), int(h1ai.nbytes + mo_energy.nbytes + mo_occ.nbytes + mo_coeff.nbytes)


def readout(cupy, mf, vectors, targets):
    mo_coeff = cupy.asarray(mf.mo_coeff)
    mo_occ = cupy.asarray(mf.mo_occ)
    mocc = mo_coeff[:, mo_occ > 0]
    mvir = mo_coeff[:, mo_occ == 0]
    with mf.mol.with_common_orig((0.0, 0.0, 0.0)):
        h1 = cupy.asarray(mf.mol.intor("int1e_r"))
    alpha = {}
    for left_name, left in vectors.items():
        for right_name, right_index in FIELD_INDEX.items():
            p10 = cupy.trace(left.conj().T @ mvir.conj().T @ h1[right_index] @ mocc) * 2
            p01 = cupy.trace(mocc.conj().T @ h1[right_index] @ mvir @ left) * 2
            alpha[left_name + right_name] = float(((p10 + p01).real).item())
    for target in targets:
        if target not in alpha:
            raise ValueError(f"missing target {target}")
    return {target: alpha[target] for target in targets}


def run(args) -> dict:
    manifest = load_manifest(args.manifest)
    protocol = manifest["protocol"]
    item = next(row for row in manifest["molecules"] if row["name"] == args.molecule)
    requests = sorted(manifest["request_trajectories"], key=lambda row: row["order"])
    import cupy
    from pyscf import gto
    from gpu4pyscf import scf
    from gpu4pyscf.properties import polarizability
    from gpu4pyscf.scf import cphf

    started = time.perf_counter()
    initial_memory = memory_snapshot(cupy)
    prepare_started = time.perf_counter()
    mol = build_molecule(gto, item, protocol)
    mf = scf.RHF(mol)
    mf.conv_tol = protocol["conv_tol"]
    mf.max_cycle = protocol["max_cycle"]
    prepare_seconds = time.perf_counter() - prepare_started
    scf_cycles = 0

    def callback(_envs):
        nonlocal scf_cycles
        scf_cycles += 1

    mf.callback = callback
    (scf_result, scf_wall_seconds, scf_gpu_seconds) = timed_gpu(cupy, mf.kernel)
    if not mf.converged:
        raise RuntimeError(f"SCF did not converge for {item['name']}")
    assets = {}
    rows = []
    for request in requests:
        requested = list(request["fields"])
        solve_names = requested if args.arm == "A" else [name for name in requested if name not in assets]
        response = None
        if solve_names:
            response, response_wall, response_gpu = timed_gpu(
                cupy,
                lambda: solve_response(
                    cupy,
                    cphf,
                    polarizability,
                    mf,
                    [FIELD_INDEX[name] for name in solve_names],
                    protocol["response_tol"],
                    protocol["response_max_cycle"],
                ),
            )
            mo1, counters, residual_linf, d2h_bytes, h2d_bytes = response
            if args.arm == "C":
                for index, name in enumerate(solve_names):
                    assets[name] = mo1[index]
        else:
            response_wall = response_gpu = 0.0
            counters = {"operator_calls": 0, "operator_rows": 0}
            residual_linf = 0.0
            d2h_bytes = h2d_bytes = 0
        vectors = mo1 if args.arm == "A" else cupy.stack([assets[name] for name in requested])
        vector_map = (
            {name: mo1[index] for index, name in enumerate(solve_names)}
            if args.arm == "A"
            else {name: assets[name] for name in requested}
        )
        targets, readout_wall, readout_gpu = timed_gpu(cupy, lambda: readout(cupy, mf, vector_map, request["targets"]))
        row = {
            "trajectory": request["id"],
            "fields_requested": requested,
            "fields_computed": solve_names,
            "fields_reused": [name for name in requested if name not in solve_names],
            "targets": targets,
            "phase_seconds": {
                "prepare": prepare_seconds if not rows else 0.0,
                "scf_fock": scf_wall_seconds if not rows else 0.0,
                "cp_hf_gmres_and_residual": response_wall,
                "property_readout": readout_wall,
            },
            "gpu_event_seconds": {
                "scf_fock": scf_gpu_seconds if not rows else 0.0,
                "cp_hf_gmres_and_residual": response_gpu,
                "property_readout": readout_gpu,
            },
            "operator_calls": counters["operator_calls"],
            "operator_rows": counters["operator_rows"],
            "residual_linf": residual_linf,
            "host_to_device_bytes": h2d_bytes,
            "device_to_host_bytes": d2h_bytes,
            "memory_after": memory_snapshot(cupy),
        }
        json.dumps(row, sort_keys=True)
        rows.append(row)
    final_memory = memory_snapshot(cupy)
    return {
        "schema": "vibedataset.gpu4pyscf_phase_profile_control.v1",
        "arm": args.arm,
        "molecule": item["name"],
        "manifest_sha256": manifest["manifest_sha256"],
        "protocol": protocol,
        "gpu4pyscf_source_commit": "5a717f899cb40d64a5799ef1df7e3626c505c3bd",
        "python": sys.version,
        "platform": platform.platform(),
        "device": memory_snapshot(cupy),
        "initial_memory": initial_memory,
        "final_memory": final_memory,
        "rows": rows,
        "serialization_seconds": time.perf_counter() - started,
        "unknowns": [
            "kernel launch count, occupancy and FLOPs were not collected",
            "compile/JIT cache hit state is not separated from the backend calls",
            "this one-molecule control does not establish A-D queue-level statistics",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--arm", choices=("A", "C"), required=True)
    parser.add_argument("--molecule", default="qm9-000001")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "accepted", "arm": result["arm"], "molecule": result["molecule"], "rows": len(result["rows"])}, indent=2))


if __name__ == "__main__":
    main()
