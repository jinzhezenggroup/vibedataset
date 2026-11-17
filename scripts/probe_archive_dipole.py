#!/usr/bin/env python3
"""AD-001. Validate a fixed archived dipole on the pinned Psi4/QCSchema fixtures."""
import hashlib
import itertools
import json
import lzma
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

import numpy as np
import pyscf
from pyscf import gto, scf
from pyscf.scf import hf

from inspect_qcschema_assets import DIRECTORY, PIN

TOL = 1e-6
REPO = Path('_references/qcfractal')
SOURCE = Path('_references/pyscf_2_14')
REFERENCE_COMMIT = 'c63a953ba603a5ad8c1d65d88da72aaf05ede4d8'
BASELINES = {'identity': (0, 1, 2), 'nominal_cca': (2, 0, 1), 'psi4_1_10_gaussian': (0, 2, 1)}


class Rejected(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def peak(array):
    return float(np.max(np.abs(array)))


def basis_and_geometry(molecule, basis):
    """Undo the exponent-dependent primitive normalization of Psi4's shell.coef."""
    symbols = molecule['symbols']
    xyz = np.asarray(molecule['geometry']).reshape(len(symbols), 3)
    require(np.isfinite(xyz).all() and len(basis['atom_map']) == len(symbols), 'geometry/center mismatch')
    require(not molecule.get('real') or all(molecule['real']), 'ghost center')
    atoms, basis_by_atom, shells = [], {}, []
    for i, (symbol, coords, center) in enumerate(zip(symbols, xyz, basis['atom_map'], strict=True)):
        label = f'{symbol}@{i}'
        atoms.append((label, coords))
        radial = []
        center_data = basis['center_data'][center]
        require(not center_data.get('ecp_potentials') and not center_data.get('ecp_electrons'), 'ECP')
        for shell in center_data['electron_shells']:
            ls = shell['angular_momentum']
            require(ls in ([0], [1]) and shell['harmonic_type'] == 'spherical', 'unsupported shell')
            l = ls[0]
            exps = np.asarray(shell['exponents'])
            coeff = np.asarray(shell['coefficients'])
            require(exps.ndim == 1 and np.all(exps > 0) and coeff.shape == (1, len(exps)), 'unsupported contraction')
            exponent_sum = exps[:, None] + exps
            overlaps = (np.pi / exponent_sum) ** 1.5 / (2 * exponent_sum) ** l
            require(abs(float(coeff[0] @ overlaps @ coeff[0]) - 1) <= TOL, 'archive shell norm')
            unnormalized = coeff[0] / exps ** (l / 2 + 0.75)
            radial.append([l, *np.column_stack((exps, unnormalized)).tolist()])
            shells.append((i, l, exps))
        basis_by_atom[label] = radial
    mol = gto.M(atom=atoms, basis=basis_by_atom, unit='Bohr', cart=False, charge=0, spin=0, verbose=0)
    require(mol.nbas == len(shells), 'shell count changed')
    for k, (atom, l, exps) in enumerate(shells):
        require(mol.bas_atom(k) == atom and mol.bas_angular(k) == l and mol.bas_nctr(k) == 1
                and np.array_equal(mol.bas_exp(k), np.sort(exps)[::-1]), 'shell ordering changed')
    return mol


def ao_order(angular_momenta, permutation):
    order = []
    for l in angular_momenta:
        offset = len(order)
        order.extend([offset] if l == 0 else [offset + i for i in permutation])
    return tuple(order)


def metric_candidates(coeff, overlap, angular_momenta):
    rows = {}
    for perm in itertools.permutations(range(3)):
        order = ao_order(angular_momenta, perm)
        if order not in rows:
            frame = coeff[list(order)]
            rows[order] = {'p_slots': perm, 'error': peak(frame.T @ overlap @ frame - np.eye(frame.shape[1]))}
    return rows


def unique_order(rows):
    accepted = [order for order, row in rows.items() if row['error'] <= TOL]
    require(len(accepted) == 1, f'{len(accepted)} admissible AO permutations')
    return accepted[0]


def occupations(wfn, stdout, alpha_count):
    if wfn.get('occupations_a'):
        occ = np.asarray(wfn[wfn['occupations_a']])
        source = 'exported occupations_a'
    else:
        # Printed six-decimal energies, matched within their reported precision.
        # Counts constrain the assignment; no filling based on orbital index.
        require('Doubly Occupied:' in stdout, 'missing occupation evidence')
        end = stdout.rsplit('Doubly Occupied:', 1)[1]
        require('Virtual:' in end and 'Final Occupation by Irrep:' in end, 'missing occupation evidence')
        block = end.split('Final Occupation by Irrep:', 1)[0]
        occ_section, virt_section = block.split('Virtual:', 1)
        pattern = r'\b\d+[A-Za-z]\S*\s+(-?\d+\.\d{6})(?!\d)'
        levels = np.asarray([float(e) for e in re.findall(pattern, occ_section) + re.findall(pattern, virt_section)])
        nocc = len(re.findall(pattern, occ_section))
        energies = np.asarray(wfn[wfn['eigenvalues_a']])
        require(nocc == alpha_count and levels.shape == energies.shape, 'printed occupation count')
        matches = np.abs(energies[:, None] - levels) <= 0.500001e-6
        require(np.all(matches.sum(axis=0) == 1) and np.all(matches.sum(axis=1) == 1),
                'ambiguous printed orbital energies')
        occ = matches[:, :nocc].any(axis=1).astype(float)
        source = 'final printed occupied and virtual energies'
    require(np.isin(occ, [0., 1.]).all() and occ.sum() == alpha_count, 'noninteger or inconsistent occupations')
    return occ, source


def archived_state(result, diagnostics):
    wfn = result['wavefunction']
    prop = result['properties']
    mol_data = result['molecule']
    require(result['provenance']['creator'] == 'Psi4' and result['provenance']['version'] == '1.10'
            and re.search(r'Solid Harmonics ordering:\s+Gaussian\b', result['stdout']), 'producer convention')
    require(result['model'] == {'method': 'b3lyp', 'basis': 'sto-3g'} and wfn['basis']['name'].lower() == 'sto-3g',
            'model outside protocol')
    require(mol_data['molecular_charge'] == 0 and mol_data['molecular_multiplicity'] == 1
            and wfn['restricted'] and prop['calcinfo_nalpha'] == prop['calcinfo_nbeta'], 'state outside protocol')
    mol = basis_and_geometry(mol_data, wfn['basis'])
    n = mol.nao_nr()
    require(n == prop['calcinfo_nmo'] == prop['calcinfo_nbasis'] and mol.nelectron == 2 * prop['calcinfo_nalpha'],
            'rank or electron count')
    coeff = np.asarray(wfn[wfn['orbitals_a']]).reshape(n, n)
    occ, occ_source = occupations(wfn, result['stdout'], mol.nelectron // 2)
    require(occ.shape == (n,) and np.isfinite(coeff).all(), 'invalid orbital frame')
    overlap = mol.intor_symmetric('int1e_ovlp')
    angular = [mol.bas_angular(i) for i in range(mol.nbas)]
    candidates = metric_candidates(coeff, overlap, angular)
    diagnostics.update(metric_candidates=list(candidates.values()), occupancy_evidence=occ_source)
    order = unique_order(candidates)
    from_orbitals = (coeff * (2 * occ)) @ coeff.T
    if wfn.get('density_a'):
        source_dm = 2 * np.asarray(wfn[wfn['density_a']]).reshape(n, n)
        diagnostics['density_vs_occupied_mo'] = peak(source_dm - from_orbitals)
        require(diagnostics['density_vs_occupied_mo'] <= TOL, 'density and MO disagree')
    else:
        source_dm = from_orbitals
    dm = source_dm[np.ix_(order, order)]
    checks = {'symmetry': peak(dm - dm.T), 'trace': abs(float(np.trace(dm @ overlap)) - mol.nelectron),
              'idempotency': peak(dm @ overlap @ dm - 2 * dm)}
    diagnostics.update(accepted_p_slots=candidates[order]['p_slots'] if 1 in angular else None,
                       density_checks=checks)
    require(all(value <= TOL for value in checks.values()), 'density check')
    return mol, source_dm, dm, angular


def blinded_record(data, report):
    result = data['result']
    if not result['success']:
        report.update(status='upstream_failure')
        return
    if not result.get('wavefunction'):
        report.update(status='no_archived_state')
        return
    t = time.perf_counter()
    mol, source_dm, dm, angular = archived_state(result, report)
    report['state_validation_seconds'] = time.perf_counter() - t

    def dipole(d):
        return scf.hf.dip_moment(mol, d, unit='AU', origin=np.zeros(3), verbose=0)

    t = time.perf_counter()
    value = dipole(dm)
    report['one_dipole_seconds'] = time.perf_counter() - t
    controls = {}
    for name, perm in BASELINES.items():
        order = ao_order(angular, perm)
        controls[name] = dipole(source_dm[np.ix_(order, order)])
    # Unblind only after admission and all predictions. No candidate sees this reference.
    oracle = np.asarray(result['properties']['scf_dipole_moment'])
    report.update(dipole_e_bohr=value.tolist(), reference_e_bohr=oracle.tolist(),
                  max_error=peak(value - oracle),
                  baseline_max_errors={k: peak(v - oracle) for k, v in controls.items()})
    report['status'] = 'verified' if report['max_error'] <= TOL else 'reference_disagreement'


def negative_controls():
    # Distinct p slots can all be orthonormal. Identity of the metric alone
    # does not resolve the axes, regardless of the target observable.
    controls = {
        'ambiguous_p_frame': lambda: unique_order(metric_candidates(np.eye(3), np.eye(3), [1])),
        'scaled_s_orbital': lambda: unique_order(metric_candidates(2 * np.eye(1), np.eye(1), [0])),
        'no_occupation_record': lambda: occupations({}, '', 1),
    }
    out = {}
    for name, action in controls.items():
        try:
            action()
        except Rejected as exc:
            out[name] = str(exc)
        else:
            raise AssertionError(f'negative control accepted: {name}')
    return out


def main():
    for checkout, sha in ((REPO, PIN), (SOURCE, REFERENCE_COMMIT)):
        require(subprocess.check_output(['git', '-C', checkout, 'rev-parse', 'HEAD'], text=True).strip() == sha
                and not subprocess.check_output(['git', '-C', checkout, 'status', '--porcelain']), 'source pin')
    modules = {}
    for module in (gto.mole, gto.moleintor, hf):
        path = Path(module.__file__)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = (SOURCE / Path(*module.__name__.split('.'))).with_suffix('.py')
        require(digest == hashlib.sha256(expected.read_bytes()).hexdigest(), 'installed source differs')
        modules[module.__name__] = digest
    started = time.perf_counter()
    records = []
    for path in sorted((REPO / DIRECTORY).glob('*.json.xz')):
        if not path.name.startswith(('sp_', 'error_')):
            continue
        t = time.perf_counter()
        raw = path.read_bytes()
        data = json.loads(lzma.decompress(raw))
        report = {'file': path.name, 'bytes_read': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                  'read_decode_seconds': time.perf_counter() - t}
        try:
            blinded_record(data, report)
        except Rejected as exc:
            report.update(status='admission_rejected', reason=str(exc))
        report['record_seconds'] = time.perf_counter() - t
        records.append(report)
    controls = negative_controls()
    native_lib = Path(gto.moleintor.libcgto._name)
    print(json.dumps({
        'protocol_commit': 'fd7e46e', 'qcfractal_commit': PIN, 'reference_source_commit': REFERENCE_COMMIT,
        'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'pyscf_version': pyscf.__version__,
        'numpy_version': np.__version__, 'python': platform.python_version(), 'platform': platform.platform(),
        'python_module_hashes': modules, 'libcgto_sha256': hashlib.sha256(native_lib.read_bytes()).hexdigest(),
        'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
        'total_record_and_controls_seconds': time.perf_counter() - started, 'scf_calls': 0, 'tolerance': TOL,
        'records': records, 'negative_controls': controls,
    }, indent=2, allow_nan=False))
    return int(any(r['status'] in ('reference_disagreement', 'admission_rejected') for r in records))


if __name__ == '__main__':
    sys.exit(main())
