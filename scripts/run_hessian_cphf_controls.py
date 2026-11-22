#!/usr/bin/env python3
"""CPU PySCF Hessian/CPKS controls for Issue #40."""
from __future__ import annotations
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np

def digest(array):
    return hashlib.sha256(np.asarray(array, dtype=np.float64).tobytes()).hexdigest()

def run_case(gto, scf_module, name, atoms, charge=0, spin=0, method="RHF"):
    mol = gto.M(atom=atoms, unit="Bohr", basis="sto-3g", charge=charge, spin=spin, verbose=0)
    mf = (scf_module.RHF(mol) if method == "RHF" else scf_module.UHF(mol)).set(conv_tol=1e-10, max_cycle=100)
    started = time.perf_counter()
    mf.kernel()
    row = {"name": name, "method": method, "charge": charge, "spin": spin, "atoms": len(atoms), "scf_converged": bool(mf.converged), "energy_hartree": float(mf.e_tot), "status": "pending"}
    if not mf.converged:
        row.update(status="reject-and-recompute", reason="SCF failed", seconds=time.perf_counter() - started)
        return row
    try:
        gradient = mf.nuc_grad_method().kernel()
        hessian = mf.Hessian().kernel()
        eigenvalues = np.linalg.eigvalsh(hessian.reshape(3 * len(atoms), 3 * len(atoms)))
        row.update(status="accepted", gradient_linf=float(np.max(np.abs(gradient))), hessian_shape=list(hessian.shape), hessian_sha256=digest(hessian), hessian_values=np.asarray(hessian, dtype=np.float64).tolist(), negative_eigenvalues=int(np.sum(eigenvalues < -1e-8)), minimum_hessian_eigenvalue=float(eigenvalues[0]), seconds=time.perf_counter() - started)
    except Exception as exc:
        row.update(status="reject-and-recompute", reason=f"{type(exc).__name__}: {exc}", seconds=time.perf_counter() - started)
    return row

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    from pyscf import gto, scf
    cases = [
        ("h2o", [("O", (0, 0, 0)), ("H", (0, 1.4, 0)), ("H", (1.3, 0, 0))], 0, 0, "RHF"),
        ("nh3", [("N", (0, 0, 0)), ("H", (0, 1.8, 0)), ("H", (1.56, -0.9, 0)), ("H", (-1.56, -0.9, 0))], 0, 0, "RHF"),
        ("lih", [("Li", (0, 0, 0)), ("H", (3.015, 0, 0))], 0, 0, "RHF"),
        ("lih-open-shell", [("Li", (0, 0, 0)), ("H", (3.015, 0, 0))], 1, 1, "UHF"),
    ]
    rows = [run_case(gto, scf, *case) for case in cases]
    result = {"schema": "vibedataset.hessian_cphf_controls.v1", "protocol": {"basis": "sto-3g", "precision": "FP64", "scf_tol": 1e-10, "response_semantics": "relaxed_hessian"}, "rows": rows, "independent_gpu4pyscf_crosscheck": "recorded separately", "veloxchem_crosscheck": "not_available", "finite_difference_hessian": "recorded separately", "limitations": ["CPU PySCF Hessian/CPKS controls only", "IR/Raman readouts not computed", "GPU4PySCF DFT/UKS Hessian support remains a separate boundary"]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "built", "rows": len(rows), "accepted": sum(row["status"] == "accepted" for row in rows)}, indent=2))

if __name__ == "__main__":
    main()
