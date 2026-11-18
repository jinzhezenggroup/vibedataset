#!/usr/bin/env python3
"""Run independent clients, concurrent writers, a rollback, repair and restart."""
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
RELEASE = 'https://api.figshare.com/v2/articles/1057646/versions/2'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    work = parser.parse_args().work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    db_path = work / 'responses.sqlite'
    def request_file(name, request):
        p = work / (name + '.jsonl')
        p.write_text(json.dumps({'source': RELEASE, **request}) + '\n')
        return p
    def execute(name, inp, code):
        result_path = work / (name + '.json')
        cmd = [sys.executable, str(ROOT/'scripts/complete_response_dataset.py'), '--requests', str(inp),
               '--cache-db', str(db_path), '--out', str(result_path)]
        start = datetime.now(timezone.utc).isoformat()
        t = time.perf_counter()
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = p.communicate(timeout=180)
        assert p.returncode == code, (name, p.returncode, stderr)
        raw = result_path.read_bytes()
        result = json.loads(raw)
        receipt = {'client': name, 'process_id': p.pid, 'started_utc': start,
                   'finished_utc': datetime.now(timezone.utc).isoformat(), 'seconds': time.perf_counter() - t,
                   'exit_code': p.returncode, 'status_counts': result['counts_by_status'], 'result_sha256': digest(raw),
                   'input_sha256': result['input_sha256'], 'stdout': stdout, 'stderr': stderr,
                   'work': result['work']}
        return result, receipt
    history = []
    def visit(name, inp, code):
        report, receipt = execute(name, inp, code)
        history.append(receipt)
        return report
    first = visit('first', HERE/'first.jsonl', 1)
    first_work, = first['work']
    labels = first['records']
    assert first_work['rhs'] == 1 and first_work['setup_jk'] > 0 and first_work['round_jk'] > 0
    assert labels[2]['status'] == 'reference_unavailable' and labels[3]['duplicate_of_line'] == 1
    assert labels[4]['status'] == 'problem_mismatch' and labels[5]['status'] == 'record_not_indexed'
    assert labels[3]['value'] == labels[0]['value']
    replay = visit('independent-hit', HERE/'hit.jsonl', 0)
    w, = replay['work']
    assert w['scalar_hits'] == 1 and not w['model_started'] and w['round_jk'] == w['setup_jk'] == 0
    assert replay['records'][0]['value'] == labels[1]['value'] and replay['records'][0]['source_attempt'] == first_work['id']
    appended = visit('append', HERE/'append.jsonl', 1)
    assert appended['work'][0]['rhs'] == 0 and appended['work'][0]['counts']['cache_validation_actions'] == 1
    failed_gate = appended['records'][2]
    assert failed_gate['value'] is None and failed_gate['status'] == 'withheld' and failed_gate['diagnostic']['raw_value'] is not None
    assert 'cphf' in failed_gate['diagnostic']['reasons']

    shared = request_file('concurrent', {'record_id': 1, 'field': 'x', 'observable': 'q0'})
    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(execute, f'concurrent-{i}', shared, 0) for i in range(2)]
        concurrent = [job.result() for job in jobs]
    for _, receipt in concurrent:
        history.append(receipt)
    receipts = [item[1] for item in concurrent]
    assert max(r['started_utc'] for r in receipts) < min(r['finished_utc'] for r in receipts)
    deliveries = [item[0]['records'][0] for item in concurrent]
    assert sorted(x['delivery'] for x in deliveries) == ['computed', 'scalar_cache']
    assert deliveries[0]['source_attempt'] == deliveries[1]['source_attempt'] and deliveries[0]['value'] == deliveries[1]['value']
    assert sum(r['work'][0]['model_started'] for r in receipts) == 1
    assert sum(r['work'][0]['rhs'] for r in receipts) == 1

    # This trigger is confined to this test's new database. The real client
    # inserts the label first. Rejecting the subsequent vector write must
    # roll back the label before any fresh client can claim a cache hit.
    with sqlite3.connect(db_path) as db:
        def state():
            return (db.execute('SELECT identity,field,observable,record,digest FROM labels ORDER BY 1,2,3').fetchall(),
                    db.execute('SELECT identity,record,digest FROM vectors ORDER BY 1').fetchall())
        previous_state = state()
        db.execute("CREATE TRIGGER inject_failure BEFORE INSERT ON vectors BEGIN SELECT RAISE(ABORT,'injected vector write failure'); END")
    probe = request_file('new', {'record_id': 2, 'field': 'y', 'observable': 'r2'})
    denied = visit('atomic-failure', probe, 1)
    assert denied['records'][0]['status'] == 'execution_failed' and denied['records'][0]['value'] is None
    assert denied['work'][0]['round_jk'] > 0 and 'injected vector write failure' in denied['work'][0]['reason']
    with sqlite3.connect(db_path) as db:
        assert state() == previous_state
        assert db.execute('SELECT status FROM attempts WHERE id=?', (denied['work'][0]['id'],)).fetchone() == ('failed',)
        db.execute('DROP TRIGGER inject_failure')
    retry = visit('retry', probe, 0)
    assert retry['records'][0]['delivery'] == 'computed' and retry['work'][0]['scalar_hits'] == 0
    for label, invalid_value in [('missing', None), ('oversized-integer', 10**400)]:
        with sqlite3.connect(db_path) as db:
            key = (first_work['identity'], 'x', 'r2')
            q = 'SELECT record FROM labels WHERE identity=? AND field=? AND observable=?'
            stored = json.loads(db.execute(q, key).fetchone()[0])
            stored['value'] = invalid_value
            encoded = json.dumps(stored, sort_keys=True, separators=(',', ':'), allow_nan=False)
            db.execute('UPDATE labels SET record=?,digest=? WHERE identity=? AND field=? AND observable=?',
                       (encoded, digest(encoded.encode()), *key))
        repaired = visit(label + '-scalar-recovered', HERE/'hit.jsonl', 0)
        r, = repaired['work']
        assert r['scalar_rejections'] == 1 and r['scalar_hits'] == 0 and r['counts']['cache_validation_actions'] == 1
        assert 'nonfinite or missing candidate' in r['rejected_labels'][0]['reason']
        assert repaired['records'][0]['value'] == replay['records'][0]['value']

    invalid = work/'invalid.jsonl'
    invalid.write_text('{"request_id":NaN}\n' + json.dumps({'source': 'unrelated', 'record_id': 3,
                      'field': 'x', 'observable': 'q0'}) + '\n')
    rejected = visit('invalid-input', invalid, 1)
    assert not rejected['work'] and rejected['counts_by_status'] == {'invalid_request': 1, 'unsupported_source': 1}
    with sqlite3.connect(db_path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        ni = db.execute('SELECT status,count(*) FROM attempts GROUP BY status').fetchall()
        row_counts = {table: db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('labels','vectors','attempts')}
    result = {'cli_sha256': digest((ROOT/'scripts/complete_response_dataset.py').read_bytes()),
              'grader_sha256': digest((ROOT/'scripts/gqc_dual_response.py').read_bytes()), 'verification_checks': [
              'fresh GQC block for caller-supplied edges, duplicate group member deduplicated',
              'failed zero-field source, unknown record and requested problem mismatch',
              'separate process consumes a qualified scalar with zero GQC setup/actions',
              'additional target reuses an admitted vector; failed numerical gate retains only raw value',
              'two overlapping OS clients commit one new solution, return the same origin and value',
              'failed vector write rolls back earlier label write; prior scientific state byte-equivalent',
              'independent retry solves after rollback; failed attempt and spent work remain in SQLite',
              're-digested invalid scalar rejected and restored through physical residual validation',
              'invalid/nonfinite requests preserve denominator, database integrity check passes'],
              'processes': history, 'attempt_states': dict(ni), 'table_rows': row_counts, 'result': 'passed'}
    (work/'verification.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(result['result'], len(history), 'processes', ni, row_counts)


if __name__ == '__main__':
    main()
