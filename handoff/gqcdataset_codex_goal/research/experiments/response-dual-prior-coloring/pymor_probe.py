"""Exercise pyMOR's primal/dual reduced output correction and coercivity input."""
import hashlib
import json
from pathlib import Path
import subprocess
from time import perf_counter

import numpy as np
import pymor
from pymor.models.basic import StationaryModel
from pymor.operators.numpy import NumpyMatrixOperator
from pymor.parameters.functionals import ConstantParameterFunctional
from pymor.reductors.dwr import DWRCoerciveRBReductor

PIN = '36a0035e180694c7ad4eb8f083d9f1d65ceb6f42'


def main():
    root = Path('_references/pymor_2026_1')
    if Path(pymor.__file__).resolve().parent != root.resolve() / 'src/pymor':
        raise ValueError('load the pinned pyMOR source using PYTHONPATH')
    if subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True).strip() != PIN:
        raise ValueError('pyMOR source pin')
    if subprocess.check_output(['git','-C',root,'status','--porcelain']):
        raise ValueError('pyMOR tree is dirty')
    started = perf_counter()
    matrix = np.diag([1., 1.5, 2.])
    inputs = np.array([[1.,2.,3.]]).T
    readouts = np.array([[2.,1.,0.],[0.,1.,1.]])
    op = NumpyMatrixOperator(matrix)
    m = StationaryModel(op, op.range.from_numpy(inputs), NumpyMatrixOperator(readouts))
    truth = (readouts @ np.linalg.solve(matrix, inputs)).ravel()
    e = np.eye(3)
    bases = [op.source.from_numpy(e[:,j:j+1]) for j in range(3)]
    plain = (readouts @ np.array([1.,0.,0.])).tolist()
    try:
        DWRCoerciveRBReductor(m, primal_RB=bases[0], dual_RBs=bases[1:])
    except AssertionError as error:
        default_dual = type(error).__name__
    else:
        default_dual = 'constructed'
    # Supply one explicit dual model per readout in the sign convention of create_dual_model.
    duals = [StationaryModel(op.H, op.source.from_numpy(-row)) for row in readouts]
    rows = []
    for alpha in [1., 1000.]:
        reductor = DWRCoerciveRBReductor(m, dual_foms=duals, primal_RB=bases[0], dual_RBs=bases[1:],
                                        coercivity_estimator=ConstantParameterFunctional(alpha))
        t = perf_counter()
        reduced = reductor.reduce()
        reduction = perf_counter() - t
        t = perf_counter()
        corrected, estimate = reduced.output(return_error_estimate=True)
        actual = np.abs(truth - np.ravel(corrected))
        covered = bool(np.all(actual <= np.ravel(estimate) + 1e-12))
        if not np.allclose(np.ravel(corrected), [10./3., 1.5]) or covered != (alpha == 1.):
            raise AssertionError('unexpected dual-residual output or estimate')
        rows.append(dict(assumed_coercivity=alpha, corrected=corrected.ravel().tolist(),
                         estimator=estimate.ravel().tolist(), actual_errors=actual.tolist(),
                         covered=covered, reduce_seconds=reduction, output_seconds=perf_counter()-t))
    print(json.dumps(dict(source_pin=PIN,version=pymor.__version__, driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          A=matrix.tolist(), b=inputs.ravel().tolist(), readouts=readouts.tolist(), true_coercivity=1.,
                          primal_basis='e1',dual_bases=['e2','e3'],full_reference=truth.tolist(),
                          uncorrected=plain, default_vector_output_dual_construction=default_dual,
                          cases=rows, elapsed_seconds=perf_counter()-started,
                          scope='Controlled three-dimensional Euclidean SPD model. No chemical error certificate.'),indent=2))


if __name__ == '__main__':
    main()
