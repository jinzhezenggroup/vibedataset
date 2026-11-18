"""Target-specific numerical evidence for small real, closed-shell archived RHF equations."""
from dataclasses import dataclass
import math
import time

import numpy as np

from probe_gqc_residual import array_hash

TOLERANCE = 1e-8
MAX_DIMENSION = 256
SCHEMA = 'vibedataset.discrete_response_error.v1'
EPS = np.finfo(np.float64).eps


def finite(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def gamma(n):
    return n * EPS / (1 - n * EPS)


def disposition(status, reason, **data):
    return {'status': status, 'reason': reason, 'value': None, 'schema': SCHEMA, **data}


def scalar_result(raw, estimate, tolerance, **data):
    if not (math.isfinite(raw) and math.isfinite(estimate) and estimate >= 0):
        return disposition('reject', 'nonfinite value or invalid propagated error')
    accepted = estimate <= tolerance
    return disposition('accepted' if accepted else 'refine', 'within target budget' if accepted else 'target budget exceeded',
                       raw_value=float(raw), value=float(raw) if accepted else None, error_estimate=float(estimate),
                       evidence_level='FP64 discrete-equation numerical estimate', **data)


@dataclass
class StabilityEvidence:
    matrix: np.ndarray | None
    report: dict

    @classmethod
    def from_model(cls, model):
        start = time.perf_counter()
        n = model.dimension
        report = {'schema': SCHEMA, 'problem': model.problem.identity, 'contract': model.contract_identity,
                  'dimension': n, 'ao_to_mo_transforms': 0, 'svd_calls': 0, 'matrix_bytes': 0}
        matrix = None
        try:
            if not 0 < n <= MAX_DIMENSION:
                raise ValueError('dimension outside measured dense evidence domain')
            co, cv = model.co, model.cv
            no, nv = co.shape[1], cv.shape[1]
            foo, fvv = co.T @ model.ref.fock @ co, cv.T @ model.ref.fock @ cv
            # Noncanonical occupied and virtual Fock blocks are part of A=-dFov/dX.
            report['ao_to_mo_transforms'] += 1
            iajb = np.einsum('uvrs,ui,va,rj,sb->iajb', model.eri, co, cv, co, cv, optimize=True)
            report['ao_to_mo_transforms'] += 1
            ijab = np.einsum('uvrs,ui,vj,ra,sb->ijab', model.eri, co, co, cv, cv, optimize=True)
            a = 4 * iajb - iajb.transpose(0, 3, 2, 1) - ijab.transpose(0, 2, 1, 3)
            a += np.einsum('ij,ab->iajb', np.eye(no), fvv) - np.einsum('ij,ab->iajb', foo, np.eye(nv))
            matrix = np.ascontiguousarray(a.reshape(n, n))
            report.update(matrix_bytes=matrix.nbytes, transformed_eri_bytes=iajb.nbytes + ijab.nbytes,
                          matrix_sha256=array_hash(matrix))
            report['svd_calls'] += 1
            s = np.linalg.svd(matrix, compute_uv=False)
            largest, smallest = float(s[0]), float(s[-1])
            skew = float(np.linalg.norm(matrix - matrix.T, ord='fro'))
            effective = smallest - gamma(16 * n) * largest - skew
            if not np.isfinite(s).all() or not math.isfinite(effective) or not smallest > 0:
                raise ValueError('unusable singular spectrum')
            report.update(sigma_min=smallest, sigma_max=largest, effective_sigma=effective, skew_frobenius=skew)
            if skew > 1e-10 * max(1., largest) or effective <= 1e-10 * largest:
                raise ValueError('asymmetric or numerically ill-conditioned response')
            report['status'] = 'available'
        except (ValueError, ArithmeticError, np.linalg.LinAlgError) as error:
            matrix = None
            report.update(status='evidence_unavailable', reason=str(error))
        report['seconds'] = time.perf_counter() - start
        return cls(matrix, report)


def check_direction(model, stability, vector, rhs, readouts, *, measured_residual=None, tolerance=TOLERANCE):
    """Check one physically identified field/adjoint RHS and only the requested contractions.

    measured_residual is the *same solve/column's* returned native true residual,
    for internal normal-solve fallback. External vector proposals must omit it.
    """
    def fail(status, reason):
        return {**disposition(status, reason), 'projections': {k: disposition(status, reason) for k in readouts}}

    if model.problem.identity != stability.report['problem'] or model.contract_identity != stability.report['contract']:
        return fail('reject', 'response problem or operator contract mismatch')
    if stability.matrix is None:
        return fail('evidence_unavailable', stability.report.get('reason', 'no matrix stability evidence'))
    x, b = np.asarray(vector), np.asarray(rhs)
    vectors = [x, b, *(np.asarray(c) for c in readouts.values())]
    if (not math.isfinite(tolerance) or tolerance <= 0 or not readouts or
            any(v.dtype != np.float64 or v.shape != (model.dimension,) or not np.isfinite(v).all() for v in vectors)):
        return fail('reject', 'invalid accuracy, vector shape, precision or nonfinite content')
    a, n = stability.matrix, model.dimension
    dense_action = a @ x
    dense = float(np.linalg.norm(b - dense_action))
    if measured_residual is None:
        applied = model.apply(x)
        residual = float(np.linalg.norm(b - applied))
        action_delta = float(np.linalg.norm(dense_action - applied))
        delta_limit = 1e-10 * max(1., np.linalg.norm(b), np.linalg.norm(applied))
    else:
        residual = float(measured_residual)
        # With a solver-returned residual norm only the reverse triangle test
        # is observable. Charge fresh proposals the full native action above.
        action_delta = abs(dense - residual)
        delta_limit = 1e-10 * max(1., np.linalg.norm(b), np.linalg.norm(dense_action))
    if (not all(map(math.isfinite, (dense, residual, action_delta))) or residual < 0 or action_delta > delta_limit):
        return fail('reject', 'dense response and native residual/action differ')
    residual_rounding = gamma(8 * n + 16) * (np.linalg.norm(b) + np.linalg.norm(np.abs(a) @ np.abs(x)))
    factor = (max(dense, residual) + residual_rounding) / stability.report['effective_sigma']
    projected = {}
    for key, readout in readouts.items():
        c = np.asarray(readout)
        dot_rounding = gamma(2 * n + 4) * float(np.abs(c) @ np.abs(x))
        projected[key] = scalar_result(float(c @ x), np.linalg.norm(c) * factor + dot_rounding, tolerance,
                                       contraction_roundoff=float(dot_rounding), readout_sha256=array_hash(c))
    statuses = {p['status'] for p in projected.values()}
    status = 'reject' if 'reject' in statuses else 'refine' if 'refine' in statuses else 'accepted'
    return {'schema': SCHEMA, 'status': status, 'reason': 'per-readout numerical error estimate',
            'rhs_sha256': array_hash(b), 'vector_sha256': array_hash(x),
            'physical_residual_l2': residual, 'dense_residual_l2': dense, 'action_or_norm_discrepancy': action_delta,
            'residual_roundoff': float(residual_rounding), 'extra_native_actions': int(measured_residual is None),
            'projections': projected}


def linear_combination(terms, divisor=1., *, tolerance=TOLERANCE):
    """Propagate measured term errors through a signed linear readout and division."""
    if not terms or not all(finite(k) for k in (divisor, tolerance)) or divisor == 0 or tolerance <= 0:
        return disposition('reject', 'invalid coefficients or error budget')
    products, errors = [], []
    for coefficient, term in terms:
        if not isinstance(term, dict) or term.get('status') not in ('accepted', 'refine', 'reject', 'evidence_unavailable'):
            return disposition('evidence_unavailable', 'missing or unrecognized term qualification')
        if term['status'] in ('reject', 'evidence_unavailable'):
            return disposition(term['status'], term.get('reason', 'unusable term in scalar relation'))
        if term.get('schema') != SCHEMA:
            return disposition('evidence_unavailable', 'missing or different numerical error protocol')
        value = term.get('raw_value', term.get('value'))
        error = term.get('error_estimate')
        if value is None or error is None:
            return disposition('evidence_unavailable', 'historical value or error estimate missing')
        if not all(finite(k) for k in (value, error, coefficient)) or error < 0:
            return disposition('reject', 'nonfinite coefficient or invalid operand evidence')
        products.append(coefficient * value)
        errors.append(abs(coefficient) * error)
    if not all(map(math.isfinite, products + errors)):
        return disposition('reject', 'linear combination overflow')
    try:
        total = math.fsum(products)
        scale = math.fsum(map(abs, products))
        propagated = math.fsum(errors) / abs(divisor)
    except OverflowError:
        return disposition('reject', 'linear combination overflow')
    rounding = gamma(2 * len(terms) + 4) * scale / abs(divisor)
    ratio = scale / abs(total) if total else None
    return scalar_result(total / divisor, propagated + rounding, tolerance, propagated_error=propagated,
                         roundoff_allowance=rounding, absolute_term_sum=scale,
                         cancellation_ratio=ratio if ratio is None or math.isfinite(ratio) else None)
