#!/usr/bin/env python3
"""Evaluate geometric CPHF equations from observed GPU Cartesian responses with CPU AO J/K."""

import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from pyscf import gto, scf


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    protocol = json.loads(a.protocol.read_bytes())
    run = json.loads((a.root / "result.json").read_bytes())
    if (
        run["protocol_sha256"] != hashlib.sha256(a.protocol.read_bytes()).hexdigest()
        or run["mode"] != "shared"
    ):
        raise ValueError("unmatched Cartesian source")
    shells = {
        s: [[q["angular_momentum"], *q["primitives"]] for q in b]
        for s, b in protocol["shells"].items()
    }
    cases = {s["id"]: s for s in protocol["cases"]}
    proofs = {}
    links = {}
    limits = dict(
        orbital_residual=1e-5, overlap_constraint=1e-7, occupied_energy_derivative=1e-5
    )
    started = time.perf_counter()
    negative = None
    for receipt in run["requests"]:
        if receipt["status"] != "accepted":
            links[receipt["request_id"]] = dict(status="evidence-unavailable")
            continue
        row = receipt["result"]
        c = cases[row["molecule"]]
        identity = row["scientific_identity"]
        proof = row["cartesian_response"]
        path = a.root / "cartesian" / proof["path"]
        if (
            path.name != proof["path"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != proof["sha256"]
        ):
            raise ValueError("Cartesian tensor digest")
        links[receipt["request_id"]] = dict(
            identity=identity, response_sha256=proof["sha256"]
        )
        if proof["sha256"] in proofs:
            continue
        tick = time.perf_counter()
        mol = gto.M(
            atom=list(zip(c["symbols"], c["xyz"])),
            unit="Bohr",
            basis=shells,
            charge=protocol["charge"],
            spin=protocol["spin"],
            cart=False,
            verbose=0,
        )
        with np.load(path, allow_pickle=False) as z:
            C, occ, e, h1, x, e1 = [
                z[k] for k in ("coeff", "occ", "energy", "h1mo", "mo1", "mo_e1")
            ]
        co = C[:, occ > 0]
        vir = occ == 0
        eo = e[~vir]
        gap = e[vir, None] - eo
        nat = mol.natm
        nmo = C.shape[1]
        no = co.shape[1]
        if (
            x.shape != (nat, 3, nmo, no)
            or h1.shape != x.shape
            or e1.shape != (nat, 3, no, no)
        ):
            raise ValueError("Cartesian RHS shape")
        ov = -mol.intor("int1e_ipovlp", comp=3)
        s1 = []
        for lo, hi in mol.aoslice_by_atom()[:, 2:]:
            part = np.zeros_like(ov)
            part[:, lo:hi, :] = ov[:, lo:hi, :]
            s1.append(C.T @ (part + part.transpose(0, 2, 1)) @ co)
        s1 = np.asarray(s1)
        bare = h1 - s1 * eo

        def residual(vector):
            half = 2 * (C @ vector @ co.T)
            dm = half + half.transpose(0, 1, 3, 2)
            j, k = scf.RHF(mol).get_jk(
                dm=dm.reshape(3 * nat, mol.nao, mol.nao), hermi=1
            )
            v = (C.T @ (j - 0.5 * k) @ co).reshape(x.shape)
            unscaled = vector[:, :, vir, :] * gap + bare[:, :, vir, :] + v[:, :, vir, :]
            normalization = vector[:, :, ~vir, :] + 0.5 * s1[:, :, ~vir, :]
            occ_energy = (
                bare[:, :, ~vir, :]
                + v[:, :, ~vir, :]
                + vector[:, :, ~vir, :] * (eo[:, None] - eo)
                - e1
            )
            return dict(
                orbital_residual=np.max(abs(unscaled), axis=(2, 3)),
                overlap_constraint=np.max(abs(normalization), axis=(2, 3)),
                occupied_energy_derivative=np.max(abs(occ_energy), axis=(2, 3)),
            )

        errs = residual(x)
        maxima = {k: float(np.max(v)) for k, v in errs.items()}
        accepted = all(np.isfinite(m) and m <= limits[k] for k, m in maxima.items())
        proofs[proof["sha256"]] = dict(
            molecule=c["id"],
            identity=identity,
            logical_RHS=3 * nat,
            status="accepted" if accepted else "reject-and-recompute",
            per_atom_axis={k: v.tolist() for k, v in errs.items()},
            maxima=maxima,
            seconds=time.perf_counter() - tick,
        )
        if negative is None:
            artificial = x.copy()
            artificial[0, 0, np.where(vir)[0][0], 0] += 0.01
            negative = {k: float(np.max(v)) for k, v in residual(artificial).items()}
    result = dict(
        schema="vibedataset.independent_geometric_cphf.v1",
        thresholds=limits,
        by_response=proofs,
        request_links=links,
        negative_control=negative,
        source_result_sha256=hashlib.sha256(
            (a.root / "result.json").read_bytes()
        ).hexdigest(),
        all_accepted=all(r["status"] == "accepted" for r in proofs.values()),
        elapsed_seconds=time.perf_counter() - started,
    )
    a.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        result["all_accepted"], [(v["molecule"], v["maxima"]) for v in proofs.values()]
    )
    if (
        len(proofs) != len(cases)
        or negative is None
        or negative["orbital_residual"] <= limits["orbital_residual"]
    ):
        raise SystemExit("missing denominator or expected physical rejection")


if __name__ == "__main__":
    main()
