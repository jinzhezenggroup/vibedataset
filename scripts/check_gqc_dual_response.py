#!/usr/bin/env python3
"""Exercise scalar acceptance, cached-asset recovery and the combined field on QM9 water."""
from argparse import ArgumentParser
import copy
import json
from pathlib import Path

import numpy as np

from gqc_dual_response import DualResponseModel, FIELD_IDS, OBSERVABLE_IDS, array_hash
from probe_gqc_residual import ROOT, check, write_json


def main():
    parser = ArgumentParser(description=__doc__)
    base = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
    parser.add_argument('--assets', type=Path, default=base / 'qm9_response_assets')
    parser.add_argument('--oracles', type=Path, default=base / 'gqc_dual_response/oracles')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    name = 'qm9-000003'
    oracle = json.loads((args.oracles / (name + '.json')).read_text())
    model = DualResponseModel(args.assets / (name + '.json'), args.assets / (name + '.npz'), args.out, oracle=oracle)
    edges = [('x', 'q0'), ('x', 'r2'), ('z', 'zz')]
    cache = model.new_cache()
    mixed = model.run_round(edges, ['x'], ['zz'], cache)
    check(mixed['counts']['rhs_columns'] == 2 and all(r['qualified'] for r in mixed['results']), 'mixed block')
    hit = model.run_round(edges, [], [], cache)
    check(hit['counts']['rhs_columns'] == 0 and hit['counts']['jk_calls'] == 2, 'cache replay')
    path = args.out / 'cache.json'
    model.save_cache(cache, path)
    cache = model.load_cache(path)
    x = cache['fields']['x']
    x['solution'][0] += .1
    x['solution_sha256'] = array_hash(x['solution'])
    corrupted = model.run_round([('x', 'q0')], [], [], cache)
    check(corrupted['cache_checks'][0]['decision'] == 'physical response residual', 'false response accepted')
    cache['fields']['x']['endpoint_identity'] = 'wrong-readout-sign-or-origin'
    changed = model.run_round([('x', 'q0')], [], [], cache)
    check(changed['cache_checks'][0]['decision'] == 'problem or endpoint identity', 'changed endpoint accepted')
    cache['problem_identity'] = 'unrelated-reference'
    stale = model.run_round([('x', 'q0')], [], [], cache)
    check(stale['counts']['cache_rejections'] == 1 and not cache['observables'], 'stale cache accepted')
    cache['fields']['x']['solution'] = None
    bad = model.run_round([('x', 'q0')], [], [], cache)
    check(bad['counts']['cache_rejections'] == 1, 'malformed cache accepted')
    for value in (None, float('nan'), float('inf'), float('-inf'), 10**400):
        row = model.assess('x', 'r2', value)
        check(row['qualified'] is False and row['value'] is None, 'nonfinite candidate accepted')
        try:
            model.combined_field([value, 1., 1.])
        except ValueError:
            pass
        else:
            raise AssertionError('invalid seed accepted')
    original = oracle['targets']['x']['q0']['direct']
    nonfinite_gates = {}
    for ref in ('direct', 'adjoint', 'cphf', '0.0005', '0.0002'):
        tainted = copy.deepcopy(oracle)
        row = tainted['targets']['x']['q0']
        if ref in row['finite_fields']:
            row['finite_fields'][ref] = float('nan')
        else:
            row[ref] = float('inf')
        model.attach_oracle(tainted)
        assessment = model.assess('x', 'q0', original)
        check(assessment['qualified'] is False and assessment['value'] is None, 'nonfinite independent value accepted')
        nonfinite_gates[ref] = assessment['reasons']
    model.attach_oracle(oracle)
    combined = model.combined_field([1, 1, 1])
    discrepancies = {o: abs(combined['values'][o] - sum(oracle['targets'][f][o]['direct'] for f in FIELD_IDS))
                     for o in OBSERVABLE_IDS}
    check(max(discrepancies.values()) <= 1e-8, 'combined seed')
    write_json(args.out / 'controls.json', {'name': name, 'setup': model.setup, 'mixed': mixed, 'cache_hit': hit,
               'rehashed_unphysical': corrupted, 'changed_endpoint': changed, 'stale_reference': stale,
               'malformed': bad, 'nonfinite_candidate_and_coefficient': 'all four rejected', 'nonfinite_references': nonfinite_gates,
               'combined': combined, 'superposition_errors': discrepancies, 'all_counts': dict(model.counts)})
    print(dict(model.counts), discrepancies)


if __name__ == '__main__':
    main()
