"""Verify the separately timed dense history-only acquisition and join its measured marginal comparator."""
import argparse
import gzip
import json
from pathlib import Path

from verify import (HERE, aggregates, archive_objects, asset, catalog, csv_bytes, dump, frontiers, package,
                    readout_terms, require, scientific, sha, verify)


def derive(dest, primary=None):
    raw = gzip.decompress((dest / 'events.jsonl.gz').read_bytes())
    events = [json.loads(l) for l in raw.splitlines()]
    finished = json.loads((dest / 'finished.json').read_bytes())
    require(finished['journal_sha256'] == sha(raw), 'dense history-only seal')
    files = json.loads((dest / 'manifest.json').read_bytes())
    for name, r in files.items():
        data = (dest / name).read_bytes()
        require(sha(data) == r['sha256'] and len(data) == r['bytes'], 'dense file digest')
    sources, oracles = catalog()
    assets, seen, histories = archive_objects(dest), set(), {}
    primary = primary or HERE / 'evidence'
    original = [json.loads(l) for l in gzip.decompress((primary / 'events.jsonl.gz').read_bytes()).splitlines()]
    original_assets, seen_old = archive_objects(primary), set()
    originals = {(r['source'], r['repetition'], r['kind']):r for r in original if r['phase'] == 'history'}
    complete, checked = 0, 0
    for e in events:
        if e['phase'] == 'reference_unavailable':
            require(e['source'] not in oracles and e['reason'] == sources[e['source']][1]['error'], 'reference reason')
        if e['phase'] != 'history':
            continue
        key = e['source'], e['repetition'], e['kind']
        complete += 1
        require(e['status'] == 'completed' and e['cost']['jk_calls'] == e['quality_native_actions'] == e['dense_rhs']
                and e['dense_solves'] == 1 and e['cost']['rhs_columns'] == 0, 'dense acquisition and physical checks')
        body = asset(assets, e, e['scalars'], seen)
        old = originals[key]
        initial = asset(original_assets, old, old['assets']['scalars'], seen_old)
        require(initial['identity'] == body['identity'] and initial['rows'].keys() == body['rows'].keys(), 'history identity or mask')
        readout_terms(e, {}, body['rows'])
        for target, val in body['rows'].items():
            require(scientific(target, val, oracles[key[0]])['v2_passed'], 'dense historical publication')
            checked += 1
        histories[key] = e
    require(complete == len(histories) == 96 and seen == assets.keys(), 'dense acquisition denominator')
    all_costs = verify(primary)[1]
    matched = []
    for r in all_costs:
        if r['method'] != 'dense':
            continue
        require(r['input_bytes'] == 0, 'dense marginal cannot reuse a separately produced history')
        h = histories[r['source'], r['repetition'], r['scenario'].split('-')[0]]
        first = h['production_seconds_before_writes'] + h['scalars']['seconds']
        matched.append(dict(r, method='dense_history_and_request', history_seconds=first, retained_bytes=h['scalars']['bytes'],
                            total_seconds=r['total_seconds']-r['history_seconds']+first,
                            first_use_total_seconds=r['first_use_total_seconds']-r['history_seconds']+first,
                            total_jk=r['total_jk']-r['history_jk']+h['cost']['jk_calls'], history_jk=h['cost']['jk_calls'],
                            history_dense_rhs=h['dense_rhs'], validation_seconds_with_shared_stability=
                            r['validation_seconds_with_shared_stability']-originals[r['source'],r['repetition'],
                            r['scenario'].split('-')[0]]['quality_seconds']+h['quality_seconds']))
    require(len(matched) == 144, 'joined marginal run count')
    jk = sum(r.get('cost',{}).get('jk_calls',0) for r in events)
    require(jk == finished['jk'], 'dense auxiliary expense')
    summary = dict(blind_seconds=finished['seconds'], actual_auxiliary_jk=jk, actual_auxiliary_dense_rhs=
                   sum(e['dense_rhs'] for e in histories.values()), dense_historical_values_scored=checked,
                   sources=17, with_state=12, dense_history_batches=len(histories), shared_marginals=len(matched),
                   reused_marginal_history_input_bytes=sum(r['input_bytes'] for r in matched),
                   supplemental_first_rounds_have_separate_timing=True)
    groups = aggregates([*all_costs, *matched])
    return summary, csv_bytes(matched), csv_bytes(groups), csv_bytes(frontiers(groups))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path)
    p.add_argument('--primary', type=Path, help='paired main evidence for a fresh replay')
    p.add_argument('--directory', type=Path, default=HERE/'dense-history')
    args = p.parse_args()
    if args.package:
        package(args.package, args.directory)
    summary, pairs, groups, bounds = derive(args.directory, args.primary)
    for name, raw in [('summary.json',dump(summary)),('matched-costs.csv.gz',pairs),
                      ('all-cohort-costs.csv',groups),('frontiers.csv',bounds)]:
        path = args.directory/name
        if args.package:
            with path.open('xb') as f:
                f.write(gzip.compress(raw,mtime=0) if name.endswith('.gz') else raw)
        require((gzip.decompress(path.read_bytes()) if name.endswith('.gz') else path.read_bytes()) == raw, name)
    print(json.dumps(summary, sort_keys=True))
