#!/usr/bin/env python3
"""Numerical failure controls for the target-evidence functions, independent of QM9 evaluation."""
from argparse import ArgumentParser
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from target_response_quality import SCHEMA, StabilityEvidence, check_direction, linear_combination, scalar_result


def main():
    p = ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    out = p.parse_args().out
    # One occupied AO and two virtual AOs, diagonal F, zero ERIs.
    # A = diag(1,1e-12) exactly in the prescribed frame.
    c = np.eye(3)
    model = SimpleNamespace(dimension=2, co=c[:, :1], cv=c[:, 1:], eri=np.zeros((3, 3, 3, 3)),
                            ref=SimpleNamespace(fock=np.diag([0., 1., 1e-12])),
                            problem=SimpleNamespace(identity='two-mode-control'), contract_identity='unit-coordinate',
                            apply=lambda x: np.array([x[0], 1e-12 * x[1]]))
    stability = StabilityEvidence.from_model(model)
    b, vector, readout = np.array([0., 1e-12]), np.zeros(2), np.array([0., 1.])
    true_error = 1.
    norm = float(np.linalg.norm(b - model.apply(vector)))
    weak = check_direction(model, stability, vector, b, {'q': readout})
    assert norm <= 1e-10 and true_error > 1e-8 and stability.matrix is None
    assert weak['projections']['q']['status'] == 'evidence_unavailable'
    # Large comparable terms yield a small observable while absolute rounding
    # contributions remain substantial, even if each operand is treated exact.
    large = [scalar_result(x, 0., 1e-8) for x in (1e12 + 1., 1e12)]
    cancellation = linear_combination([(2., large[0]), (-2., large[1])], divisor=2.)
    assert cancellation['status'] == 'refine' and cancellation['raw_value'] == 1.
    assert cancellation['roundoff_allowance'] > 1e-8 and cancellation['cancellation_ratio'] > 1e12
    bounded = scalar_result(2., 5e-8, 1e-8)
    downweighted = linear_combination([(1., bounded)], divisor=100.)
    assert bounded['status'] == 'refine' and downweighted['status'] == 'accepted'
    invalid = {}
    for key, record in {'unknown_status': dict(status='ungraded', value=2., error_estimate=0.),
                        'wrong_protocol': dict(status='accepted', schema='other', value=2., error_estimate=0.),
                        'overflow': dict(status='accepted', schema=SCHEMA, value=10 ** 400, error_estimate=0.),
                        'missing_error': dict(status='accepted', schema=SCHEMA, value=2.)}.items():
        invalid[key] = linear_combination([(1., record)])
        assert invalid[key]['status'] in ('reject', 'evidence_unavailable') and invalid[key]['value'] is None
    report = dict(weak_mode=dict(stability=stability.report, residual=norm, readout_error=true_error, decision=weak),
                  signed_coefficient_cancellation=cancellation, downweighted_interval=downweighted,
                  invalid_terms=invalid, issued_physical_jk=0, result='passed')
    out.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
