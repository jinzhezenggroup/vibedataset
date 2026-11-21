#!/usr/bin/env python3
"""Independent scorer for the four-arm attribution records.

This process reads the sealed manifest and raw arm records, then rebuilds each
reference with official GPU4PySCF.  It does not import the GQC planner or trust
an arm's own error estimate.  Orbital-response vectors are compared through
an induced-potential image as well as the final target scalars because CPHF
solutions may differ by an occupied/virtual orbital gauge while representing
an identical physical density response.
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


def load(path):
    return json.loads(Path(path).read_text())


def field_index(name):
    return {"x": 0, "y": 1, "z": 2}[name]


def molecule(gto, item, protocol):
    symbols = {1: "H", 6: "C", 7: "N", 8: "O", 9: "F"}
    atoms = [(symbols[z], tuple(coords)) for z, coords in zip(item["atomic_numbers"], item["coordinates_bohr"])]
    return gto.M(atom=atoms, unit="Bohr", basis=protocol["basis"], charge=item["charge"],
                  spin=item["multiplicity"] - 1, cart=False, verbose=0)


def oracle_for_molecule(cupy, cphf, gto, scf, polarizability, item, protocol):
    mol = molecule(gto, item, protocol)
    mf = scf.RHF(mol).set(conv_tol=protocol["conv_tol"], max_cycle=protocol["max_cycle"])
    mf.kernel()
    if not mf.converged:
        raise RuntimeError(f"oracle SCF did not converge for {item['name']}")
    mo_coeff = cupy.asarray(mf.mo_coeff)
    mo_occ = cupy.asarray(mf.mo_occ)
    mo_energy = cupy.asarray(mf.mo_energy)
    mocc = mo_coeff[:, mo_occ > 0]
    mvir = mo_coeff[:, mo_occ == 0]
    with mol.with_common_orig((0.0, 0.0, 0.0)):
        h1 = cupy.asarray(mol.intor("int1e_r"))
    h1ai_all = -cupy.einsum("au,dui->dai", mvir.conj().T, cupy.einsum("duv,vi->dui", h1, mocc))
    fvind = polarizability.gen_vind(mf, mo_coeff, mo_occ, with_nlc=True)
    values = {}
    images = {}
    densities = {}
    residuals = {}
    for direction in ("x", "y", "z"):
        index = field_index(direction)
        vector, _ = cphf.solve(fvind, mo_energy, mo_occ, h1ai_all[index:index + 1],
                               max_cycle=protocol["response_max_cycle"], tol=protocol["response_tol"], verbose=0)
        vector = vector[0]
        values[direction] = np.asarray(cupy.asnumpy(vector), dtype=np.float64)
        images[direction] = np.asarray(cupy.asnumpy(fvind(vector[None])), dtype=np.float64)[0]
        mo1_ao = cupy.einsum("ai,ua->ui", vector, mvir)
        density = 2 * cupy.einsum("ui,vi->uv", mo1_ao, mocc.conj())
        density += density.T.conj()
        densities[direction] = np.asarray(cupy.asnumpy(density), dtype=np.float64)
        e_a = mo_energy[mo_occ == 0]
        e_i = mo_energy[mo_occ > 0]
        e_ai = 1.0 / (e_a[:, None] - e_i)
        base = h1ai_all[index] * -e_ai
        residuals[direction] = float(cupy.max(cupy.abs(vector + fvind(vector[None])[0] * e_ai - base)).item())
    alpha = {}
    for left_name, left_value in values.items():
        left = cupy.asarray(left_value)
        for right_name, right in ((name, field_index(name)) for name in values):
            p10 = cupy.trace(left.conj().T @ mvir.conj().T @ h1[right] @ mocc) * 2
            p01 = cupy.trace(mocc.conj().T @ h1[right] @ mvir @ left) * 2
            alpha[left_name + right_name] = float(((p10 + p01).real).item())
    return {"vectors": values, "images": images, "densities": densities, "targets": alpha, "residuals": residuals, "apply": fvind}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target-tol", type=float, default=1e-5)
    parser.add_argument("--image-tol", type=float, default=1e-5)
    parser.add_argument("--residual-tol", type=float, default=1e-5)
    args = parser.parse_args()
    manifest = load(args.manifest)
    import cupy
    from pyscf import gto
    from gpu4pyscf import scf
    from gpu4pyscf.scf import cphf
    from gpu4pyscf.properties import polarizability

    oracles = {}
    started = time.perf_counter()
    items = {item["name"]: item for item in manifest["molecules"]}
    for name, item in items.items():
        oracles[name] = oracle_for_molecule(cupy, cphf, gto, scf, polarizability, item, manifest["protocol"])

    arm_rows = {}
    for raw_path in sorted(args.raw_dir.glob("raw-*.jsonl")):
        arm = raw_path.stem.removeprefix("raw-")
        rows = [json.loads(line) for line in raw_path.read_text().splitlines() if line.strip()]
        arm_rows[arm] = rows

    scored = []
    for arm, rows in arm_rows.items():
        for row in rows:
            oracle = oracles[row["molecule"]]
            target_errors = {
                key: abs(float(value) - oracle["targets"][key])
                for key, value in row["targets"].items()
            }
            image_errors = {}
            density_errors = {}
            raw_vector_errors = {}
            for field, encoded in row["response_vectors"].items():
                observed = np.asarray(encoded, dtype=np.float64)
                reference = oracle["vectors"][field]
                raw_vector_errors[field] = float(np.max(np.abs(observed - reference.reshape(-1))))
                observed_density = np.asarray(row["response_densities"][field], dtype=np.float64).reshape(oracle["densities"][field].shape)
                density_errors[field] = float(np.max(np.abs(observed_density - oracle["densities"][field])))
                # The physical operator image is the gauge-invariant quantity
                # consumed by the response equation.
                observed_image = oracle["apply"](cupy.asarray(observed.reshape(reference.shape))[None])[0]
                image_errors[field] = float(cupy.max(cupy.abs(
                    observed_image - cupy.asarray(oracle["images"][field])
                )).item())
            # A raw residual estimate is not trusted as truth.  Compare its
            # declared value with the independently recomputed residual scale.
            observed_residual = float((row.get("response_metrics") or {}).get("residual_linf", 0.0))
            reference_residual = max(oracle["residuals"][field] for field in row["fields_requested"])
            residual_error = abs(observed_residual - reference_residual)
            accepted = (
                max(target_errors.values(), default=0.0) <= args.target_tol
                and reference_residual <= args.residual_tol
                and max(density_errors.values(), default=0.0) <= args.image_tol
            )
            scored.append({
                "arm": arm,
                "molecule": row["molecule"],
                "trajectory": row["trajectory"],
                "fields_requested": row["fields_requested"],
                "target_errors": target_errors,
                "max_target_error": max(target_errors.values(), default=0.0),
                "raw_vector_errors": raw_vector_errors,
                "operator_image_errors": image_errors,
                "max_operator_image_error": max(image_errors.values(), default=0.0),
                "ao_density_errors": density_errors,
                "max_ao_density_error": max(density_errors.values(), default=0.0),
                "observed_residual_linf": observed_residual,
                "oracle_residual_linf": reference_residual,
                "residual_scale_difference": residual_error,
                "status": "accepted" if accepted else "reject-and-recompute",
            })
    summary = {
        "schema": "vibedataset.attribution_4arm.score.v1",
        "manifest_sha256": manifest["manifest_sha256"],
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": sys.version,
        "platform": platform.platform(),
        "oracle_backend": "official-gpu4pyscf-independent-process",
        "oracle_loaded_gqc_planner": False,
        "thresholds": {"target_linf": args.target_tol, "operator_residual_linf": args.residual_tol},
        "rows": scored,
        "counts": {},
        "elapsed_seconds": time.perf_counter() - started,
    }
    for arm in arm_rows:
        arm_scored = [row for row in scored if row["arm"] == arm]
        summary["counts"][arm] = {
            "rows": len(arm_scored),
            "accepted": sum(row["status"] == "accepted" for row in arm_scored),
            "reject_and_recompute": sum(row["status"] != "accepted" for row in arm_scored),
            "max_target_error": max((row["max_target_error"] for row in arm_scored), default=0.0),
            "max_oracle_residual": max((row["oracle_residual_linf"] for row in arm_scored), default=0.0),
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
