#!/usr/bin/env python3
"""Matched orbital/auxiliary-basis analytic gradients, Hessians and directional gradient differences."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pyscf
from pyscf import df, dft, gto


def seal(data):
    return hashlib.sha256(data).hexdigest()


def data_hash(value):
    return seal(np.ascontiguousarray(value, dtype="<f8").tobytes())


def compute(case, protocol, coords, backend, full):
    if backend == "gpu":
        import cupy as xp
        from gpu4pyscf import scf as scfmod, dft as dftmod

        host = xp.asnumpy
    else:
        import numpy as xp
        from pyscf import scf as scfmod, dft as dftmod

        host = np.asarray
    atoms = [(v[0], c) for v, c in zip(case["atoms"], coords)]
    mol = gto.M(
        atom=atoms,
        basis=protocol["basis"],
        unit=protocol["unit"],
        charge=case["charge"],
        spin=case["spin"],
        cart=False,
        verbose=0,
    )
    if case["method"] == "B3LYP":
        mf = dftmod.RKS(mol)
        mf.xc = "b3lyp"
        grid = dft.gen_grid.Grids(mol)
        grid.level = protocol["fixed_quadrature"]["level"]
        grid.build()
        mf.grids.coords = xp.asarray(grid.coords)
        mf.grids.weights = xp.asarray(grid.weights)
        mf.small_rho_cutoff = 0.0
        grid_id = [data_hash(grid.coords), data_hash(grid.weights)]
    else:
        mf = scfmod.RHF(mol) if case["method"] == "RHF" else scfmod.UHF(mol)
        grid_id = None
    mf = mf.density_fit(auxbasis=protocol["auxbasis"])
    mf.conv_tol = protocol["scf_tol"]
    mf.conv_tol_cpscf = protocol["response_tol"]
    mf.max_cycle = 150
    mf.kernel()
    if not mf.converged:
        raise ValueError("unconverged SCF")
    grad = mf.nuc_grad_method()
    grad.auxbasis_response = protocol["gradient_auxbasis_response"]
    if hasattr(grad, "grid_response"):
        grad.grid_response = False
    g = host(grad.kernel())
    auxmol = df.addons.make_auxmol(mol, protocol["auxbasis"])
    stable = lambda obj: seal(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    )
    row = dict(
        energy=float(mf.e_tot),
        gradient=g.tolist(),
        orbital_basis_sha256=stable(mol._basis),
        auxiliary_basis_sha256=stable(auxmol._basis),
        ao_count=mol.nao,
        aux_count=auxmol.nao,
        grid_id=grid_id,
    )
    if full:
        hessian = mf.Hessian()
        hessian.auxbasis_response = protocol["hessian_auxbasis_response"]
        if hasattr(hessian, "grid_response"):
            hessian.grid_response = False
        h = host(hessian.kernel()).transpose(0, 2, 1, 3).reshape(3 * mol.natm, -1)
        row["hessian"] = h.tolist()
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("backend", choices=("cpu", "gpu"))
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    protocol = json.loads(a.protocol.read_bytes())
    rows = []
    a.out.mkdir(parents=True, exist_ok=False)
    with (a.out / "attempts.jsonl").open("x") as log:
        for case in protocol["cases"]:
            row = dict(id=case["id"])
            start = time.perf_counter()

            def attempt(coords, full, step=0, sign=0):
                log.write(
                    json.dumps(
                        dict(id=case["id"], step=step, sign=sign, started=time.time())
                    )
                    + "\n"
                )
                log.flush()
                result = compute(case, protocol, coords, a.backend, full)
                log.write(
                    json.dumps(
                        dict(id=case["id"], step=step, sign=sign, completed=time.time())
                    )
                    + "\n"
                )
                log.flush()
                return result

            try:
                coords = np.array([a[1] for a in case["atoms"]], dtype=float)
                row.update(attempt(coords, True))
                if case["finite_gradient_direction"]:
                    v = np.zeros_like(coords)
                    v[0, 0] = -(0.5**0.5)
                    v[-1, 0] = 0.5**0.5
                    row["direction"] = v.tolist()
                    row["differences"] = []
                    for step in protocol["steps_bohr"]:
                        g = [
                            attempt(coords + sign * step * v, False, step, sign)
                            for sign in (-1, 1)
                        ]
                        fd = (
                            np.array(g[1]["gradient"]) - np.array(g[0]["gradient"])
                        ).ravel() / (2 * step)
                        row["differences"].append(
                            dict(
                                step=step,
                                displaced_gradients=[r["gradient"] for r in g],
                                directional_Hv=fd.tolist(),
                            )
                        )
                row["status"] = "produced"
            except (
                RuntimeError,
                ValueError,
                NotImplementedError,
                TypeError,
                AttributeError,
                AssertionError,
            ) as exc:
                row.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
            row["wall_seconds"] = time.perf_counter() - start
            rows.append(row)
    report = dict(
        backend=a.backend,
        pyscf=pyscf.__version__,
        slurm_job=os.getenv("SLURM_JOB_ID"),
        protocol_sha256=seal(a.protocol.read_bytes()),
        code_sha256=seal(Path(__file__).read_bytes()),
        rows=rows,
    )
    if a.backend == "gpu":
        import cupy, gpu4pyscf

        report.update(
            gpu4pyscf=gpu4pyscf.__version__,
            gpu=cupy.cuda.runtime.getDeviceProperties(0)["name"].decode(),
        )
    (a.out / "result.json").write_text(
        json.dumps(report, allow_nan=False, indent=2) + "\n"
    )
    print([(r["id"], r["status"], r.get("reason")) for r in rows])


if __name__ == "__main__":
    main()
