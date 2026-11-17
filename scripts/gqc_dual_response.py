"""GQC direct/adjoint static RHF response on a byte-identified molecular archive.

The scheduling caller chooses endpoint IDs. A persisted vector is a response
proposal whose physical residual is rechecked at consumption. Independent
scalar reference data is used only after the requested contractions are made.
"""
from collections import Counter
from itertools import combinations
import json
import math
import os
from pathlib import Path
import tempfile
import time

import numpy as np

from probe_gqc_residual import (GQC, MoleculeResponse, array_hash, check, file_hash,
                                git, jk_and_observables, json_hash, max_error, write_json)
from generativeqc.profiles import canonical_hash
from generativeqc.response_problem import ResponseProblem
from generativeqc.response_solver import GMRESOptions, solve_many
from generativeqc_compiler.common.cpp_adapter import CppCompilerAdapter
from generativeqc_compiler.method.rhf_orbital_response import build_rhf_frame_response
from generativeqc_compiler.tensor import (Index, IndexSpace, Program, TensorSpec, add, einsum,
                                         input_tensor, transpose, transpose_program)
from generativeqc_compiler.tensor.cpu import NativeTensorProgram
from tools.generate_validation_references import pyscf_molecule
from tools.generativeqc_posthf.fixtures import fixture_snapshot

FIELD_IDS = ('x', 'y', 'z')
OBSERVABLE_IDS = ('q0', 'r2', 'zz')
GQC_PIN = '2791504cc238fe83d328fc1718080642b288222a'
GATE = 1e-10
ANALYTIC_TOL = 1e-8
FIELD_TOL = 1e-4
STEPS = (0.0005, 0.0002)


def operator_matrices(mol):
    """Readout operators in PySCF's AO normalization, with a fixed origin."""
    overlap = mol.intor_symmetric('int1e_ovlp')
    with mol.with_common_orig(np.zeros(3)):
        field = mol.intor_symmetric('int1e_r', comp=3)
        r2 = mol.intor_symmetric('int1e_r2')
        rr = mol.intor('int1e_rr', comp=9).reshape(3, 3, mol.nao_nr(), mol.nao_nr())
    lo, hi = mol.aoslice_by_atom()[0, 2:]
    selected = np.zeros_like(overlap)
    selected[lo:hi] = overlap[lo:hi]
    return field, {'q0': -0.5 * (selected + selected.T), 'r2': r2, 'zz': rr[2, 2]}


def derivative_kernels(n, no):
    """Generate the direct field RHS and the VJP of each linear readout."""
    ao = IndexSpace("ao", "ao", n)
    occ = IndexSpace("occupied", "orbital", no)
    vir = IndexSpace("virtual", "orbital", n - no)
    u, v = Index("u", ao), Index("v", ao)
    i, a = Index("i", occ), Index("a", vir)
    co = input_tensor("occupied", TensorSpec((u, i), role='input'))
    cv = input_tensor("virtual", TensorSpec((v, a), role='input'))
    op = input_tensor("one_body", TensorSpec((u, v), role='input'))
    x = input_tensor("amplitude", TensorSpec((i, a), role='parameter', differentiable=True))
    # K_ai=-X_ia. The 2/0 occupations are part of the RHF state contract.
    half_dm = einsum("ui,ia,va->uv", co, x, cv, coefficient=-2)
    dm = add(half_dm, transpose(half_dm, (1, 0)))
    observable = Program({'observable': einsum("uv,vu->", op, dm)})
    pullback = transpose_program(observable, ('observable',), inputs=('amplitude',))
    field_rhs = Program({'rhs': einsum("ui,uv,va->ia", co, op, cv)})
    return field_rhs, pullback.program


class DualResponseModel(MoleculeResponse):
    """Validated shared operator. Each direct or adjoint action uses the native TensorIR kernels."""

    def __init__(self, metadata_file, array_file, workdir, oracle=None):
        started = time.perf_counter()
        check(git(GQC, 'rev-parse', 'HEAD') == GQC_PIN and not git(GQC, 'status', '--porcelain'),
              'GQC source checkout differs from the protocol')
        meta_path, arr_path = Path(metadata_file), Path(array_file)
        meta = json.loads(meta_path.read_text())
        self.name = meta['inputs']['name']
        self.source = {'metadata_file': meta_path.name, 'metadata_sha256': file_hash(meta_path),
                       'array_file': arr_path.name, 'array_sha256': file_hash(arr_path)}
        with np.load(arr_path, allow_pickle=False) as packed:
            arrays = {name: packed[name] for name in packed.files}
        checksums = {key: array_hash(value) for key, value in arrays.items()}
        check(meta.get('array_hash') == canonical_hash(checksums), 'published molecular-array hash mismatch')
        self.ref = ref = fixture_snapshot(meta, arrays)
        self.mol, self.scale, _ = pyscf_molecule(meta['inputs'])
        self.counts = Counter()
        self.artifacts = []
        self.options = GMRESOptions(rtol=1e-12, atol=1e-13, max_iterations=200)
        self.oracle = None
        n = ref.nmo
        self.nocc, self.dimension = ref.nocc, ref.nocc * (n - ref.nocc)
        self.eri = arrays['ao']
        self.identity_rotation = np.eye(n)
        kernel_cache = Path(workdir) / 'compiled'
        cxx = CppCompilerAdapter(Path('c++'))

        def compile_kernel(program):
            begin = time.perf_counter()
            owner = NativeTensorProgram(program, compiler=cxx, cache=kernel_cache,
                                        max_bytes=256 << 20, max_work=1_000_000_000)
            self.artifacts.append({'source': program.logical_hash, 'lowered': owner.identity,
                                   'binary_sha256': file_hash(owner.library._name), 'resources': owner.resources,
                                   'elapsed_seconds': time.perf_counter() - begin})
            return owner

        frame = build_rhf_frame_response(ref.nocc, n - ref.nocc)
        self.direction = compile_kernel(frame.density_direction)
        self.orbital = compile_kernel(frame.orbital_action)
        jk, _ = jk_and_observables(n)
        self.jk = compile_kernel(jk)
        b_program, c_program = derivative_kernels(n, self.nocc)
        b_kernel, c_kernel = compile_kernel(b_program), compile_kernel(c_program)
        self.co = ref.coefficients[:, :ref.nocc]
        self.cv = ref.coefficients[:, ref.nocc:]
        self.problem = ResponseProblem.from_reference(
            ref, operator_identity=json_hash({'frame': frame.orbital_action.logical_hash,
                                              'density': frame.density_direction.logical_hash,
                                              'jk': jk.logical_hash, 'eri': array_hash(self.eri),
                                              'gqc': GQC_PIN}))
        self.problem.require_stable()
        self.raw_fields, self.raw_observables = operator_matrices(self.mol)
        metric_scale = self.scale[:, None] * self.scale
        self.readouts = {key: op * metric_scale for key, op in self.raw_observables.items()}
        fixed = {'occupied': self.co, 'virtual': self.cv}
        self.rhs_values = {'fields': {}, 'observables': {}}
        for key, operator in zip(FIELD_IDS, self.raw_fields * metric_scale, strict=True):
            self.rhs_values['fields'][key] = b_kernel.execute({**fixed, 'one_body': operator})['rhs'].ravel()
        vjp_errors = {}
        for key, operator in self.readouts.items():
            vector = c_kernel.execute({**fixed, 'one_body': operator, 'bar_observable': np.array(1.)})['bar_amplitude']
            self.rhs_values['observables'][key] = vector.ravel()
            vjp_errors[key] = max_error(vector, -4 * self.co.T @ operator @ self.cv)
        check(max(vjp_errors.values()) <= GATE, 'generated readout VJP differs from RHF convention')
        self.endpoint_identity = {'fields': {}, 'observables': {}}
        elements = ({'x': self.raw_fields[0] * metric_scale, 'y': self.raw_fields[1] * metric_scale,
                     'z': self.raw_fields[2] * metric_scale}, self.readouts)
        contracts = {'x': 'h(F)=h0+F*r_x, atomic field', 'y': 'h(F)=h0+F*r_y, atomic field',
                     'z': 'h(F)=h0+F*r_z, atomic field', 'q0': 'Mulliken net charge of atom 0, e',
                     'zz': 'sum of electronic z^2, bohr^2', 'r2': 'sum of electronic |r|^2, bohr^2'}
        for g, definitions in zip(('fields', 'observables'), elements, strict=True):
            for key, matrix in definitions.items():
                self.endpoint_identity[g][key] = json_hash({
                    'problem': self.problem.identity, 'group': g, 'id': key, 'convention': contracts[key],
                    'origin_bohr': [0, 0, 0], 'normalized_ao_operator': array_hash(matrix),
                    'rhs_sha256': array_hash(self.rhs_values[g][key])})
        self.contract_identity = json_hash(self.endpoint_identity)
        density = 2 * self.co @ self.co.T
        f_error = max_error(ref.hcore + self.potential(density), ref.fock)
        check(f_error <= 1e-9, 'stored Fock fails physical AO contraction')
        # Check the self-adjoint substitution in this molecular gauge with
        # independent deterministic bilinear probes and the generated dD map.
        rng = np.random.default_rng(32417)
        dots = []
        readout_error = 0.
        for _ in range(2):
            u, v = rng.normal(size=(2, self.dimension))
            u /= np.linalg.norm(u)
            v /= np.linalg.norm(v)
            left, right = float(u @ self.apply(v)), float(self.apply(u) @ v)
            dots.append(abs(left - right) / max(1., abs(left), abs(right)))
            dd = self.density_direction(self.direction_feeds(v))
            for key, op in self.readouts.items():
                actual = float(self.rhs_values['observables'][key] @ v)
                readout_error = max(readout_error, abs(actual - np.einsum('ij,ji->', op, dd)))
        check(max(dots) <= GATE and readout_error <= GATE, 'bilinear or dD/readout duality check failed')
        self.setup = {'name': self.name, 'source': self.source, 'problem_identity': self.problem.identity,
                      'reference_identity': ref.identity, 'geometry_hash': ref.geometry_hash,
                      'contract_identity': self.contract_identity, 'endpoint_identities': self.endpoint_identity,
                      'basis_hash': ref.basis_hash, 'dimension': self.dimension, 'nbasis': n,
                      'nocc': ref.nocc, 'fock_error': f_error, 'vjp_errors': vjp_errors,
                      'scaled_dot_errors': dots, 'readout_dot_error': float(readout_error),
                      'minimum_ov_gap': self.problem.diagnostics['minimum_ov_gap'], 'counts': dict(self.counts),
                      'native_kernels': self.artifacts, 'seconds': time.perf_counter() - started}
        if oracle is not None:
            self.attach_oracle(oracle)

    def new_cache(self):
        return {'problem_identity': self.problem.identity, 'fields': {}, 'observables': {}}

    def save_cache(self, cache, path):
        check(cache['problem_identity'] == self.problem.identity, 'cache identity mismatch')
        path = Path(path)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            write_json(temporary, cache)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def load_cache(path):
        cache = json.loads(Path(path).read_text())
        check(isinstance(cache, dict) and isinstance(cache.get('problem_identity'), str)
              and isinstance(cache.get('fields'), dict) and isinstance(cache.get('observables'), dict),
              'invalid response cache envelope')
        return cache

    def attach_oracle(self, oracle):
        if isinstance(oracle, (str, Path)):
            oracle = json.loads(Path(oracle).read_text())
        check(oracle['problem_identity'] == self.problem.identity, 'independent oracle identity mismatch')
        check(oracle['source'] == self.source, 'independent oracle source mismatch')
        attestation = oracle.get('operator_attestation', oracle['setup'])
        check(attestation.get('contract_identity') == self.contract_identity,
              'independent oracle operator definitions or origin differ')
        for field in FIELD_IDS:
            for observable in OBSERVABLE_IDS:
                cell = oracle.get('targets', {}).get(field, {}).get(observable)
                check(isinstance(cell, dict) and isinstance(cell.get('finite_fields'), dict) and
                      isinstance(cell.get('reasons'), list), 'invalid scalar reference structure')
        self.oracle = oracle

    def assess(self, field, observable, value):
        check(field in FIELD_IDS and observable in OBSERVABLE_IDS, 'unknown scalar response endpoint')
        def finite(v):
            return isinstance(v, (float, int, np.floating, np.integer)) and not isinstance(v, (bool, np.bool_)) and math.isfinite(v)
        raw = float(value) if finite(value) else None
        out = {'field': field, 'observable': observable, 'raw_value': raw,
               'target_identity': json_hash([self.endpoint_identity['fields'][field],
                                             self.endpoint_identity['observables'][observable]]),
               'qualified': None, 'value': None, 'status': 'residual_verified', 'reasons': []}
        if raw is None:
            out.update(qualified=False, status='withheld', reasons=['nonfinite or missing candidate'])
            return out
        if self.oracle is None:
            return out
        ref = self.oracle['targets'][field][observable]
        reference_failures = list(ref['reasons'])
        comparable = {method: ref.get(method) for method in ('direct', 'adjoint', 'cphf')}
        comparable.update({str(h): ref['finite_fields'].get(str(h)) for h in STEPS})
        errors = {method: abs(raw - float(expected)) for method, expected in comparable.items() if finite(expected)}
        failed = [tag for tag, err in errors.items() if err > (FIELD_TOL if tag in ref['finite_fields'] else ANALYTIC_TOL)]
        failed.extend(f'missing or nonfinite {tag}' for tag, expected in comparable.items() if not finite(expected))
        reasons = sorted(set(reference_failures + failed))
        out.update(qualified=not reasons, value=None if reasons else raw, status='withheld' if reasons else 'qualified',
                   errors=errors, reasons=reasons)
        return out

    def combined_field(self, coefficients, observables=OBSERVABLE_IDS):
        """Solve one physical superposition. Recovery of individual scalars is caller-owned."""
        begin = time.perf_counter()
        u = np.asarray(coefficients)
        check(u.shape == (3,) and u.dtype.kind in 'iuf' and np.isfinite(u).all(), 'invalid field coefficients')
        names = sorted(set(observables))
        check(set(names) <= set(OBSERVABLE_IDS), 'unknown combined-field observable')
        before = self.counts.copy()
        rhs = np.column_stack([self.rhs_values['fields'][key] for key in FIELD_IDS]) @ u.astype(float)
        solve = solve_many(self, rhs[:, None], strategy='blocked', options=self.options,
                           raise_on_failure=True, collect_basis=False)
        result = solve.results[0]
        check(result.residual_norm <= GATE, 'combined field failed physical residual')
        counts = {'rhs_columns': 1, 'jk_calls': self.counts['jk_calls'] - before['jk_calls'],
                  'operator_actions': self.counts['response_operator_actions'] - before['response_operator_actions'],
                  'solver_actions': solve.operator_actions, 'cache_validation_actions': 0}
        check(counts['operator_actions'] == solve.operator_actions, 'combined-field action count')
        values = {j: float(self.rhs_values['observables'][j] @ result.solution) for j in names}
        check(all(math.isfinite(value) for value in values.values()), 'nonfinite combined-field readout')
        return {'problem_identity': self.problem.identity, 'coefficients': u.tolist(),
                'origin_bohr': [0, 0, 0], 'combined_rhs_sha256': array_hash(rhs),
                'field_identity': json_hash({'axes': self.endpoint_identity['fields'], 'coefficients': u.tolist(),
                                             'rhs': array_hash(rhs)}),
                'observable_identities': {j: self.endpoint_identity['observables'][j] for j in names},
                'values': values,
                'solution_sha256': array_hash(result.solution), 'true_residual': float(result.residual_norm),
                'counts': counts, 'elapsed_seconds': time.perf_counter() - begin}

    def _cached(self, group, key, cache):
        entry = cache[group][key]
        vector = np.array([], dtype=np.float64)
        b = self.rhs_values[group][key]
        residual = None
        reason = 'accepted'
        if not isinstance(entry, dict):
            reason = 'invalid endpoint record'
        elif (cache['problem_identity'] != self.problem.identity or entry.get('problem_identity') != self.problem.identity
                or entry.get('group') != group or entry.get('id') != key
                or entry.get('endpoint_identity') != self.endpoint_identity[group][key]):
            reason = 'problem or endpoint identity'
        else:
            try:
                vector = np.asarray(entry.get('solution'), dtype=np.float64)
            except (TypeError, ValueError, OverflowError):
                reason = 'invalid solution values'
            if reason == 'accepted':
                if vector.shape != b.shape or not np.isfinite(vector).all():
                    reason = 'shape or finiteness'
                elif entry.get('solution_sha256') != array_hash(vector) or entry.get('rhs_sha256') != array_hash(b):
                    reason = 'content or physical RHS digest'
                else:
                    residual = float(np.linalg.norm(self.apply(vector) - b))
                    if residual > GATE:
                        reason = 'physical response residual'
        return vector, {'group': group, 'id': key, 'decision': reason, 'true_residual': residual}

    def run_round(self, requests, fields, observables, cache):
        """Execute a selection with one block, then contract every requested scalar.

        Unselected cached endpoints are read only as needed to cover remaining
        edges. Among interchangeable cache hits use the fewest validations.
        A damaged chosen solution is replaced only after a successful solve.
        """
        start = time.perf_counter()
        before = self.counts.copy()
        edges = sorted(set(tuple(x) for x in requests))
        selected = {('fields', k) for k in fields} | {('observables', k) for k in observables}
        check(all(i in FIELD_IDS and j in OBSERVABLE_IDS for i, j in edges), 'unknown request')
        check(all(k in self.rhs_values[g] for g, k in selected), 'unknown endpoint')
        active = [{('fields', i), ('observables', j)} for i, j in edges]
        unknown = [ends for ends in active if not ends & selected]
        available = sorted({point for ends in unknown for point in ends if point[1] in cache[point[0]]})
        if unknown:
            cached_cover = next((set(s) for n in range(1, len(available) + 1)
                                 for s in combinations(available, n) if all(set(s) & ends for ends in unknown)), None)
            check(cached_cover is not None, 'uncovered request: select a field or an observable')
            selected.update(cached_cover)
        vectors, missing, checks = {}, [], []
        for g, key in sorted(selected):
            if key in cache[g]:
                vec, msg = self._cached(g, key, cache)
                checks.append(msg)
                if msg['decision'] == 'accepted':
                    vectors[(g, key)] = vec
                    continue
            missing.append((g, key))
        before_solve = self.counts['response_operator_actions']
        cache_actions = before_solve - before['response_operator_actions']
        stats = {'rhs_rank': 0, 'residuals': {}, 'solver_actions': 0}
        if missing:
            b = np.column_stack([self.rhs_values[g][key] for g, key in missing])
            result = solve_many(self, b, strategy='blocked', options=self.options,
                                raise_on_failure=True, collect_basis=False)
            held = {}
            for (g, key), part in zip(missing, result.results, strict=True):
                check(part.residual_norm <= GATE, 'new response failed physical residual')
                vec = np.asarray(part.solution, dtype=np.float64)
                held[(g, key)] = {'problem_identity': self.problem.identity, 'group': g, 'id': key,
                                  'endpoint_identity': self.endpoint_identity[g][key],
                                  'solution': vec.tolist(), 'solution_sha256': array_hash(vec),
                                  'rhs_sha256': array_hash(self.rhs_values[g][key]),
                                  'solver_true_residual': float(part.residual_norm)}
                vectors[(g, key)] = vec
                stats['residuals'][f'{g}/{key}'] = float(part.residual_norm)
            # A foreign cache is never relabelled while stale unselected assets survive.
            if cache['problem_identity'] != self.problem.identity:
                cache.clear()
                cache.update(self.new_cache())
            for (g, key), row in held.items():
                cache[g][key] = row
            stats.update(rhs_rank=result.rhs_rank, solver_actions=result.operator_actions)
        check(self.counts['response_operator_actions'] - before_solve == stats['solver_actions'], 'solver action count')
        rows = []
        for field, observable in edges:
            direct, adjoint = ('fields', field), ('observables', observable)
            if direct in vectors:
                value = self.rhs_values['observables'][observable] @ vectors[direct]
                via = 'direct'
            else:
                value = self.rhs_values['fields'][field] @ vectors[adjoint]
                via = 'adjoint'
            row = self.assess(field, observable, value)
            row['via'] = via
            if direct in vectors and adjoint in vectors:
                row['cross_side_difference'] = abs(float(value - self.rhs_values['fields'][field] @ vectors[adjoint]))
                check(row['cross_side_difference'] <= ANALYTIC_TOL, 'direct/adjoint reciprocity disagreement')
            rows.append(row)
        actions = self.counts['response_operator_actions'] - before['response_operator_actions']
        counts = {'jk_calls': self.counts['jk_calls'] - before['jk_calls'], 'operator_actions': actions,
                  'rhs_columns': len(missing), 'cache_validation_actions': cache_actions,
                  'solver_actions': stats['solver_actions'], 'cache_rejections': sum(
                      x['decision'] != 'accepted' for x in checks), 'requests': len(rows)}
        return {'problem_identity': self.problem.identity, 'results': rows, 'counts': counts, 'block': stats,
                'new_fields': [k for g, k in missing if g == 'fields'],
                'new_observables': [k for g, k in missing if g == 'observables'],
                'cache_checks': checks, 'elapsed_seconds': time.perf_counter() - start}
