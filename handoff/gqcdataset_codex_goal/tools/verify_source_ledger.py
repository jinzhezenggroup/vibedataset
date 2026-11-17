#!/usr/bin/env python3
"""Check complete coverage, immutable evidence hashes and manual status provenance."""
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path('handoff/gqcdataset_codex_goal')


def files(inv, prefix=''):
    for file in inv['files']:
        yield inv['commit'], prefix + file['path'], file
    for submodule in inv['submodules']:
        if 'inventory' in submodule:
            yield from files(submodule['inventory'], prefix + submodule['path'] + '/')


def main():
    lock_path = BASE / 'research/sources.lock.json'
    lock = json.loads(lock_path.read_text())
    plan = json.loads((BASE / 'research/acquisition_plan.json').read_text())
    locked = {s['id']: s for s in lock['repositories']}
    assert set(locked) == {s['id'] for s in plan['repositories']}
    for source in plan['repositories']:
        if source.get('commit') and locked[source['id']].get('inventory_path'):
            assert source['commit'] == locked[source['id']]['commit'], source['id']
    review = json.loads((BASE / 'research/intake_review.json').read_text())
    manual = {(r['repository_id'],r['path']):r for r in review['file_reading']}
    assert len(manual) == len(review['file_reading']), 'duplicate review'
    expected = {}
    by_source = {}
    for source in lock['repositories']:
        if not source.get('inventory_path'):
            continue
        path = BASE / source['inventory_path']
        packed = path.read_bytes()
        assert hashlib.sha256(packed).hexdigest() == source['inventory_sha256'], path
        unpacked = gzip.decompress(packed)
        assert hashlib.sha256(unpacked).hexdigest() == source['inventory_uncompressed_sha256'], path
        inv = json.loads(unpacked)['inventory']
        assert inv['commit'] == source['commit'] and inv['tree'] == source['tree']
        conversions = review['repositories'].get(source['id'],{}).get('reviewed_checkout_conversions',{})
        for name, record in conversions.items():
            data = (Path(source['checkout_path']) / name).read_bytes()
            blob = subprocess.check_output(['git','-C',source['checkout_path'],
                                            'cat-file','blob',record['commit_object_id']])
            attr = subprocess.check_output(['git','-C',source['checkout_path'],
                                            'check-attr','eol','--',name],text=True)
            assert attr.rstrip().endswith(': eol: crlf')
            assert record['kind']=='git_eol_crlf' and record['verified_lf_to_crlf'] is True
            assert data == blob.replace(b'\n',b'\r\n')
            assert hashlib.sha256(data).hexdigest() == record['worktree_sha256']
        if source['acquisition_status'] == 'acquired':
            assert not inv['dirty']
            assert all(b['path'] in conversions and b['reason'].startswith('worktree differs from pinned blob')
                       for b in inv['acquisition_blockers'])
            assert review['repositories'][source['id']]['commit'] == source['commit']
        actual = subprocess.check_output(['git','-C',source['checkout_path'],
                                          'rev-parse','HEAD','HEAD^{tree}'],text=True).splitlines()
        assert actual == [source['commit'],source['tree']], source['id']
        if source.get('include_tag_history'):
            assert source['history_scope'] == 'full'
            assert subprocess.check_output(['git', '-C', source['checkout_path'], 'rev-parse',
                                             '--is-shallow-repository'], text=True).strip() == 'false'
            subprocess.check_output(['git', '-C', source['checkout_path'], 'describe',
                                     '--tags', '--match', 'v*', '--abbrev=0'])
        assert not subprocess.check_output(['git','-C',source['checkout_path'],
                                             'status','--porcelain'],text=True), source['id']
        by_source[source['id']] = dict(read=0, behavior_traced=0, executed=0)
        for commit, name, file in files(inv):
            key = (source['id'],name)
            assert key not in expected, key
            expected[key] = (commit,file,conversions.get(name))
    coverage_path = BASE / 'research/source_coverage.csv'
    seen = set()
    counters = dict(indexed=0,read=0,behavior_traced=0,executed=0)
    with coverage_path.open(newline='') as handle:
        for row in csv.DictReader(handle):
            key = (row['repository_id'],row['path'])
            assert key not in seen and key in expected, key
            seen.add(key)
            commit,file,conversion = expected[key]
            assert commit == row['commit']
            valid = file['present'] and (file['lfs']['hydrated'] if file['lfs'] else
                    file['worktree_matches_commit_blob'] or bool(conversion and
                    conversion['commit_object_id']==file['commit_object_id'] and
                    conversion['worktree_sha256']==file['worktree_sha256']))
            assert row['acquired'] == str(valid), key
            assert row['indexed'] == 'True', key
            counters['indexed'] += 1
            if key in manual:
                assert manual[key]['blob'] == file['commit_object_id'], key
                assert (BASE / row['evidence_paths']).is_file(), key
            for status in ('read','behavior_traced','executed'):
                assert row[status] == str(manual.get(key,{}).get(status,False)), (key,status)
                if row[status] == 'True':
                    assert manual[key]['blob'] == file['commit_object_id']
                    assert row['reader'] and row['read_at'] and row['evidence_paths']
                    counters[status] += 1
                    by_source[row['repository_id']][status] += 1
    assert seen == set(expected)
    assert set(manual) <= seen, 'orphan review'
    assert counters['indexed'] == lock['summary']['files_indexed']
    for status, field in [('read', 'files_read'), ('behavior_traced', 'behavior_traced'), ('executed', 'executed')]:
        assert counters[status] == lock['summary'][field], field
        for source in lock['repositories']:
            if source['id'] in by_source:
                assert by_source[source['id']][status] == source['evidence_status'][field], (source['id'], field)
    report = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  result='passed', coverage_counts=counters,
                  source_lock_sha256=hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                  source_coverage_sha256=hashlib.sha256(coverage_path.read_bytes()).hexdigest(),
                  checks=['inventory gzip and SHA256 round-trip','lock vs checkout commit/tree and clean state',
                          'exact full-tree coverage including submodule commits','no duplicate or missing paths',
                          'reviewed CRLF conversions verified against pinned blobs and Git attributes',
                          'read/traced/executed flags backed by explicit blob-bound reviewer records'],
                  scope='Ledger consistency only; no third-party behavior or numerical validation.')
    (BASE / 'research/ledger_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
