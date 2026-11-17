#!/usr/bin/env python3
"""Join the two disjoint QM9 cohorts, check their raw receipts and attribute work."""
from argparse import ArgumentParser
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path

from summarize_response_planning import EXPERIMENTS, check, cohort, scalar_tables, write_table

DATA = EXPERIMENTS / 'qm9_extension'


def read(name):
    b = (DATA/name).read_bytes()
    if name.endswith('.gz'):
        b = gzip.decompress(b)
    return json.loads(b)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    first, _ = cohort()
    records, oracles = cohort(DATA/'assets/index.json', DATA/'oracles')
    labels = [dict(cohort=cohort_name, **r) for cohort_name, group in [('initial', first), ('holdout', records)] for r in group]
    initial_source = json.loads((EXPERIMENTS/'qm9_response_assets/cohort.json').read_text())
    eligible = {n for stratum in initial_source['strata'] for n in stratum['eligible_ids']}
    check({r['qm9_id'] for r in labels} == eligible and len({(r['qm9_id'],r['field'],r['observable']) for r in labels})
          == len(labels) == 9*len(eligible), 'one row for each eligible target')
    n5, oracle_index = read('assets/index.json'), read('oracle-index.json')
    check(n5['cohort_sha256'] == sha256((DATA/'cohort.json').read_bytes()).hexdigest(), 'cohort digest')
    check(oracle_index['index_sha256'] == sha256((DATA/'assets/index.json').read_bytes()).hexdigest(), 'oracle index digest')
    for r in n5['rows']:
        if r['status'] == 'verified':
            for k,h in [('metadata_file','metadata_sha256'),('array_file','array_file_sha256')]:
                check(sha256((DATA/'assets'/r[k]).read_bytes()).hexdigest() == r[h], r[k])
    for r in oracle_index['strata']:
        if r['status'] == 'completed':
            check(sha256((DATA/r['oracle']).read_bytes()).hexdigest() == r['sha256'], r['oracle'])
    result = read('cli-result.json.gz')
    by_key = {(r['qm9_id'],r['field'],r['observable']):r for r in records}
    check(result['input_sha256'] == sha256((DATA/'requests.jsonl').read_bytes()).hexdigest(), 'client input digest')
    seen = set()
    for r in result['records']:
        req = r['request']
        k = req['record_id'], req['field'], req['observable']
        target = by_key[k]
        status = {'qualified':'qualified', 'response_rejected':'withheld', 'reference_unavailable':'reference_unavailable'}[target['status']]
        check(r['status'] == status and r['value'] == target['value'] and k not in seen, str(k) + ': CLI mismatch')
        seen.add(k)
    check(seen == by_key.keys(), 'client denominator')
    scalar = read('scalar-summary.json.gz')
    events = [json.loads(line) for line in gzip.decompress((DATA/'scalar-events.jsonl.gz').read_bytes()).splitlines()]
    table, _ = scalar_tables(scalar,events,oracles,{'all_sources':set(oracles)})
    write_table(out/'costs.csv',table)
    study = read('same-operator.json.gz')
    cases = [r for r in study['records'] if r['status'] == 'completed']
    checked = [v for r in cases for v in r['comparisons']]
    per_case = []
    for r in cases:
        for v in r['comparisons']:
            ref = by_key[r['qm9_id'],v['field'],v['observable']]
            check(v['independent_reference_qualified'] == (ref['status']=='qualified'), 'independent status')
            check(abs(v['recovered_diagnostic']-v['direct_diagnostic']) == v['absolute_difference'], 'reported discrepancy')
        per_case.append({'id':r['qm9_id'],'history_jk':r['history']['counts']['jk_calls'],
                         'direct_jk':r['direct']['counts']['jk_calls'],'combined_jk':r['combined']['counts']['jk_calls'],
                         'direct_rhs':r['direct']['counts']['rhs_columns'],'combined_rhs':r['combined']['counts']['rhs_columns'],
                         'combined_residual':r['combined']['true_residual'], 'operand_bytes':r['operand_bytes'],
                         'direct_seconds':r['direct_seconds'],'combined_seconds':r['recovery_seconds_with_read'],
                         'max_difference':max(v['absolute_difference'] for v in r['comparisons'])})
    write_table(out/'same-operator-costs.csv',per_case)
    with (out/'response-labels.jsonl').open('w') as f:
        for r in sorted(labels, key=lambda r:(r['qm9_id'],r['field'],r['observable'])):
            print(json.dumps(r,allow_nan=False,separators=(',',':')),file=f)
    refs = [row for o in oracles.values() for row in o['independent']['scf']]
    account = {'initial_status':Counter(r['status'] for r in first),'holdout_status':Counter(r['status'] for r in records),
               'all_status':Counter(r['status'] for r in labels),'n5_outcomes':n5['outcomes'],
               'gpu_scf_cycles':sum(r['gqc']['iterations'] for r in n5['rows']),
               'gpu_focks':sum(r['gqc']['fock_builds'] for r in n5['rows']),
               'independent_base_scf_cycles':sum(r['pyscf']['scf_cycles'] for r in n5['rows']),
               'independent_response_scf':len(refs),'independent_response_scf_status':Counter(r['status'] for r in refs),
               'independent_response_scf_cycles':sum(r['cycles'] for r in refs),
               'independent_response_scf_jk':sum(r['counts']['jk_calls'] for r in refs),
               'cphf_calls':len(oracles),'cphf_jk_batches':sum(o['independent']['cphf_counts'].get('jk_calls',0) for o in oracles.values()),
               'cphf_density_columns':sum(o['independent']['cphf_counts'].get('density_columns',0) for o in oracles.values()),
               'oracle_setup_jk':sum(o['setup']['counts']['jk_calls'] for o in oracles.values()),
               'oracle_direct_jk':sum(o['direct']['counts']['jk_calls'] for o in oracles.values()),
               'oracle_adjoint_jk':sum(o['adjoint']['counts']['jk_calls'] for o in oracles.values()),
               'five_policy_trajectories':len(scalar['runs']),'five_policy_jk':sum(x['cumulative_jk'] for x in scalar['runs']),
               'five_policy_shared_setup_jk':sum(t['setup']['counts']['jk_calls'] for t in scalar['strata'] if 'setup' in t),
               'five_policy_seconds':scalar['wall_seconds_including_journal_and_output'],
               'diagnostic_totals':{k:sum(r[k] for r in per_case) for k in ('history_jk','direct_jk','combined_jk','direct_rhs','combined_rhs','operand_bytes','direct_seconds','combined_seconds')},
               'diagnostic_preparation_jk':sum(r['setup']['counts']['jk_calls'] for r in cases),
               'diagnostic_eligible_sources':len(cases),'diagnostic_same_operator_passed':sum(v['passes_same_operator_tolerance'] for v in checked),
               'diagnostic_max_abs_difference':max(v['absolute_difference'] for v in checked),
               'diagnostic_independently_qualified':sum(v['independent_reference_qualified'] for v in checked),
               'diagnostic_seconds':study['total_seconds'],'client_status':result['counts_by_status'],
               'client_jk':sum(w['round_jk'] for w in result['work']),'client_setup_jk':sum(w['setup_jk'] for w in result['work']),
               'client_seconds':result['seconds']}
    (out/'verification.json').write_text(json.dumps(account,indent=2,sort_keys=True)+'\n')


if __name__ == '__main__':
    main()
