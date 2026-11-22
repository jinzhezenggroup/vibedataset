#!/usr/bin/env python3
"""Independently assemble dense CPU response operators and verify frontier outputs."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pyscf
from pyscf import dft, gto, lib, scf
from pyscf.data.elements import ELEMENTS
from pyscf.scf import _response_functions  # registers gen_response


def hashed(value):
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(data).hexdigest()


def array_hash(x):
    return hashlib.sha256(np.asarray(x, dtype="<f8", order="C").tobytes()).hexdigest()


def independent_model(item, case, protocol):
    coordinates = np.array(item["coordinates_bohr"], copy=True)
    origin = list(protocol["origin"])
    change = case["change"]
    if change == "displaced":
        coordinates[-1, 0] += 0.02
    if change == "different-origin":
        origin = [0.1, 0.0, 0.0]
    basis = "6-31g*" if change == "split-valence" else protocol["basis"]
    charge, mult = item["charge"], item["multiplicity"]
    if change == "open-shell":
        charge, mult = 1, 2
    method = "B3LYP" if change == "hybrid-functional" else "RHF"
    atoms = [
        (ELEMENTS[z], coords.tolist())
        for z, coords in zip(item["atomic_numbers"], coordinates)
    ]
    mol = gto.M(
        atom=atoms,
        unit="Bohr",
        basis=basis,
        cart=False,
        charge=charge,
        spin=mult - 1,
        verbose=0,
    )
    ident = dict(
        protocol,
        method=method,
        basis=basis,
        origin=origin,
        charge=charge,
        multiplicity=mult,
        ordered_geometry_sha256=hashed(atoms),
        basis_parameters_sha256=hashed(mol._basis),
        grid_sha256=None,
        rhs=["electric-field-x", "electric-field-y", "electric-field-z"],
        state="lowest converged canonical restricted SCF",
    )
    if mult != 1:
        return {"identity": ident, "unsupported": True}
    if method == "B3LYP":
        mf = dft.RKS(mol)
        mf.xc = "b3lyp"
        mf.grids.level = 3
        mf.grids.build()
        mf.small_rho_cutoff = 0
        ident["grid_sha256"] = hashed(
            [array_hash(mf.grids.coords), array_hash(mf.grids.weights)]
        )
    else:
        mf = scf.RHF(mol)
    mf.conv_tol = 1e-12
    mf.conv_tol_grad = 1e-9
    mf.max_cycle = 150
    mf.kernel()
    if not mf.converged:
        raise ValueError("independent CPU SCF nonconvergence")
    occ = mf.mo_occ > 0
    co, cv = mf.mo_coeff[:, occ], mf.mo_coeff[:, ~occ]
    gap = mf.mo_energy[~occ, None] - mf.mo_energy[None, occ]
    n = gap.size
    if not 0 < n <= 256:
        raise ValueError("bounded dense reference dimension exceeded")
    trial = np.eye(n).reshape(n, *gap.shape)
    half = 2 * (cv @ trial @ co.T)
    dm = half + half.transpose(0, 2, 1)
    induced = mf.gen_response(hermi=1)

    # Columns are obtained from the CPU induced potential on unit orbital rotations.
    def potential(densities):
        return cv.T @ induced(densities) @ co

    images = np.concatenate([potential(dm[i : i + 8]) for i in range(0, n, 8)])
    operator = np.diag(gap.ravel()) + images.reshape(n, n).T
    with mol.with_common_orig(tuple(origin)):
        position = mol.intor("int1e_r", comp=3)
    b = (cv.T @ position @ co).reshape(3, n)
    x = np.linalg.solve(operator, b.T).T
    dm0 = 2 * (cv @ x.reshape(3, *gap.shape) @ co.T)
    dm0 = dm0 + dm0.transpose(0, 2, 1)
    oracle_residual = float(
        np.max(
            abs(
                x.reshape(3, *gap.shape) * gap
                + potential(dm0)
                - b.reshape(3, *gap.shape)
            )
        )
    )
    singular = np.linalg.svd(operator, compute_uv=False)
    return dict(
        identity=ident,
        co=co,
        cv=cv,
        gap=gap,
        orbital_overlap=mf.get_ovlp(),
        position=position,
        rhs=b,
        density=dm0,
        targets=np.einsum("duv,kvu->dk", dm0, position),
        dual=np.linalg.solve(operator.T, 4 * b.T).T,
        condition=float(singular[0] / singular[-1]),
        sigma_min=float(singular[-1]),
        oracle_residual=oracle_residual,
        potential=potential,
        energy=float(mf.e_tot),
    )


def certify(row, model, limits):
    identity = model["identity"]
    if row.get("target_identity") != identity or row.get(
        "target_identity_sha256"
    ) != hashed(identity):
        return dict(status="reject-and-recompute", reason="target identity")
    if model.get("unsupported"):
        return dict(
            status="evidence-unavailable"
            if row["status"] == "evidence-unavailable"
            else "reject-and-recompute",
            reason="no qualified restricted target for this charge/spin",
        )
    if row.get("status") != "computed":
        return dict(
            status="reject-and-recompute", reason="missing or rejected producer output"
        )
    co, cv, s = model["co"], model["cv"], model["orbital_overlap"]
    dm, q = np.asarray(row["density"]), np.asarray(row["polarizability"])
    if (
        dm.shape != (3, len(s), len(s))
        or q.shape != (3, 3)
        or not np.isfinite(dm).all()
        or not np.isfinite(q).all()
    ):
        return dict(status="reject-and-recompute", reason="invalid output tensors")
    if row["density_sha256"] != array_hash(dm):
        return dict(status="reject-and-recompute", reason="candidate density digest")
    x = (cv.T @ s @ dm @ s @ co) / 2
    d = 2 * (cv @ x @ co.T)
    tangent = d + d.transpose(0, 2, 1)
    res = (x * model["gap"] + model["potential"](tangent)).reshape(3, -1) - model["rhs"]
    measured = np.einsum("duv,kvu->dk", dm, model["position"])
    error = dict(
        physical_residual_linf=float(np.max(abs(res))),
        reference_residual_linf=model["oracle_residual"],
        ao_linf=float(np.max(abs(dm - model["density"]))),
        tangent_linf=float(np.max(abs(dm - tangent))),
        readout_linf=float(np.max(abs(q - model["targets"]))),
        readout_vs_density=float(np.max(abs(q - measured))),
    )
    thresholds = dict(
        physical_residual_linf=limits["cpu_residual_linf"],
        reference_residual_linf=limits["cpu_oracle_linf"],
        ao_linf=limits["ao_linf"],
        tangent_linf=limits["ao_linf"],
        readout_linf=limits["readout_linf"],
        readout_vs_density=limits["readout_linf"],
    )
    failed = [k for k, x in error.items() if not np.isfinite(x) or x > thresholds[k]]
    return dict(
        status="reject-and-recompute" if failed else "accepted",
        failed_gates=failed,
        errors=error,
        cpu_targets=model["targets"].tolist(),
        sigma_min=model["sigma_min"],
        condition=model["condition"],
        projected_readout_signed_error=(res @ model["dual"].T).tolist(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "protocol", "manifest", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_bytes())
    manifest = json.loads(args.manifest.read_bytes())
    if (
        pyscf.__version__ != "2.14.0"
        or manifest["manifest_sha256"] != spec["manifest_sha256"]
    ):
        raise ValueError("reference environment or inputs mismatch")
    molecules = {i["name"]: i for i in manifest["molecules"]}
    models = {}
    model_cost = {}
    rows = []
    elapsed = time.perf_counter()
    for case in spec["cases"]:
        name = case["molecule"]
        change = case["change"]
        key = (
            name,
            change
            if change
            in {
                "split-valence",
                "hybrid-functional",
                "displaced",
                "different-origin",
                "open-shell",
            }
            else "exact",
        )
        if key not in models:
            tick = time.perf_counter()
            models[key] = independent_model(molecules[name], case, manifest["protocol"])
            model_cost["/".join(key)] = time.perf_counter() - tick
        for mode in spec["modes"]:
            tick = time.perf_counter()
            file = args.root / mode / (case["id"] + ".json.gz")
            record = dict(case=case["id"], mode=mode)
            try:
                data = gzip.decompress(file.read_bytes())
                row = json.loads(data)
                if row["case"] != case["id"] or row["mode"] != mode:
                    raise ValueError("candidate identity")
                quality = certify(row, models[key], spec["limits"])
                record.update(
                    action=row.get("action"),
                    candidate_sha256=hashlib.sha256(data).hexdigest(),
                    operator_rows=row.get("solver_operator_rows"),
                    producer_status=row["status"],
                    producer_seconds_before_io=row["elapsed_before_io_s"],
                    **quality,
                )
            except (KeyError, ValueError, OSError) as exc:
                record.update(status="evidence-unavailable", reason=str(exc))
            record["scorer_seconds"] = time.perf_counter() - tick
            rows.append(record)
    result = dict(
        schema="vibedataset.independent_frontier_score.v1",
        cpu_pyscf=pyscf.__version__,
        threads=lib.num_threads(),
        protocol_sha256=hashlib.sha256(args.protocol.read_bytes()).hexdigest(),
        rows=rows,
        counts=dict(Counter(r["status"] for r in rows)),
        ref_seconds=model_cost,
        full_seconds=time.perf_counter() - elapsed,
    )
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
