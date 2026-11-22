#!/usr/bin/env python3
"""Check the static polarizability sign, units and Cartesian axes by finite electric fields."""

import argparse
import json
from pathlib import Path
import time

import numpy as np
from pyscf import scf

from run_qm9_scale_response import digest, molecule, requests


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("protocol", "geometries", "reference", "out"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    start = time.perf_counter()
    raw = a.protocol.read_bytes()
    spec = json.loads(raw)
    frozen = requests(a.geometries, spec, digest(raw))
    rows = []
    reference = spec["reference"]
    for index in (1, 501, 1000):
        item, identity = frozen[index - 1]
        mol = molecule(item, spec)
        with mol.with_common_orig(spec["origin_bohr"]):
            r = mol.intor("int1e_r", comp=3)
        nuclear = np.einsum("i,ij->j", mol.atom_charges(), mol.atom_coords())
        h = scf.hf.get_hcore(mol)
        folder = a.reference / item["request_id"]
        certificate = json.loads((folder / "receipt.json").read_bytes())
        if certificate["input_sha256"] != identity or certificate[
            "arrays_sha256"
        ] != digest((folder / "arrays.npz").read_bytes()):
            raise ValueError("unmatched blind reference")
        with np.load(folder / "arrays.npz", allow_pickle=False) as data:
            analytical = data["polarizability"]
        steps = []
        for step in (0.0005, 0.00025):
            values = []
            outputs = []
            for axis in range(3):
                dipoles = []
                for sign in (-1, 1):
                    mf = scf.RHF(mol)
                    mf.conv_tol = 1e-13
                    mf.conv_tol_grad = 1e-10
                    mf.max_cycle = reference["scf_cycles"]
                    perturbation = h + sign * step * r[axis]
                    mf.get_hcore = lambda *args, matrix=perturbation: matrix
                    tick = time.perf_counter()
                    mf.kernel()
                    if not mf.converged:
                        raise RuntimeError(f"field SCF failed {index}/{axis}/{sign}")
                    dip = nuclear - np.einsum("uv,kvu->k", mf.make_rdm1(), r)
                    dipoles.append(dip)
                    outputs.append(
                        dict(
                            axis=axis,
                            sign=sign,
                            dipole_au=dip.tolist(),
                            energy_hartree=float(mf.e_tot),
                            scf_seconds=time.perf_counter() - tick,
                        )
                    )
                values.append((dipoles[1] - dipoles[0]) / (2 * step))
            array = np.array(values)
            steps.append(
                dict(
                    field_au=step,
                    polarizability_au=array.tolist(),
                    displaced=outputs,
                    max_absolute_analytic_error=float(np.max(abs(array - analytical))),
                )
            )
        rows.append(
            dict(request_id=item["request_id"], input_sha256=identity, steps=steps)
        )
    result = dict(
        schema="vibedataset.qm9_finite_field_check.v1",
        protocol_sha256=digest(raw),
        rows=rows,
        primary_threshold_unchanged=True,
        elapsed_seconds=time.perf_counter() - start,
    )
    a.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        [
            (r["request_id"], [s["max_absolute_analytic_error"] for s in r["steps"]])
            for r in rows
        ]
    )


if __name__ == "__main__":
    main()
