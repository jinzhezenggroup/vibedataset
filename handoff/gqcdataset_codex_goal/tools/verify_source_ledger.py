#!/usr/bin/env python3
"""Check complete coverage, immutable evidence hashes and manual status provenance."""
import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

BASE = Path('handoff/gqcdataset_codex_goal')


def files(inv, prefix=''):
    for file in inv['files']:
        yield inv['commit'], prefix + file['path'], file
    for submodule in inv['submodules']:
        if 'inventory' in submodule:
            yield from files(submodule['inventory'], prefix + submodule['path'] + '/')


def verify_git_tree(checkout, inv):
    """Compare archived paths, modes and blob IDs to Git, including every pinned submodule."""
    raw = subprocess.check_output(['git', '-C', str(checkout), 'ls-tree', '-rz', '--full-tree', inv['commit']])
    actual = {}
    for entry in raw.split(b'\0'):
        if entry:
            meta, path = entry.split(b'\t', 1)
            actual[os.fsdecode(path)] = tuple(meta.decode('ascii').split())
    recorded = {item['path']: (item['mode'], item['git_type'], item['commit_object_id'])
                for item in (*inv['files'], *inv['submodules'])}
    assert len(recorded) == len(inv['files']) + len(inv['submodules']), checkout
    assert actual == recorded, f'pinned tree differs from inventory: {checkout}'
    for child in inv['submodules']:
        if 'inventory' in child:
            path = checkout / child['path']
            child_inv = child['inventory']
            assert child['commit_object_id'] == child_inv['commit']
            identity = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD', 'HEAD^{tree}'], text=True)
            assert identity.splitlines() == [child_inv['commit'], child_inv['tree']], path
            assert not subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain']), path
            verify_git_tree(path, child_inv)


def evidence_file(relative):
    path = Path(relative)
    assert relative and not path.is_absolute() and '..' not in path.parts, relative
    assert (BASE / path).is_file(), relative
    return BASE / path


def verify_archive(archive, source, raw_path):
    receipt_bytes = evidence_file(archive['inspection_path']).read_bytes()
    assert hashlib.sha256(receipt_bytes).hexdigest() == archive['inspection_sha256']
    receipt = json.loads(receipt_bytes)
    for lock_name, field in [('archive_bytes','archive_bytes'), ('archive_sha256','sha256'), ('publisher_md5','md5'),
                             ('doi','doi'), ('version','version'), ('rights','rights'), ('archive_url','archive_url'),
                             ('publication_date','publication_date'), ('related_identifiers','related_identifiers')]:
        assert archive[lock_name] == receipt[field], (archive['id'], lock_name)
    assert source['commit'] == archive['selected_branch_commit'] == receipt['paper_branch_commit']
    assert source['tree'] == archive['selected_branch_tree'] == receipt['paper_branch_tree']
    packed = evidence_file(archive['member_index_path']).read_bytes()
    unpacked = gzip.decompress(packed)
    assert hashlib.sha256(packed).hexdigest() == archive['index_sha256'] == receipt['member_index_gzip_sha256']
    assert hashlib.sha256(unpacked).hexdigest() == archive['index_uncompressed_sha256'] == receipt['member_index_uncompressed_sha256']
    entries = json.loads(unpacked)
    members = {m['name']: m for m in entries}
    assert len(members) == len(entries), 'duplicate release member'
    for name, m in members.items():
        path = PurePosixPath(name)
        assert name and not path.is_absolute() and '..' not in path.parts and m['type'] in ('0','5')
        assert m['bytes'] >= 0 and (m['type'] == '5' or len(bytes.fromhex(m['sha256'])) == 32)
    assert sum(m['type'] == '0' for m in entries) == archive['regular_files'] == receipt['regular_files']
    assert sum(m['type'] == '5' for m in entries) == archive['directories'] == receipt['directories']
    assert sum(m['bytes'] for m in entries) == archive['total_file_bytes'] == receipt['total_file_bytes']
    assert len(receipt['source_members']) == archive['source_like_members']
    for item in receipt['source_members']:
        assert members[item['name']]['sha256'] == item['sha256']
        for path in item['identical_in_qm7']:
            oid = subprocess.check_output(['git','-C',source['checkout_path'],'rev-parse',source['commit']+':'+path],text=True).strip()
            assert item['git_blob'] == oid, path
    if raw_path:
        assert raw_path.stat().st_size == archive['archive_bytes']
        sha, md5 = hashlib.sha256(), hashlib.md5()
        with raw_path.open('rb') as f:
            for chunk in iter(lambda: f.read(4*1024**2), b''):
                sha.update(chunk)
                md5.update(chunk)
        assert sha.hexdigest() == archive['archive_sha256'] and md5.hexdigest() == archive['publisher_md5']
        seen = set()
        with tarfile.open(raw_path, 'r|xz') as f:
            for item in f:
                name = str(PurePosixPath(item.name))
                m = members[name]
                assert name not in seen and m['type'] == item.type.decode() and item.size == m['bytes'], name
                seen.add(name)
                if item.isfile():
                    digest = hashlib.sha256()
                    with f.extractfile(item) as stream:
                        for chunk in iter(lambda: stream.read(4*1024**2), b''):
                            digest.update(chunk)
                    assert digest.hexdigest() == m['sha256'], name
        assert seen == set(members)
    return members


def compare_replay(root, report, lock):
    """Compare the published artifacts to a separate checkout rebuilt from compressed inventories."""
    replay = root / BASE / 'research'
    assert not any((replay / 'inventories').glob('*.json')), 'replay used raw machine-local inventories'
    other = json.loads((replay / 'ledger_validation.json').read_text())
    assert other['result'] == 'passed'
    for field in ('coverage_counts', 'reviewer_observations', 'reviewed_paths', 'unique_claims',
                  'catalog_original_source_locations_blocked'):
        assert report[field] == other[field], ('replay validation', field)
    for field, name in [('source_review_sha256', 'intake_review.json'), ('claims_sha256', 'claims.csv'),
                        ('source_lock_sha256', 'sources.lock.json'), ('source_coverage_sha256', 'source_coverage.csv')]:
        assert report[field] == other[field] == hashlib.sha256((replay / name).read_bytes()).hexdigest(), name
    pins = [s for s in lock['repositories'] if s.get('inventory_path')]
    for item in pins:
        assert hashlib.sha256((root / BASE / item['inventory_path']).read_bytes()).hexdigest() == item['inventory_sha256']
    for item in lock.get('release_archives', []):
        assert hashlib.sha256((root / BASE / item['member_index_path']).read_bytes()).hexdigest() == item['index_sha256']
    paths = [str(BASE / 'research' / n) for n in ('acquisition_plan.json','intake_review.json','sources.lock.json',
                                                 'source_coverage.csv','claims.csv','inventories')]
    paths.extend(str(BASE / a['member_index_path']) for a in lock.get('release_archives', []))
    subprocess.run(['git','-C',str(root),'diff','--exit-code','--quiet','HEAD','--',*paths], check=True)
    return dict(result='identical', repository_commit=subprocess.check_output(
                    ['git','-C',str(root),'rev-parse','HEAD'], text=True).strip(),
                git_inventories=len(pins), release_member_inventories=len(lock.get('release_archives', [])),
                local_uncompressed_inventories=0, replay_validated_at_utc=other['checked_at_utc'],
                scope='Separate checkout and compressed-only ledger rebuild, sharing verified third-party checkouts.')


def main():
    if not __debug__:
        raise RuntimeError('Verification requires Python assertions enabled.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', nargs=2, metavar=('ID','LOCAL_TAR_XZ'), action='append', default=[],
                        help='also rehash the original release bytes and every regular tar member')
    parser.add_argument('--compare-replay', type=Path, metavar='CHECKOUT',
                        help='compare a separately rebuilt and verified compressed-only checkout')
    args = parser.parse_args()
    raw_inputs = dict(args.archive)
    assert len(raw_inputs) == len(args.archive), 'duplicate archive ID'
    lock_path = BASE / 'research/sources.lock.json'
    lock = json.loads(lock_path.read_text())
    plan = json.loads((BASE / 'research/acquisition_plan.json').read_text())
    locked = {s['id']: s for s in lock['repositories']}
    assert len(locked) == len(lock['repositories']) == len(plan['repositories'])
    assert set(locked) == {s['id'] for s in plan['repositories']}
    for source in plan['repositories']:
        if source.get('commit') and locked[source['id']].get('inventory_path'):
            assert source['commit'] == locked[source['id']]['commit'], source['id']
    review = json.loads((BASE / 'research/intake_review.json').read_text())
    manual = defaultdict(list)
    observations = set()
    for record in review['file_reading']:
        signature = json.dumps(record, sort_keys=True)
        assert signature not in observations, 'duplicate observation'
        observations.add(signature)
        assert record['reader'] and record['read_at'] and record['module_role']
        datetime.fromisoformat(record['read_at'].replace('Z', '+00:00'))
        evidence_file(record['evidence_paths'])
        for status in ('read','behavior_traced','executed'):
            assert isinstance(record.get(status, False), bool), (record['path'], status)
        manual[(record['repository_id'],record['path'])].append(record)
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
            assert source['reviewer_record'] == review['repositories'][source['id']]
        actual = subprocess.check_output(['git','-C',source['checkout_path'],
                                          'rev-parse','HEAD','HEAD^{tree}'],text=True).splitlines()
        assert actual == [source['commit'],source['tree']], source['id']
        verify_git_tree(Path(source['checkout_path']), inv)
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
                records = manual[key]
                assert all(r['blob'] == file['commit_object_id'] for r in records), key
                paths = list(dict.fromkeys(r['evidence_paths'] for r in records))
                expected_paths = paths[0] if len(paths) == 1 else json.dumps(paths, ensure_ascii=False)
                assert row['evidence_paths'] == expected_paths, key
                for field in ('reader','module_role','open_questions'):
                    assert row[field] == ' | '.join(dict.fromkeys(r[field] for r in records)), (key, field)
                assert row['read_at'] == max(r['read_at'] for r in records), key
            else:
                assert not row['reader'] and not row['read_at'] and not row['evidence_paths'], key
            for status in ('read','behavior_traced','executed'):
                assert row[status] == str(any(r.get(status,False) for r in manual.get(key, []))), (key,status)
                if row[status] == 'True':
                    assert row['reader'] and row['read_at'] and row['evidence_paths']
                    counters[status] += 1
                    by_source[row['repository_id']][status] += 1
    assert seen == set(expected)
    assert set(manual) <= seen, 'orphan review'
    assert len(by_source) == lock['summary']['repositories_indexed']
    catalogs = json.loads((BASE / 'sources/catalog.json').read_text())['entries']
    originals = {r['id']:r for r in lock['catalog_origin_results']}
    assert set(originals) == {s['id'] for s in catalogs if not s['repository_url']}
    assert lock['unresolved_catalog_entries'] == [v for v in originals.values() if not v['commit']]
    for id, row in originals.items():
        declared = review.get('catalog_origin_reviews',{}).get(id,{})
        assert all(row[k] == v for k,v in declared.items())
        evidence_file(row['evidence'])
        evidence_file(row['acquisition_evidence'])
        assert row['reason'] and row['next_step'] and row['paper_commit'] is None
        assert all(other in locked for other in row.get('other_repository_ids', []))
        if row.get('historical_author_repository'):
            repo = locked[row['historical_author_repository']]
            assert id in repo['catalog_ids'] and repo['commit'] == row['commit'] and repo['acquisition_status'] == 'acquired'
        else:
            assert row['commit'] is None and row['acquisition_status'] == 'blocked_source_location'
    archives = {a['id']:a for a in lock.get('release_archives', [])}
    assert set(archives) == {a['id'] for a in plan.get('release_archives', [])}
    assert set(raw_inputs) <= set(archives), 'unrecognized archive ID'
    archive_indexes = {}
    archive_reviews = review.get('release_archive_reviews', {})
    assert set(archive_reviews) <= set(archives)
    for declared in plan.get('release_archives', []):
        id = declared['id']
        archive = archives[id]
        assert all(archive[k] == v for k,v in declared.items())
        archive_indexes[id] = verify_archive(archive, locked[archive['repository_id']],
                                             Path(raw_inputs[id]) if id in raw_inputs else None)
        packet = archive_reviews.get(id, {})
        observations_for_archive = packet.get('archive_file_reading', [])
        if packet:
            assert packet['repository_id'] == id and packet['release_id'] == archive['record_id']
            for field in ('doi','version','publication_date','archive_url','archive_sha256',
                          'archive_bytes','publisher_md5','regular_files','directories'):
                assert packet[field] == archive[field], (id, field)
            assert packet['tree_summary_path'] == archive['inspection_path']
            assert packet['member_inventory_path'] == archive['member_index_path']
            assert packet['tree_summary_sha256'] == archive['inspection_sha256']
            assert packet['member_inventory_uncompressed_sha256'] == archive['index_uncompressed_sha256']
            assert packet['member_inventory_gzip_sha256'] == archive['index_sha256']
            assert packet['github_linked_checkout'] == archive['repository_id']
            assert packet['members'] == len(archive_indexes[id])
            assert packet['total_uncompressed_regular_bytes'] == archive['total_file_bytes']
            for field in ('receipts_path','result_path','readme_path'):
                evidence_file(packet[field])
            assert len({r['path'] for r in observations_for_archive}) == len(observations_for_archive)
            for record in observations_for_archive:
                assert archive_indexes[id][record['path']]['sha256'] == record['sha256']
                assert record['role'] and record['evidence_paths']
                for relative in record['evidence_paths']:
                    evidence_file(relative)
                assert all(isinstance(record.get(s), bool) for s in ('read','behavior_traced','executed'))
        for status in ('read','behavior_traced','executed'):
            assert sum(r[status] for r in observations_for_archive) == archive['evidence_status'][status]
    claims_path = BASE / 'research/claims.csv'
    claim_ids = set()
    with claims_path.open(newline='') as f:
        for claim in csv.DictReader(f):
            id, repo, path = claim['claim_id'], claim['repository_id'], claim['source_path']
            assert id and id not in claim_ids and path and claim['symbol'], id
            claim_ids.add(id)
            if repo in archives:
                assert claim['commit'] == archives[repo]['archive_sha256'] and path in archive_indexes[repo], id
            elif repo in locked:
                assert (repo,path) in expected and expected[repo, path][0] == claim['commit'], id
            else:
                assert repo == 'vibedataset' and len(claim['commit']) == 40, id
                assert subprocess.check_output(['git','cat-file','-t',claim['commit']+':'+path]).strip() == b'blob', id
    assert counters['indexed'] == lock['summary']['files_indexed']
    for status, field in [('read', 'files_read'), ('behavior_traced', 'behavior_traced'), ('executed', 'executed')]:
        assert counters[status] == lock['summary'][field], field
        for source in lock['repositories']:
            if source['id'] in by_source:
                assert by_source[source['id']][status] == source['evidence_status'][field], (source['id'], field)
    report = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  result='passed', coverage_counts=counters,
                  reviewer_observations=len(observations), reviewed_paths=len(manual), unique_claims=len(claim_ids),
                  catalog_original_source_locations_blocked=len(lock['unresolved_catalog_entries']),
                  release_archives={k:{'indexed_members':len(v), 'bytes_and_members_rechecked':k in raw_inputs}
                                    for k,v in archive_indexes.items()},
                  source_review_sha256=hashlib.sha256((BASE/'research/intake_review.json').read_bytes()).hexdigest(),
                  claims_sha256=hashlib.sha256(claims_path.read_bytes()).hexdigest(),
                  source_lock_sha256=hashlib.sha256(lock_path.read_bytes()).hexdigest(),
                  source_coverage_sha256=hashlib.sha256(coverage_path.read_bytes()).hexdigest(),
                  checks=['inventory gzip and SHA256 round-trip','lock vs checkout commit/tree and clean state',
                          'git ls-tree path/mode/object equality for roots and initialized submodule commits','no duplicate or missing paths',
                          'reviewed CRLF conversions verified against pinned blobs and Git attributes',
                          'each dated evidence path and aggregated file flag matches its blob-bound observations',
                          'all claim source paths and snapshot IDs resolve', 'catalog origin evidence and formal release archive inventories verified'],
                  scope='Ledger consistency only; no third-party behavior or numerical validation.')
    if args.compare_replay:
        assert args.compare_replay.resolve() != Path.cwd().resolve(), 'a separate git checkout is required'
        report['compressed_only_replay'] = compare_replay(args.compare_replay, report, lock)
    (BASE / 'research/ledger_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
