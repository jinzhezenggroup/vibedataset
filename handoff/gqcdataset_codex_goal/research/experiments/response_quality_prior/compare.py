#!/usr/bin/env python3
"""Run the registered DWR control using the pinned original pyMOR implementation."""
from argparse import ArgumentParser
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[5]
PYMOR = ROOT / '_references/pymor_2026_1'
PIN = '36a0035e180694c7ad4eb8f083d9f1d65ceb6f42'
sys.path.insert(0, str(PYMOR / 'src'))
import pymor
from pymor.models.basic import StationaryModel
from pymor.operators.numpy import NumpyMatrixOperator
from pymor.parameters.functionals import ConstantParameterFunctional
from pymor.reductors.dwr import DWRCoerciveRBReductor


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out
    out.mkdir(parents=True, exist_ok=False)
    if (subprocess.check_output(['git', '-C', PYMOR, 'rev-parse', 'HEAD'], text=True).strip() != PIN
            or subprocess.check_output(['git', '-C', PYMOR, 'status', '--porcelain'])
            or Path(pymor.__file__).resolve().parent != (PYMOR / 'src/pymor').resolve()):
        raise ValueError('pyMOR source identity mismatch')
    minimum, component = Fraction(1, 2**33), Fraction(1, 2**35)
    matrix = np.diag([1., float(minimum), 2.])
    rhs = np.array([1., float(component), 0.])
    readout = np.array([0., 1., 0.])
    op = NumpyMatrixOperator(matrix)
    full = StationaryModel(op, op.range.from_numpy(rhs), NumpyMatrixOperator(readout[None, :]))
    basis = [op.source.from_numpy(col) for col in np.eye(3)]
    tolerance = 1e-8

    # Each candidate/estimate is produced before the analytical target is examined.
    costs = []
    for dual, description in [(2, 'unresolved_output_mode'), (1, 'resolved_output_mode')]:
        for alpha in [float(minimum), 1.]:
            start = perf_counter()
            reductor = DWRCoerciveRBReductor(full, primal_RB=basis[0], dual_RBs=[basis[dual]],
                                             coercivity_estimator=ConstantParameterFunctional(alpha))
            reduced = reductor.reduce()
            reduction_seconds = perf_counter() - start
            start = perf_counter()
            q, estimate = reduced.output(return_error_estimate=True)
            costs.append(dict(dual_basis=description, supplied_alpha=alpha,
                              q_corrected=float(q.item()), dwr_estimate=float(estimate.item()),
                              accepted=float(estimate.item()) <= tolerance,
                              reduction_seconds=reduction_seconds, evaluate_seconds=perf_counter() - start))
    truth = component / minimum
    for row in costs:
        row['error'] = abs(row['q_corrected'] - float(truth))
        row['false_accept'] = row['accepted'] and row['error'] > tolerance
    q0 = float(readout @ np.eye(3)[0])
    r0 = float(np.linalg.norm(rhs - matrix @ np.eye(3)[0]))
    report = dict(pymor_commit=PIN, pymor=pymor.__version__, numpy=np.__version__, scipy=scipy.__version__,
                  python=platform.python_version(), threads={k: os.environ.get(k) for k in
                     ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS')},
                  code_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), basis_order='e1,e2,e3',
                  matrix=matrix.tolist(), rhs=rhs.tolist(), readout=readout.tolist(),
                  represented_exact_minimum=str(minimum), exact_target=str(truth), tolerance=tolerance, cases=costs,
                  residual_only=dict(candidate=q0, physical_residual=r0, residual_gate=1e-10,
                                     accepted=r0 <= 1e-10, observed_error=abs(q0 - float(truth))))
    (out / 'pymor.json').write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + '\n')
    if not (r0 <= 1e-10 and abs(q0 - float(truth)) > tolerance):
        raise ValueError('the small-residual control did not challenge the proposed rule')


if __name__ == '__main__':
    main()
