#!/usr/bin/env python3
"""Verify the n5 archive offline against the published molecular independent reference."""
from collections import Counter
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    here = Path(__file__).resolve().parent
    result, libs = read(here/'result.json'), read(here/'runtime-libraries.json')
    oracle_file = here.parents[1]/'gqc_dual_response/oracles/qm9-000003.json'
    oracle = read(oracle_file)
    assert all(sha(here/name) == value for name,value in libs['checksums'].items())
    assert sha(here/'independent.py') == result['driver_sha256']
    assert sha(oracle_file) == result['inputs_sha256']['oracle.json']
    assert result['status'] == 'passed' and libs['source_files'] == 15690 and libs['clean_source']
    steps = {v['stage']: v for v in result['attempts']}
    events = [json.loads(line) for line in (here/'events.jsonl').read_text().splitlines()]
    assert len(steps) == len(result['attempts']) == 10
    assert [(r['stage'],r['state']) for r in events] == [(name,state) for name in steps for state in ('start','completed')]
    assert all(step['status']=='completed' for step in steps.values())
    environment = result['environment']
    assert environment['slurm_job'] == '2048' and environment['slurm_cpus'] == '1' and not environment['slurm_gpus']
    slurm = (here/'slurm-accounting.txt').read_text()
    assert all(s in slurm for s in ('JobId=2048', 'JobState=COMPLETED','ExitCode=0:0','TRES=cpu=1,mem=4G,node=1'))
    setup = steps['shared_setup']['output']
    assert setup['problem_identity'] == oracle['problem_identity'] and setup['reference_identity'] == oracle['reference_identity']
    assert setup['contract_identity'] == oracle['operator_attestation']['contract_identity']
    binaries = [k['binary_sha256'] for k in setup['native_kernels']]
    binaries.extend(k['binary_sha256'] for k in steps['shared_decoders']['output'].values())
    assert sorted(binaries) == sorted(f['sha256'] for f in libs['native'])
    producer = steps['four_scalar_producer']['output']
    assert sha(here/'history.json') == producer['history_sha256']
    assert sha(here/'producer-vectors.json') == producer['vectors_sha256']
    previous = {(row['field'],row['observable']):row['value'] for row in read(here/'history.json')['rows']}
    assert set(previous) == {('y','q0'),('z','q0'),('x','r2'),('z','r2')}
    counts = Counter()
    for step in steps.values():
        counts.update(step['counts'])
    assert dict(counts) == result['all_counts']
    expected = {'ordinary_xyz':(3,22), 'separate_xyz_z':(2,36), 'joint_xyz_z':(2,20),
                'joint_xy_z':(2,20),'joint_xy_adjoint_zz':(2,20),'joint_xyz_adjoint_zz':(2,20)}
    comparisons = 0
    for name,(rhs,jk) in expected.items():
        rec = steps[name]['output']
        assert (rec['rhs'],rec['jk']) == (rhs,jk)
        assert sum(p['actions'] for p in rec['panels']) == jk
        for p in rec['panels']:
            assert p['extensions'] + p['residual_checks'] == p['actions']
            assert all(v <= 1e-10 for v in p['true_residuals'])
            assert sum(n for _,n in p['action_runs']) == p['actions']
        for row in rec['rows']:
            ref = oracle['targets'][row['field']][row['observable']]
            assert row['qualified'] and not row['reasons'] and not ref['reasons']
            for method in ('direct','adjoint','cphf'):
                assert abs(row['value']-ref[method]) <= 1e-8
            for value in ref['finite_fields'].values():
                assert abs(row['value']-value) <= 1e-4
            deps = [tuple(pair) for pair in row['operand_edges']]
            assert abs(row['value']-row['hand']) <= 1e-14
            if deps:
                # Reconstruct the mixed readout two ways, including the independently recorded direct axis solutions.
                support = [f for f in 'xyz' if f == row['field'] or (f,row['observable']) in deps]
                prior_direct_sum = sum(oracle['targets'][f][row['observable']]['direct'] for f in support)
                current_sum = row['value'] + sum(previous[edge] for edge in deps)
                assert abs(current_sum-prior_direct_sum) <= 1e-8
            comparisons += 1
    kept = steps['kept_historical_adjoint_vectors']['output']
    assert all(r['qualified'] for r in kept['results'])
    assert kept['counts']['cache_validation_actions'] == 2 and kept['counts']['solver_actions'] == 18
    print(f'passed: {len(steps)} operations, {comparisons} scalar comparisons, {counts["jk_calls"]} measured J/K')


if __name__ == '__main__':
    main()
