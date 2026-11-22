#!/usr/bin/env python3
"""Finite-difference gradient Hessian control for the H2O RHF protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np


ATOMS = [("O", (0.0, 0.0, 0.0)), ("H", (0.0, 1.4, 0.0)), ("H", (1.3, 0.0, 0.0))]


def digest(array: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(array, dtype=np.float64).tobytes()).hexdigest()


def gradient(gto, scf, coordinates: np.ndarray) -> np.ndarray:
    atom = [(symbol, tuple(float(value) for value in position)) for (symbol, _), position in zip(ATOMS, coordinates)]
    mol = gto.M(atom=atom, unit="Bohr", basis="sto-3g", charge=0, spin=0, verbose=0)
    mf = scf.RHF(mol).set(conv_tol=1e-10, max_cycle=100)
    mf.kernel()
    if not mf.converged:
        raise RuntimeError("SCF failed for displaced geometry")
    return np.asarray(mf.nuc_grad_method().kernel(), dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--step", type=float, default=1e-4)
    args = parser.parse_args()
    from pyscf import gto, scf

    coordinates = np.asarray([position for _, position in ATOMS], dtype=np.float64)
    started = time.perf_counter()
    hessian = np.empty((len(ATOMS), len(ATOMS), 3, 3), dtype=np.float64)
    gradient_calls = 0
    for atom_index in range(len(ATOMS)):
        for coordinate_index in range(3):
            plus = coordinates.copy()
            minus = coordinates.copy()
            plus[atom_index, coordinate_index] += args.step
            minus[atom_index, coordinate_index] -= args.step
            g_plus = gradient(gto, scf, plus)
            g_minus = gradient(gto, scf, minus)
            gradient_calls += 2
            hessian[:, atom_index, :, coordinate_index] = (g_plus - g_minus) / (2.0 * args.step)
    values = hessian.tolist()
    result = {
        "schema": "vibedataset.hessian_cphf.finite_difference_control.v1",
        "protocol": {
            "method": "RHF",
            "basis": "sto-3g",
            "unit": "Bohr",
            "precision": "FP64",
            "scf_tol": 1e-10,
            "difference": "central difference of analytic nuclear gradients",
            "step_bohr": args.step,
        },
        "geometry": [[symbol, list(position)] for symbol, position in ATOMS],
        "gradient_calls": gradient_calls,
        "hessian_shape": list(hessian.shape),
        "hessian_sha256": digest(hessian),
        "hessian_values": values,
        "hessian_max": float(np.max(np.abs(hessian))),
        "seconds": time.perf_counter() - started,
        "status": "accepted",
        "limitations": [
            "Finite-difference truncation and SCF convergence error are not a formal error bound.",
            "This control covers H2O/RHF only and does not validate GPU mixed precision.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "gradient_calls": gradient_calls, "seconds": result["seconds"]}, indent=2))


if __name__ == "__main__":
    main()
