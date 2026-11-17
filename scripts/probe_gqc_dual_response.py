#!/usr/bin/env python3
"""Run the blinded direct/adjoint comparison and an independent oracle for a fixed cohort."""
from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import pyscf
from pyscf import ao2mo, scf
from pyscf.scf import cphf

from gqc_dual_response import (ANALYTIC_TOL, FIELD_IDS, FIELD_TOL, GQC_PIN, OBSERVABLE_IDS, STEPS,
                               DualResponseModel, operator_matrices)
from probe_gqc_residual import GQC, ROOT, check, file_hash, git, max_error, write_json

PYS_PIN = 'c63a953ba603a5ad8c1d65d88da72aaf05ede4d8'
DIRECTIONS = np.eye(3)


class Journal:
    def __init__(self, path, name):
        self.path, self.name = path, name
        self.started = time.perf_counter()

    def add(self, event, **data):
        with self.path.open('a') as h:
            h.write(json.dumps({'molecule': self.name, 'at_utc': datetime.now(timezone.utc).isoformat(),
                                'elapsed_from_case_start': time.perf_counter() - self.started,
                                'event': event, **data}, allow_nan=False) + '\n')


def run_pyscf(op, journal):
    mol = op.mol
    h0 = scf.hf.get_hcore(mol)
    s = mol.intor_symmetric('int1e_ovlp')
    g = mol.intor('int2e', aosym='s1')
    scale = op.scale
    integral_errors = {'hcore': max_error(h0 * scale[:, None] * scale, op.ref.hcore),
                       'overlap': max_error(s * scale[:, None] * scale, op.ref.overlap),
                       'eri': max_error(np.einsum('pqrs,p,q,r,s->pqrs', g, scale, scale, scale, scale), op.eri)}
    check(max(integral_errors.values()) <= 1e-9, 'physical input or AO conventions differ')
    packed = ao2mo.restore(8, g, mol.nao_nr())
    fields, readouts = operator_matrices(mol)
    observables = np.stack([readouts[key] for key in OBSERVABLE_IDS])
    nuclear = np.array([mol.atom_charge(0), 0., 0.])
    scf_rows = []
    def relax(field):
        start = time.perf_counter()
        journal.add('independent_scf_started', field=field.tolist())
        mf = scf.RHF(mol)
        h = h0 + np.einsum('k,kuv->uv', field, fields)
        mf.get_hcore = lambda *args: h
        mf._eri = packed
        mf.chkfile = None
        mf.conv_tol = 1e-13
        mf.conv_tol_grad = 1e-11
        mf.direct_scf_tol = 0
        mf.max_cycle = 150
        counts = Counter()
        get_jk = mf.get_jk
        def counted_jk(mol=None, dm=None, hermi=1, with_j=True, with_k=True, omega=None):
            counts['jk_calls'] += 1
            densities = mf.make_rdm1() if dm is None else np.asarray(dm)
            counts['density_columns'] += densities.size // (densities.shape[-1] * densities.shape[-2])
            return get_jk(mol, densities, hermi, with_j, with_k, omega)
        mf.get_jk = counted_jk
        row = {'field_au': field.tolist()}
        vals = None
        try:
            mf.kernel()
            check(mf.converged, 'SCF did not converge within 150 cycles')
            vals = np.einsum('quv,vu->q', observables, mf.make_rdm1()) + nuclear
            check(np.all(np.isfinite(vals)), 'nonfinite observables')
            row.update(status='completed', raw_observables=vals.tolist(), cycles=mf.cycles,
                       energy_excluding_nuclear_field_coupling=mf.e_tot)
        except Exception as exc:
            row.update(status='failed', reason=str(exc), cycles=getattr(mf, 'cycles', None))
        row.update(counts=dict(counts), seconds=time.perf_counter() - start)
        scf_rows.append(row)
        journal.add('independent_scf_finished', **row)
        return mf, vals

    zero, baseline = relax(np.zeros(3))
    branch_error = None
    energy_error = None
    analytical = None
    cphf_counts = Counter()
    error = None
    if baseline is not None:
        initial = 2 * op.co @ op.co.T * scale[:, None] * scale
        branch_error = max_error(zero.make_rdm1(), initial)
        energy_error = abs(float(zero.e_tot) - op.ref.reference_energy)
    if branch_error is not None and branch_error <= 1e-7 and energy_error <= 1e-8:
        start = time.perf_counter()
        journal.add('independent_cphf_started', rhs=3)
        try:
            occ = zero.mo_coeff[:, zero.mo_occ > 0]
            vir = zero.mo_coeff[:, zero.mo_occ == 0]
            def vind(rots):
                cphf_counts['jk_calls'] += 1
                cphf_counts['density_columns'] += len(rots)
                half = 2 * np.einsum('ua,kai,vi->kuv', vir, rots, occ)
                j, k = zero.get_jk(dm=half + half.transpose(0, 2, 1), hermi=1)
                return np.einsum('ua,kuv,vi->kai', vir, j - 0.5 * k, occ)
            h1 = np.einsum('kuv,ua,vi->kai', fields, vir, occ)
            x, _ = cphf.solve(vind, zero.mo_energy, zero.mo_occ, h1, tol=1e-12, max_cycle=200)
            dm = 2 * np.einsum('ua,kai,vi->kuv', vir, x, occ)
            analytical = np.einsum('quv,kvu->kq', observables, dm + dm.transpose(0, 2, 1))
            check(np.isfinite(analytical).all(), 'nonfinite CPHF output')
        except Exception as exc:
            error, analytical = str(exc), None
        journal.add('independent_cphf_finished', error=error, seconds=time.perf_counter() - start,
                    counts=dict(cphf_counts))
    else:
        error = 'zero field did not recover the stored reference energy and density'
    slopes = {}
    for step in STEPS:
        slopes[str(step)] = []
        for direction in DIRECTIONS:
            _, p = relax(step * direction)
            _, m = relax(-step * direction)
            row = (p - m) / (2 * step) if p is not None and m is not None else None
            slopes[str(step)].append(row.tolist() if row is not None else [None] * len(OBSERVABLE_IDS))
    return {'integral_errors': integral_errors, 'zero_field_density_error': branch_error,
            'zero_field_energy_error': energy_error, 'cphf': analytical.tolist() if analytical is not None else None,
            'cphf_error': error, 'cphf_counts': dict(cphf_counts), 'scf': scf_rows, 'finite_fields': slopes}


def validate_case(meta_path, arrays_path, directory, *, expected_identity=None):
    start = time.perf_counter()
    journal = Journal(directory / 'events.jsonl', meta_path.stem)
    journal.add('setup_started', inputs=[meta_path.name, arrays_path.name])
    op = DualResponseModel(meta_path, arrays_path, directory / 'native')
    journal.add('setup_finished', **op.setup)
    if expected_identity is not None:
        check(op.ref.identity == expected_identity, 'producer reference state identity changed')
    edges = [(i, j) for i in FIELD_IDS for j in OBSERVABLE_IDS]
    direct = op.run_round(edges, FIELD_IDS, [], op.new_cache())
    adjoint = op.run_round(edges, [], OBSERVABLE_IDS, op.new_cache())
    journal.add('gqc_oracle_finished', direct_counts=direct['counts'], adjoint_counts=adjoint['counts'])
    ref = run_pyscf(op, journal)
    def values(which):
        return {(r['field'], r['observable']): r['raw_value'] for r in which['results']}
    d, a = values(direct), values(adjoint)
    targets = {}
    for i, f in enumerate(FIELD_IDS):
        targets[f] = {}
        for j, o in enumerate(OBSERVABLE_IDS):
            c = None if ref['cphf'] is None else ref['cphf'][i][j]
            finite = {key: vals[i][j] for key, vals in ref['finite_fields'].items()}
            reasons = []
            if abs(d[f, o] - a[f, o]) > ANALYTIC_TOL:
                reasons.append('direct/adjoint disagreement')
            for label, value, limit in [('cphf', c, ANALYTIC_TOL),
                                         *((k, v, FIELD_TOL) for k, v in finite.items())]:
                if value is None:
                    reasons.append('missing ' + label)
                elif max(abs(d[f, o] - value), abs(a[f, o] - value)) > limit:
                    reasons.append(label)
            targets[f][o] = {'direct': d[f, o], 'adjoint': a[f, o], 'cphf': c, 'finite_fields': finite,
                             'reasons': reasons, 'qualified': not reasons, 'value': None if reasons else d[f, o]}
    oracle = {'name': op.name, 'source': op.source, 'problem_identity': op.problem.identity,
              'reference_identity': op.ref.identity, 'field_ids': FIELD_IDS, 'observable_ids': OBSERVABLE_IDS,
              'units_per_au_field': {'q0': 'e', 'r2': 'bohr^2', 'zz': 'bohr^2'}, 'targets': targets,
              'setup': op.setup, 'direct': direct, 'adjoint': adjoint, 'independent': ref,
              'seconds': time.perf_counter() - start}
    journal.add('case_finished', qualified=sum(t['qualified'] for by_field in targets.values() for t in by_field.values()))
    return oracle


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=Path('.work/qm9_response_assets/index.json'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    output = args.out / 'oracles'
    output.mkdir()
    idx = json.loads(args.index.read_text())
    pysroot = ROOT / '_references/pyscf_2_14'
    check(git(pysroot, 'rev-parse', 'HEAD') == PYS_PIN and pyscf.__version__ == '2.14.0', 'PySCF version mismatch')
    modules = {}
    for module in (cphf, scf.hf):
        actual = Path(module.__file__)
        expected = (pysroot / Path(*module.__name__.split('.'))).with_suffix('.py')
        check(file_hash(expected) == file_hash(actual), 'installed PySCF module mismatch')
        modules[module.__name__] = file_hash(actual)
    summary = {'index_sha256': file_hash(args.index), 'job': idx.get('job'), 'gqc': GQC_PIN,
               'pyscf_source': PYS_PIN, 'pyscf_modules': modules, 'driver_sha256': file_hash(__file__),
               'api_sha256': file_hash(ROOT / 'scripts/gqc_dual_response.py'), 'project_commit': git(ROOT, 'rev-parse', 'HEAD'),
               'numpy': np.__version__, 'pyscf': pyscf.__version__, 'python': platform.python_version(),
               'cxx': subprocess.check_output(['c++', '--version'], text=True).splitlines()[0],
               'threads': {k: os.environ.get(k) for k in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']},
               'strata': []}
    failed = False
    for row in idx['rows']:
        case = {'name': row.get('name'), 'stratum': row['stratum'], 'input_status': row['status']}
        if row['status'] != 'verified':
            case.update(status='not_run', reason=row.get('error', row['status']))
        else:
            try:
                meta, arr = (args.index.parent / row[k] for k in ('metadata_file', 'array_file'))
                check(file_hash(meta) == row['metadata_sha256'] and file_hash(arr) == row['array_file_sha256'], 'input file identity')
                result = validate_case(meta, arr, args.out, expected_identity=row.get('reference_identity'))
                path = output / (row['name'] + '.json')
                write_json(path, result)
                count = sum(r['qualified'] for field in result['targets'].values() for r in field.values())
                case.update(status='completed', qualified=count, targets=9, oracle='oracles/' + path.name, sha256=file_hash(path))
                failed |= count != 9
            except Exception as exc:
                import traceback
                case.update(status='execution_failed', reason=str(exc), traceback=traceback.format_exc())
                failed = True
        summary['strata'].append(case)
        write_json(args.out / 'summary.json', summary)
        print(case['name'], case['status'], case.get('qualified'), case.get('reason', ''), flush=True)
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
