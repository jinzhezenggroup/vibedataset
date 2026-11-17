#!/usr/bin/env python3
"""RES-002. Charge three actual property rounds to four response-asset strategies."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import pyscf

from probe_gqc_residual import (GQC, ROOT, MoleculeResponse, Run, admit, check, file_hash,
                                git, independent_observables, max_error, planned_solutions,
                                store_assets, write_json)
from gqc_residual_plan import plan_fields, recovery_program
from generativeqc_compiler.tensor import Index, IndexSpace, Program, TensorSpec, einsum, input_tensor

AXES = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
DIFFERENCES = [[1, -1, 0], [1, 0, -1], [0, 1, -1]]
STRATEGIES = ('labels_only', 'hand_incremental', 'gqc_incremental', 'hand_all_axes')
PRIOR = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments/gqc_residual_response/report.json'


def qualification(fields, results, oracle, cfg, *, width=None):
    local = np.asarray(results)[:, :width]
    analytic = np.max(np.abs(local - np.asarray(oracle['cphf'])[:, :width]), axis=1)
    differences = {step: np.max(np.abs(local - np.asarray(values)[:, :width]), axis=1)
                   for step, values in oracle['finite_fields'].items()}
    return [{'field': field, 'cphf_error': float(analytic[i]),
             'fd_errors': {step: float(values[i]) for step, values in differences.items()},
             'passed': bool(analytic[i] <= cfg['analytic_max_abs_tolerance']
                            and all(x[i] <= cfg['finite_field_max_abs_tolerance'] for x in differences.values()))}
            for i, field in enumerate(fields)]


def spatial_extent(op):
    n = op.ref.nmo
    space = IndexSpace("ao", "ao", n)
    spec = TensorSpec(tuple(Index(c, space) for c in 'pq'), role='input')
    density, r2 = (input_tensor(name, spec) for name in ('density', 'r2'))
    owner = op.run.native(Program({'d_extent': einsum('pq,qp->', density, r2)}))
    with op.mol.with_common_orig(np.zeros(3)):
        integrals = op.mol.intor_symmetric('int1e_r2') * op.scale[:, None] * op.scale

    def evaluate(vectors):
        values = []
        for v in vectors.T:
            dd = op.density_direction(op.direction_feeds(v))
            op.counts['extent_calls'] += 1
            values.append([float(owner.execute({'density': dd, 'r2': integrals})['d_extent'])])
        return np.asarray(values)
    return evaluate


def manual_cartesian(op, accepted, targets):
    basis = {tuple(field): vector for field, vector in accepted}
    missing = [axis for axis in AXES if tuple(axis) not in basis]
    new = op.solve(missing, 'manual_missing_cartesian')
    basis.update({tuple(axis): x for axis, x in zip(missing, new.T, strict=True)})
    # Three components from the known Cartesian basis, including any early investment.
    return np.column_stack([basis[tuple(axis)] for axis in AXES]) @ np.asarray(targets, float).T


def manual_differences(op, accepted):
    if len(accepted) == 3:
        check([f for f, x in accepted] == op.config['requested_fields'], 'hand mixed-field basis mismatch')
        a, b, c = [x for f, x in accepted]
        return np.column_stack((b - c, a - c, a - b))
    # With just x+y from the prior gate there is no nonzero vector shared with
    # the difference plane. Two new independent responses determine all three.
    check(not accepted or [f for f, x in accepted] == [[1, 1, 0]], 'unsupported manual partial mixed basis')
    u, v = op.solve(DIFFERENCES[:2], 'manual_independent_differences').T
    return np.column_stack((u, v, v - u))


def topology_checks(run):
    accepted_ids, missing, weights = plan_fields([], [[0, 0, 0]])
    check(not accepted_ids and not missing, 'zero target triggered a solve')
    zero = run.native(recovery_program(3, weights)).execute({})['target0']
    check(np.array_equal(zero, np.zeros(3)), 'compiled zero')
    retained, missing, weights = plan_fields([AXES[0], AXES[0]], [AXES[0], AXES[0], AXES[1], [0, 0, 0]])
    check(retained == [0] and missing == [tuple(AXES[1])], 'dependent assets or target rank')
    a = np.array([1., 2., 3.])
    b = np.array([-2., 4., 1.])
    out = run.native(recovery_program(3, weights)).execute({'x0': a, 'x1': b})
    for i, expected in enumerate([a, a, b, np.zeros(3)]):
        check(np.array_equal(out[f'target{i}'], expected), 'duplicated or absent field')
    retained, missing, weights = plan_fields([], [AXES[0], AXES[1], [1, 1, 0]])
    check(not retained and len(missing) == 2, 'empty archive missed two-field span')
    absent = run.native(recovery_program(3, weights)).execute({'x0': a, 'x1': b})
    check(np.array_equal(absent['target2'], a + b), 'no-asset reconstruction')
    try:
        plan_fields([], [])
    except ValueError as exc:
        empty = str(exc)
    else:
        raise AssertionError('empty request not rejected')
    return {'zero': zero.tolist(), 'duplicate_inputs_and_targets': 'passed', 'empty_archive': 'passed',
            'empty_target_list': empty}


def one_stage(op, strategy, stage, fields, oracle, directory, *, input_path=None, authorized=None, replay=False):
    cfg = op.config
    start, before = time.perf_counter(), op.counts.copy()
    info = {'fields': fields}
    state_file = directory / f'{op.name}-round{stage}-state.json'
    label_file = directory / f'{op.name}-round{stage}-labels.json'
    is_persistent = strategy != 'labels_only'
    actual_fields = AXES if (stage == 1 and strategy == 'hand_all_axes') else fields
    if stage == 1 or not is_persistent:
        vectors = op.solve(actual_fields, f'{strategy}_round{stage}')
    else:
        read_started = time.perf_counter()
        contents = input_path.read_bytes()
        rows = json.loads(contents)
        info.update(state_read_bytes=len(contents), state_read_seconds=time.perf_counter() - read_started)
        accepted, info['admission'] = admit(op, rows, authorized)
        if strategy == 'gqc_incremental':
            vectors = planned_solutions(op, accepted, fields, f'{strategy}_round{stage}', info)
        elif stage == 3 and strategy == 'hand_incremental':
            vectors = manual_differences(op, accepted)
        else:
            vectors = manual_cartesian(op, accepted, fields)
    residuals = [op.residual(x, f) for x, f in zip(vectors.T, actual_fields, strict=True)]
    check(max(residuals) <= cfg['target_residual_tolerance'], 'published response residual')
    values = spatial_extent(op)(vectors) if stage == 3 else op.outputs(vectors)
    used_reference = oracle
    if stage == 1:
        used_reference = {'cphf': oracle['cphf'][:len(actual_fields)], 'finite_fields':
                          {step: vals[:len(actual_fields)] for step, vals in oracle['finite_fields'].items()}}
    flags = qualification(actual_fields, values, used_reference, cfg, width=3 if stage == 1 else None)
    # The hidden oracle first judges this stage after the values are published.
    # Only directions passing that independent test may feed a later stage.
    permitted = {tuple(row['field']) for row in flags if row['passed']}
    published = [{'field': f, 'values': result[:3 if stage == 1 else None].tolist(), 'qualified': flag['passed']}
                 for f, result, flag in zip(actual_fields, values, flags, strict=True) if f in fields]
    if not replay:
        write_json(label_file, published)
        info['label_bytes_written'] = label_file.stat().st_size
        if is_persistent and (stage == 1 or stage == 2 and strategy != 'hand_all_axes'):
            store_assets(op, actual_fields, vectors, state_file)
            info.update(state_bytes_written=state_file.stat().st_size, state_sha256=file_hash(state_file),
                        numeric_vector_bytes=vectors.nbytes)
    info.update(published=published, qualification=flags, residuals=residuals, counts=dict(op.counts - before),
                elapsed_seconds=time.perf_counter() - start)
    return info, state_file, permitted


def measure(name, cfg, directory, prior):
    refdir = directory / f'{name}-independent'
    refdir.mkdir()
    log = Run(refdir)
    before = time.perf_counter()
    oracle_op = MoleculeResponse(name, cfg, log)
    check(prior['problem_identity'] == oracle_op.problem.identity, 'stored reference belongs to a different problem')
    # Independent Cartesian gates also qualify the extra z investment made by the
    # full-basis baseline. Each validation block records its actual SCF and CPHF costs.
    axis_oracle = independent_observables(oracle_op, dict(cfg, requested_fields=AXES), log)
    final_oracle = independent_observables(oracle_op, dict(cfg, requested_fields=DIFFERENCES), log, spatial_extent=True)
    verification_seconds = time.perf_counter() - before
    stages = {}
    for strategy in STRATEGIES:
        path = directory / f'{name}-{strategy}'
        path.mkdir()
        started = time.perf_counter()
        route_run = Run(path)
        op = MoleculeResponse(name, cfg, route_run)
        setup = time.perf_counter() - started
        first, saved1, good1 = one_stage(op, strategy, 1, cfg['archived_fields'], axis_oracle, path)
        second, saved2, good2 = one_stage(op, strategy, 2, cfg['requested_fields'], prior['independent'], path,
                                          input_path=saved1, authorized=good1)
        new_input, qualified = (saved1, good1) if strategy == 'hand_all_axes' else (saved2, good2)
        third, _, _ = one_stage(op, strategy, 3, DIFFERENCES, final_oracle, path,
                                 input_path=new_input, authorized=qualified)
        elapsed = time.perf_counter() - started
        total = dict(op.counts)
        replay, _, _ = one_stage(op, strategy, 3, DIFFERENCES, final_oracle, path, replay=True,
                                  input_path=new_input, authorized=qualified)
        stages[strategy] = {'setup_seconds': setup, 'rounds': [first, second, third], 'trajectory_counts': total,
                            'first_trajectory_seconds': elapsed, 'warm_third_round_replay': replay}
    direct = stages['labels_only']['rounds']
    for strategy in stages.values():
        for number, record in enumerate(strategy['rounds']):
            errors = [max_error(a['values'], b['values'])
                      for a, b in zip(record['published'], direct[number]['published'], strict=True)]
            record['max_errors_vs_direct'] = errors
            check(max(errors) <= cfg['analytic_max_abs_tolerance'], 'route disagrees with shared-target baseline')
    return {'name': name, 'strategies': stages, 'axes_oracle': axis_oracle, 'third_round_oracle': final_oracle,
            'independent_seconds': verification_seconds, 'independent_preflight_counts': dict(oracle_op.counts),
            'retained_second_round_reference': file_hash(PRIOR)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg_path = ROOT / 'configs/gqc_residual_response.json'
    cfg = json.loads(cfg_path.read_text())
    for repo, expected in ((GQC, cfg['gqc_commit']), (ROOT / '_references/pyscf_2_14', cfg['pyscf_commit'])):
        check(git(repo, 'rev-parse', 'HEAD') == expected and not git(repo, 'status', '--porcelain'), 'source pin')
    check(pyscf.__version__ == cfg['pyscf_version'], 'PySCF version')
    prior = {row['name']: row for row in json.loads(PRIOR.read_text())['cases']}
    args.out.mkdir(parents=True, exist_ok=False)
    controls = args.out / 'plan-controls'
    controls.mkdir()
    manifest = {'project_commit': git(ROOT, 'rev-parse', 'HEAD'), 'config_sha256': file_hash(cfg_path),
                'drivers': {p: file_hash(ROOT / 'scripts' / p) for p in
                            ['gqc_residual_plan.py', 'probe_gqc_residual.py', Path(__file__).name]},
                'python': platform.python_version(), 'numpy': np.__version__, 'pyscf': pyscf.__version__,
                'gqc': cfg['gqc_commit'], 'pyscf_reference': cfg['pyscf_commit'],
                'cxx': subprocess.check_output(['c++', '--version'], text=True).splitlines()[0],
                'sccache': subprocess.check_output(['sccache', '--version'], text=True).strip(),
                'threads': {k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                'planning_controls': topology_checks(Run(controls)), 'cases': []}
    for name in cfg['fixtures']:
        try:
            case = measure(name, cfg, args.out, prior[name])
        except Exception as exc:
            import traceback
            case = {'name': name, 'error': str(exc), 'traceback': traceback.format_exc()}
        manifest['cases'].append(case)
        write_json(args.out / 'report.json', manifest)
        print(name, case.get('error', {k: v['trajectory_counts']['jk_calls'] for k, v in case.get('strategies', {}).items()}),
              flush=True)
    # Ineligible targets are explicitly retained; an infrastructure failure or a
    # scientific gate miss on requested output produces a nonzero result.
    for case in manifest['cases']:
        if 'error' in case or any(not row['qualified'] for strategy in case['strategies'].values()
                                  for stage in strategy['rounds'] for row in stage['published']):
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
