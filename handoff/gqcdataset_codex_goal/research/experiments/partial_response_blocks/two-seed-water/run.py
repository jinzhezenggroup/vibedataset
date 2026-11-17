"""Reproduce the preregistered two-seed water control using the physical GQC operator."""
from argparse import ArgumentParser
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np
import pyscf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[5] / 'scripts'))
from gqc_dual_response import FIELD_IDS, GATE, GQC_PIN, DualResponseModel, solve_many
from probe_gqc_residual import ROOT, array_hash, check, file_hash, git, json_hash, write_json

HISTORY = (('y', 'q0'), ('z', 'r2'), ('x', 'zz'))
REQUESTS = (('x', 'q0'), ('y', 'r2'), ('z', 'zz'))
UNITS = {'q0': 'e per atomic unit of field', 'r2': 'bohr^2 per atomic unit of field',
         'zz': 'bohr^2 per atomic unit of field'}


def measure(model, operation):
    before = model.counts.copy()
    start = time.perf_counter()
    try:
        result = {'status': 'completed', 'result': operation()}
    except Exception as exc:
        result = {'status': 'failed', 'exception': type(exc).__name__, 'reason': str(exc)}
        failed = getattr(exc, 'result', None)
        if failed is not None:
            result.update(solver_reason=failed.reason, iterations=failed.iterations, true_residual=failed.residual_norm)
    result['seconds'] = time.perf_counter() - start
    result['counts'] = dict(model.counts - before)
    return result


def direct(model, edges):
    ephemeral = model.new_cache()
    run = model.run_round(edges, FIELD_IDS, (), ephemeral)
    columns = {k: {name: entry[name] for name in
                  ('endpoint_identity', 'rhs_sha256', 'solution_sha256', 'solver_true_residual')}
               for k, entry in ephemeral['fields'].items()}
    for row in run['results']:
        row.update(unit=UNITS[row['observable']], problem_identity=model.problem.identity)
    return {'columns': columns, 'rhs_rank': run['block']['rhs_rank'], 'rows': run['results'],
            'raw_projection_count': len(run['results'])}


def mixed(model, history):
    inputs = {}
    for row in history['rows']:
        f, o = row['field'], row['observable']
        checked = model.assess(f, o, row['value'])
        check(row['problem_identity'] == model.problem.identity and row['unit'] == UNITS[o]
              and row['target_identity'] == checked['target_identity'] and row['qualified'] and checked['qualified'],
              'historical scalar failed identity or quality checks')
        inputs[f, o] = np.float64(row['value'])
    check(set(inputs) == set(HISTORY), 'incorrect historical coverage')
    rhs, columns = [], {}
    for name, axes, observables in (('U', (1, 1, 0), ('q0', 'zz')), ('V', (0, 1, 1), ('r2', 'zz'))):
        col, identity = model._combined_column(axes, observables)
        rhs.append(col)
        columns[name] = identity
    block_rhs = np.column_stack(rhs)
    model.counts['submitted_rhs'] += len(rhs)
    model.counts['submitted_blocks'] += 1
    before = model.counts['response_operator_actions']
    result = solve_many(model, block_rhs, strategy='blocked', options=model.options,
                        raise_on_failure=True, collect_basis=False)
    check(result.operator_actions == model.counts['response_operator_actions'] - before, 'block work mismatch')
    for name, part in zip(('U', 'V'), result.results, strict=True):
        check(part.residual_norm <= GATE, 'combined direction failed physical residual')
        values = {o: float(model.rhs_values['observables'][o] @ part.solution)
                  for o in columns[name]['observable_identities']}
        check(all(math.isfinite(v) for v in values.values()), 'nonfinite mixed readout')
        columns[name].update(values=values, solution_sha256=array_hash(part.solution),
                             true_residual=float(part.residual_norm))
    u, v = (columns[k]['values'] for k in ('U', 'V'))
    decoded = (u['q0'] - inputs['y', 'q0'], v['r2'] - inputs['z', 'r2'],
               (v['zz'] - u['zz']) + inputs['x', 'zz'])
    rows = [dict(model.assess(f, o, value), unit=UNITS[o], problem_identity=model.problem.identity)
            for (f, o), value in zip(REQUESTS, decoded, strict=True)]
    return {'columns': columns, 'rhs_rank': result.rhs_rank, 'rows': rows, 'raw_projection_count': 4,
            'fp64_additions_and_subtractions': 4, 'historical_rows_sha256': json_hash(history['rows'])}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    base = HERE.parents[1]
    assets, oracles = base / 'qm9_response_assets', base / 'gqc_dual_response'
    name = 'qm9-000003'
    start = time.perf_counter()
    source_index = json.loads((assets / 'index.json').read_text())
    source = next(row for row in source_index['rows'] if row.get('name') == name)
    attested = next(row for row in json.loads((oracles / 'summary.json').read_text())['strata']
                    if row.get('name') == name)
    meta, arrays = (assets / source[k] for k in ('metadata_file', 'array_file'))
    oracle_file = oracles / attested['oracle']
    check(source['status'] == 'verified' and source['metadata_sha256'] == file_hash(meta)
          and source['array_file_sha256'] == file_hash(arrays) and attested['sha256'] == file_hash(oracle_file),
          'source digest or reference-state status')
    oracle = json.loads(oracle_file.read_text())
    op = DualResponseModel(meta, arrays, args.out, oracle=oracle)
    att = oracle['operator_attestation']
    report = {'name': name, 'recorded_utc': datetime.now(timezone.utc).isoformat(), 'gqc_commit': GQC_PIN,
              'checkout': git(ROOT, 'rev-parse', 'HEAD'), 'driver_sha256': file_hash(__file__),
              'protocol_sha256': file_hash(HERE / 'protocol.md'), 'model_sha256': file_hash(ROOT / 'scripts/gqc_dual_response.py'),
              'python': platform.python_version(), 'numpy': np.__version__, 'pyscf': pyscf.__version__,
              'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
              'source_index_sha256': file_hash(assets / 'index.json'), 'n5_job': source_index['job'],
              'qm9_member_sha256': source['member_sha256'],
              'archived_ground_state': {'native_scf_iterations': source['gqc']['iterations'],
                  'native_fock_builds': source['gqc']['fock_builds'], 'pyscf_scf_cycles': source['pyscf']['scf_cycles'],
                  'reference_and_storage_seconds': source['reference_and_storage_seconds']},
              'archived_oracle': {'sha256': file_hash(oracle_file),
                  'setup_jk': oracle['setup']['counts']['jk_calls'], 'direct_jk': oracle['direct']['counts']['jk_calls'],
                  'adjoint_jk': oracle['adjoint']['counts']['jk_calls'], 'seconds': oracle['seconds'],
                  'cphf_jk': oracle['independent']['cphf_counts']['jk_calls'],
                  'cphf_density_columns': oracle['independent']['cphf_counts']['density_columns'],
                  'scf_runs': len(oracle['independent']['scf']),
                  'scf_jk': sum(s['counts']['jk_calls'] for s in oracle['independent']['scf']),
                  'additional_operator_attestation': {k: v for k, v in att.items() if k.startswith('extra_')}},
              'shared_setup': op.setup}
    history = report['history'] = measure(op, lambda: direct(op, HISTORY))
    regular = report['ordinary'] = measure(op, lambda: direct(op, REQUESTS))
    if history['status'] == 'completed' and all(r['qualified'] for r in history['result']['rows']):
        two = measure(op, lambda: mixed(op, history['result']))
    else:
        two = {'status': 'withheld', 'reason': 'three qualified historical scalars required', 'counts': {}, 'seconds': 0.0}
    report['two_field'] = two
    if two['status'] == regular['status'] == 'completed':
        direct_by_edge = {(r['field'], r['observable']): r for r in regular['result']['rows']}
        differences = {}
        for row in two['result']['rows']:
            edge = row['field'], row['observable']
            left, right = row['raw_value'], direct_by_edge[edge]['raw_value']
            differences['/'.join(edge)] = abs(left - right) if left is not None and right is not None else None
        report['absolute_raw_differences'] = differences
    report['setup_plus_history_plus_route_jk'] = {
        k: op.setup['counts']['jk_calls'] + history['counts'].get('jk_calls', 0) + r['counts'].get('jk_calls', 0)
        for k, r in (('ordinary', regular), ('two_field', two))}
    report.update(actual_counts=dict(op.counts), measured_seconds_to_report=time.perf_counter() - start)
    write_json(args.out / 'results.json', report)
    for name, case in [('history', history), ('ordinary', regular), ('two_field', two)]:
        print(name, case['status'], case['counts'], case.get('reason', ''))
    return int(any(case['status'] != 'completed' or not all(r['qualified'] for r in case['result']['rows'])
                   for case in (history, regular, two)))


if __name__ == '__main__':
    raise SystemExit(main())
