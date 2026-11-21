#!/usr/bin/env python3
"""Check mixed combined/endpoint blocks on the archived QM9 water reference."""
from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path

from check_gqc_dual_response import release_oracle
from gqc_dual_response import ANALYTIC_TOL, FIELD_IDS, GATE, DualResponseModel
from generativeqc.response_problem import ResponseSolveError
from probe_gqc_residual import ROOT, check, file_hash, write_json


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    base = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
    stem = base / 'qm9_response_assets/qm9-000003'
    oracle = release_oracle('qm9-000003')
    model = DualResponseModel(stem.with_suffix('.json'), stem.with_suffix('.npz'), args.out, oracle=oracle)
    target = [('z', 'zz')]
    observations = ['q0', 'r2']
    report = {'setup': model.setup, 'oracle_sha256': file_hash(oracle),
              'model_source_sha256': file_hash(ROOT / 'scripts/gqc_dual_response.py'), 'cases': []}
    for coefficients in ((1, 1, 1), (1, 1, 0)):
        separate = model.combined_field(coefficients, observations)
        for fields, observables, key in ((['z'], [], 'fields/z'), ([], ['zz'], 'observables/zz')):
            ordinary = model.run_round(target, fields, observables, model.new_cache())
            cache = model.new_cache()
            before = model.counts.copy()
            joint = model.run_round(target, fields, observables, cache,
                                    combined_coefficients=coefficients, combined_observables=observations)
            work = model.counts - before
            block = joint['block']
            check(work['submitted_blocks'] == 1 and work['submitted_rhs'] == 2, 'expected one two-column solve')
            check(work['jk_calls'] == joint['counts']['solver_actions'] == joint['counts']['jk_calls'],
                  'whole-block work mismatch')
            check(block['column_order'] == ['combined_field', key] and max(block['residuals'].values()) <= GATE,
                  'new column order or physical residual mismatch')
            check(block['raw_projection_count'] == 3 and block['readouts']['combined_field'] == joint['combined']['values'],
                  'raw projection accounting')
            check(joint['combined']['field_identity'] == separate['field_identity']
                  and joint['combined']['observable_identities'] == separate['observable_identities'],
                  'combined physical identity mismatch')
            scalar = joint['results'][0]
            check(scalar['qualified'] and ordinary['results'][0]['qualified'] and
                  scalar['raw_value'] == block['readouts'][key]['zz' if fields else 'z'], 'ordinary projection')
            errors = {'ordinary': abs(scalar['value'] - ordinary['results'][0]['value'])}
            for name, value in joint['combined']['values'].items():
                expected = sum(c * model.oracle['targets'][f][name]['direct']
                               for f, c in zip(FIELD_IDS, coefficients, strict=True))
                errors[name + '_cartesian'] = abs(value - expected)
                errors[name + '_separate'] = abs(value - separate['values'][name])
            check(max(errors.values()) <= ANALYTIC_TOL, 'single/joint or Cartesian readout disagreement')
            report['cases'].append({'coefficients': coefficients, 'ordinary_column': key,
                                    'separate_combined': separate['counts'], 'separate_ordinary': ordinary['counts'],
                                    'joint': joint, 'errors': errors})
    # The last case cached the adjoint zz. A new combined field must still
    # validate that ordinary direction, and must never enter its cache slot.
    path = args.out / 'cache.json'
    model.save_cache(cache, path)
    replay = model.run_round(target, [], [], model.load_cache(path),
                             combined_coefficients=(1, 1, 0), combined_observables=observations)
    check(replay['block']['column_order'] == ['combined_field'] and replay['counts']['cache_validation_actions'] == 1,
          'restored ordinary cache did not pay exactly one validation')
    check(not cache['fields'] and set(cache['observables']) == {'zz'}, 'combined field leaked into endpoint cache')
    duplicate = model.run_round([('x', 'q0')], ['x'], [], model.new_cache(),
                                combined_coefficients=(1, 0, 0), combined_observables=['q0'])
    check(duplicate['counts']['rhs_columns'] == 2 and duplicate['block']['rhs_rank'] == 1
          and abs(duplicate['results'][0]['raw_value'] - duplicate['combined']['values']['q0']) <= ANALYTIC_TOL,
          'duplicate physical RHS rank or response mismatch')
    # Force a real bounded-solver failure after a stored zz is validated.
    # The normal protocol uses 200 iterations and is restored after the check.
    previous = model.options
    model.options = replace(previous, max_iterations=1)
    before = model.counts.copy()
    try:
        model.run_round([('y', 'q0'), *target], ['y'], ['zz'], cache,
                        combined_coefficients=(1, 1, 0), combined_observables=observations)
    except ResponseSolveError as error:
        failed = model.counts - before
        check(failed['submitted_blocks'] == 1 and failed['submitted_rhs'] == 2 and
              failed['cache_validation_actions'] == 1 and failed['jk_calls'] > 1, 'failed-block work missing')
        check(cache == model.load_cache(path), 'failed solve changed the persisted ordinary endpoints')
        failure = {'reason': str(error), 'counts': dict(failed)}
    else:
        raise AssertionError('one iteration unexpectedly solved the failure control')
    finally:
        model.options = previous
    report.update(cache_replay=replay, duplicate=duplicate, bounded_failure=failure, all_counts=dict(model.counts))
    write_json(args.out / 'controls.json', report)
    for case in report['cases']:
        serial_jk = case['separate_combined']['jk_calls'] + case['separate_ordinary']['jk_calls']
        print(case['coefficients'], case['ordinary_column'], serial_jk, case['joint']['counts']['jk_calls'],
              max(case['errors'].values()))


if __name__ == '__main__':
    main()
