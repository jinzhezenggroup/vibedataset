#!/usr/bin/env python3
"""Replay all 153 requests across the v1/v2 SQLite and measured-history boundary."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
V1 = 'faf93dd4a95d9a12ee06bdcf85040ecb38d9107b'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v1-checkout', type=Path, required=True, help='clean checkout of the reviewed commit')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    old = args.v1_checkout.resolve()
    require(subprocess.check_output(['git', '-C', old, 'rev-parse', 'HEAD'], text=True).strip() == V1
            and not subprocess.check_output(['git', '-C', old, 'status', '--porcelain']), 'v1 checkout differs')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    req = HERE.parent / 'qm9_extension/all-requests.jsonl'
    receipts = {}

    def run(name, checkout, database, previous=None):
        target = out / (name + '.json')
        cmd = [sys.executable, checkout / 'scripts/complete_response_dataset.py', '--requests', req,
               '--cache-db', out / database, '--kernel-cache', out / 'kernels', '--out', target]
        if previous:
            cmd.extend(('--history', digest(previous), previous))
        code = subprocess.run(cmd).returncode
        batch = json.loads(target.read_bytes())
        require(code == 1 and batch['input_sha256'] == digest(req) and len(batch['records']) == 153,
                name + ' incomplete expected scientific result')
        require(len(batch['work']) == 12 and all(w['status'] == 'completed' for w in batch['work']),
                name + ' incomplete molecular work')
        with sqlite3.connect(out / database) as db:
            for work in batch['work']:
                saved = db.execute('SELECT receipt FROM attempts WHERE id=?', (work['id'],)).fetchone()
                require(saved is not None and json.loads(saved[0]) == work, 'SQLite / JSON mismatch')
        receipts[name] = {'cli_commit': subprocess.check_output(['git', '-C', checkout, 'rev-parse', 'HEAD'],
                                                                  text=True).strip(),
                          'batch_sha256': digest(target), 'input_sha256': digest(req), 'exit': code,
                          'statuses': batch['counts_by_status'],
                          'work': {k: sum(w[k] for w in batch['work'])
                                   for k in ('setup_jk', 'round_jk', 'rhs', 'scalar_hits', 'historical_hits')}}
        return batch

    v1 = run('v1', old, 'cohort.sqlite')
    migrated = run('v2', ROOT, 'cohort.sqlite', out / 'v1.json')
    warm = run('reopen', ROOT, 'cohort.sqlite')
    transferred = run('v2-history', ROOT, 'history-only.sqlite', out / 'v2.json')
    require(v1['counts_by_status'] == {'qualified': 37, 'withheld': 71, 'reference_unavailable': 45},
            'v1 release denominator')
    require(migrated['history']['eligible_rows'] == 0 and len(migrated['history']['excluded_catalog_records']) == 37,
            'stale external history accepted or not accounted')
    old_ids = {w['identity'] for w in v1['work']}
    require(old_ids.isdisjoint(w['identity'] for w in migrated['work']), 'v1 cache identities reused')
    require(all(w['model_started'] and w['scalar_hits'] == 0 and w['rhs'] == 3 and not w['cache_checks']
                for w in migrated['work']), 'v2 read stale assets')
    for replay in (warm, transferred):
        require(replay['counts_by_status'] == migrated['counts_by_status'] and
                all(w['scalar_hits'] == 9 and not w['model_started'] for w in replay['work']),
                'qualified history replay performed extra solves or changed qualification')
        for x, y in zip(migrated['records'], replay['records'], strict=True):
            require((x['status'], x['value'], x.get('source_attempt')) ==
                    (y['status'], y['value'], y.get('source_attempt')), 'replay changed value or provenance')
    for name in receipts:
        path = out / (name + '.json')
        path.with_suffix('.json.gz').write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    (out / 'cache-replay.json').write_text(json.dumps(receipts, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    main()
