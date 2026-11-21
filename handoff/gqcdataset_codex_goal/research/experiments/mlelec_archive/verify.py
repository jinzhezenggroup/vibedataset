"""Replay the deposited member hashes, operation counts and finite differences from the retained evidence."""
import gzip
from hashlib import sha256
import json
from math import isclose
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def max_diff(left, right):
    require(len(left) == len(right) == 3, 'expected a three-axis tensor')
    require(all(len(row) == 3 for row in [*left, *right]), 'incomplete tensor row')
    return max(abs(a - b) for ra, rb in zip(left, right) for a, b in zip(ra, rb))


def read_members(folder):
    release = json.loads((folder / 'release.json').read_bytes())
    packed = (folder / 'members.json.gz').read_bytes()
    raw = gzip.decompress(packed)
    require(sha256(packed).hexdigest() == release['member_index_gzip_sha256'], 'member index gzip digest')
    require(sha256(raw).hexdigest() == release['member_index_uncompressed_sha256'], 'member index digest')
    members = json.loads(raw)
    by_name = {row['name']: row for row in members}
    require(len(members) == len(by_name) == 1182, 'unexpected paths')
    files = [r for r in members if r['type'] == '0']
    require(len(files) == release['regular_files'] == 915, 'regular file count')
    require(sum(r['type'] == '5' for r in members) == release['directories'] == 267, 'directory count')
    require(sum(r['bytes'] for r in files) == release['total_file_bytes'], 'decompressed byte count')
    require(all(len(bytes.fromhex(r['sha256'])) == 32 for r in files), 'missing file digest')
    for source in release['source_members']:
        require(source['sha256'] == by_name[source['name']]['sha256'], 'source digest')
        require(not source['identical_in_qm7'], 'unexpected byte match')
    return release, by_name


def read_journal(folder, receipt):
    packed = (folder / receipt['compressed_journal']).read_bytes()
    raw = gzip.decompress(packed)
    require(sha256(packed).hexdigest() == receipt['compressed_sha256'], 'journal gzip digest')
    require(sha256(raw).hexdigest() == receipt['raw_journal_sha256'], 'journal digest')
    rows = [json.loads(line) for line in raw.splitlines()]
    starts, ends = rows[::2], rows[1::2]
    require(len(starts) == len(ends) == receipt['completed_operations'] == 28, 'operation count')
    for seq, (start, end) in enumerate(zip(starts, ends), start=1):
        require((start['status'], end['status']) == ('started', 'completed'), 'incomplete operation')
        require(start['sequence'] == end['sequence'] == seq and start['label'] == end['label'], 'journal order')
    require(sum(r.get('scf_cycles', 0) for r in ends) == receipt['field_scf_cycles'], 'field SCF cycles')
    require(isclose(sum(r['elapsed_seconds'] for r in ends), receipt['operation_elapsed_s_sum']), 'cost sum')
    return {r['label']: r for r in ends}


def verify_case(case, events, thresholds):
    name = case['case']
    zero = events[name + '/author_single_point']
    actions = zero['source_eigen_and_veff_order']
    require(zero['source_converged'], 'zero-field SCF convergence')
    require(actions.count('eig') == case['source_eig_calls'] == 4, 'source eigensolves')
    require(actions[actions.index('eig'):].count('veff') == case['source_veff_calls_after_first_eig'] == 0,
            'effective potential was rebuilt in perturbation stage')
    require(case['final_mf_density_change_from_archived_density'] > 0, 'unchanged final density')
    cpks_event = events[name + '/coupled_RKS_linear_response']
    require(cpks_event['true_max_residual'] == case['cpks_true_max_residual'], 'CPKS residual')

    tensors = []
    for step in ('0.0005', '0.0002'):
        tensor = [[0.0] * 3 for _ in range(3)]
        for direction in range(3):
            label = f'{name}/selfconsistent_{step}_{direction}_'
            left = events[label + '-1']['dipole_au']
            right = events[label + '1']['dipole_au']
            for observed in range(3):
                tensor[observed][direction] = (right[observed] - left[observed]) / (2 * float(step))
        require(max_diff(tensor, case['selfconsistent_centered_fd'][step]) <= 1e-12, 'finite differences')
        tensors.append(tensor)

    author = case['author_one_sided_1e_minus_8']
    observed = {
        'author_vs_sum_over_states': max_diff(author, case['fock_frozen_analytic']),
        'relaxed_step_agreement': max_diff(*tensors),
        'cpks_vs_relaxed_fd': max(max_diff(fd, case['coupled_cpks']) for fd in tensors),
        'distinct_response': min(max_diff(fd, author) for fd in tensors),
    }
    for key, measured in observed.items():
        require(isclose(measured, case['checks'][key], abs_tol=1e-12), f'{name} {key} magnitude')
        if key == 'distinct_response':
            require(measured > thresholds[key], f'{name} fixed and relaxed not distinguished')
        else:
            require(measured <= thresholds[key], f'{name} {key} exceeded acceptance')
    require(case['passed'], f'{name} recorded failure')


def main():
    folder = Path(__file__).resolve().parent
    release, members = read_members(folder)
    receipts = json.loads((folder / 'receipts.json').read_bytes())
    result = json.loads((folder / 'result.json').read_bytes())
    require(sha256((folder / 'probe.py').read_bytes()).hexdigest() == result['probe_sha256'], 'driver digest')
    require(receipts['transfer']['sha256'] == release['sha256'], 'source archive digest')
    require(result['author_driver_sha256'] == members['dataset/scripts/pyscf_ref_calc.py']['sha256'],
            'upstream driver identity')
    require(result['archive_labels_deserialized'] is False and result['training_steps'] == 0, 'scope')
    for receipt in receipts['attempts']:
        events = read_journal(folder, receipt)
    require(receipts['attempts'][-1]['raw_journal_sha256'] == result['journal_sha256'], 'final run linkage')
    require({c['case'] for c in result['cases']} == {'water', 'qm7'}, 'missing molecule')
    for case in result['cases']:
        if case['case'] == 'qm7':
            require(case['xyz_file_sha256'] == members['dataset/data/qm7/qm7.xyz']['sha256'], 'geometry source')
        verify_case(case, events, result['thresholds'])
    print('915 member hashes, 267 directories, 56 completed operations, two molecular response comparisons verified.')


if __name__ == '__main__':
    main()
