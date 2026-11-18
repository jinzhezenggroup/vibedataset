#!/usr/bin/env python3
"""PLAN-001. Replay endpoint choices and scalar/vector retention on independent QM9 records."""
import argparse
from collections import Counter
from itertools import product
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import time

from gqc_dual_response import ANALYTIC_TOL, FIELD_TOL, GATE, STEPS, DualResponseModel, FIELD_IDS, OBSERVABLE_IDS
from probe_gqc_residual import array_hash, file_hash, json_hash, write_json
from response_cover import plan_cover

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
EDGES = tuple(product(FIELD_IDS, OBSERVABLE_IDS))
CROSS = (('x', 'r2'), ('x', 'zz'), ('y', 'q0'), ('z', 'q0'))
TRACES = {
    'sparse_stop': (CROSS, (('x', 'q0'), ('y', 'q0'))),
    'row_growth': (CROSS, (('x', 'q0'), ('y', 'r2'), ('y', 'zz')), (('z', 'r2'), ('z', 'zz'))),
    'column_growth': (CROSS, (('x', 'q0'), ('y', 'r2'), ('z', 'r2')), (('y', 'zz'), ('z', 'zz'))),
}
POLICIES = ('labels_only', 'lazy_direct', 'lazy_adjoint', 'mixed', 'eager_field_table',
            'eager_observable_table', 'mixed_materialize')
VECTOR_POLICIES = {'lazy_direct', 'lazy_adjoint', 'mixed', 'mixed_materialize'}
COUNT_NAMES = ('jk_calls', 'operator_actions', 'rhs_columns', 'cache_validation_actions',
               'solver_actions', 'cache_rejections', 'requests')


def scalar_identity(model):
    """Bind the scalar cache to both physical derivative operands and the publication regime."""
    return json_hash({
        'definition': 'clamped-nuclei RHF at zero uniform field, atomic units, origin (0,0,0)',
        'problem': model.problem.identity, 'derivative_contract': model.contract_identity, 'source': model.source,
        'rhs': {g: {k: array_hash(v) for k, v in group.items()} for g, group in model.rhs_values.items()},
        'qualification': {'residual': GATE, 'analytic_absolute': ANALYTIC_TOL,
                          'finite_field_absolute': FIELD_TOL, 'field_steps': STEPS,
                          'oracle_sha256': json_hash(model.oracle) if model.oracle is not None else None},
    })


def _read_asset(path, identity, key):
    if not path.is_file():
        return [], 0
    raw = path.read_bytes()
    envelope = json.loads(raw)
    body = envelope['payload']
    if json_hash(body) != envelope['sha256'] or body['scientific_identity'] != identity:
        raise ValueError('scalar payload or scientific identity mismatch')
    return body[key], len(raw)


def _write_asset(path, identity, key, rows):
    body = {'scientific_identity': identity, key: rows}
    temp = path.with_suffix('.tmp')
    write_json(temp, {'payload': body, 'sha256': json_hash(body)})
    temp.replace(path)
    return path.stat().st_size


def read_scalars(path, identity):
    rows, size = _read_asset(path, identity, 'labels')
    return {(r['field'], r['observable']): r['value'] for r in rows}, size


def write_scalars(path, identity, labels):
    rows = [{'field': f, 'observable': o, 'value': v} for (f, o), v in sorted(labels.items())]
    return _write_asset(path, identity, 'labels', rows)


def choose(policy, pending, cache, first):
    fields = set(cache['fields'])
    obs = set(cache['observables'])
    requested_fields = {f for f, _ in pending}
    requested_obs = {o for _, o in pending}
    if policy == 'labels_only':
        selected = (sorted(requested_fields), []) if len(requested_fields) <= len(requested_obs) else ([], sorted(requested_obs))
    elif policy == 'lazy_direct':
        selected = sorted(requested_fields - fields), []
    elif policy == 'lazy_adjoint':
        selected = [], sorted(requested_obs - obs)
    elif policy == 'eager_field_table':
        selected = list(FIELD_IDS) if first else sorted(requested_fields), []
    elif policy == 'eager_observable_table':
        selected = [], list(OBSERVABLE_IDS) if first else sorted(requested_obs)
    elif policy in ('mixed', 'mixed_materialize'):
        selected = plan_cover(pending, fields, obs)
    else:
        raise ValueError(f'unknown policy {policy}')
    targets = set(pending)
    if first and policy in ('eager_field_table', 'eager_observable_table'):
        targets.update(EDGES)
    if policy == 'mixed_materialize':
        active_fields, active_obs = fields.union(selected[0]), obs.union(selected[1])
        targets.update((f, o) for f, o in EDGES if f in active_fields or o in active_obs)
    return tuple(selected[0]), tuple(selected[1]), targets


def journal(path, entry):
    with path.open('a') as handle:
        handle.write(json.dumps(entry, allow_nan=False, separators=(',', ':')) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def run_trajectory(model, name, policy, replicate, out, identity, events, remember_rejections):
    directory = out / model.name / name / f'{policy}-{replicate}'
    directory.mkdir(parents=True, exist_ok=False)
    vector_path = directory / 'vectors.json'
    scalar_path = directory / 'scalars.json'
    refusal_path = directory / 'rejections.json'
    measurements = []
    for index, requests in enumerate(TRACES[name]):
        event = {'molecule': model.name, 'trace': name, 'policy': policy, 'replicate': replicate,
                 'round': index + 1, 'requests': requests}
        journal(events, dict(event, event='started'))
        before = model.counts.copy()
        start = time.perf_counter()
        try:
            labels, scalar_read = read_scalars(scalar_path, identity)
            refusals, refusal_read = {}, 0
            if remember_rejections:
                rows, refusal_read = _read_asset(refusal_path, identity, 'rejections')
                for row in rows:
                    f, o = row['field'], row['observable']
                    # Only previously observed failures of the shared target reference may be reused.
                    if row['gate_sha256'] == json_hash(model.oracle['targets'][f][o]):
                        refusals[(f, o)] = row
            needed = set(requests).difference(labels, refusals)
            hits = set(requests).intersection(labels)
            vector_read = vector_path.stat().st_size if needed and vector_path.is_file() else 0
            cache = model.load_cache(vector_path) if vector_read else model.new_cache()
            read_seconds = time.perf_counter() - start
            t = time.perf_counter()
            fields, obs, targets = choose(policy, needed, cache, index == 0)
            targets.difference_update(labels)
            targets.difference_update(refusals)
            plan_seconds = time.perf_counter() - t
            counts = dict.fromkeys(COUNT_NAMES, 0)
            values = {}
            r = None
            if targets:
                r = model.run_round(targets, fields, obs, cache)
                counts = r['counts']
                values = {(v['field'], v['observable']): v for v in r['results']}
            elapsed_kernel = time.perf_counter() - t - plan_seconds
            t = time.perf_counter()
            new_labels = {key: info['value'] for key, info in values.items() if info['qualified']}
            labels.update(new_labels)
            scalar_written = write_scalars(scalar_path, identity, labels) if new_labels else 0
            refusal_written = 0
            if remember_rejections:
                new_refusals = {}
                for (f, o), result in values.items():
                    reference = model.oracle['targets'][f][o]
                    if result['qualified'] is False and reference['reasons']:
                        new_refusals[(f, o)] = {'field': f, 'observable': o, 'reasons': reference['reasons'],
                                                'gate_sha256': json_hash(reference)}
                if new_refusals:
                    refusals.update(new_refusals)
                    refusal_written = _write_asset(refusal_path, identity, 'rejections',
                                                   [refusals[k] for k in sorted(refusals)])
            vector_written = 0
            if r and policy in VECTOR_POLICIES and (r['new_fields'] or r['new_observables']):
                model.save_cache(cache, vector_path)
                vector_written = vector_path.stat().st_size
            write_seconds = time.perf_counter() - t
            elapsed = time.perf_counter() - start
            delivered = [{'field': f, 'observable': o, 'value': labels.get((f, o)),
                          'cached_scalar': (f, o) in hits,
                          'cached_gate_rejection': (f, o) in refusals and (f, o) not in values}
                         for f, o in requests]
            entry = dict(event, event='completed', selected_fields=fields, selected_observables=obs,
                         filled=delivered, computed=list(values.values()), counts=counts,
                         block=r['block'] if r else None, cache_checks=r['cache_checks'] if r else [],
                         scalar_read=scalar_read, vector_read=vector_read,
                         scalar_written=scalar_written, vector_written=vector_written,
                         refusal_read=refusal_read, refusal_written=refusal_written,
                         retained_bytes=scalar_path.stat().st_size if scalar_path.exists() else 0,
                         read_seconds=read_seconds, plan_seconds=plan_seconds, compute_seconds=elapsed_kernel,
                         write_seconds=write_seconds, elapsed_seconds=elapsed)
            if vector_path.is_file():
                entry['retained_bytes'] += vector_path.stat().st_size
            if refusal_path.is_file():
                entry['retained_bytes'] += refusal_path.stat().st_size
        except Exception as exc:
            journal(events, dict(event, event='failed', error=f'{type(exc).__name__}: {exc}',
                                 actual_counter_change=dict(model.counts - before), elapsed_seconds=time.perf_counter() - start))
            raise
        journal(events, entry)
        measurements.append(entry)
    counts = Counter()
    for m in measurements:
        counts.update(m['counts'])
    return {'molecule': model.name, 'trace': name, 'policy': policy, 'replicate': replicate,
            'counts': dict(counts), 'request_count': sum(len(r['requests']) for r in measurements),
            'published_requests': sum(row['value'] is not None for r in measurements for row in r['filled']),
            'cached_requests': sum(row['cached_scalar'] for r in measurements for row in r['filled']),
            'cached_rejections': sum(row['cached_gate_rejection'] for r in measurements for row in r['filled']),
            'seconds': sum(m['elapsed_seconds'] for m in measurements),
            'io_read': sum(m['scalar_read'] + m['vector_read'] + m['refusal_read'] for m in measurements),
            'io_written': sum(m['scalar_written'] + m['vector_written'] + m['refusal_written'] for m in measurements),
            'retained_bytes': measurements[-1]['retained_bytes'],
            'jk_by_round': [m['counts']['jk_calls'] for m in measurements]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--oracles', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--remember-reference-rejections', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    source = json.loads((args.assets / 'index.json').read_text())
    summary = {
        'project_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'driver_sha256': file_hash(__file__), 'planner_sha256': file_hash(ROOT / 'scripts/response_cover.py'),
        'molecular_api_sha256': file_hash(ROOT / 'scripts/gqc_dual_response.py'),
        'source_index_sha256': file_hash(args.assets / 'index.json'), 'source_job': source['job'],
        'python': platform.python_version(), 'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
        'traces': TRACES, 'policies': POLICIES, 'replicates': 2, 'order_seed': 60129,
        'remember_reference_rejections': args.remember_reference_rejections, 'strata': [], 'trajectories': [],
    }
    for case in source['rows']:
        receipt = {k: case.get(k) for k in ('name', 'stratum', 'status', 'error', 'member_sha256')}
        summary['strata'].append(receipt)
        if case['status'] != 'verified':
            continue
        meta = args.assets / case['metadata_file']
        arrays = args.assets / case['array_file']
        if (file_hash(meta), file_hash(arrays)) != (case['metadata_sha256'], case['array_file_sha256']):
            raise ValueError('upstream archive bytes changed')
        oracle = args.oracles / (case['name'] + '.json')
        model = DualResponseModel(meta, arrays, args.out / 'native', oracle)
        identity = scalar_identity(model)
        receipt.update(setup=model.setup, oracle_sha256=file_hash(oracle), scalar_identity=identity)
        order = list(product(TRACES, POLICIES))
        random.Random(60129 + case['qm9_id']).shuffle(order)
        for rep, tasks in enumerate((order, reversed(order)), 1):
            for trace, policy in tasks:
                summary['trajectories'].append(run_trajectory(
                    model, trace, policy, rep, args.out, identity, args.out / 'operations.jsonl',
                    args.remember_reference_rejections))
        write_json(args.out / 'summary.json', summary)
        print(case['name'], len(summary['trajectories']), flush=True)
    summary['wall_seconds_including_journal_and_output'] = time.perf_counter() - start
    write_json(args.out / 'summary.json', summary)


if __name__ == '__main__':
    main()
