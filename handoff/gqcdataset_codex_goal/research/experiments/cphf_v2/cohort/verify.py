"""Replay the archived PLAN-004 measurements and compare all strict histories across oracle releases."""
import argparse
from collections import Counter
import csv
import gzip
import io
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
OLD = EXP / 'partial_response_blocks/cohort'
sys.path.insert(0, str(OLD))
import evidence


def pinned_oracles(protocol):
    paths = {}
    for version_dir, source, recorded in zip(
            ('seed', 'extension'), ('qm9_response_assets/index.json', 'qm9_extension/assets/index.json'),
            protocol['catalogs'], strict=True):
        index = HERE.parent / version_dir / 'index.json'
        raw = index.read_bytes()
        oracle_catalog = json.loads(raw)
        evidence.require(recorded['oracle_index_sha256'] == evidence.sha(raw), f'{version_dir} oracle index')
        evidence.require(recorded['source_index_sha256'] == oracle_catalog['index_sha256'] ==
                         evidence.sha((EXP / source).read_bytes()), f'{version_dir} source index')
        for row in oracle_catalog['strata']:
            if row.get('status') == 'completed':
                path = index.parent / row['oracle']
                evidence.require(row['name'] not in paths and evidence.sha(path.read_bytes()) == row['sha256'],
                                 f'catalog entry {row["name"]}')
                paths[row['name']] = path
    evidence.require(len(paths) == 12, 'twelve verified states')
    return paths


def load_plans(directory):
    completed, failed = evidence.pairs(evidence.events(directory / 'operations.jsonl.gz'))
    evidence.require(not failed, 'failed scientific operation in final cohort')
    assets = evidence.read_assets(directory / 'assets.tar.gz')
    histories, plans = {}, {}
    for row in completed:
        key = row['source'], row.get('mask')
        if row['phase'] == 'history':
            body = evidence.artifact(assets, f'{key[0]}/assets/{key[1]}/strict.json', row['scalar_assets']['strict'])
            histories[key] = {evidence.scalar_key(r) for r in body['records']}
        if row['phase'] == 'completion' and row['mode'] == 'strict':
            plans[key + (row['policy'],)] = row
    return histories, plans


def block_plan(row):
    blocks = []
    for block in row['blocks']:
        blocks.append({'fields': block['fields'], 'observables': block['observables'], 'mixed': block['support']})
    return {'blocks': blocks, 'subtractions': [
        [r['field'], r['observable'], [term['pair'] for term in r['operands']]]
        for r in row['relation'].get('reconstructions', [])]}


def compact(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True)


def compare(directory):
    old_protocol = json.loads((OLD / 'protocol.json').read_bytes())
    new_protocol = json.loads((directory / 'protocol.json').read_bytes())
    for key in ('masks', 'policies', 'release', 'gqc_commit', 'qualification'):
        evidence.require(old_protocol[key] == new_protocol[key], f'changed comparison protocol: {key}')
    for source, rec in old_protocol['source_candidates'].items():
        new = new_protocol['source_candidates'][source]
        evidence.require(all(new[key] == rec[key] for key in ('member_sha256', 'status', 'stratum', 'reason')),
                         f'changed source or failure: {source}')
    old_hist, old = load_plans(OLD)
    new_hist, new = load_plans(directory)
    evidence.require(new_hist.keys() == old_hist.keys() and len(new_hist) == 120, 'history denominator')
    evidence.require(new.keys() == old.keys() and len(new) == 600, 'strict policy denominator')
    result, changed = [], Counter()
    for key, after in sorted(new.items()):
        before = old[key]
        hist_key = key[:2]
        old_plan, new_plan = block_plan(before), block_plan(after)
        if old_plan != new_plan:
            changed[key[2]] += 1
        result.append(dict(source=key[0], mask=key[1], policy=key[2],
                           v1_history=compact(sorted(old_hist[hist_key])), v2_history=compact(sorted(new_hist[hist_key])),
                           v1_plan=compact(old_plan), v2_plan=compact(new_plan),
                           v1_rhs=before['counts']['rhs_columns'], v2_rhs=after['counts']['rhs_columns'],
                           v1_jk=before['counts']['jk_calls'], v2_jk=after['counts']['jk_calls'],
                           v1_qualified=sum(t['qualified'] is True for t in before['results']),
                           v2_qualified=sum(t['qualified'] is True for t in after['results'])))
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=result[0], lineterminator='\n')
    writer.writeheader()
    writer.writerows(result)
    return out.getvalue().encode(), dict(changed_plans=dict(changed), strict_replays=len(result),
                                         changed_histories=sum(old_hist[k] != v for k, v in new_hist.items()),
                                         v1_admitted_history_entries=sum(map(len, old_hist.values())),
                                         v2_admitted_history_entries=sum(map(len, new_hist.values())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, help='fresh PLAN-004 output to package once')
    parser.add_argument('--directory', type=Path, default=HERE)
    args = parser.parse_args()
    dest = args.directory
    if args.package:
        evidence.pack(args.package, None, dest)
    protocol = json.loads((dest / 'protocol.json').read_bytes())
    report = evidence.verify(dest, oracle_paths=pinned_oracles(protocol), expect_pilot=False)
    delta, changes = compare(dest)
    report.update(changes)
    table, receipt = dest / 'v1-v2-plans.csv.gz', dest / 'verification.json'
    if args.package:
        with table.open('xb') as f:
            f.write(gzip.compress(delta, mtime=0))
        with receipt.open('xb') as f:
            f.write(evidence.pretty(report))
    evidence.require(gzip.decompress(table.read_bytes()) == delta and json.loads(receipt.read_bytes()) == report,
                     'comparison table or receipt mismatch')
    print(json.dumps(changes, sort_keys=True))


if __name__ == '__main__':
    main()
