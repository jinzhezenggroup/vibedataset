"""Count PySCF's orbital-relaxation solves for a full restricted MP2 nuclear gradient."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
from time import perf_counter
from unittest.mock import patch

import numpy as np
import pyscf
from pyscf import gto, lib, mp, scf
from pyscf.grad import mp2 as mp2_grad
from pyscf.scf import cphf

PIN = 'c63a953ba603a5ad8c1d65d88da72aaf05ede4d8'
XYZ = np.array([[0.1, 0.1, -0.1], [1.50, 0.21, 0.86], [-1.25, -0.25, 1.30]])
VECTOR = np.array([[0., 0., 0.], [0.75, 0.25, -0.1], [0.10, -0.2, 0.45]])
DIRECTION = VECTOR / np.linalg.norm(VECTOR)
FD_STEPS = [0.001, 0.0003]
FD_TOL = 2e-6
CP_TOL = 2e-7


def main():
    root = Path('_references/pyscf_2_14')
    if subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True).strip() != PIN:
        raise ValueError('PySCF source pin')
    if subprocess.check_output(['git','-C',root,'status','--porcelain']):
        raise ValueError('PySCF checkout is dirty')
    modules = {}
    for module in (mp2_grad, cphf, scf.hf):
        source = (root / Path(*module.__name__.split('.'))).with_suffix('.py')
        raw = Path(module.__file__).read_bytes()
        if source.read_bytes() != raw:
            raise ValueError(f'installed PySCF module differs: {module.__name__}')
        modules[module.__name__] = hashlib.sha256(raw).hexdigest()
    lib.num_threads(1)
    events = []
    cphf_events = []
    original = cphf.solve
    started = perf_counter()

    def solve_geometry(xyz, label):
        event = dict(label=label, xyz_bohr=xyz.tolist(), status='started')
        events.append(event)
        t = perf_counter()
        mol = gto.M(atom=list(zip(['O','H','H'], xyz, strict=True)), basis='sto-3g', unit='Bohr',
                    charge=0, spin=0, cart=False, verbose=0)
        mf = scf.RHF(mol)
        mf.conv_tol = 1e-13
        mf.conv_tol_grad = 1e-9
        mf.max_cycle = 120
        mf.chkfile = None
        mf.kernel()
        if not mf.converged:
            raise ArithmeticError('RHF failed')
        corr = mp.MP2(mf)
        corr.kernel()
        if not np.isfinite(corr.e_tot):
            raise ArithmeticError('MP2 energy is nonfinite')
        event.update(energy_hartree=corr.e_tot, rhf_cycles=mf.cycles, status='completed',
                     elapsed_seconds=perf_counter()-t)
        return corr

    def instrument(fvind, mo_energy, mo_occ, h1, *args, **kwargs):
        event = dict(rhs_shape=list(h1.shape), induced_potential_calls=0)
        cphf_events.append(event)
        def measured(vectors):
            event['induced_potential_calls'] += 1
            return fvind(vectors)
        solution = original(measured, mo_energy, mo_occ, h1, *args, **kwargs)
        z = solution[0]
        gap = mo_energy[mo_occ == 0, None] - mo_energy[mo_occ > 0]
        residual = gap * z + fvind(z) + h1
        event.update(extra_validation_actions=1, primal_equation_max_residual=float(abs(residual).max()))
        return solution

    corr = solve_geometry(XYZ, 'zero')
    t = perf_counter()
    with patch.object(cphf, 'solve', instrument):
        grad = corr.nuc_grad_method().kernel()
    grad_seconds = perf_counter() - t
    analytic = float(np.sum(grad * DIRECTION))
    nmo = corr.mo_coeff.shape[1]
    with patch.object(mp2_grad, '_response_dm1', return_value=np.zeros((nmo,nmo))):
        frozen = float(np.sum(corr.nuc_grad_method().kernel() * DIRECTION))

    fd = []
    for h in FD_STEPS:
        plus = solve_geometry(XYZ + h * DIRECTION, f'plus_{h}').e_tot
        minus = solve_geometry(XYZ - h * DIRECTION, f'minus_{h}').e_tot
        value = (plus - minus) / (2 * h)
        fd.append(dict(step_bohr=h, gradient=value, relaxed_error=abs(value-analytic),
                       omitted_orbital_relaxation_error=abs(value-frozen)))

    checks = (len(cphf_events)==1 and len(cphf_events[0]['rhs_shape'])==2
              and cphf_events[0]['primal_equation_max_residual'] < CP_TOL
              and len(events)==5 and all(row['relaxed_error'] < FD_TOL and
                                        row['omitted_orbital_relaxation_error'] > FD_TOL for row in fd))
    print(json.dumps(dict(pyscf_pin=PIN, module_sha256=modules, pyscf_version=pyscf.__version__,
        program='restricted all-electron MP2/RHF STO-3G, spherical, no DF, neutral singlet',
        c1=True, lib_threads=lib.num_threads(), python=platform.python_version(), numpy=np.__version__,
        driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        libcgto_sha256=hashlib.sha256(Path(gto.moleintor.libcgto._name).read_bytes()).hexdigest(),
        scf_conv_tol=1e-13, scf_conv_tol_grad=1e-9, finite_difference_tolerance=FD_TOL,
        cphf_residual_tolerance=CP_TOL, calls=events, cphf=cphf_events,
        elapsed_seconds_after_imports=perf_counter()-started, relaxed_gradient_seconds=grad_seconds,
        relaxed_gradient=grad.tolist(), direction=DIRECTION.tolist(), units='hartree/bohr', analytic_projection=analytic,
        ablated_projection=frozen, finite_differences=fd, checks_passed=checks),indent=2,allow_nan=False))
    return int(not checks)


if __name__ == '__main__':
    raise SystemExit(main())
