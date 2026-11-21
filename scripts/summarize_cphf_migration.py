#!/usr/bin/env python3
"""Reconcile both pinned CPHF releases, the physical evidence and the ordinary CLI for all 153 targets."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path


EXP = Path(__file__).resolve().parents[1] / 'handoff/gqcdataset_codex_goal/research/experiments'
RELEASE = EXP / 'cphf_v2'
FIELDS = ('x', 'y', 'z')
OBS = ('q0', 'r2', 'zz')
CATALOGS = (
    ('initial', EXP / 'qm9_response_assets/index.json', EXP / 'gqc_dual_response/summary.json', RELEASE / 'seed/index.json'),
    ('holdout', EXP / 'qm9_extension/assets/index.json', EXP / 'qm9_extension/oracle-index.json', RELEASE / 'extension/index.json'),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def target_key(row):
    return row['molecule'], row['field'], row['observable']


def oracle(index, meta):
    path = index.parent / meta['oracle']
    require(digest(path) == meta['sha256'], str(path) + ' digest')
    return read(path)


def cost(mol):
    ref = mol['independent']
    scfs = ref['scf']
    return {
        'gqc_setup_jk': mol['setup']['counts']['jk_calls'],
        'gqc_direct_jk': mol['direct']['counts']['jk_calls'], 'gqc_adjoint_jk': mol['adjoint']['counts']['jk_calls'],
        'gqc_rhs': mol['direct']['counts']['rhs_columns'] + mol['adjoint']['counts']['rhs_columns'],
        'scf_attempts': len(scfs), 'scf_failures': sum(r['status'] != 'completed' for r in scfs),
        'scf_cycles': sum(r['cycles'] for r in scfs), 'scf_jk': sum(r['counts']['jk_calls'] for r in scfs),
        'scf_density_columns': sum(r['counts']['density_columns'] for r in scfs),
        'scf_seconds': sum(r['seconds'] for r in scfs),
        'sum_case_seconds': mol['seconds'], **{'cphf_' + k: v for k, v in ref['cphf_counts'].items()},
    }


def check_target(new, f, o, i, j):
    ref = new['independent']
    solver = ref['cphf_solver']
    cell = new['targets'][f][o]
    dense = solver['dense']
    resid, estimate = dense['physical_residual_l2'][i], dense['readout_error_estimate'][i][j]
    analytic = dense['labels'][i][j]
    require(cell['reference_precision'] == dict(physical_residual_l2=resid, readout_error_estimate=estimate)
            and analytic == cell['cphf'] == ref['cphf'][i][j], 'independent reference evidence mismatch')
    d, a = cell['direct'], cell['adjoint']
    analytic_diff = max(abs(d - analytic), abs(a - analytic))
    finite = {}
    for step in ('0.0005', '0.0002'):
        plus, minus = ref['scf'][1 + 6 * int(step == '0.0002') + 2*i:3 + 6 * int(step == '0.0002') + 2*i]
        field = [0., 0., 0.]
        field[i] = float(step)
        require(plus['field_au'] == field and minus['field_au'] == [-x for x in field], 'finite-field direction')
        slope = (plus['raw_observables'][j] - minus['raw_observables'][j]) / (2 * float(step))
        require(slope == cell['finite_fields'][step] == ref['finite_fields'][step][i][j], 'finite-field readout')
        finite[step] = max(abs(d - slope), abs(a - slope))
    reference_ok = (0 <= resid <= 1e-10 and 0 <= estimate <= 1e-9 and not ref['cphf_error']
                    and ref['zero_field_density_error'] <= 1e-7 and ref['zero_field_energy_error'] <= 1e-8
                    and max(ref['integral_errors'].values()) <= 1e-9)
    passed = reference_ok and abs(d - a) <= 1e-8 and analytic_diff + estimate <= 1e-8 and max(finite.values()) <= 1e-4
    status = 'qualified' if passed else ('response_rejected' if reference_ok else 'oracle_unqualified')
    require(status == cell['status'] and passed == cell['qualified'] and (cell['value'] is not None) == passed,
            'published disposition disagrees with raw physics')
    return dict(v2_physical_residual_l2=resid, v2_readout_error_estimate=estimate,
                v2_max_analytic_difference=analytic_diff, v2_max_finite_field_difference=max(finite.values()),
                replay_krylov_residual_l2=solver['krylov']['physical_residual_l2'][i],
                replay_krylov_value=solver['krylov']['labels'][i][j])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=False)
    original = EXP / 'qm9_extension/response-labels.jsonl'
    old_labels = [json.loads(line) for line in original.read_bytes().splitlines()]
    batches = read(RELEASE / 'cli/cache-replay.json')
    cli_raw = gzip.decompress((RELEASE / 'cli/v2.json.gz').read_bytes())
    require(hashlib.sha256(cli_raw).hexdigest() == batches['v2']['batch_sha256'], 'migration CLI digest')
    batch = json.loads(cli_raw)
    cli_rows = {(r['source']['record_id'], r['request']['field'], r['request']['observable']): r for r in batch['records']}
    require(len(old_labels) == len(cli_rows) == len(batch['records']) == 153 and
            set(cli_rows) == {target_key(r) for r in old_labels}, 'target denominator')
    costs = {}
    cases = {}
    for cohort, source, v1, v2 in CATALOGS:
        src, left, right = map(read, (source, v1, v2))
        require(left['index_sha256'] == right['index_sha256'] == digest(source), 'molecular source index digest')
        require(right['schema'] == 'vibedataset.cphf_reference.v2', 'oracle catalog version')
        for row, a, b in zip(src['rows'], left['strata'], right['strata'], strict=True):
            name = row.get('name')
            require(a['name'] == b['name'] == name and a['stratum'] == b['stratum'] == row['stratum'],
                    'catalog stratum mismatch')
            if name is None:
                continue
            require(name not in cases, 'duplicate molecule')
            prior, current = None, None
            if row['status'] == 'verified':
                require(a['status'] == b['status'] == 'completed', 'incomplete reference production')
                prior, current = oracle(v1, a), oracle(v2, b)
                require(prior['problem_identity'] == current['problem_identity'] and prior['source'] == current['source']
                        and current['schema'] == right['schema'] and prior['reference_identity'] ==
                        current['reference_identity'] == row['reference_identity'], 'molecular identity mismatch')
                costs[name] = cost(current)
            else:
                require(a['status'] == b['status'] == 'not_run' and a['reason'] == b['reason'], 'missing state changed')
            cases[name] = (cohort, row, a, b, prior, current)
    labels, changes = [], []
    counts = Counter()
    for old in old_labels:
        name, f, o = target_key(old)
        i, j = FIELDS.index(f), OBS.index(o)
        cohort, src, a, b, prior, current = cases[name]
        cli = cli_rows[name, f, o]
        require(old['source_member_sha256'] == src['member_sha256'] == cli['source']['member_sha256'] and
                old['cohort'] == cohort, 'source member mismatch')
        label = {**old, 'oracle_version': 2, 'oracle_sha256': b.get('sha256')}
        change = dict(molecule=name, field=f, observable=o, unit=old['unit'], v1_status=old['status'],
                      v1_reason=old['reason'], v1_value=old['value'], v1_cphf=old['pyscf_cphf'],
                      v1_oracle_sha256=a.get('sha256'), v2_oracle_sha256=b.get('sha256'))
        if current is None:
            require(old['status'] == cli['status'] == 'reference_unavailable' and
                    old['reason'] == b['reason'] == cli['diagnostic']['reason'], 'unavailable input or reason drift')
            cause = 'missing_ground_state'
        else:
            target, previous = current['targets'][f][o], prior['targets'][f][o]
            require((old['status'] == 'qualified') == previous['qualified'] and
                    old['pyscf_cphf'] == previous['cphf'] and old['reason'] == ', '.join(previous['reasons']),
                    'v1 record disagrees with its oracle')
            change.update(check_target(current, f, o, i, j))
            cli_status = 'response_rejected' if cli['status'] == 'withheld' else cli['status']
            require(cli_status == target['status'] and cli['source']['oracle_sha256'] == b['sha256'] and
                    old['response_contract'] == current['setup']['contract_identity'], 'CLI or target binding mismatch')
            if target['qualified']:
                require(math.isfinite(cli['value']) and abs(cli['value'] - target['value']) <= 1e-8, 'CLI value mismatch')
            label.update(status=target['status'], value=cli['value'], reason=', '.join(target['reasons']),
                         gqc_direct_diagnostic=target['direct'], pyscf_cphf=target['cphf'],
                         **{'fd_' + h: v for h, v in target['finite_fields'].items()})
            if old['status'] == 'response_rejected' and old['reason'] == 'cphf' and target['qualified']:
                cause = 'v1_cphf_disagreement_resolved_by_verified_dense_reference'
            else:
                cause = 'requalified' if target['qualified'] else target['status']
        counts[(old['status'], label['status'])] += 1
        changes.append({**change, 'v2_status': label['status'], 'v2_reason': label['reason'],
                        'v2_value': label['value'], 'v2_cphf': label['pyscf_cphf'], 'classification': cause})
        labels.append(label)
    with (out / 'migration.csv').open('w', newline='') as h:
        writer = csv.DictWriter(h, fieldnames=list(dict.fromkeys(k for row in changes for k in row)), lineterminator='\n')
        writer.writeheader()
        writer.writerows(changes)
    with (out / 'response-labels.jsonl').open('w') as h:
        for label in labels:
            h.write(json.dumps(label, allow_nan=False, separators=(',', ':')) + '\n')
    total = Counter()
    for row in costs.values():
        total.update(row)
    summary = dict(v1_table_sha256=digest(original), v2_table_sha256=digest(out / 'response-labels.jsonl'),
                   denominator=len(labels), input_molecules=len(cases), available_states=len(costs),
                   transitions={f'{old} -> {new}': n for (old, new), n in sorted(counts.items())},
                   v2_oracle_production=dict(totals=total, molecules=costs), cache_replay=batches)
    (out / 'qualification-costs.json').write_text(json.dumps(summary, sort_keys=True, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
