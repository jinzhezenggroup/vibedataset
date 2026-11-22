#!/usr/bin/env python3
"""Run one A-D arm with request-level phase telemetry.

The scientific producer remains the official GPU4PySCF CPHF path.  This
receipt only adds timing and transfer counters around the existing producer,
with the optional Issue #31 cache applied to B/D.  The independent scorer is
kept outside the producer process and is therefore recorded as unknown in each
row rather than being estimated.
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

TIMING_FIELDS = [
    "prepare",
    "environment_startup",
    "data_read",
    "compile_jit",
    "warmup",
    "h2d",
    "scf_fock",
    "cp_hf_gmres",
    "property_readout",
    "physical_residual",
    "independent_scorer",
    "serialization",
    "retry",
    "fallback",
]
FIELD_INDEX = {"x": 0, "y": 1, "z": 2}
SYMBOLS = {1: "H", 6: "C", 7: "N", 8: "O", 9: "F"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> tuple[dict, float]:
    started = time.perf_counter()
    manifest = json.loads(path.read_text())
    encoded = dict(manifest)
    observed = encoded.pop("manifest_sha256")
    actual = hashlib.sha256(json.dumps(encoded, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != observed:
        raise ValueError(f"manifest hash mismatch: {actual} != {observed}")
    return manifest, time.perf_counter() - started


def build_molecule(gto, item: dict, protocol: dict):
    atoms = [(SYMBOLS[z], tuple(coords)) for z, coords in zip(item["atomic_numbers"], item["coordinates_bohr"])]
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


def sync(cupy) -> None:
    cupy.cuda.get_current_stream().synchronize()


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


def field_rhs(cupy, mf, field_indices: list[int]):
    """Build the selected electric-field RHS and report explicit H2D time."""
    mo_coeff = cupy.asarray(mf.mo_coeff)
    mo_occ = cupy.asarray(mf.mo_occ)
    mo_energy = cupy.asarray(mf.mo_energy)
    mocc = mo_coeff[:, mo_occ > 0]
    mvir = mo_coeff[:, mo_occ == 0]
    with mf.mol.with_common_orig((0.0, 0.0, 0.0)):
        h1_host = mf.mol.intor("int1e_r")
    started = time.perf_counter()
    h1 = cupy.asarray(h1_host)
    sync(cupy)
    h2d_seconds = time.perf_counter() - started
    h1ai_all = -cupy.einsum("au,dui->dai", mvir.conj().T, cupy.einsum("duv,vi->dui", h1, mocc))
    h1ai = h1ai_all[field_indices]
    sync(cupy)
    h2d_bytes = int(h1_host.nbytes)
    return mo_coeff, mo_occ, mo_energy, h1, h1ai, h2d_seconds, h2d_bytes


def solve_response(cupy, cphf, polarizability, mf, field_indices, tol, max_cycle, backend_cache):
    mo_coeff, mo_occ, mo_energy, h1, h1ai, h2d_seconds, h2d_bytes = field_rhs(cupy, mf, field_indices)
    fvind_original = polarizability.gen_vind(mf, mo_coeff, mo_occ, with_nlc=True)
    counters = {"operator_calls": 0, "operator_rows": 0}

    def fvind_counted(mo1):
        counters["operator_calls"] += 1
        counters["operator_rows"] += int(mo1.shape[0])
        return fvind_original(mo1)

    solve_started = time.perf_counter()
    kwargs = {"max_cycle": max_cycle, "tol": tol, "verbose": 0}
    if backend_cache is not None:
        kwargs["backend_cache"] = backend_cache
    mo1, _ = cphf.solve(fvind_counted, mo_energy, mo_occ, h1ai, **kwargs)
    sync(cupy)
    solve_seconds = time.perf_counter() - solve_started
    solve_gpu_seconds = None

    residual_started = time.perf_counter()
    e_a = mo_energy[mo_occ == 0]
    e_i = mo_energy[mo_occ > 0]
    e_ai = 1.0 / (e_a[:, None] - e_i)
    base = h1ai * -e_ai
    residual_image = fvind_original(mo1)
    residual = mo1 + residual_image * e_ai - base
    residual_linf = float(cupy.max(cupy.abs(residual)).item())
    sync(cupy)
    residual_seconds = time.perf_counter() - residual_started
    return {
        "vectors": {
            ("x", "y", "z")[direction]: np.asarray(cupy.asnumpy(mo1[index]), dtype=np.float64)
            for index, direction in enumerate(field_indices)
        },
        "h1": h1,
        "mo_coeff": mo_coeff,
        "mo_occ": mo_occ,
        "seconds": solve_seconds,
        "gpu_seconds": solve_gpu_seconds,
        "residual_seconds": residual_seconds,
        "residual_linf": residual_linf,
        "operator_calls": counters["operator_calls"],
        "operator_rows": counters["operator_rows"],
        "h2d_seconds": h2d_seconds,
        "h2d_bytes": h2d_bytes,
    }


def target_values(cupy, mf, vectors: dict[str, np.ndarray], targets: list[str]) -> dict[str, float]:
    mo_coeff = cupy.asarray(mf.mo_coeff)
    mo_occ = cupy.asarray(mf.mo_occ)
    mocc = mo_coeff[:, mo_occ > 0]
    mvir = mo_coeff[:, mo_occ == 0]
    with mf.mol.with_common_orig((0.0, 0.0, 0.0)):
        h1 = cupy.asarray(mf.mol.intor("int1e_r"))
    alpha = {}
    for left_name, left_value in vectors.items():
        left = cupy.asarray(left_value)
        for right_name, right in FIELD_INDEX.items():
            p10 = cupy.trace(left.conj().T @ mvir.conj().T @ h1[right] @ mocc) * 2
            p01 = cupy.trace(mocc.conj().T @ h1[right] @ mvir @ left) * 2
            alpha[left_name + right_name] = float(((p10 + p01).real).item())
    missing = [target for target in targets if target not in alpha]
    if missing:
        raise ValueError(f"missing targets {missing}")
    return {target: alpha[target] for target in targets}


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


def request_timing(values: dict[str, float | None], wall_seconds: float) -> dict:
    timing = {field: values.get(field) for field in TIMING_FIELDS}
    known = sum(value for value in timing.values() if isinstance(value, (int, float)))
    timing["end_to_end_wall_seconds"] = wall_seconds
    timing["unattributed_seconds"] = max(0.0, wall_seconds - known)
    timing["known_seconds"] = known
    return timing


def run(args) -> None:
    process_started = time.perf_counter()
    manifest, data_read_seconds = load_manifest(args.manifest)
    protocol = manifest["protocol"]
    if args.arm not in {"A", "B", "C", "D"}:
        raise ValueError(args.arm)

    import_started = time.perf_counter()
    import cupy
    from pyscf import gto
    from gpu4pyscf import scf
    from gpu4pyscf.properties import polarizability
    from gpu4pyscf.scf import cphf

    environment_startup_seconds = time.perf_counter() - import_started
    backend_patched = args.arm in {"B", "D"}
    cache_type = None
    if backend_patched:
        from gpu4pyscf.lib.response_cache import ResponseOperatorCache

        cache_type = ResponseOperatorCache
    arm_is_gqc = args.arm in {"C", "D"}
    requests = sorted(manifest["request_trajectories"], key=lambda row: row["order"])
    records = []
    failed = []
    process_rows = 0
    device = device_info(cupy)
    for item in manifest["molecules"]:
        molecule_started = time.perf_counter()
        mol = build_molecule(gto, item, protocol)
        mf = scf.RHF(mol)
        mf.conv_tol = protocol["conv_tol"]
        mf.max_cycle = protocol["max_cycle"]
        prepare_seconds = time.perf_counter() - molecule_started
        scf_cycles = 0

        def callback(_envs):
            nonlocal scf_cycles
            scf_cycles += 1

        mf.callback = callback
        scf_started = time.perf_counter()
        mf.kernel()
        sync(cupy)
        scf_seconds = time.perf_counter() - scf_started
        if not mf.converged:
            raise RuntimeError(f"SCF did not converge for {item['name']}")
        cache = cache_type() if cache_type else None
        assets: dict[str, np.ndarray] = {}
        for request in requests:
            first_request_for_molecule = not any(row["molecule"] == item["name"] for row in records)
            request_started = process_started if process_rows == 0 else molecule_started if first_request_for_molecule else time.perf_counter()
            requested = list(request["fields"])
            solve_names = requested if not arm_is_gqc else [name for name in requested if name not in assets]
            response = None
            status = "accepted"
            failure_reason = None
            try:
                if solve_names:
                    response = solve_response(
                        cupy,
                        cphf,
                        polarizability,
                        mf,
                        [FIELD_INDEX[name] for name in solve_names],
                        protocol["response_tol"],
                        protocol["response_max_cycle"],
                        cache,
                    )
                    if arm_is_gqc:
                        assets.update(response["vectors"])
                vectors = {name: (assets[name] if arm_is_gqc else response["vectors"][name]) for name in requested}
                vector_h2d_started = time.perf_counter()
                device_vectors = {name: cupy.asarray(vector) for name, vector in vectors.items()}
                sync(cupy)
                vector_h2d_seconds = time.perf_counter() - vector_h2d_started
                vector_h2d_bytes = sum(np.asarray(vector).nbytes for vector in vectors.values())
                readout_started = time.perf_counter()
                values = target_values(cupy, mf, device_vectors, request["targets"])
                densities = density_values(cupy, mf, device_vectors)
                sync(cupy)
                readout_seconds = time.perf_counter() - readout_started
                residual_seconds = 0.0 if response is None else response["residual_seconds"]
                h2d_seconds = (0.0 if response is None else response["h2d_seconds"]) + vector_h2d_seconds
                h2d_bytes = (0 if response is None else response["h2d_bytes"]) + vector_h2d_bytes
                response_seconds = 0.0 if response is None else response["seconds"]
                operator_calls = 0 if response is None else response["operator_calls"]
                operator_rows = 0 if response is None else response["operator_rows"]
                residual_linf = 0.0 if response is None else response["residual_linf"]
            except Exception as exc:  # retain a failure denominator and continue the queue
                status = "failed"
                failure_reason = f"{type(exc).__name__}: {exc}"
                failed.append({"molecule": item["name"], "trajectory": request["id"], "reason": failure_reason})
                values = {}
                densities = {}
                readout_seconds = 0.0
                vector_h2d_seconds = 0.0
                vector_h2d_bytes = 0
                residual_seconds = 0.0
                h2d_seconds = 0.0
                h2d_bytes = 0
                response_seconds = 0.0
                operator_calls = 0
                operator_rows = 0
                residual_linf = None
            timing_values = {
                "prepare": prepare_seconds if process_rows == 0 or records and records[-1]["molecule"] != item["name"] else 0.0,
                "environment_startup": environment_startup_seconds if process_rows == 0 else 0.0,
                "data_read": data_read_seconds if process_rows == 0 else 0.0,
                "compile_jit": None,
                "warmup": 0.0,
                "h2d": h2d_seconds,
                "scf_fock": scf_seconds if process_rows == 0 or records and records[-1]["molecule"] != item["name"] else 0.0,
                "cp_hf_gmres": response_seconds,
                "property_readout": readout_seconds,
                "physical_residual": residual_seconds,
                "independent_scorer": None,
                "serialization": None,
                "retry": 0.0,
                "fallback": 0.0,
            }
            row = {
                "schema": "vibedataset.attribution_4arm.telemetry_row.v1",
                "arm": args.arm,
                "molecule": item["name"],
                "qm9_id": item["qm9_id"],
                "trajectory": request["id"],
                "protocol": protocol,
                "input_sha256": manifest["manifest_sha256"],
                "backend": "gpu4pyscf-patched" if backend_patched else "gpu4pyscf-official",
                "orchestration": "gqc-planner-assets" if arm_is_gqc else "native-ordinary",
                "status": status,
                "failure_reason": failure_reason,
                "fields_requested": requested,
                "fields_computed": solve_names,
                "fields_reused": [name for name in requested if name not in solve_names],
                "targets": values,
                "response_vectors": {name: np.asarray(vector, dtype=np.float64).reshape(-1).tolist() for name, vector in ({name: assets[name] for name in requested} if arm_is_gqc else ({name: response["vectors"][name] for name in requested} if response else {})).items()},
                "response_densities": {name: density.reshape(-1).tolist() for name, density in densities.items()},
                "response_metrics": {
                    "operator_calls": operator_calls,
                    "operator_rows": operator_rows,
                    "residual_linf": residual_linf,
                    "device_to_host_bytes": sum(np.asarray(value).nbytes for value in response["vectors"].values()) if response else 0,
                    "host_to_device_bytes": h2d_bytes,
                },
                "cache": None if cache is None else {"calls": cache.calls, "hits": cache.hits, "misses": cache.misses},
                "scf_cycles": scf_cycles,
                "timing_unknowns": [
                    "compile_jit is not exposed by the official Python API",
                    "independent_scorer runs in a separate process and is not included in producer wall time",
                ],
            }
            serialization_started = time.perf_counter()
            encoded = json.dumps(row, sort_keys=True)
            serialization_seconds = time.perf_counter() - serialization_started
            timing_values["serialization"] = serialization_seconds
            row["timing"] = request_timing(timing_values, time.perf_counter() - request_started)
            records.append(row)
            process_rows += 1
            _ = encoded
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    with (out / "raw.jsonl").open("w") as handle:
        for row in records:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    run = {
        "schema": "vibedataset.attribution_4arm.telemetry_run.v1",
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
        "device": device,
        "record_count": len(records),
        "failed_count": len(failed),
        "failures": failed,
        "elapsed_seconds": time.perf_counter() - process_started,
        "timing_fields": TIMING_FIELDS,
        "timing_semantics": {
            "compile_jit": "null because official API does not expose compilation timing",
            "independent_scorer": "null because the scorer is a separate process",
            "end_to_end_wall_seconds": "request process wall time from request entry through row construction",
            "known_seconds": "sum of non-null timing fields",
            "unattributed_seconds": "end_to_end_wall_seconds minus known_seconds, never reclassified as a speedup",
        },
        "blind": True,
        "oracle_loaded": False,
        "scorer_loaded": False,
    }
    (out / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    print(json.dumps({"status": "accepted" if not failed else "completed-with-failures", "arm": args.arm, "rows": len(records), "failed": len(failed)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--arm", choices=("A", "B", "C", "D"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--gpu4pyscf-source-commit", default="unknown")
    parser.add_argument("--patch", type=Path)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
