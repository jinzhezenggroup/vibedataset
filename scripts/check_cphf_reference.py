#!/usr/bin/env python3
"""Reproduce an inaccurate finite Krylov solution and the independent 77-D molecular control."""
from argparse import ArgumentParser
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
from pyscf import lib

from cphf_reference import READOUT_BUDGET, RESIDUAL_TOL, SCHEMA
from gqc_dual_response import ANALYTIC_TOL, FIELD_IDS, OBSERVABLE_IDS, assess_scalar
from probe_gqc_dual_response import validate_case
from probe_gqc_residual import ROOT, check, file_hash, write_json


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    e = np.array([[0., 2e-7], [2e-7, 0.]])
    b = np.array([1., 0.])
    x = lib.krylov(lambda u: u @ e.T, b, tol=1e-12, max_cycle=200)
    residual = float(np.linalg.norm((np.eye(2) + e) @ x - b))
    check(np.isfinite(x).all() and residual > RESIDUAL_TOL, 'Krylov control should fail the physical gate')

    exp = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
    assets = exp / 'qm9_response_assets'
    name = 'qm9-000010'
    row = next(r for r in json.loads((assets / 'index.json').read_bytes())['rows'] if r.get('name') == name)
    meta, arrays = (assets / row[k] for k in ('metadata_file', 'array_file'))
    check((file_hash(meta), file_hash(arrays)) == (row['metadata_sha256'], row['array_file_sha256']),
          'molecular control source digest')
    oracle = validate_case(meta, arrays, args.out, expected_identity=row['reference_identity'])
    write_json(args.out / 'oracle.json', oracle)
    s = oracle['independent']['cphf_solver']
    old = json.loads((exp / 'gqc_dual_response/oracles' / (name + '.json')).read_bytes())
    reproduced = np.max(abs(np.array(old['independent']['cphf']) - s['krylov']['labels']))
    check(s['dimension'] == 77 and reproduced < 1e-9, 'reproduce the finite v1 molecular readouts')
    check(min(s['krylov']['physical_residual_l2']) > 1e-7 and max(s['dense']['physical_residual_l2']) <= RESIDUAL_TOL,
          'fresh AO residuals must distinguish the two solvers')
    check(sum(c['reasons'] == ['cphf'] for f in old['targets'].values() for c in f.values()) == 8,
          'v1 rejection denominator')
    endpoint = oracle['setup']['endpoint_identities']
    for f in FIELD_IDS:
        for o in OBSERVABLE_IDS:
            cell = oracle['targets'][f][o]
            check(cell['qualified'] and assess_scalar(oracle, endpoint, f, o, cell['direct'])['qualified'],
                  'fresh molecular target gate')

    # Keep all readouts and saved qualification flags finite and unchanged.
    # Each independent defect must still withhold the candidate at consumption.
    target = oracle['targets']['x']['q0']['direct']
    controls = {}
    for label, version, precision in [
        ('legacy', None, {'physical_residual_l2': 0., 'readout_error_estimate': 0.}),
        ('actual_krylov_residual', SCHEMA, {'physical_residual_l2': residual, 'readout_error_estimate': 0.}),
        ('ill_conditioned_readout', SCHEMA, {'physical_residual_l2': 1e-14, 'readout_error_estimate': 2 * READOUT_BUDGET}),
        ('missing_evidence', SCHEMA, None),
    ]:
        example = deepcopy(oracle)
        example['schema'] = version
        example['targets']['x']['q0']['reference_precision'] = precision
        grade = assess_scalar(example, endpoint, 'x', 'q0', target)
        check(grade['status'] == 'oracle_unqualified' and grade['qualified'] is None and grade['value'] is None,
              'unqualified reference published a label: ' + label)
        controls[label] = grade['reasons']
    wrong = assess_scalar(oracle, endpoint, 'x', 'q0', target + 2 * ANALYTIC_TOL)
    check(wrong['status'] == 'withheld' and wrong['qualified'] is False, 'wrong candidate at a qualified reference')
    write_json(args.out / 'verification.json', dict(
        krylov_solution=x.tolist(), physical_residual_l2=residual, status_controls=controls,
        inaccurate_candidate=wrong, legacy_max_readout_difference=float(reproduced),
        oracle_sha256=file_hash(args.out / 'oracle.json'), molecular_targets_checked=9))


if __name__ == '__main__':
    main()
