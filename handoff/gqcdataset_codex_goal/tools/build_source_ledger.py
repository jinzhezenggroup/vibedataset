#!/usr/bin/env python3
"""Join inventory facts with explicit reviewer records; never infer reading.

Run from the project root. Raw JSON inventories remain local. Compressed JSON
preserves the complete index; path redaction is documented in its notice.
"""
import csv
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path('handoff/gqcdataset_codex_goal')
RESEARCH = BASE / 'research'


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def flatten(inv, prefix=''):
    for file in inv['files']:
        yield inv['commit'], prefix + file['path'], file
    for child in inv['submodules']:
        if 'inventory' in child:
            yield from flatten(child['inventory'], prefix + child['path'] + '/')


def redact_paths(inv):
    path = Path(inv['repository_path'])
    if path.is_absolute():
        inv['repository_path'] = str(path.relative_to(Path.cwd()))
    for child in inv['submodules']:
        if 'inventory' in child:
            redact_paths(child['inventory'])


def crlf_review_matches(file, record):
    return bool(record and record.get('kind') == 'git_eol_crlf'
                and record.get('commit_object_id') == file['commit_object_id']
                and record.get('worktree_sha256') == file.get('worktree_sha256')
                and record.get('verified_lf_to_crlf') is True)


def combine_reviews(records, blob):
    """One coverage row per tracked file. Each dated observation stays in intake_review.json."""
    if not records:
        return {}
    if any(r['blob'] != blob for r in records):
        raise ValueError(f'stale file review for {records[0]["repository_id"]}/{records[0]["path"]}')
    result = {key: any(r.get(key, False) for r in records) for key in ('read', 'behavior_traced', 'executed')}
    # Preserve a single path verbatim for old CSV readers. Multiple paths use an unambiguous JSON array.
    paths = list(dict.fromkeys(r['evidence_paths'] for r in records))
    result['evidence_paths'] = paths[0] if len(paths) == 1 else json.dumps(paths, ensure_ascii=False)
    result['read_at'] = max(r['read_at'] for r in records)
    for key in ('module_role', 'reader', 'open_questions'):
        result[key] = ' | '.join(dict.fromkeys(r[key] for r in records))
    return result


def archive_lock(source, review):
    receipt_path = BASE / source['inspection_path']
    raw = receipt_path.read_bytes()
    receipt = json.loads(raw)
    for lock_name, receipt_name in [('doi', 'doi'), ('version', 'version'), ('archive_sha256', 'sha256'),
                                     ('publisher_md5', 'md5'), ('archive_bytes', 'archive_bytes')]:
        if source[lock_name] != receipt[receipt_name]:
            raise ValueError(f'{source["id"]}: published archive identity differs at {lock_name}')
    observations = review.get('archive_file_reading', [])
    statuses = {key: sum(r[key] for r in observations) for key in ('read', 'behavior_traced', 'executed')}
    return dict(source, archive_url=receipt['archive_url'], rights=receipt['rights'],
                publication_date=receipt['publication_date'], related_identifiers=receipt['related_identifiers'],
                selected_branch_commit=receipt['paper_branch_commit'], selected_branch_tree=receipt['paper_branch_tree'],
                inspection_sha256=hashlib.sha256(raw).hexdigest(),
                index_sha256=receipt['member_index_gzip_sha256'],
                index_uncompressed_sha256=receipt['member_index_uncompressed_sha256'],
                regular_files=receipt['regular_files'], directories=receipt['directories'],
                total_file_bytes=receipt['total_file_bytes'], source_like_members=len(receipt['source_members']),
                reviewer_record='research/intake_review.json', evidence_status=statuses)


def main():
    plan = json.loads((RESEARCH / 'acquisition_plan.json').read_text())
    review = json.loads((RESEARCH / 'intake_review.json').read_text())
    records = review['repositories']
    old_lock = RESEARCH / 'sources.lock.json'
    previous = {r['id']: r for r in json.loads(old_lock.read_text())['repositories']} if old_lock.exists() else {}
    read_records = defaultdict(list)
    for record in review['file_reading']:
        read_records[(record['repository_id'], record['path'])].append(record)
    template = json.loads((BASE / 'templates/sources.lock.json').read_text())
    template.update(notice='Git snapshot counts include initialized submodules. Formal release archives '
                    'have separate file/member hashes. Reading, execution, paper-version attribution, '
                    'and external runtime closure are independent.',
                    generated_at_utc=review.get('reconciled_at_utc') or datetime.now(timezone.utc).isoformat())
    coverage_fields = (BASE / 'templates/source_coverage.csv').read_text().strip().split(',')
    totals = dict(repositories_indexed=0, files_indexed=0, files_read=0,
                  behavior_traced=0, executed=0)
    with (RESEARCH / 'source_coverage.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=coverage_fields, lineterminator='\n')
        writer.writeheader()
        for source in plan['repositories']:
            name = source['id']
            raw_path = RESEARCH / 'inventories' / f'{name}.json'
            archived = raw_path.with_suffix('.json.gz')
            item = dict(source)
            receipts = sorted((RESEARCH / 'acquisition').glob(f'{name}-[0-9]*.json'))
            item['acquisition_receipts'] = [str(p.relative_to(BASE)) for p in receipts]
            if not raw_path.exists() and not archived.exists():
                item.update(acquisition_status='not_acquired', inventory_path=None)
                if receipts:
                    receipt = json.loads(receipts[-1].read_text())
                    item.update(commit=receipt.get('resolved_commit'),
                                acquisition_status=receipt['status'],
                                known_gaps=[receipt.get('error', 'acquisition not finished')])
                template['repositories'].append(item)
                continue
            if raw_path.exists():
                doc = json.loads(raw_path.read_text())
            else:
                packed = archived.read_bytes()
                if hashlib.sha256(packed).hexdigest() != previous.get(name, {}).get('inventory_sha256'):
                    raise ValueError(f'{name}: archived inventory does not match the published lock')
                doc = json.loads(gzip.decompress(packed))
            inv = doc['inventory']
            if source.get('commit') and source['commit'] != inv['commit']:
                raise ValueError(f'{name}: inventory does not match the selected source version')
            inspected = records.get(name, {})
            approved = inspected.get('root_tree_reviewed', False)
            if approved and inspected.get('commit') != inv['commit']:
                raise ValueError(f'{name}: stale root-tree review')
            conversions = inspected.get('reviewed_checkout_conversions', {})
            accepted_conversions = {f['path'] for f in inv['files']
                                    if crlf_review_matches(f, conversions.get(f['path']))}
            unresolved = [b for b in inv['acquisition_blockers'] if not
                          (b['path'] in accepted_conversions and b['reason'].startswith('worktree differs from pinned blob'))]
            if approved and unresolved:
                raise ValueError(f'{name}: review cannot override integrity blockers')
            redact_paths(inv)
            doc['path_normalization'] = 'repository_path made relative to vibedataset root; no file facts changed'
            encoded = (json.dumps(doc, ensure_ascii=True, indent=2) + '\n').encode()
            compressed = archived.read_bytes() if archived.exists() else b''
            if not compressed or gzip.decompress(compressed) != encoded:
                compressed = gzip.compress(encoded, mtime=0)
                assert gzip.decompress(compressed) == encoded
                archived.write_bytes(compressed)
            files = list(flatten(inv))
            root_paths = [f['path'] for f in inv['files']]
            license_paths = [p for p in root_paths if
                             Path(p).name.lower().startswith(('license', 'copying', 'copyright'))
                             or 'NOTICE' in Path(p).name or 'EXCEPTION' in Path(p).name]
            item.update(commit=inv['commit'], tree=inv['tree'],
                        retrieved_at_utc=doc['created_at_utc'],
                        checkout_kind='full-tree' if not unresolved else 'partial',
                        history_scope=subprocess.check_output(['git', '-C', source['checkout_path'],
                                       'rev-parse', '--is-shallow-repository'], text=True).strip(),
                        license={'paths': license_paths, 'interpretation': inspected.get('license_note',
                                 'License files located; no redistribution or legal interpretation claimed.')},
                        inventory_path=str(archived.relative_to(BASE)),
                        inventory_sha256=hashlib.sha256(compressed).hexdigest(),
                        inventory_uncompressed_sha256=hashlib.sha256(encoded).hexdigest(),
                        submodules=[{k:v for k,v in c.items() if k != 'inventory'} for c in inv['submodules']],
                        lfs={'pointer_count': sum(bool(f['lfs']) for _,_,f in files),
                             'unhydrated_count': sum(bool(f['lfs']) and not f['lfs']['hydrated'] for _,_,f in files)},
                        acquisition_status='acquired' if approved else 'indexed_pending_review',
                        acquisition_scope='Complete pinned tracked trees including initialized submodules; '
                                          'not all build dependencies, paper supplements, datasets or weights.',
                        reviewer_record=inspected, file_count=len(files),
                        top_level_directories=sorted({p.split('/')[0] for p in root_paths if '/' in p}),
                        build_and_dependency_metadata=[p for p in root_paths if '/' not in p and any(
                            q in p.lower() for q in ('cmake','meson','setup','pyproject','requirements','makefile','environment','lock'))],
                        reviewed_integrity_notices=inv['acquisition_blockers'] if accepted_conversions else [],
                        known_gaps=unresolved + inspected.get('known_gaps', []),
                        external_dependency_closure='pending; see SOURCE_GAPS.md')
            item['history_scope'] = 'shallow' if item['history_scope']=='true' else 'full'
            totals['repositories_indexed'] += 1
            totals['files_indexed'] += len(files)
            count_read = count_traced = count_executed = 0
            for commit, path, file in files:
                reading = combine_reviews(read_records.pop((name, path), []), file['commit_object_id'])
                fully_read = reading.get('read', False)
                count_read += fully_read
                traced = reading.get('behavior_traced', False)
                executed = reading.get('executed', False)
                count_traced += traced
                count_executed += executed
                valid_file = file['present'] and (file['lfs']['hydrated'] if file['lfs'] else
                              file['worktree_matches_commit_blob'] or path in accepted_conversions)
                writer.writerow(dict(repository_id=name, commit=commit, path=path,
                    module_role=reading.get('module_role','unreviewed'), relevance=source['priority'],
                    acquired=valid_file, indexed=True, read=fully_read,
                    behavior_traced=traced, executed=executed,
                    reader=reading.get('reader',''), read_at=reading.get('read_at',''),
                    evidence_paths=reading.get('evidence_paths',''),
                    open_questions=reading.get('open_questions','Not read; no behavioral or numerical claim.'),
                    exclusion_reason=''))
            item['evidence_status'] = dict(indexed=True, files_read=count_read,
                                          behavior_traced=count_traced, executed=count_executed)
            totals['files_read'] += count_read
            totals['behavior_traced'] += count_traced
            totals['executed'] += count_executed
            template['repositories'].append(item)
    catalog = json.loads((BASE / 'sources/catalog.json').read_text())
    if read_records:
        raise ValueError(f'file review outside indexed trees: {next(iter(read_records))}')
    origins = review.get('catalog_origin_reviews', {})
    outcomes = []
    sources = {s['id']: s for s in template['repositories']}
    for entry in catalog['entries']:
        if entry['repository_url']:
            continue
        origin = dict(origins.get(entry['id'], {}))
        repo_id = origin.get('historical_author_repository')
        if repo_id:
            locked = sources[repo_id]
            if locked['acquisition_status'] != 'acquired' or entry['id'] not in locked['catalog_ids']:
                raise ValueError(f'{repo_id}: historical author source lacks a verified snapshot')
        outcomes.append(dict(id=entry['id'], primary_urls=entry['primary_urls'],
                             acquisition_status='author_history_acquired_paper_revision_unverified' if repo_id else 'blocked_source_location',
                             commit=sources[repo_id]['commit'] if repo_id else None,
                             evidence=origin.pop('evidence', 'research/SOURCE_GAPS.md'), **origin))
    template['catalog_origin_results'] = outcomes
    template['unresolved_catalog_entries'] = [v for v in outcomes if not v['commit']]
    archive_reviews = review.get('release_archive_reviews', {})
    template['release_archives'] = [archive_lock(a, archive_reviews.get(a['id'], {}))
                                    for a in plan.get('release_archives', [])]
    template['summary'] = totals
    dump(RESEARCH / 'sources.lock.json', template)
    print(json.dumps(totals))


if __name__ == '__main__':
    main()
