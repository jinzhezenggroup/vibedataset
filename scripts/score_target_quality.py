#!/usr/bin/env python3
"""Verify sealed sparse decisions with an independent qualified oracle in a separate process (stdlib)."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
BUDGET = 1e-8


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def score(sealed):
    seal = json.loads((sealed / 'seal.json').read_bytes())
    refs = EXP / 'cphf_v2' / ('extension' if seal['split'] == 'holdout' else 'seed')
    index = json.loads((refs / 'index.json').read_bytes())
    require(index['schema'] == 'vibedataset.cphf_reference.v2' and index['index_sha256'] == seal['source_sha256'],
            'wrong reference schema or molecular source')
    require(all(not v['denied'] for v in seal['source_opens'].values()), 'unexpected producer file access')
    require(sha(encoded({k: h for k, h in seal['reports'].items() if k not in ('ordinary', 'dense')})) ==
            seal['prebaseline_decisions_sha256'], 'candidate decisions changed after running the competing baselines')
    reports, oracles = {}, {}
    for k, digest in seal['reports'].items():
        data = gzip.decompress((sealed / (k + '.json.gz')).read_bytes())
        require(sha(data) == digest, 'changed sealed report: ' + k)
        doc = reports[k] = json.loads(data)
        require(doc['source_index_sha256'] == seal['source_sha256'], 'response batch bound to different source')
        require(all(seal['code'][f] == v for f, v in doc['code'].items()), 'production code changed')
    scope = [r for r in index['strata'] if r.get('name') and (not seal['record_filter'] or r['name'] == seal['record_filter'])]
    for r in scope:
        if not r.get('oracle'):
            continue
        raw = (refs / r['oracle']).read_bytes()
        require(sha(raw) == r['sha256'], 'changed independent oracle')
        oracles[r['name']] = json.loads(raw)
    histories = {}
    for h in reports['history']['records']:
        for kind, asset in h.get('files', {}).items():
            raw = gzip.decompress((sealed / (asset['file'] + '.gz')).read_bytes())
            require(sha(raw) == asset['sha256'] and len(raw) == asset['bytes'], 'historical asset not as produced')
            histories[h['name'], kind] = json.loads(raw)['assets']
    normal_jk = {r['name']: sum(s['operations'].get('jk_calls', 0) for s in r['costs'] if 'solve' in s['phase'])
                 for r in reports['ordinary']['records']}
    dense_values = {(r['name'], d['field'], d['observable']): d['final']['value']
                    for r in reports['dense']['records'] for d in r.get('decisions', ())}
    metrics, details = {}, {}
    expected_requests = {tuple(x) for x in seal['requests']}
    for k, report in reports.items():
        rows = report['records']
        expected = {r['name'] for r in scope if not report['record_filter'] or r['name'] == report['record_filter']}
        require({r['name'] for r in rows} == expected and len(rows) == len(expected), 'molecular denominator')
        states, initial, totals, costs = Counter(), Counter(), Counter(), defaultdict(Counter)
        fail_accepted = uncertainty_crosses = exceeds_est = refined = unscored = 0
        observations = []
        for r in rows:
            name = r['name']
            reference = oracles.get(name)
            if reference and 'scope' in r:
                attest = reference.get('operator_attestation', reference['setup'])
                require(r['scope']['problem'] == reference['problem_identity'] and r['scope']['source'] == reference['source']
                        and r['scope']['operators'] == attest['contract_identity'],
                        'molecular or operator source mismatch')
            counted = Counter()
            for event in r['costs']:
                counted.update(event['operations'])
                phase = costs[event['phase']]
                phase.update(event['operations'])
                phase.update(seconds=event['seconds'], invocations=1, failed=int(event['status'] == 'failed'))
                for data in ('bytes_read', 'input_file_bytes', 'vector_bytes', 'rhs_bytes', 'readout_bytes'):
                    phase[data] += event.get(data, 0)
                phase['asset_bytes_written'] += sum(event.get('bytes_written', {}).values())
                for kind, length in event.get('bytes_written', {}).items():
                    phase[kind + '_bytes_written'] += length
            require(counted == Counter(r['operations']), 'unmetered or overlapping operations')
            totals.update(counted)
            if s := r.get('stability'):
                for key in ('svd_calls', 'ao_to_mo_transforms', 'matrix_bytes', 'transformed_eri_bytes'):
                    totals[key] += s.get(key, 0)
                    costs['stability_evidence'][key] += s.get(key, 0)
            if k == 'history':
                continue
            rows_for_record = r.get('decisions', [])
            require({(d['field'], d['observable']) for d in rows_for_record} == expected_requests and
                    len(rows_for_record) == len(expected_requests), 'requested target denominator')
            if v := r.get('validation_budget'):
                extra = sum(s['operations'].get('jk_calls', 0) for s in r['costs']
                            if s['phase'] in ('target_evidence', 'refinement_evidence'))
                require(extra == v['physical_actions'] <= v['limit'] and extra <= normal_jk[name],
                        'physical quality evidence exceeded ordinary solve budget')
            for d in rows_for_record:
                f, o = d['field'], d['observable']
                decision = d['final']
                before = d['initial']
                if k in ('mixed', 'quantized') and 'history_operand' in before:
                    kind = 'scalars' if k == 'mixed' else k
                    old = histories[name, kind][before['history_operand']]
                    mixed = r['directions']['x+y']['projections'][o]
                    require(before['historical_error'] == old['error_estimate'] and
                            before['propagated_error'] == old['error_estimate'] + mixed['error_estimate'] and
                            before['raw_value'] == mixed['raw_value'] - old['raw_value'] and
                            before['error_estimate'] == before['propagated_error'] + before['roundoff_allowance'],
                            'historical operand, propagated error or reconstructed scalar differs')
                states[decision['status']] += 1
                initial[d['initial']['status']] += 1
                detail = dict(name=name, field=f, observable=o, terminal=decision['status'],
                              initial=d['initial']['status'], reason=decision['reason'])
                require(decision['status'] in ('accepted', 'refine', 'reject', 'evidence_unavailable'), 'unknown outcome')
                if decision['status'] != 'accepted':
                    require(decision['value'] is None, 'unqualified output has a published value')
                else:
                    q, est = decision['value'], decision['error_estimate']
                    require(math.isfinite(q) and 0 <= est <= BUDGET, 'incomplete acceptance evidence')
                    refined += d['initial']['status'] == 'refine'
                    ref = reference['targets'][f][o] if reference else None
                    if not ref or not ref['qualified'] or ref['status'] != 'qualified':
                        unscored += 1
                    else:
                        independent = ref['cphf']
                        guard = ref['reference_precision']['readout_error_estimate']
                        difference = abs(q - independent)
                        fail_accepted += difference > BUDGET
                        uncertainty_crosses += difference + guard > BUDGET
                        exceeds_est += difference > est + guard
                        same = dense_values.get((name, f, o))
                        detail.update(independent_cphf=independent, independent_uncertainty=guard,
                                      absolute_difference=difference, decision_estimate=est,
                                      same_archived_equation_difference=abs(q - same) if same is not None else None)
                observations.append(detail)
        metrics[k] = dict(molecules=len(rows), requests=len(observations), initial=initial, states=states,
                          refined_to_accept=refined, false_accept_central=fail_accepted,
                          crosses_with_reference_budget=uncertainty_crosses, unscored_accepted=unscored,
                          outside_discrete_estimate_plus_reference_uncertainty=exceeds_est,
                          max_cphf_difference=max((x['absolute_difference'] for x in observations if 'absolute_difference' in x), default=None),
                          max_dense_difference=max((x['same_archived_equation_difference'] for x in observations
                              if x.get('same_archived_equation_difference') is not None), default=None),
                          operations=totals, phase_costs=costs, batch_elapsed_seconds=report['seconds'],
                          process_seconds=seal.get('client_seconds', {}).get(k))
        details[k] = observations
    return dict(split=seal['split'], outputs=metrics, targets=details, seal_sha256=sha((sealed/'seal.json').read_bytes()),
                independent_index_sha256=sha((refs/'index.json').read_bytes()), evaluator_sha256=sha(Path(__file__).read_bytes()))


def check_frozen_controls(result):
    for name, metrics in result['outputs'].items():
        require(metrics['false_accept_central'] == metrics['crosses_with_reference_budget'] ==
                metrics['unscored_accepted'] == 0, 'failed independent acceptance control: ' + name)
    if result['split'] == 'seed':
        for label in ('wrong-rhs', 'wrong-readout', 'no-origin', 'huge-number', 'wrong-problem', 'bad-digest'):
            outcomes = {(d['field'], d['observable']): d['terminal'] for d in result['targets'][label]}
            altered = 'evidence_unavailable' if label == 'no-origin' else 'reject'
            require(outcomes == {('x', 'q0'): 'reject' if label in ('wrong-problem', 'bad-digest') else 'accepted',
                                 ('y', 'r2'): altered, ('z', 'zz'): 'accepted'}, 'history control changed: ' + label)
    for name in ('mixed', 'retained', 'ordinary', 'dense', 'quantized'):
        require(result['outputs'][name]['states'].get('accepted', 0) > 0, 'no numerically accepted control')
    require(result['outputs']['quantized']['refined_to_accept'] > 0 and
            result['outputs']['unrated']['states'].get('evidence_unavailable', 0) > 0, 'missing refinement/withholding')


def write_costs(path, result):
    fields = ('invocations', 'failed', 'jk_calls', 'submitted_rhs', 'submitted_blocks', 'dense_solve_rhs',
              'ao_to_mo_transforms', 'svd_calls', 'matrix_bytes', 'transformed_eri_bytes', 'bytes_read',
              'input_file_bytes', 'vector_bytes', 'rhs_bytes', 'readout_bytes', 'asset_bytes_written',
              'scalars_bytes_written', 'vectors_bytes_written', 'quantized_bytes_written', 'unrated_bytes_written',
              'seconds')
    with path.open('w', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(('split', 'mode', 'phase', *fields))
        for mode, report in sorted(result['outputs'].items()):
            for name, costs in sorted(report['phase_costs'].items()):
                writer.writerow((result['split'], mode, name, *(costs.get(k, 0) for k in fields)))


def main():
    p = ArgumentParser(description=__doc__)
    p.add_argument('--sealed', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--costs', type=Path, help='write stage costs as CSV')
    p.add_argument('--check-controls', action='store_true', help='enforce the frozen molecular acceptance and negative controls')
    args = p.parse_args()
    result = score(args.sealed)
    args.out.write_bytes(encoded(result))
    if args.costs:
        write_costs(args.costs, result)
    if args.check_controls:
        check_frozen_controls(result)


if __name__ == '__main__':
    main()
