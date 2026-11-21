#!/usr/bin/env python3
"""Run one blind arm of the GPU4PySCF/GQC attribution matrix.

The script never reads an oracle or a scorer output.  A, B, C and D are run in
separate processes with the same sealed manifest.  A/B solve every request in
ordinary field batches.  C/D retain response vectors only when the planner
can prove the protocol identity is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np


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


def field_index(name: str) -> int:
    return {"x": 0, "y": 1, "z": 2}[name]


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


def device_info(cupy) -> dict:
    device = cupy.cuda.Device()
    props = cupy.cuda.runtime.getDeviceProperties(device.id)
    name = props.get("name", b"unknown")
    if isinstance(name, bytes):
        name = name.decode(errors="replace")
    free, total = cupy.cuda.runtime.memGetInfo()
    return {
        "cuda_device": int(device.id),
        "cuda_name": name,
        "cuda_total_bytes": int(total),
        "cuda_free_bytes_at_start": int(free),
        "cupy_version": cupy.__version__,
    }


def solve_fields(cupy, cphf, mf, field_indices, tol, max_cycle, backend_cache):
    """Solve a batch of electric-field response columns and return diagnostics."""
    from gpu4pyscf.properties import polarizability

    mo_coeff = cupy.asarray(mf.mo_coeff)
    mo_occ = cupy.asarray(mf.mo_occ)
    mo_energy = cupy.asarray(mf.mo_energy)
    mocc = mo_coeff[:, mo_occ > 0]
    mvir = mo_coeff[:, mo_occ == 0]
    with mf.mol.with_common_orig((0.0, 0.0, 0.0)):
        h1 = cupy.asarray(mf.mol.intor("int1e_r"))
    h1ai_all = -cupy.einsum("au,dui->dai", mvir.conj().T, cupy.einsum("duv,vi->dui", h1, mocc))
    h1ai = h1ai_all[field_indices]
    fvind_original = polarizability.gen_vind(mf, mo_coeff, mo_occ, with_nlc=True)
    counters = {"operator_calls": 0, "operator_rows": 0}

    def fvind_counted(mo1):
        counters["operator_calls"] += 1
        counters["operator_rows"] += int(mo1.shape[0])
        return fvind_original(mo1)

    started = time.perf_counter()
    solve_kwargs = {
        "max_cycle": max_cycle,
        "tol": tol,
        "verbose": 0,
    }
    if backend_cache is not None:
        solve_kwargs["backend_cache"] = backend_cache
    mo1, _ = cphf.solve(fvind_counted, mo_energy, mo_occ, h1ai, **solve_kwargs)
    elapsed = time.perf_counter() - started

    # This is the same residual expression used by the upstream CPHF map.  It
    # is evaluated through the original function so a backend cache cannot
    # turn the quality check into an assumed result.
    e_a = mo_energy[mo_occ == 0]
    e_i = mo_energy[mo_occ > 0]
    e_ai = 1.0 / (e_a[:, None] - e_i)
    base = h1ai * -e_ai
    residual_image = fvind_original(mo1)
    residual = mo1 + residual_image * e_ai - base
    residual_norm = float(cupy.max(cupy.abs(residual)).item())

    values = {}
    names = {0: "x", 1: "y", 2: "z"}
    for local, direction in enumerate(field_indices):
        values[direction] = np.asarray(cupy.asnumpy(mo1[local]), dtype=np.float64)
        values[names[direction]] = values.pop(direction)
    host_bytes = int(mo1.nbytes)
    return {
        "vectors": values,
        "seconds": elapsed,
        "operator_calls": counters["operator_calls"],
        "operator_rows": counters["operator_rows"],
        "quality_operator_rows": len(field_indices),
        "residual_linf": residual_norm,
        "device_to_host_bytes": host_bytes,
        "host_to_device_bytes": int(h1ai.nbytes + mo_energy.nbytes + mo_occ.nbytes + mo_coeff.nbytes),
    }


def target_values(cupy, mf, vectors: dict[str, np.ndarray], targets: list[str]) -> dict[str, float]:
    mo_coeff = cupy.asarray(mf.mo_coeff)
    mo_occ = cupy.asarray(mf.mo_occ)
    mocc = mo_coeff[:, mo_occ > 0]
    mvir = mo_coeff[:, mo_occ == 0]
    with mf.mol.with_common_orig((0.0, 0.0, 0.0)):
        h1 = cupy.asarray(mf.mol.intor("int1e_r"))
    result = {}
    alpha = {}
    for left_name, left_vector in vectors.items():
        left = cupy.asarray(left_vector)
        for right_name in vectors:
            right = field_index(right_name)
            p10 = cupy.trace(left.conj().T @ mvir.conj().T @ h1[right] @ mocc) * 2
            p01 = cupy.trace(mocc.conj().T @ h1[right] @ mvir @ left) * 2
            alpha[left_name + right_name] = float(((p10 + p01).real).item())
    for target in targets:
        if target not in alpha:
            raise ValueError(f"missing target {target} from fields {sorted(vectors)}")
        result[target] = alpha[target]
    return result


def density_values(cupy, mf, vectors: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    mo_coeff = cupy.asarray(mf.mo_coeff)
    mo_occ = cupy.asarray(mf.mo_occ)
    mocc = mo_coeff[:, mo_occ > 0]
    mvir = mo_coeff[:, mo_occ == 0]
    result = {}
    for name, vector in vectors.items():
        mo1 = cupy.asarray(vector)
        mo1_ao = cupy.einsum("ai,ua->ui", mo1, mvir)
        dm1 = 2 * cupy.einsum("ui,vi->uv", mo1_ao, mocc.conj())
        dm1 += dm1.T.conj()
        result[name] = np.asarray(cupy.asnumpy(dm1), dtype=np.float64)
    return result


def run_arm(args) -> None:
    started = time.perf_counter()
    manifest = load_manifest(args.manifest)
    protocol = manifest["protocol"]
    if args.arm not in {"A", "B", "C", "D"}:
        raise ValueError(args.arm)

    # Imports happen after the caller has selected the official or patched
    # package through PYTHONPATH.  No GQC planner or target oracle is loaded.
    import cupy
    from pyscf import gto
    from gpu4pyscf import scf
    from gpu4pyscf.scf import cphf

    backend_patched = args.arm in {"B", "D"}
    cache_type = None
    if backend_patched:
        from gpu4pyscf.lib.response_cache import ResponseOperatorCache
        cache_type = ResponseOperatorCache

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    records = []
    arm_is_gqc = args.arm in {"C", "D"}
    for item in manifest["molecules"]:
        molecule_started = time.perf_counter()
        mol = build_molecule(gto, item, protocol)
        scf_cycles = 0

        def callback(_envs):
            nonlocal scf_cycles
            scf_cycles += 1

        mf = scf.RHF(mol)
        mf.conv_tol = protocol["conv_tol"]
        mf.max_cycle = protocol["max_cycle"]
        mf.callback = callback
        scf_started = time.perf_counter()
        mf.kernel()
        scf_seconds = time.perf_counter() - scf_started
        if not mf.converged:
            raise RuntimeError(f"SCF did not converge for {item['name']}")

        cache = cache_type() if cache_type else None
        assets: dict[str, np.ndarray] = {}
        requests = sorted(manifest["request_trajectories"], key=lambda row: row["order"])
        for request in requests:
            requested = list(request["fields"])
            if arm_is_gqc:
                solve_names = [name for name in requested if name not in assets]
            else:
                solve_names = requested
            response = None
            if solve_names:
                response = solve_fields(
                    cupy,
                    cphf,
                    mf,
                    [field_index(name) for name in solve_names],
                    protocol["response_tol"],
                    protocol["response_max_cycle"],
                    cache,
                )
                if arm_is_gqc:
                    assets.update(response["vectors"])
            vectors = {name: (assets[name] if arm_is_gqc else response["vectors"][name]) for name in requested}
            values = target_values(cupy, mf, vectors, request["targets"])
            densities = density_values(cupy, mf, vectors)
            vector_rows = {
                name: np.asarray(vector, dtype=np.float64).reshape(-1).tolist()
                for name, vector in vectors.items()
            }
            records.append(
                {
                    "arm": args.arm,
                    "molecule": item["name"],
                    "qm9_id": item["qm9_id"],
                    "trajectory": request["id"],
                    "protocol": protocol,
                    "input_sha256": manifest["manifest_sha256"],
                    "backend": "gpu4pyscf-patched" if backend_patched else "gpu4pyscf-official",
                    "orchestration": "gqc-planner-assets" if arm_is_gqc else "native-ordinary",
                    "fields_requested": requested,
                    "fields_computed": solve_names,
                    "fields_reused": [name for name in requested if name not in solve_names],
                    "targets": values,
                    "response_vectors": vector_rows,
                    "response_densities": {
                        name: density.reshape(-1).tolist() for name, density in densities.items()
                    },
                    "response_metrics": None if response is None else {
                        "seconds": response["seconds"],
                        "operator_calls": response["operator_calls"],
                        "operator_rows": response["operator_rows"],
                        "quality_operator_rows": response["quality_operator_rows"],
                        "residual_linf": response["residual_linf"],
                        "device_to_host_bytes": response["device_to_host_bytes"],
                        "host_to_device_bytes": response["host_to_device_bytes"],
                    },
                    "cache": None if cache is None else {
                        "calls": cache.calls,
                        "hits": cache.hits,
                        "misses": cache.misses,
                    },
                    "scf_cycles": scf_cycles,
                    "scf_seconds": scf_seconds,
                    "molecule_seconds": time.perf_counter() - molecule_started,
                }
            )
    with (out / "raw.jsonl").open("w") as handle:
        for row in records:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    run = {
        "schema": "vibedataset.attribution_4arm.raw.v1",
        "arm": args.arm,
        "backend": "gpu4pyscf-patched" if backend_patched else "gpu4pyscf-official",
        "orchestration": "gqc-planner-assets" if arm_is_gqc else "native-ordinary",
        "manifest": str(args.manifest),
        "manifest_sha256": manifest["manifest_sha256"],
        "driver_sha256": sha256_file(Path(__file__)),
        "source_commit": args.source_commit,
        "gpu4pyscf_source_commit": args.gpu4pyscf_source_commit,
        "patch_sha256": sha256_file(args.patch) if backend_patched and args.patch else None,
        "python": sys.version,
        "platform": platform.platform(),
        "pid": os.getpid(),
        "device": device_info(cupy),
        "record_count": len(records),
        "elapsed_seconds": time.perf_counter() - started,
        "cold_start_seconds": None,
        "blind": True,
        "oracle_loaded": False,
        "scorer_loaded": False,
    }
    (out / "run.json").write_text(json.dumps(run, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--arm", required=True, choices=["A", "B", "C", "D"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--gpu4pyscf-source-commit", default="unknown")
    parser.add_argument("--patch", type=Path)
    args = parser.parse_args()
    run_arm(args)


if __name__ == "__main__":
    main()
