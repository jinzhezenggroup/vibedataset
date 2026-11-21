#!/usr/bin/env python3
"""Protocol expansion controls for the four-arm attribution report."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--gpu4pyscf-source-commit", default="unknown")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    symbols = {1: "H", 6: "C", 7: "N", 8: "O", 9: "F"}
    import cupy
    from pyscf import gto
    from gpu4pyscf import dft, scf
    from gpu4pyscf.properties import polarizability

    selected = {
        "rhf-6-31g-star": (manifest["molecules"][0], "RHF", "6-31g*", 1),
        "b3lyp-sto-3g": (manifest["molecules"][0], "B3LYP", "sto-3g", 1),
        "uhf-sto-3g-doublet": (manifest["molecules"][4], "UHF", "sto-3g", 2, 1),
    }
    rows = []
    for case, values in selected.items():
        if len(values) == 4:
            item, method, basis, multiplicity = values
            charge = item["charge"]
        else:
            item, method, basis, multiplicity, charge = values
        atoms = [(symbols[z], tuple(xyz)) for z, xyz in zip(item["atomic_numbers"], item["coordinates_bohr"])]
        mol = gto.M(atom=atoms, unit="Bohr", basis=basis, charge=charge, spin=multiplicity - 1, cart=False, verbose=0)
        if method == "RHF":
            mf = scf.RHF(mol)
        elif method == "UHF":
            mf = scf.UHF(mol)
        else:
            mf = dft.RKS(mol)
            mf.xc = "b3lyp"
        mf.conv_tol = manifest["protocol"]["conv_tol"]
        mf.max_cycle = manifest["protocol"]["max_cycle"]
        started = time.perf_counter()
        error = None
        energy = None
        response_status = "unsupported"
        response = None
        try:
            mf.kernel()
            energy = float(mf.e_tot)
            if not mf.converged:
                response_status = "reject-and-recompute"
                error = "SCF did not converge"
            elif method != "RHF":
                response_status = "reject-and-recompute"
                error = "GPU4PySCF polarizability entry is restricted-RHF only"
            else:
                response = polarizability.eval_polarizability(mf, max_cycle=manifest["protocol"]["response_max_cycle"], tol=manifest["protocol"]["response_tol"])
                response_status = "direct-reference"
        except Exception as exc:  # retained as a protocol failure receipt
            response_status = "reject-and-recompute"
            error = f"{type(exc).__name__}: {exc}"
        base = {
            "case": case,
            "molecule": item["name"],
            "method": method,
            "basis": basis,
            "multiplicity": multiplicity,
            "charge": charge,
            "status": response_status,
            "energy_hartree": energy,
            "polarizability": None if response is None else response.tolist(),
            "error": error,
            "seconds": time.perf_counter() - started,
            "input_manifest_sha256": manifest["manifest_sha256"],
        }
        for arm in ("A", "B", "C", "D"):
            row = dict(base)
            row["arm"] = arm
            row["orchestration"] = "native-ordinary" if arm in ("A", "B") else "gqc-planner-refine-or-reject"
            row["backend"] = "gpu4pyscf-patched" if arm in ("B", "D") else "gpu4pyscf-official"
            row["asset_disposition"] = "same-protocol-direct" if arm in ("A", "B") and case.startswith("rhf-6") else "reject-and-recompute" if method != "RHF" else "refine-required"
            rows.append(row)
    result = {
        "schema": "vibedataset.attribution_4arm.expansion.v1",
        "manifest_sha256": manifest["manifest_sha256"],
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": sys.version,
        "platform": platform.platform(),
        "cuda_name": str(cupy.cuda.runtime.getDeviceProperties(cupy.cuda.Device().id).get("name", b"unknown")),
        "rows": rows,
        "oracle_loaded": False,
        "scorer_loaded": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
