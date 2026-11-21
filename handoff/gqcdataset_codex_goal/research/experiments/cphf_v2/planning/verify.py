"""Package or check the paired PLAN-001, PLAN-002 and held-out same-operator measurements."""
import argparse
from collections import Counter
import csv
import gzip
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
sys.path.insert(0, str(HERE.parents[5] / 'scripts'))
from summarize_response_planning import (check, planning_rows, scalar_tables, sha,
                                          verify_trajectories)

RUNS = ('seed-scalar', 'extension-scalar', 'seed-remember', 'seed-retry', 'extension-diagnostic')
SOURCES = {'seed': EXP / 'qm9_response_assets/index.json', 'extension': EXP / 'qm9_extension/assets/index.json'}
LEGACY = {'seed': EXP / 'response_planning/raw/plan002-first-summary.json.gz',
          'extension': EXP / 'qm9_extension/scalar-summary.json.gz'}


def readgz(path):
    return gzip.decompress(path.read_bytes())


def table(rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=rows[0], lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def pack(work, dest):
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for run in RUNS:
        directory = work / run
        events = 'events.jsonl' if run == 'extension-diagnostic' else 'operations.jsonl'
        files = {run + '-events.jsonl.gz': (directory / events).read_bytes(),
                 run + '-summary.json.gz': (directory / 'summary.json').read_bytes()}
        asset_buffer = io.BytesIO()
        with tarfile.open(fileobj=asset_buffer, mode='w', format=tarfile.USTAR_FORMAT) as tar:
            paths = sorted([*directory.glob('qm9-*/**/*.json'), *directory.glob('qm9-*-diagnostic-operands.json')])
            check(bool(paths), run + ': empty asset archive')
            for p in paths:
                data = p.read_bytes()
                entry = tarfile.TarInfo(p.relative_to(directory).as_posix())
                entry.size = len(data)
                tar.addfile(entry, io.BytesIO(data))
        files[run + '-assets.tar.gz'] = asset_buffer.getvalue()
        for name, data in files.items():
            raw = gzip.compress(data, mtime=0)
            with (dest / name).open('xb') as f:
                f.write(raw)
            manifest[name] = {'bytes': len(raw), 'sha256': sha(raw), 'raw_sha256': sha(data)}
    with (dest / 'manifest.json').open('x') as f:
        print(json.dumps(manifest, indent=2, sort_keys=True), file=f)


def oracles_for(catalog):
    index = HERE.parent / catalog / 'index.json'
    pinned = json.loads(index.read_bytes())
    check(sha(SOURCES[catalog].read_bytes()) == pinned['index_sha256'], 'source index digest')
    oracles, hashes = {}, {}
    for item in pinned['strata']:
        if item.get('status') == 'completed':
            data = (index.parent / item['oracle']).read_bytes()
            check(sha(data) == item['sha256'], 'oracle digest')
            obj = json.loads(data)
            check(obj['schema'] == 'vibedataset.cphf_reference.v2' and obj['name'] == item['name'], 'v2 oracle')
            oracles[obj['name']], hashes[obj['name']] = obj, item['sha256']
    return oracles, hashes


def legacy_cache_control(work):
    # Invoke the same reader used in each scientific trajectory on actual v1 scalar assets.
    from probe_response_planning import read_scalars
    summary = json.loads((work / 'seed-scalar/summary.json').read_bytes())
    old = EXP / 'response_planning/raw/plan002-first-assets.tar.gz'
    controls = {}
    with tarfile.open(old, 'r:gz') as archive, tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'scalars.json'
        for state in summary['strata']:
            if 'scalar_identity' not in state:
                continue
            name = state['name']
            data = archive.extractfile(name + '/legacy_decode/scalars.json').read()
            path.write_bytes(data)
            before = json.loads(data)['payload']['scientific_identity']
            old_labels, _ = read_scalars(path, before)
            try:
                read_scalars(path, state['scalar_identity'])
            except ValueError as exc:
                controls[name] = dict(v1_sha256=sha(data), v1_entries=len(old_labels),
                                      v1_identity=before, v2_identity=state['scalar_identity'], reason=str(exc))
            else:
                raise ValueError(name + ': v1 cache admitted under v2')
    return controls


def check_scalar_file(data, identity, rows):
    obj = json.loads(data)
    body = obj['payload']
    digest = sha(json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())
    check(digest == obj['sha256'] and body['scientific_identity'] == identity, 'scalar archive identity')
    saved = {(t['field'], t['observable']): t['value'] for t in body['labels']}
    check(len(saved) == len(body['labels']) and saved == {
        (t['field'], t['observable']): t['value'] for t in rows if t['qualified'] is True}, 'published scalar archive')


def check_scalar_assets(directory, run, summary, events):
    ended = {(e['case'], e['policy'], e['event']): e['counts'] for e in events if e['event'].endswith('_finished')}
    policy_set = {'legacy_recompute', 'legacy_decode', 'keep_vectors', 'eager_table', 'remove_history'}
    identities = {r['name']: r['scalar_identity'] for r in summary['strata'] if 'scalar_identity' in r}
    seen = set()
    with tarfile.open(directory / (run + '-assets.tar.gz'), 'r:gz') as archive:
        for r in summary['runs']:
            name, policy = key = r['name'], r['policy']
            check(key not in seen, 'repeated scalar trajectory')
            seen.add(key)
            prefix = name + '/' + policy + '/'
            inputs = archive.extractfile(prefix + 'scalars.json').read()
            outputs = archive.extractfile(prefix + 'new-labels.json').read()
            vector_size = archive.getmember(prefix + 'vectors.json').size if policy == 'keep_vectors' else 0
            check_scalar_file(inputs, identities[name], r['first_results'])
            check_scalar_file(outputs, identities[name], r['completion_results'])
            check((len(inputs), vector_size, len(inputs) + vector_size, len(outputs)) ==
                  (r['history_scalar_bytes'], r['history_vector_bytes'], r['second_read_bytes'], r['second_label_bytes']),
                  'serialized inputs/outputs or read charges')
            for event_name, tag in [('history_finished', 'first_counts'), ('completion_finished', 'second_counts')]:
                check(ended.pop((*key, event_name)) == r[tag], 'actual scalar solve costs')
    check(seen == {(source, p) for source in identities for p in policy_set} and not ended, 'scalar policy coverage')


def verify(dest, package=False):
    manifest = json.loads((dest / 'manifest.json').read_bytes())
    expected = {run + suffix for run in RUNS for suffix in ('-summary.json.gz', '-events.jsonl.gz', '-assets.tar.gz')}
    check(set(manifest) == expected, 'raw file denominator')
    for name, entry in manifest.items():
        data = (dest / name).read_bytes()
        check((len(data), sha(data), sha(gzip.decompress(data))) ==
              (entry['bytes'], entry['sha256'], entry['raw_sha256']), name)
    costs, acquisitions, diagnostic_costs, account = [], [], [], {}
    for run in RUNS:
        catalog = run.split('-')[0]
        oracles, hashes = oracles_for(catalog)
        summary = json.loads(readgz(dest / (run + '-summary.json.gz')))
        events = [json.loads(line) for line in readgz(dest / (run + '-events.jsonl.gz')).splitlines()]
        states = summary.get('strata', summary.get('records'))
        check(summary.get('source_index_sha256', summary.get('index_sha256')) == sha(SOURCES[catalog].read_bytes()),
              'measured source index')
        source_rows = json.loads(SOURCES[catalog].read_bytes())['rows']
        check([(r['name'], r['member_sha256']) for r in states] ==
              [(r['name'], r.get('member_sha256')) for r in source_rows], 'source and failure denominator')
        check({r['name']: r['oracle_sha256'] for r in states if 'setup' in r} == hashes, 'measured v2 oracle')
        setups = [r['setup'] for r in states if 'setup' in r]
        row = {'computed_sources': len(setups), 'selected_sources': sum(bool(r['name']) for r in states),
               'setup_jk': sum(s['counts']['jk_calls'] for s in setups), 'setup_seconds': sum(s['seconds'] for s in setups)}
        if run.endswith('-scalar'):
            check_scalar_assets(dest, run, summary, events)
            result, extrema = scalar_tables(summary, events, oracles, {'all_sources': set(oracles)})
            costs.extend(dict(cohort=catalog, **r) for r in result)
            prior = [r for r in json.loads(readgz(LEGACY[catalog]))['strata'] if 'scalar_identity' in r]
            ids = {r['name']: r['scalar_identity'] for r in states if 'scalar_identity' in r}
            check(all(ids[r['name']] != r['scalar_identity'] for r in prior), 'old scalar identity reused')
            row.update(trajectories=len(summary['runs']), history_and_completion_jk=sum(r['cumulative_jk'] for r in result),
                       new_rhs=sum(r[k].get('rhs_columns', 0) for r in summary['runs'] for k in ('first_counts', 'second_counts')),
                       decoder_setup_seconds=summary['decoder_startup_seconds'], hand_and_oracle_errors=extrema)
        elif run.startswith('seed-'):
            prior = json.loads(readgz(EXP / 'response_planning/raw' / (
                'plan001-paired-' + run.split('-')[1] + '-summary.json.gz')))
            check(all(summary[key] == prior[key] for key in ('traces', 'policies', 'replicates', 'order_seed',
                      'remember_reference_rejections')), 'changed trajectory protocol or sampling seed')
            groups = verify_trajectories(summary, events, oracles)
            result = planning_rows(run, summary, groups, {'all_sources': set(oracles)})
            acquisitions.extend(result)
            row.update(trajectories=len(summary['trajectories']), history_and_completion_jk=sum(r['jk'] for r in result),
                       new_rhs=sum(r['new_rhs'] for r in result))
        else:
            event_count = Counter((e['molecule'], e['event']) for e in events)
            for state in states:
                if 'setup' not in state:
                    continue
                name = state['name']
                check(state['status'] == 'completed' and event_count.pop((name, 'started'), 0) ==
                      event_count.pop((name, 'completed'), 0) == 1, 'diagnostic completion')
                check(len(state['comparisons']) == 3, 'diagnostic targets')
                for result in state['comparisons']:
                    ref = oracles[name]['targets'][result['field']][result['observable']]
                    check(result['independent_reference_qualified'] == ref['qualified']
                          and result['passes_same_operator_tolerance']
                          and abs(result['recovered_diagnostic'] - result['direct_diagnostic']) == result['absolute_difference'],
                          'diagnostic equivalence or independent status')
                diagnostic_costs.append(dict(source=name, **{phase + '_jk': state[phase]['counts']['jk_calls']
                                                             for phase in ('history','combined','direct')},
                                             maximum_difference=max(r['absolute_difference'] for r in state['comparisons']),
                                             independently_qualified=sum(r['independent_reference_qualified'] is True
                                                                         for r in state['comparisons'])))
            check(not event_count, 'unmatched diagnostic operation')
            row.update(history_and_completion_jk=sum(r[phase + '_jk'] for r in diagnostic_costs
                                                      for phase in ('history', 'direct', 'combined')),
                       new_rhs=sum(r[phase]['counts']['rhs_columns'] for r in states if 'setup' in r
                                   for phase in ('history', 'direct', 'combined')), decoder_setup_seconds=summary['decoder_seconds'])
        row['wall_seconds'] = summary.get('total_seconds', summary.get('wall_seconds_including_journal_and_output'))
        row['measured_project_commit'] = summary.get('project_commit', summary.get('source_commit'))
        account[run] = row
    files = {'scalar-costs.csv': table(costs), 'trajectory-costs.csv': table(acquisitions),
             'same-operator-costs.csv': table(diagnostic_costs),
             'costs.json': (json.dumps(account, sort_keys=True, indent=2) + '\n').encode()}
    for name, content in files.items():
        if package:
            with (dest / name).open('xb') as f:
                f.write(content)
        check((dest / name).read_bytes() == content, name + ': derived table')
    controls = json.loads((dest / 'v1-history-rejections.json').read_bytes())
    seed = json.loads(readgz(dest / 'seed-scalar-summary.json.gz'))
    identities = {r['name']: r['scalar_identity'] for r in seed['strata'] if 'scalar_identity' in r}
    check(controls.keys() == identities.keys(), 'v1 history control coverage')
    with tarfile.open(EXP / 'response_planning/raw/plan002-first-assets.tar.gz', 'r:gz') as old:
        for name, control in controls.items():
            data = old.extractfile(name + '/legacy_decode/scalars.json').read()
            body = json.loads(data)['payload']
            check(control['v1_sha256'] == sha(data) and control['v1_identity'] == body['scientific_identity']
                  and control['v1_entries'] == len(body['labels'])
                  and control['v2_identity'] == identities[name] != control['v1_identity']
                  and control['reason'] == 'scalar payload or scientific identity mismatch', 'v1 cache rejection')
    print(json.dumps({k: {'charged_jk': v['setup_jk'] + v['history_and_completion_jk'], 'new_rhs': v['new_rhs']}
                      for k, v in account.items()}, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=HERE)
    parser.add_argument('--package', type=Path, help='directory with the five completed runs')
    args = parser.parse_args()
    if args.package:
        pack(args.package, args.directory)
        with (args.directory / 'v1-history-rejections.json').open('x') as f:
            print(json.dumps(legacy_cache_control(args.package), sort_keys=True, indent=2), file=f)
    verify(args.directory, args.package is not None)
