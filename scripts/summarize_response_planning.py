#!/usr/bin/env python3
"""Verify the measured PLAN-001/002 journals and export the cohort and cost tables offline."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
from itertools import product
import json
from pathlib import Path
import tarfile

EXPERIMENTS = Path(__file__).resolve().parents[1] / 'handoff/gqcdataset_codex_goal/research/experiments'
FIELDS = ('x', 'y', 'z')
READOUTS = ('q0', 'r2', 'zz')
HISTORY = set(product(FIELDS, READOUTS)) - set(zip(FIELDS, READOUTS))
EVENT_KEY = ('molecule', 'trace', 'policy', 'replicate')
FINAL_PAIR = ('plan001-paired-retry', 'plan001-paired-remember')


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unpack(directory, entry):
    packed = (directory / entry['file']).read_bytes()
    check(sha(packed) == entry['sha256'], entry['file'] + ': compressed digest')
    raw = gzip.decompress(packed)
    check(sha(raw) == entry['raw_sha256'] and len(raw) == entry['raw_bytes'], entry['file'] + ': raw digest')
    return raw


def write_table(path, rows):
    with path.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def cohort(source_path=EXPERIMENTS / 'qm9_response_assets/index.json', oracle_dir=EXPERIMENTS / 'gqc_dual_response/oracles'):
    source = json.loads(source_path.read_text())
    labels = []
    by_name = {}
    for case in source['rows']:
        name = case['name']
        if name is None:
            continue
        oracle = {}
        if case['status'] == 'verified':
            path = oracle_dir / (name + '.json')
            oracle = json.loads(path.read_text())
            check(oracle['source']['array_sha256'] == case['array_file_sha256'], f'{name}: source array')
            check(oracle['source']['metadata_sha256'] == case['metadata_sha256'], f'{name}: source metadata')
            by_name[name] = oracle
        for f, o in product(FIELDS, READOUTS):
            row = oracle.get('targets', {}).get(f, {}).get(o, {})
            qualified = row.get('qualified', False)
            labels.append({'molecule': name, 'qm9_id': case['qm9_id'], 'stratum': case['stratum'],
                           'source_member_sha256': case['member_sha256'], 'reference_identity': case.get('reference_identity'),
                           'response_contract': oracle.get('operator_attestation', oracle.get('setup', {})).get('contract_identity'),
                           'field': f, 'observable': o,
                           'unit': ('e' if o == 'q0' else 'bohr^2') + ' per atomic unit of electric field',
                           'status': ('qualified' if qualified else 'response_rejected') if oracle else 'reference_unavailable',
                           'value': row.get('value'), 'gqc_direct_diagnostic': row.get('direct'),
                           'pyscf_cphf': row.get('cphf'), 'fd_0.0005': row.get('finite_fields', {}).get('0.0005'),
                           'fd_0.0002': row.get('finite_fields', {}).get('0.0002'),
                           'reason': ', '.join(row['reasons']) if oracle else case['error']})
    return labels, by_name


def verify_value(oracle, field, obs, value):
    ref = oracle['targets'][field][obs]
    check((value is not None) == ref['qualified'], f'{field}/{obs}: qualification mismatch')
    if value is not None:
        check(abs(value - ref['direct']) <= 1e-8 and abs(value - ref['cphf']) <= 1e-8,
              f'{field}/{obs}: independent tolerance')


def verify_trajectories(summary, events, oracles):
    grouped = defaultdict(list)
    started = Counter()
    for event in events:
        key = tuple(event[k] for k in EVENT_KEY)
        if event['event'] == 'started':
            started[key, event['round']] += 1
            continue
        check(event['event'] == 'completed', str(key) + ': failed trajectory')
        grouped[key].append(event)
    expected = set(product(oracles, summary['traces'], summary['policies'], range(1, summary['replicates'] + 1)))
    check(grouped.keys() == expected and len(summary['trajectories']) == len(expected), 'trajectory coverage')
    seen = set()
    for row in summary['trajectories']:
        key = tuple(row[k] for k in EVENT_KEY)
        check(key not in seen, 'duplicate trajectory')
        seen.add(key)
        rounds = grouped[key]
        expected_rounds = summary['traces'][row['trace']]
        check([e['requests'] for e in rounds] == expected_rounds, str(key) + ': requests')
        total = Counter()
        delivered = []
        for idx, event in enumerate(rounds, 1):
            check(event['round'] == idx and started.pop((key, idx), 0) == 1, str(key) + ': lifecycle')
            total.update(event['counts'])
            check([[r['field'], r['observable']] for r in event['filled']] == event['requests'], str(key) + ': output order')
            for r in event['filled'] + event['computed']:
                verify_value(oracles[row['molecule']], r['field'], r['observable'], r['value'])
            delivered.extend(event['filled'])
        check(total == Counter(row['counts']), str(key) + ': summed work')
        check(row['jk_by_round'] == [e['counts']['jk_calls'] for e in rounds], str(key) + ': per round J/K')
        check((row['published_requests'], row['request_count']) == (sum(r['value'] is not None for r in delivered), len(delivered)),
              str(key) + ': published requests')
    check(not started, 'unmatched operation starts')
    return grouped


def planning_rows(run, summary, groups, molecules):
    rows = []
    for population, names in molecules.items():
        for trace, policy, rep in product(summary['traces'], summary['policies'], range(1, summary['replicates'] + 1)):
            trajectories = [v for v in summary['trajectories'] if v['molecule'] in names and
                            (v['trace'], v['policy'], v['replicate']) == (trace, policy, rep)]
            events = [event for name in sorted(names) for event in groups[name, trace, policy, rep]]
            costs = Counter()
            for e in events:
                costs.update(e['counts'])
            fills = [r for e in events for r in e['filled']]
            distinct = {(e['molecule'], r['field'], r['observable']) for e in events for r in e['filled'] if r['value'] is not None}
            per_source = summary['traces'][trace]
            unique_demand = {tuple(pair) for batch in per_source for pair in batch}
            # Six selected source members. Only verified reference states generate operations.
            full = len(names) if population == 'all_nine_qualified' else sum(s['name'] is not None for s in summary['strata'])
            rows.append({'run': run, 'population': population, 'trace': trace, 'policy': policy, 'replicate': rep,
                         'selected_molecules': full, 'computed_molecules': len(names),
                         'requested_slots': full * sum(map(len, per_source)), 'unique_requested': full * len(unique_demand),
                         'qualified_slots': sum(r['value'] is not None for r in fills), 'unique_qualified': len(distinct),
                         'scalar_hits': sum(r['cached_scalar'] for r in fills),
                         'known_reference_rejections': sum(r.get('cached_gate_rejection', False) for r in fills),
                         'first_round_jk': sum(v['jk_by_round'][0] for v in trajectories),
                         'jk': costs['jk_calls'], 'new_rhs': costs['rhs_columns'],
                         'solve_actions': costs['solver_actions'], 'check_actions': costs['cache_validation_actions'],
                         'projections_assessed': sum(len(e['computed']) for e in events),
                         'bytes_read': sum(v['io_read'] for v in trajectories), 'bytes_written': sum(v['io_written'] for v in trajectories),
                         'retained_bytes': sum(v['retained_bytes'] for v in trajectories),
                         **{k: sum(e[k] for e in events) for k in
                            ('read_seconds', 'plan_seconds', 'compute_seconds', 'write_seconds', 'elapsed_seconds')}})
    return rows


def scalar_tables(summary, events, oracles, populations):
    event_counts = Counter((x['case'], x['policy'], x['event']) for x in events)
    cases = summary['runs']
    policies = sorted({r['policy'] for r in cases})
    check(len(cases) == len(policies) * len(oracles), 'scalar coverage')
    residual_errors = defaultdict(list)
    for r in cases:
        for event in ('history_started', 'history_finished', 'completion_started', 'completion_finished'):
            check(event_counts.pop((r['name'], r['policy'], event), 0) == 1, 'scalar lifecycle')
        published_history = {(v['field'], v['observable']):v['value'] for v in r['first_results'] if v['qualified']}
        diagonal = r['completion_results']
        check({(v['field'], v['observable']) for v in diagonal} == set(zip(FIELDS, READOUTS)), 'diagonal targets')
        for target in r['first_results'] + diagonal:
            verify_value(oracles[r['name']], target['field'], target['observable'], target['value'])
        for v in diagonal:
            if v.get('via') != 'combined_field_minus_published':
                continue
            terms = {tuple(e) for e in v['subtracted']}
            check(terms == {e for e in HISTORY if e[1] == v['observable']}, 'wrong subtraction operands')
            combined, first, second = v['operands']
            check([published_history[tuple(e)] for e in v['subtracted']] == [first, second], 'unavailable legacy scalar')
            check(abs(v['raw_value'] - (combined - first - second)) <= 1e-10, 'manual scalar recovery')
            residual_errors[v['observable']].append({'hand': v['hand_difference'], 'cphf': v['errors']['cphf'],
                                                     'without_known_terms': abs(combined - v['raw_value'])})
        check(r['cumulative_jk'] == r['first_counts']['jk_calls'] + r['second_counts'].get('jk_calls', 0), 'scalar J/K')
    check(not event_counts, 'unmatched scalar event')
    check(all(s['foreign_identity_rejected'] for s in summary['strata'] if s['status'] == 'verified'), 'foreign identity')
    table = []
    for population, names in populations.items():
        for policy in policies:
            data = [r for r in cases if r['name'] in names and r['policy'] == policy]
            full = len(names) if population == 'all_nine_qualified' else sum(s['name'] is not None for s in summary['strata'])
            table.append({'population': population, 'policy': policy, 'selected_molecules': full,
                          'missing_targets': 3 * full, 'qualified': sum(v['qualified'] for r in data for v in r['completion_results']),
                          'first_jk': sum(r['first_counts']['jk_calls'] for r in data),
                          'second_jk': sum(r['second_counts'].get('jk_calls', 0) for r in data),
                          'second_rhs': sum(r['second_counts'].get('rhs_columns', 0) for r in data),
                          'cumulative_jk': sum(r['cumulative_jk'] for r in data),
                          **{k: sum(r[k] for r in data) for k in ('first_seconds', 'second_seconds', 'history_scalar_bytes',
                            'history_vector_bytes', 'second_read_bytes', 'second_label_bytes')}})
    maxima = {o:{k:max(v[k] for v in rows) for k in rows[0]} for o, rows in residual_errors.items()}
    return table, maxima


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence', type=Path, default=EXPERIMENTS / 'response_planning/raw')
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    labels, oracles = cohort()
    ready = {name for name, oracle in oracles.items() if all(v['qualified'] for field in oracle['targets'].values() for v in field.values())}
    populations = {'all_sources': set(oracles), 'all_nine_qualified': ready}
    manifest = json.loads((args.evidence / 'manifest.json').read_text())
    planning, scalars, costs, errors = [], [], {}, {}
    for run, files in sorted(manifest.items()):
        summary = json.loads(unpack(args.evidence, files['summary.json']))
        events = [json.loads(line) for line in unpack(args.evidence, files['operations.jsonl']).splitlines()]
        asset_contents = unpack(args.evidence, files['assets'])
        with tarfile.open(fileobj=io.BytesIO(asset_contents)) as archive:
            entries = archive.getmembers()
            check(len(entries) == files['assets']['members'] and all(e.isfile() for e in entries), run + ': projected assets')
        setups = [s['setup'] for s in summary['strata'] if s['status'] == 'verified']
        info = {'executing_head': summary['project_commit'], 'total_seconds': summary['wall_seconds_including_journal_and_output'],
                'shared_setup_jk': sum(x['counts']['jk_calls'] for x in setups), 'shared_setup_seconds': sum(x['seconds'] for x in setups),
                'native_kernels': sum(len(x['native_kernels']) for x in setups), 'asset_files': len(entries),
                'contained_asset_bytes': sum(e.size for e in entries), 'raw_events': len(events)}
        if 'trajectories' in summary:
            groups = verify_trajectories(summary, events, oracles)
            info.update(trajectories=len(summary['trajectories']), strategy_jk=sum(r['counts']['jk_calls'] for r in summary['trajectories']),
                        strategy_rhs=sum(r['counts']['rhs_columns'] for r in summary['trajectories']))
            if run in FINAL_PAIR:
                planning.extend(planning_rows(run, summary, groups, populations))
        else:
            scalars, errors = scalar_tables(summary, events, oracles, populations)
            info.update(trajectories=len(summary['runs']), strategy_jk=sum(x['cumulative_jk'] for x in summary['runs']),
                        strategy_rhs=sum(x['first_counts']['rhs_columns'] + x['second_counts'].get('rhs_columns', 0) for x in summary['runs']),
                        decoder_setup_seconds=summary['decoder_startup_seconds'])
        costs[run] = info
    write_table(args.out / 'planning-costs.csv', planning)
    write_table(args.out / 'scalar-costs.csv', scalars)
    with (args.out / 'response-labels.jsonl').open('w') as out:
        for row in labels:
            print(json.dumps(row, allow_nan=False, separators=(',', ':')), file=out)
    result = {'label_status': Counter(r['status'] for r in labels), 'measured_runs': costs,
              'recovered_scalar_max_absolute_differences_by_observable': errors}
    (args.out / 'verification.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
