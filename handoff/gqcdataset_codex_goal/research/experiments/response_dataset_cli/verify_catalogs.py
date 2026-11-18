#!/usr/bin/env python3
"""Check multi-catalog routing, measured mixed requests, and v1 provenance compatibility."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EXPERIMENTS = HERE.parent
SOURCE = 'https://api.figshare.com/v2/articles/1057646/versions/2'
LEGACY_COMMIT = 'dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a'
sys.path.insert(0, str(ROOT / 'scripts'))
from complete_response_dataset import DEFAULT_CATALOGS


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
    for row, pair in zip(rows[:2], DEFAULT_CATALOGS, strict=True):
        assert row['catalog'] == {'source_index_sha256':sha(pair[0]), 'oracle_index_sha256':sha(pair[1])}
        oracle = json.loads((pair[1].parent/row['source']['oracle_file']).read_bytes())
        r=row['request']; assert abs(row['value'] - oracle['targets'][r['field']][r['observable']]['direct'])<=1e-8
    replay = call('mixed-replay')
    assert all(w['scalar_hits']==1 and not w['model_started'] for w in replay['work'])
    transferred = call('mixed-history', history=work/'mixed.json', database='mixed-transfer')
    assert all(w['historical_hits']==1 and not w['model_started'] for w in transferred['work'])
    for i, pair in enumerate(DEFAULT_CATALOGS):
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
    assert all(w['historical_hits'] == 0 and w['model_started'] for w in legacy['work'])
    assert [r['delivery'] for r in legacy['records'][:2]] == ['computed', 'computed']
    # Reproduce the former executable with its own solver/grader source. Shallow
    # PR clones need exactly this extra historical object from the public project.
    known = subprocess.run(['git', 'cat-file', '-e', LEGACY_COMMIT + '^{commit}'], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if known.returncode:
        subprocess.run(['git', 'fetch', '--no-tags', '--depth=1', 'https://github.com/jinzhezenggroup/vibedataset.git',
                        LEGACY_COMMIT], check=True, cwd=ROOT)
    snapshot = subprocess.check_output(['git', 'archive', '--format=tar', LEGACY_COMMIT, 'scripts'], cwd=ROOT)
    with tempfile.TemporaryDirectory(dir=work) as temp:
        prior_tree = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(snapshot)) as archive:
            archive.extractall(prior_tree, filter='data')
        for name in ('_references', 'handoff'):
            (prior_tree / name).symlink_to(ROOT / name, target_is_directory=True)
        generated = call('old-executable', requests=HERE/'hit.jsonl', database='legacy-sqlite',
                         code=0, script=prior_tree/'scripts/complete_response_dataset.py')
    hit = call('new-executable-old-sqlite', requests=HERE/'hit.jsonl', database='legacy-sqlite', code=0)
    assert generated['work'][0]['identity'] != hit['work'][0]['identity']
    assert hit['records'][0]['source_attempt'] != generated['records'][0]['source_attempt']
    assert hit['records'][0]['delivery'] == 'computed' and hit['work'][0]['model_started']
    v2_hit = call('new-executable-reopen', requests=HERE/'hit.jsonl', database='legacy-sqlite', code=0)
    assert v2_hit['records'][0]['source_attempt'] == hit['records'][0]['source_attempt']
    assert v2_hit['work'][0]['scalar_hits'] == 1 and not v2_hit['work'][0]['model_started']
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
    assert not call('crossed-source-oracle-index',pair=(DEFAULT_CATALOGS[0][0],DEFAULT_CATALOGS[1][1]),code=2)
    result={'passed':True,'cli_sha256':sha(ROOT/'scripts/complete_response_dataset.py'),
            'legacy_commit':LEGACY_COMMIT, 'prior_immutable_batch_sha256':sha(old),'first_records':rows,'catalogs':mixed['catalogs'],'clients':logs}
    (work/'verification.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('passed',len(logs),'clients with actual mixed-lot computation, v1/v2 isolation and fresh SQLite reuse')


if __name__ == '__main__':
    main()
