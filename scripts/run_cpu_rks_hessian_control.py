#!/usr/bin/env python3
"""CPU PySCF RKS(B3LYP)/STO-3G Hessian control matching the GPU row."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np


def digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(array, dtype=np.float64).tobytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from pyscf import gto, dft

    mol = gto.M(
        atom="O 0 0 0; H 0 1.4 0; H 1.3 0 0",
        unit="Bohr",
        basis="sto-3g",
        charge=0,
        spin=0,
        verbose=0,
    )
    mf = dft.RKS(mol).set(conv_tol=1e-10, max_cycle=100)
    mf.xc = "b3lyp"
    started = time.perf_counter()
    mf.kernel()
    row = {
        "name": "h2o-rks",
        "method": "RKS",
        "xc": "b3lyp",
        "scf_converged": bool(mf.converged),
        "energy_hartree": float(mf.e_tot),
        "status": "pending",
    }
    if not mf.converged:
        row.update(status="reject-and-recompute", reason="SCF failed")
    else:
        hessian = np.asarray(mf.Hessian().kernel(), dtype=np.float64)
        row.update(
            status="accepted",
            hessian_shape=list(hessian.shape),
            hessian_sha256=digest(hessian),
            hessian_values=hessian.tolist(),
            hessian_max=float(np.max(np.abs(hessian))),
            seconds=time.perf_counter() - started,
        )
    result = {
        "schema": "vibedataset.cpu_rks_hessian_control.v1",
        "protocol": {"method": "RKS", "xc": "b3lyp", "basis": "sto-3g", "unit": "Bohr", "precision": "FP64", "scf_tol": 1e-10},
        "rows": [row],
        "limitations": ["This is a CPU/GPU micro-control for H2O/RKS(B3LYP), not a multi-sample spectroscopy benchmark."],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": row["status"], "seconds": row.get("seconds")}, indent=2))


if __name__ == "__main__":
    main()
