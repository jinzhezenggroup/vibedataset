#!/usr/bin/env python3
"""RES-001. Use archived closed-shell HF states and GQC-generated CPU response kernels."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
GQC = ROOT / '_references/gqc'
sys.path[:0] = [str(GQC / 'python'), str(GQC)]
from generativeqc.response_problem import ResponseProblem
from generativeqc.response_solver import GMRESOptions, solve_many
from generativeqc_compiler.common.cpp_adapter import CppCompilerAdapter
from generativeqc_compiler.method.rhf_orbital_response import build_rhf_frame_response
from generativeqc_compiler.tensor import Index, IndexSpace, Program, TensorSpec, add, einsum, input_tensor
from generativeqc_compiler.tensor.cpu import NativeTensorProgram
from tools.generate_validation_references import pyscf_molecule
from tools.generativeqc_posthf.fixtures import fixture_snapshot, load_fixture

from gqc_residual_plan import plan_fields, recovery_program


def array_hash(array):
    return hashlib.sha256(np.ascontiguousarray(array, dtype='<f8').tobytes()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def git(checkout, *args):
    return subprocess.check_output(['git', '-C', str(checkout), *args], text=True).strip()


def check(condition, description):
    if not condition:
        raise ValueError(description)


def max_error(a, b):
    return float(np.max(np.abs(np.asarray(a) - b)))


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def jk_and_observables(n):
    ao = IndexSpace("ao", "ao", n)
    axis = IndexSpace("observables", "batch", 4)
    p, q, r, s = (Index(letter, ao) for letter in "pqrs")
    density = input_tensor("density", TensorSpec((p, q), role="input"))
    eri = input_tensor("eri", TensorSpec((p, q, r, s), role="input"))
    coulomb = einsum("pqrs,rs->pq", eri, density)
    exchange = einsum("prqs,rs->pq", eri, density)
    jk = Program({"G": add(coulomb, exchange, coefficients=(1, Fraction(-1, 2)))})
    operators = input_tensor("observables", TensorSpec((Index("a", axis), p, q), role="input"))
    obs = Program({"derivatives": einsum("apq,qp->a", operators, density, coefficient=-1)})
    return jk, obs


class Run:
    def __init__(self, directory):
        self.path = directory
        self.log = directory / 'events.jsonl'
        self.kernels = {}
        self.cxx = CppCompilerAdapter(Path('c++'))

    def event(self, event, **data):
        with self.log.open('a') as handle:
            handle.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "event": event, **data},
                                    allow_nan=False) + '\n')
            handle.flush()

    def native(self, program):
        key = program.logical_hash
        if key not in self.kernels:
            self.event('compile_started', program=key)
            start = time.perf_counter()
            owner = NativeTensorProgram(program, compiler=self.cxx, cache=self.path / 'compiled')
            library = Path(owner.library._name)
            self.event('compile_completed', program=key, lowered=owner.identity, binary_sha256=file_hash(library),
                       resources=owner.resources, elapsed_seconds=time.perf_counter() - start)
            self.kernels[key] = owner
        return self.kernels[key]


class MoleculeResponse:
    def __init__(self, name, config, run):
        self.name, self.config, self.run = name, config, run
        self.counts = Counter()
        meta, arrays = load_fixture(name)
        ref = self.ref = fixture_snapshot(meta, arrays)
        self.mol, self.scale, _ = pyscf_molecule(meta['inputs'])
        self.eri = arrays['ao']
        with self.mol.with_common_orig([0, 0, 0]):
            self.raw_r = self.mol.intor_symmetric('int1e_r', comp=3)
        self.r = self.raw_r * self.scale[:, None] * self.scale
        atom = self.mol.aoslice_by_atom()[0]
        mulliken = np.zeros_like(ref.overlap)
        mulliken[atom[2]:atom[3]] = ref.overlap[atom[2]:atom[3]]
        self.observables = np.concatenate((self.r, mulliken[None]))
        self.dimension = ref.nocc * (ref.nmo - ref.nocc)
        self.nocc = ref.nocc
        frame = build_rhf_frame_response(ref.nocc, ref.nmo - ref.nocc)
        jk, observe = jk_and_observables(ref.nmo)
        self.direction, self.orbital, self.jk, self.observe = [
            run.native(p) for p in (frame.density_direction, frame.orbital_action, jk, observe)]
        self.identity_rotation = np.eye(ref.nmo)
        identity = {"frame_jvp": frame.orbital_action.logical_hash, "density_jvp": frame.density_direction.logical_hash,
                    "jk": jk.logical_hash, "eri": array_hash(self.eri), "field_operator": array_hash(self.r),
                    "field_coupling": "hcore plus uniform field dot position in atomic units",
                    "origin_bohr": [0, 0, 0], "compiler": config['gqc_commit']}
        self.problem = ResponseProblem.from_reference(ref, operator_identity=json_hash(identity))
        self.problem.require_stable()
        self.b = np.einsum('ui,kuv,va->iak', ref.coefficients[:, :ref.nocc],
                           self.r, ref.coefficients[:, ref.nocc:]).reshape(self.dimension, 3)
        self.options = GMRESOptions(rtol=config['gmres_rtol'], atol=config['gmres_atol'])
        density = 2 * ref.coefficients[:, :ref.nocc] @ ref.coefficients[:, :ref.nocc].T
        self.physical_fock_error = max_error(ref.hcore + self.potential(density), ref.fock)
        check(self.physical_fock_error <= 1e-10, 'physical Fock does not agree with the archived state')

    def direction_feeds(self, vector):
        k = np.zeros_like(self.ref.coefficients)
        k[:self.nocc, self.nocc:] = vector.reshape(self.nocc, -1)
        k[self.nocc:, :self.nocc] = -k[:self.nocc, self.nocc:].T
        return {'coefficients': self.ref.coefficients, 'rotation': self.identity_rotation,
                'd_rotation': k, 'fock_ao': self.ref.fock}

    def density_direction(self, feeds):
        self.counts['density_jvp_calls'] += 1
        return self.direction.execute(feeds)['density_direction']

    def potential(self, density):
        self.counts['jk_calls'] += 1
        return self.jk.execute({'density': density, 'eri': self.eri})['G']

    def apply(self, vector):
        self.counts['response_operator_actions'] += 1
        feeds = self.direction_feeds(vector)
        feeds['d_fock_ao'] = self.potential(self.density_direction(feeds))
        return self.orbital.execute(feeds)['orbital_action'].ravel()

    def rhs(self, fields):
        return self.b @ np.asarray(fields, dtype=np.float64).reshape(-1, 3).T

    def solve(self, fields, label):
        if not len(fields):
            return np.empty((self.dimension, 0))
        self.run.event('response_solve_started', molecule=self.name, label=label, fields=np.asarray(fields, dtype=float).tolist())
        start = time.perf_counter()
        before = self.counts['response_operator_actions']
        self.counts['rhs_sent_to_solver'] += len(fields)
        result = solve_many(self, self.rhs(fields), strategy='blocked', options=self.options,
                            raise_on_failure=True, collect_basis=False)
        actions = self.counts['response_operator_actions'] - before
        check(actions == result.operator_actions, 'GQC blocked action counter discrepancy')
        self.run.event('response_solve_completed', molecule=self.name, label=label, rank=result.rhs_rank,
                       true_residuals=[x.residual_norm for x in result.results], operator_actions=actions,
                       elapsed_seconds=time.perf_counter() - start)
        return result.solution

    def residual(self, x, field):
        return float(np.linalg.norm(self.apply(x) - self.rhs([field])[:, 0]))

    def outputs(self, vectors):
        results = []
        for x in vectors.T:
            dd = self.density_direction(self.direction_feeds(x))
            self.counts['observation_calls'] += 1
            results.append(self.observe.execute({'density': dd, 'observables': self.observables})['derivatives'])
        return np.asarray(results)


def store_assets(operator, fields, solutions, path):
    records = []
    for field, vector in zip(fields, solutions.T, strict=True):
        records.append({'problem_identity': operator.problem.identity, 'field': list(field), 'solution': vector.tolist()})
    write_json(path, [{'payload': obj, 'sha256': json_hash(obj)} for obj in records])


def admit(operator, assets, qualified_fields=None):
    accepted, decisions = [], []
    for asset in assets:
        start = time.perf_counter()
        doc = asset['payload']
        reason = 'accepted'
        residual = None
        if json_hash(doc) != asset['sha256']:
            reason = 'payload checksum'
        elif doc['problem_identity'] != operator.problem.identity:
            reason = 'response problem mismatch'
        else:
            vector = np.asarray(doc['solution'], dtype=np.float64)
            field = doc['field']
            # This bounded protocol admits integer directions in laboratory coordinates.
            if vector.shape != (operator.dimension,) or not np.isfinite(vector).all() or not (
                isinstance(field, list) and len(field) == 3 and all(type(x) is int for x in field)
            ):
                reason = 'invalid response record'
            elif qualified_fields is not None and tuple(field) not in qualified_fields:
                reason = 'previous independent gate failed'
            else:
                residual = operator.residual(vector, field)
                if residual <= operator.config['target_residual_tolerance']:
                    accepted.append((field, vector))
                else:
                    reason = 'physical response residual'
        decisions.append({'field': doc['field'], 'decision': reason, 'residual': residual,
                          'elapsed_seconds': time.perf_counter() - start})
    return accepted, decisions


def planned_solutions(op, accepted, targets, label, details):
    start = time.perf_counter()
    retained, new_fields, weights = plan_fields([field for field, _ in accepted], targets)
    ir = recovery_program(op.dimension, weights)
    details.update(new_fields=[[str(v) for v in field] for field in new_fields],
                   weights=[[str(v) for v in row] for row in weights],
                   reconstruction_ir=ir.logical_hash, planning_seconds=time.perf_counter() - start)
    native = op.run.native(ir)
    new_vectors = op.solve(new_fields, label)
    columns = [accepted[k][1] for k in retained] + list(new_vectors.T)
    outputs = native.execute({f'x{k}': v for k, v in enumerate(columns)})
    return np.column_stack([outputs[f'target{i}'] for i in range(len(targets))])


def evaluate_route(op, cfg, route, path, mutation=None):
    before = op.counts.copy()
    start = time.perf_counter()
    targets = cfg['requested_fields']
    details = {}
    if route == 'direct_blocked':
        solutions = op.solve(targets, route)
    else:
        archive = json.loads(path.read_text())
        if mutation:
            bad = archive[0]['payload']
            if mutation == 'different_problem':
                bad['problem_identity'] = json_hash({'other_problem': op.problem.identity})
            elif mutation == 'wrong_response':
                bad['solution'][0] += 0.1
            archive[0]['sha256'] = json_hash(bad)
        accepted, details['admission'] = admit(op, archive)
        if route == 'hand_basis':
            check([f for f, _ in accepted] == [[1, 0, 0], [0, 1, 0]] and
                  targets == [[1, 1, 0], [1, 0, 1], [0, 1, 1]], 'hand baseline field contract')
            x, y = [vec for _, vec in accepted]
            z = op.solve([[0, 0, 1]], route)[:, 0]
            solutions = np.column_stack((x + y, x + z, y + z))
        else:
            solutions = planned_solutions(op, accepted, targets, mutation or route, details)
    residuals = [op.residual(x, field) for x, field in zip(solutions.T, targets, strict=True)]
    check(max(residuals) <= cfg['target_residual_tolerance'], f'{route} failed final response residual')
    observables = op.outputs(solutions)
    details.update(target_residuals=residuals, observables=observables.tolist(), counts=dict(op.counts - before),
                   elapsed_seconds=time.perf_counter() - start)
    return details


def independent_observables(op, cfg, log, *, spatial_extent=False):
    """PySCF ground states, independent CPHF and two-step fully relaxed field derivatives."""
    mol = op.mol
    field_directions = np.asarray(cfg['requested_fields'], dtype=float)
    s = mol.intor_symmetric('int1e_ovlp')
    if spatial_extent:
        with mol.with_common_orig(np.zeros(3)):
            r2 = mol.intor_symmetric('int1e_r2')
    h0 = scf.hf.get_hcore(mol)
    g = mol.intor('int2e', aosym='s1')
    eri8 = ao2mo.restore(8, g, mol.nao_nr())
    scale = op.scale
    g_normalized = np.einsum('pqrs,p,q,r,s->pqrs', g, scale, scale, scale, scale)
    integral_errors = {'overlap': max_error(s * scale[:, None] * scale, op.ref.overlap),
                       'hcore': max_error(h0 * scale[:, None] * scale, op.ref.hcore),
                       'eri': max_error(g_normalized, op.eri)}
    check(max(integral_errors.values()) <= 1e-10, 'independent integral convention mismatch')
    records = []
    def relax(field):
        log.event('independent_scf_started', molecule=op.name, field=field.tolist())
        begin = time.perf_counter()
        mf = scf.RHF(mol)
        h = h0 + np.einsum('x,xij->ij', field, op.raw_r)
        mf.get_hcore = lambda *args: h
        mf._eri = eri8
        mf.chkfile = None
        mf.direct_scf_tol = 0
        mf.conv_tol, mf.conv_tol_grad = cfg['scf_energy_tolerance'], cfg['scf_gradient_tolerance']
        mf.max_cycle = cfg['max_scf_cycles']
        mf.kernel()
        check(mf.converged, 'independent SCF unconverged')
        density = mf.make_rdm1()
        atom = mol.aoslice_by_atom()[0]
        q0 = mol.atom_charge(0) - np.einsum('ij,ji->i', density, s)[atom[2]:atom[3]].sum()
        if spatial_extent:
            values = np.array([np.einsum('ij,ji->', density, r2)])
        else:
            values = np.r_[mf.dip_moment(dm=density, unit='AU', origin=np.zeros(3), verbose=0), q0]
        value_name = 'electronic_spatial_extent' if spatial_extent else 'dipole_and_charge'
        row = {'field_au': field.tolist(), value_name: values.tolist(), 'cycles': mf.cycles,
               'electronic_plus_nuclear_energy_at_zero_nuclear_field_coupling': mf.e_tot,
               'seconds': time.perf_counter() - begin}
        records.append(row)
        log.event('independent_scf_completed', molecule=op.name, **row)
        return mf, values
    mf, _ = relax(np.zeros(3))
    archive_dm = 2 * op.ref.coefficients[:, :op.nocc] @ op.ref.coefficients[:, :op.nocc].T
    branch_error = max_error(mf.make_rdm1(), archive_dm * scale[:, None] * scale)
    check(branch_error < 1e-8, 'independent zero-field density differs')
    occ, vir = mf.mo_coeff[:, mf.mo_occ > 0], mf.mo_coeff[:, mf.mo_occ == 0]
    counts = Counter()
    def vind(rotations):
        counts['jk_batches'] += 1
        counts['jk_density_columns'] += len(rotations)
        delta = 2 * np.einsum('ua,nai,vi->nuv', vir, rotations, occ)
        j, k = mf.get_jk(dm=delta + delta.transpose(0, 2, 1), hermi=1)
        return np.einsum('ua,nuv,vi->nai', vir, j - 0.5 * k, occ)
    h1 = np.einsum('nx,xuv,ua,vi->nai', field_directions, op.raw_r, vir, occ)
    # PySCF uses C_v U_ai as dC_occ; GQC uses -C_v X_ia.T.
    start = time.perf_counter()
    log.event('independent_cphf_started', molecule=op.name, rhs=len(h1))
    response, _ = cphf.solve(vind, mf.mo_energy, mf.mo_occ, h1, tol=cfg['gmres_rtol'], max_cycle=150)
    dm_half = 2 * np.einsum('ua,nai,vi->nuv', vir, response, occ)
    dm1 = dm_half + dm_half.transpose(0, 2, 1)
    dmu = -np.einsum('xuv,nvu->nx', op.raw_r, dm1)
    a = mol.aoslice_by_atom()[0]
    dq = -np.einsum('nuv,vu->nu', dm1, s)[:, a[2]:a[3]].sum(axis=1)
    cphf_values = np.column_stack((dmu, dq))
    if spatial_extent:
        cphf_values = np.einsum('nuv,vu->n', dm1, r2)[:, None]
    log.event('independent_cphf_completed', molecule=op.name, seconds=time.perf_counter() - start, counts=dict(counts))
    finite = {}
    for step in cfg['field_steps_au']:
        slopes = []
        for direction in field_directions:
            _, plus = relax(step * direction)
            _, minus = relax(-step * direction)
            slopes.append((plus - minus) / (2 * step))
        finite[str(step)] = np.asarray(slopes).tolist()
    return {'cphf': cphf_values.tolist(), 'finite_fields': finite, 'scf': records, 'cphf_counts': dict(counts),
            'independent_zero_field_density_error': branch_error, 'integral_errors': integral_errors}


def run_case(name, cfg, run):
    begin = time.perf_counter()
    op = MoleculeResponse(name, cfg, run)
    prep = time.perf_counter() - begin
    known = cfg['archived_fields']
    before = op.counts.copy()
    start = time.perf_counter()
    solutions = op.solve(known, 'round1')
    observables = op.outputs(solutions)
    asset_path = run.path / f'{name}-round1.json'
    store_assets(op, known, solutions, asset_path)
    round1 = {'counts': dict(op.counts - before), 'seconds': time.perf_counter() - start,
              'requested_dipole_columns': observables[:, :3].tolist(), 'solution_vector_bytes': solutions.nbytes,
              'archive_file_bytes': asset_path.stat().st_size, 'asset_sha256': file_hash(asset_path)}
    routes = {}
    for label, mutation in [('direct_blocked', None), ('hand_basis', None), ('planned', None),
                            ('planned', 'different_problem'), ('planned', 'wrong_response')]:
        routes[mutation or label] = evaluate_route(op, cfg, label, asset_path, mutation)
    oracle_started = time.perf_counter()
    oracle = independent_observables(op, cfg, run)
    oracle_seconds = time.perf_counter() - oracle_started
    direct = np.asarray(routes['direct_blocked']['observables'])
    errors = {name: max_error(r['observables'], direct) for name, r in routes.items()}
    independent = max_error(oracle['cphf'], direct)
    fd = {step: max_error(values, direct) for step, values in oracle['finite_fields'].items()}
    # A frozen density predicts exactly zero for each of these field derivatives.
    frozen_error = max_error(np.zeros_like(direct), oracle['cphf'])
    passed = (max(errors.values()) <= cfg['analytic_max_abs_tolerance']
              and independent <= cfg['analytic_max_abs_tolerance']
              and max(fd.values()) <= cfg['finite_field_max_abs_tolerance']
              and frozen_error > cfg['finite_field_max_abs_tolerance']
              and routes['different_problem']['admission'][0]['decision'] == 'response problem mismatch'
              and routes['wrong_response']['admission'][0]['decision'] == 'physical response residual')
    return {'name': name, 'passed': bool(passed), 'dimension': op.dimension, 'problem_identity': op.problem.identity,
            'reference_identity': op.ref.identity, 'physical_fock_error': op.physical_fock_error,
            'reference_diagnostics': dict(op.ref.diagnostics), 'basis_hash': op.ref.basis_hash,
            'geometry_hash': op.ref.geometry_hash, 'minimum_ov_gap': op.problem.diagnostics['minimum_ov_gap'],
            'prepare_seconds': prep, 'prepare_jk_calls': 1, 'round1': round1, 'round2': routes,
            'independent': oracle, 'independent_seconds': oracle_seconds,
            'max_abs_errors_vs_direct': errors, 'max_cphf_error': independent, 'max_fd_errors': fd,
            'frozen_response_max_error': frozen_error, 'total_seconds': time.perf_counter() - begin}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/gqc_residual_response.json')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    pyroot = ROOT / '_references/pyscf_2_14'
    for repo, pin in ((GQC, cfg['gqc_commit']), (pyroot, cfg['pyscf_commit'])):
        check(git(repo, 'rev-parse', 'HEAD') == pin and not git(repo, 'status', '--porcelain'), 'reference pin')
    check(pyscf.__version__ == cfg['pyscf_version'], 'unexpected PySCF version')
    installed_sources = {}
    for module in (cphf, scf.hf):
        actual = Path(module.__file__)
        expected = (pyroot / Path(*module.__name__.split('.'))).with_suffix('.py')
        check(file_hash(expected) == file_hash(actual), 'installed PySCF differs')
        installed_sources[module.__name__] = file_hash(actual)
    args.out.mkdir(parents=True, exist_ok=False)
    run = Run(args.out)
    manifest = {'config_sha256': file_hash(args.config), 'compiler_commit': cfg['gqc_commit'],
                'project_commit': git(ROOT, 'rev-parse', 'HEAD'), 'driver_sha256': file_hash(__file__),
                'planner_sha256': file_hash(ROOT / 'scripts/gqc_residual_plan.py'),
                'python': platform.python_version(), 'platform': platform.platform(), 'numpy': np.__version__,
                'pyscf': pyscf.__version__, 'pyscf_module_hashes': installed_sources,
                'cxx': subprocess.check_output(['c++', '--version'], text=True).splitlines()[0],
                'threads': {k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                'cases': []}
    for name in cfg['fixtures']:
        run.event('case_started', molecule=name)
        try:
            case = run_case(name, cfg, run)
        except Exception as exc:
            import traceback
            case = {'name': name, 'passed': False, 'error': str(exc), 'traceback': traceback.format_exc()}
        manifest['cases'].append(case)
        run.event('case_finished', molecule=name, passed=case['passed'])
        write_json(args.out / 'report.json', manifest)
        print(name, case['passed'], case.get('error', ''), flush=True)
    return int(not all(c['passed'] for c in manifest['cases']))


if __name__ == '__main__':
    sys.exit(main())
