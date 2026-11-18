#!/usr/bin/env python3
"""Check failed scientific attempts against native calls, SQLite and fresh CLI processes."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import ExitStack
from dataclasses import replace
import gzip
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import time
from unittest.mock import patch

import complete_response_dataset as client
import gqc_dual_response as molecular
from probe_gqc_residual import ROOT, file_hash, write_json

URL = 'https://api.figshare.com/v2/articles/1057646/versions/2'
CROSS = [('y', 'q0'), ('x', 'r2')]
DIAGONAL = [('x', 'q0'), ('y', 'r2'), ('z', 'zz')]


def interrupted_run(argv, mode):
    """Observe the unmodified numerical calls from outside the production meter."""
    phase = Counter()
    observed = [('model_setup', phase)]
    validating = False
    model = molecular.DualResponseModel
    original_potential, original_apply = model.potential, model.apply
    original_round, original_cached, original_solve = model.run_round, model._cached, molecular.solve_many

    def potential(operator, density):
        phase['jk_calls'] += 1
        value = original_potential(operator, density)
        # Corrupt only this control's in-memory Fock contraction, after the
        # native J/K call, to trigger the real setup gate.
        return value + 0.1 if mode == 'constructor' else value

    def apply(operator, vector):
        phase['response_operator_actions'] += 1
        if validating:
            phase['cache_validation_actions'] += 1
        return original_apply(operator, vector)

    def cached(operator, *args):
        nonlocal validating
        validating = True
        try:
            return original_cached(operator, *args)
        finally:
            validating = False

    def traced_round(operator, *args, **kw):
        nonlocal phase
        phase = Counter()
        name = 'ordinary_response' if kw.get('combined_coefficients') is None else 'combined_response'
        observed.append((name, phase))
        return original_round(operator, *args, **kw)

    def limited_solve(operator, rhs, **kw):
        phase['submitted_blocks'] += 1
        phase['submitted_rhs'] += rhs.shape[1]
        kw['options'] = replace(kw['options'], max_iterations=1)
        return original_solve(operator, rhs, **kw)

    with ExitStack() as changes:
        for target, name, replacement in ((model, 'potential', potential), (model, 'apply', apply),
                                          (model, '_cached', cached), (model, 'run_round', traced_round),
                                          (molecular, 'solve_many', limited_solve), (sys, 'argv', argv)):
            changes.enter_context(patch.object(target, name, replacement))
        assert client.main() == 1, mode
    return observed


def scientific_state(db):
    """Byte-level comparison includes labels and every serialized vector and digest."""
    return [db.execute('SELECT * FROM labels ORDER BY identity,field,observable').fetchall(),
            db.execute('SELECT * FROM vectors ORDER BY identity').fetchall()]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    folder = parser.parse_args().work.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    batches, controls = {}, {}
    normal_cli = str(ROOT / 'scripts/complete_response_dataset.py')
    _, routes, _, _ = client.route_catalogs(client.DEFAULT_CATALOGS)
    paired_indexes = {name: route[-1] for name, route in routes.items()}

    def run(label, db_path, edges, *, history=None, failure=None):
        inputs, output = folder / (label + '.jsonl'), folder / (label + '.json')
        inputs.write_text(''.join(json.dumps(dict(source=URL, record_id=3, field=f, observable=o)) + '\n'
                                  for f, o in edges))
        args = [normal_cli, '--cache-db', str(db_path), '--requests', str(inputs), '--out', str(output),
                '--kernel-cache', str(folder / 'kernels')]
        if history:
            args.extend(['--history', file_hash(history), str(history)])
        trace = []
        if failure:
            trace = interrupted_run(args, failure)
        else:
            subprocess.run([sys.executable, *args], check=True)
        batch = batches[label] = json.loads(output.read_bytes())
        attempt, = batch['work']
        with sqlite3.connect(db_path) as db:
            status, persisted = db.execute('SELECT status, receipt FROM attempts WHERE id=?',
                                           (attempt['id'],)).fetchone()
            assert json.loads(persisted) == attempt and status == attempt['status']
            assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        return batch, attempt, trace

    ordinary_db = folder / 'ordinary.sqlite'
    run('prior-vector', ordinary_db, [('x', 'zz')])
    run('history', folder / 'history.sqlite', CROSS)
    for case, db_path, edges, history in (
            ('ordinary', ordinary_db, [('x', 'q0'), ('y', 'r2')], None),
            ('combined_and_fallback', folder / 'combined.sqlite', DIAGONAL, folder / 'history.json'),
            ('constructor', folder / 'constructor.sqlite', [('x', 'q0')], None)):
        with sqlite3.connect(db_path) as db:
            db.executescript(client.SCHEMA)
            before = scientific_state(db)
            earlier = db.execute('SELECT count(*) FROM attempts').fetchone()[0]
        batch, failed, trace = run(case, db_path, edges, history=history, failure=case)
        assert failed['status'] == 'failed' and failed['model_started']
        assert all(row['value'] is None and row['status'] == 'execution_failed' for row in batch['records'])
        with sqlite3.connect(db_path) as db:
            assert scientific_state(db) == before
            assert db.execute('SELECT count(*) FROM attempts').fetchone()[0] == earlier + 1
        prior = folder / (case + '.json')
        history_costs, assets = client.load_history((file_hash(prior), prior), paired_indexes)
        assert history_costs['status'] == 'read' and not assets
        assert history_costs['producer_failed_attempts'] == [failed['id']]
        assert (history_costs['producer_setup_jk'], history_costs['producer_round_jk']) == (
            failed['setup_jk'], failed['round_jk'])
        stages = failed['cost_stages']
        assert trace[0][0] == stages[0]['phase'] == 'model_setup'
        assert all(s['seconds'] >= 0 for s in stages)
        assert failed['setup_seconds'] == stages[0]['seconds'] and failed['setup_seconds'] > 0
        assert len(failed['native_kernel_attempts']) == len(failed['native_kernel_sha256']) == 5
        assert all(len(k['binary_sha256']) == 64 and k['elapsed_seconds'] > 0 for k in failed['native_kernel_attempts'])
        assert failed['setup_compile_only_seconds'] is None
        observed_stages = [s for s in stages if s['phase'] != 'decoder_setup']
        for actual, (name, calls) in zip(observed_stages, trace, strict=True):
            assert name == actual['phase']
            for key in ('jk_calls', 'response_operator_actions', 'submitted_rhs', 'submitted_blocks', 'cache_validation_actions'):
                assert actual['operations'].get(key, 0) == calls[key], (case, key, calls, actual)
        new_work = sum((ops for _, ops in trace[1:]), Counter())
        counts = failed['counts']
        assert failed['setup_jk'] == trace[0][1]['jk_calls']
        assert failed['rhs'] == counts['rhs_columns'] == new_work['submitted_rhs']
        assert counts['submitted_blocks'] == new_work['submitted_blocks']
        assert failed['round_jk'] == counts['jk_calls'] == new_work['jk_calls']
        assert counts['operator_actions'] == new_work['response_operator_actions']
        assert counts['cache_validation_actions'] == new_work['cache_validation_actions']
        assert counts['solver_actions'] == counts['operator_actions'] - counts['cache_validation_actions']
        if case == 'constructor':
            assert failed['setup_jk'] == 1 and failed['round_jk'] == failed['rhs'] == counts['submitted_blocks'] == 0
            assert failed['failed_stage'] == 'model_setup' and failed['setup_status'] == 'failed'
            assert len(stages) == 1 and 'stored Fock fails physical AO contraction' in failed['reason']
            assert counts['requests'] == 0
            # Review-version constructor failures had no counters available.
            legacy = folder / 'legacy-partial-control.json'
            old_work = {k: failed[k] for k in ('id', 'record_id', 'identity', 'model_started', 'status')}
            old_work.update(setup_jk=None, round_jk=0, rhs=0)
            write_json(legacy, {**batch, 'work': [old_work]})
            old, _ = client.load_history((file_hash(legacy), legacy), paired_indexes)
            assert old['status'] == 'read' and old['producer_setup_jk'] is None and old['producer_round_jk'] is None
        else:
            assert failed['failed_stage'] == 'solve_and_assess' and failed['setup_status'] == 'completed'
            assert failed['setup_jk'] == 5 and failed['solve_and_assess_seconds'] > 0 and counts['requests'] is None
            assert all(s['status'] == 'failed' and s['reason'] for s in observed_stages[1:])
            assert all(s['operations']['jk_calls'] > 0 for s in observed_stages[1:])
            if case == 'ordinary':
                assert [s['phase'] for s in stages] == ['model_setup', 'ordinary_response']
                assert failed['rhs'] == counts['submitted_blocks'] == counts['cache_validation_actions'] == 1
            else:
                assert [s['phase'] for s in stages] == [
                    'model_setup', 'decoder_setup', 'combined_response', 'ordinary_response']
                assert failed['validated_history_scalars'] == 2 and not any(before)
                assert [s['operations']['submitted_rhs'] for s in stages[-2:]] == [2, 3]
                assert counts['submitted_blocks'] == 2 and failed['rhs'] == 5

        retried_batch, retry, _ = run(case + '-retry', db_path, edges, history=history)
        hit_batch, hit, _ = run(case + '-reopen', db_path, edges)
        assert all(r['status'] == 'qualified' and r['delivery'] == 'computed' for r in retried_batch['records'])
        assert all(r['status'] == 'qualified' and r['source_attempt'] == retry['id'] for r in hit_batch['records'])
        assert retry['id'] != failed['id'] and retry['model_started'] and retry['round_jk'] > 0
        assert retry['rhs'] == {'ordinary': 1, 'combined_and_fallback': 2, 'constructor': 1}[case]
        assert not hit['model_started'] and hit['rhs'] == hit['round_jk'] == hit['setup_jk'] == 0
        assert hit['counts']['submitted_blocks'] == 0 and len({r['id'] for r in (failed, retry, hit)}) == 3
        with sqlite3.connect(db_path) as db:
            stored = dict(db.execute('SELECT id, receipt FROM attempts'))
            assert len(stored) == earlier + 3
            for attempt in (failed, retry, hit):
                assert json.loads(stored[attempt['id']]) == attempt
        controls[case] = dict(before_rows=[len(table) for table in before], rollback_equal=True,
                              observations=trace, failure=failed, history_costs=history_costs,
                              retry=retry['id'], reopen=hit['id'])

    receipts = {w['id']: w for b in batches.values() for w in b['work']}
    report = dict(controls=controls, record_id='qm9-000003', python=platform.python_version(),
                  compiler=subprocess.check_output(['c++', '--version'], text=True).splitlines()[0],
                  versions={k: version(k) for k in ('numpy', 'pyscf', 'scipy', 'h5py')},
                  threads={k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
                  gqc_commit=molecular.GQC_PIN, cli_sha256=file_hash(normal_cli),
                  model_sha256=file_hash(molecular.__file__), regression_sha256=file_hash(__file__),
                  totals={k: sum(row[k] for row in receipts.values()) for k in ('setup_jk', 'round_jk', 'rhs', 'seconds')},
                  unique_attempts=len(receipts), suite_seconds=time.perf_counter() - start, result='passed')
    compressed = gzip.compress(json.dumps(batches, sort_keys=True, allow_nan=False).encode(), mtime=0)
    (folder / 'batches.json.gz').write_bytes(compressed)
    report['batches_sha256'] = sha256(compressed).hexdigest()
    write_json(folder / 'verification.json', report)
    print('three failed attempts, three independent retries and three zero-cost reopens verified', report['totals'])


if __name__ == '__main__':
    main()
