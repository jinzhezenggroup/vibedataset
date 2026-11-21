#!/usr/bin/env python3
"""Publish the RES-002 per-component labels and keep rejected diagnostics auditable."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
DEFAULT_REPORT = EXPERIMENTS / 'gqc_residual_multiround/report.json'
PREVIOUS = EXPERIMENTS / 'gqc_residual_response/report.json'
DIPOLE = [(f'total_dipole_{axis}', 'e*a0 / au_field') for axis in 'xyz']
CHARGE = ('mulliken_net_charge_atom_0', 'e / au_field')
EXTENT = ('electronic_sum_radius_squared', 'a0^2 / au_field')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def pinned_source_hash(commit, path):
    blob = subprocess.check_output(['git', '-C', str(ROOT / '_references/gqc'),
                                    'show', f'{commit}:{path.as_posix()}'])
    return hashlib.sha256(blob).hexdigest()


def rows(report_path):
    report = read(report_path)
    previous = {case['name']: case for case in read(PREVIOUS)['cases']}
    config_path = ROOT / 'configs/gqc_residual_response.json'
    cfg = read(config_path)
    if report['config_sha256'] != sha(config_path):
        raise ValueError('response protocol digest differs')
    report_digest = sha(report_path)
    for case_index, case in enumerate(report['cases']):
        name = case['name']
        prior = previous[name]
        if case['retained_second_round_reference'] != sha(PREVIOUS):
            raise ValueError('independent second round reference has changed')
        stage_rows = case['strategies']['gqc_incremental']['rounds']
        controls = case['strategies']['labels_only']['rounds']
        oracles = [case['axes_oracle'], prior['independent'], case['third_round_oracle']]
        fixture_path = Path('tests/reference_data/posthf') / (name + '.json')
        archive_path = fixture_path.with_suffix('.npz')
        source = {'repository': 'jinzhezenggroup/generativeqc', 'commit': report['gqc'],
                  'fixture': str(fixture_path), 'fixture_sha256': pinned_source_hash(report['gqc'], fixture_path),
                  'arrays': str(archive_path), 'arrays_sha256': pinned_source_hash(report['gqc'], archive_path)}
        for stage, (measured, control, oracle, props) in enumerate(
                zip(stage_rows, controls, oracles, [DIPOLE, DIPOLE + [CHARGE], [EXTENT]], strict=True), 1):
            for field_index, bundle in enumerate(measured['published']):
                field = bundle['field']
                residual = measured['residuals'][field_index]
                limits = {'direct': cfg['analytic_max_abs_tolerance'], 'cphf': cfg['analytic_max_abs_tolerance'],
                          **{f'finite_field_{step}': cfg['finite_field_max_abs_tolerance'] for step in oracle['finite_fields']}}
                diagnostics = []
                for component_index, ((label, unit), raw) in enumerate(zip(props, bundle['values'], strict=True)):
                    references = {'direct': control['published'][field_index]['values'][component_index],
                                  'cphf': oracle['cphf'][field_index][component_index]}
                    references.update({f'finite_field_{step}': values[field_index][component_index]
                                       for step, values in oracle['finite_fields'].items()})
                    errors = {method: abs(raw - expected) for method, expected in references.items()}
                    failed = [method for method, err in errors.items() if err > limits[method]]
                    if residual > cfg['target_residual_tolerance']:
                        failed.append('physical_residual')
                    diagnostics.append((label, unit, raw, errors, failed))
                cause = {label: failed for label, _, _, _, failed in diagnostics if failed}
                if (not cause) != bundle['qualified']:
                    raise ValueError(f'published flag disagrees with independent evidence: {name} round {stage} {field}')
                for label, unit, raw, errors, failed in diagnostics:
                    target = {'problem_identity': prior['problem_identity'], 'observable': label, 'unit': unit,
                              'field_direction_xyz': field, 'origin_bohr': [0, 0, 0], 'derivative_at_field_au': 0,
                              'property_definition': 'linear derivative under fully relaxed restricted HF, clamped nuclei'}
                    stable_id = hashlib.sha256(json.dumps(target, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                    yield {
                        'id': stable_id, 'molecule': name, 'method': 'conventional RHF', 'precision': 'float64',
                        'geometry_hash': prior['geometry_hash'], 'basis_hash': prior['basis_hash'],
                        'reference_identity': prior['reference_identity'], 'source': source,
                        'round': stage, 'target': target,
                        'status': 'qualified' if not cause else 'withheld',
                        'value': raw if not cause else None,
                        'diagnostic': {'raw_value': raw, 'component_passed': not failed,
                                       'direction_bundle_failures': cause, 'absolute_errors': errors, 'limits': limits,
                                       'true_residual_2norm': residual, 'true_residual_limit': cfg['target_residual_tolerance']},
                        'result': {'path': 'research/experiments/gqc_residual_multiround/report.json',
                                   'sha256': report_digest, 'pointer': f'/cases/{case_index}/strategies/gqc_incremental/rounds/{stage-1}/published/{field_index}'},
                    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=DEFAULT_REPORT)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = list(rows(args.report))
    if len({record['id'] for record in data}) != len(data):
        raise ValueError('duplicate scientific target identity')
    encoded = ''.join(json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
                      for record in data)
    args.out.write_text(encoded)


if __name__ == '__main__':
    main()
