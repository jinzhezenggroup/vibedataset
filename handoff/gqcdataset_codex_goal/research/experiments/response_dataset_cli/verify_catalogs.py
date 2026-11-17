#!/usr/bin/env python3
"""Check multi-catalog routing, measured mixed requests, and v1 provenance compatibility."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EXPERIMENTS = HERE.parent
SOURCE = 'https://api.figshare.com/v2/articles/1057646/versions/2'
SETS = [(EXPERIMENTS/'qm9_response_assets/index.json', EXPERIMENTS/'gqc_dual_response/summary.json'),
        (EXPERIMENTS/'qm9_extension/assets/index.json', EXPERIMENTS/'qm9_extension/oracle-index.json')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    work = parser.parse_args().work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    logs = []
    def call(name, *, requests=HERE/'both-catalogs.jsonl', database='mixed', history=None, pair=None, code=1, script=None):
        out = work/(name + '.json')
        cmd = [sys.executable, str(script or (ROOT/'scripts/complete_response_dataset.py')),
               '--requests', str(requests), '--out', str(out), '--cache-db', str(work/(database + '.sqlite')),
               '--kernel-cache', str(work/'kernels')]
        if history:
            cmd.extend(['--history', sha(history), str(history)])
        if pair:
            cmd.extend(['--source-index', str(pair[0]), '--oracle-index', str(pair[1])])
        start = time.perf_counter()
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        assert done.returncode == code, (name, done.stderr)
        rec = {'client': name, 'seconds': time.perf_counter()-start, 'exit_code': done.returncode, 'stderr': done.stderr}
        if not out.is_file():
            logs.append(rec)
            return {}
        data = json.loads(out.read_bytes())
        rec.update(sha256=sha(out), statuses=data['counts_by_status'], work=data['work'], input_sha256=data['input_sha256'])
        logs.append(rec)
        return data
    mixed = call('mixed')
    assert [len(c['record_ids']) for c in mixed['catalogs']] == [6,11] and 'source_index_sha256' not in mixed
    rows = mixed['records']
    assert [r['status'] for r in rows] == ['qualified','qualified','reference_unavailable','qualified','reference_unavailable']
    assert rows[0]['catalog'] != rows[1]['catalog'] and rows[0]['source_attempt'] == rows[3]['source_attempt']
    assert rows[3]['delivery']=='same_batch_duplicate' and len(mixed['work'])==2
    for row, pair in zip(rows[:2], SETS, strict=True):
        assert row['catalog'] == {'source_index_sha256':sha(pair[0]), 'oracle_index_sha256':sha(pair[1])}
        oracle = json.loads((pair[1].parent/row['source']['oracle_file']).read_bytes())
        r=row['request']; assert abs(row['value'] - oracle['targets'][r['field']][r['observable']]['direct'])<=1e-8
    replay = call('mixed-replay')
    assert all(w['scalar_hits']==1 and not w['model_started'] for w in replay['work'])
    transferred = call('mixed-history', history=work/'mixed.json', database='mixed-transfer')
    assert all(w['historical_hits']==1 and not w['model_started'] for w in transferred['work'])
    for i, pair in enumerate(SETS):
        one = call(f'explicit-{i}', pair=pair)
        assert len(one['catalogs']) == 1 and one['records'][i]['status']=='qualified'
        assert one['records'][1-i]['status']=='record_not_indexed' and not one['work'][0]['model_started']
    # Recover the byte-exact original eaa6def receipt from the committed QA archive.
    initial = json.loads(gzip.decompress((HERE/'client-results.json.gz').read_bytes()))['first']
    old = work/'original-first-batch.json'
    old.write_text(json.dumps(initial,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    measured_hash = next(r['result_sha256'] for r in json.loads((HERE/'verification.json').read_bytes())['processes']
                         if r['client']=='first')
    assert sha(old) == measured_hash and 'catalogs' not in initial
    legacy = call('legacy-history', history=old, database='old-external')
    assert legacy['records'][0]['delivery']=='historical_scalar' and not legacy['work'][0]['model_started']
    assert legacy['records'][1]['delivery']=='computed'
    # Exercise the real former executable in a new database. Only its one-file
    # script is checked out; the dependencies and reference data stay by the repository.
    code = subprocess.check_output(['git','show','dbfde3e:scripts/complete_response_dataset.py'], cwd=ROOT)
    previous = work/'legacy_cli.py'
    previous.write_bytes(code)
    # The script imports the same model and paths via the repository's scripts directory.
    import os
    os.environ['PYTHONPATH'] = str(ROOT/'scripts')
    generated = call('old-executable',requests=HERE/'hit.jsonl',database='legacy-sqlite',code=0,script=previous)
    hit = call('new-executable-old-sqlite', requests=HERE/'hit.jsonl', database='legacy-sqlite',code=0)
    assert hit['records'][0]['source_attempt']==generated['records'][0]['source_attempt'] and not hit['work'][0]['model_started']
    # A mislabeled row of an otherwise authenticated mixed file is not an operand.
    foreign = json.loads((work/'mixed.json').read_bytes())
    foreign['records'][0]['catalog'] = foreign['records'][1]['catalog']
    altered=work/'misbound.json';altered.write_text(json.dumps(foreign))
    recovered=call('disagreeing-catalog',history=altered,database='misbound')
    assert len(recovered['history']['excluded_catalog_records'])==1 and recovered['records'][0]['delivery']=='computed'
    assert recovered['records'][1]['delivery']=='historical_scalar'
    # Route every ID through its real source without requesting an additional calculation.
    names = [name for cat in mixed['catalogs'] for name in cat['record_ids']]
    probes=work/'all17.jsonl';probes.write_text(''.join(json.dumps({'source':SOURCE,'record_id':n,'field':'z','observable':'r2',
                       'expected_problem_identity':'deliberately-different'})+'\n' for n in names))
    routes=call('all-record-identity-check',requests=probes)
    assert len(set(names))==17 and len(routes['records'])==17 and not routes['work']
    assert routes['counts_by_status']=={'reference_unavailable':5,'problem_mismatch':12}
    assert not call('crossed-source-oracle-index',pair=(SETS[0][0],SETS[1][1]),code=2)
    result={'passed':True,'cli_sha256':sha(ROOT/'scripts/complete_response_dataset.py'),
            'prior_immutable_batch_sha256':sha(old),'first_records':rows,'catalogs':mixed['catalogs'],'clients':logs}
    (work/'verification.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('passed',len(logs),'clients with actual mixed-lot computation, v1 archive and SQLite reuse')


if __name__ == '__main__':
    main()
