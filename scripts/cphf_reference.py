"""Numerical qualification of small, real closed-shell RHF field responses."""
import inspect
import time

import numpy as np
from pyscf import lib
from pyscf.scf import cphf


SCHEMA = 'vibedataset.cphf_reference.v2'
RESIDUAL_TOL = 1e-10
READOUT_BUDGET = 1e-9
MAX_DIMENSION = 256


def precision_reasons(schema, evidence):
    if schema != SCHEMA:
        return ['unverified CPHF reference version']
    if not isinstance(evidence, dict):
        return ['missing independent CPHF precision evidence']
    reasons = []
    for key, limit in (('physical_residual_l2', RESIDUAL_TOL), ('readout_error_estimate', READOUT_BUDGET)):
        value = evidence.get(key)
        if type(value) not in (float, int) or not 0 <= value <= limit:
            reasons.append('unqualified ' + key)
    return reasons


def ao_operators(mol, overlap):
    """Integrate the fields and readouts at the protocol origin in PySCF's AO basis."""
    n = mol.nao_nr()
    with mol.with_common_orig((0., 0., 0.)):
        fields = mol.intor('int1e_r', comp=3)
        moments = mol.intor('int1e_rr', comp=9).reshape(3, 3, n, n)
    lo, hi = mol.aoslice_by_atom()[0, 2:]
    mask = np.zeros(n)
    mask[lo:hi] = 1
    charge = -0.5 * (mask[:, None] + mask[None, :]) * overlap
    return fields, np.stack((charge, moments.trace(axis1=0, axis2=1), moments[2, 2]))


class KrylovTrace(lib.logger.Logger):
    """Collect the trial norms logged by the unmodified, pinned Krylov implementation."""
    def __init__(self):
        super().__init__(verbose=lib.logger.QUIET)
        self.norms = []

    def debug(self, msg, *args):
        if msg == 'krylov cycle %d  r = %g':
            self.norms.append(float(args[1]))


def solve_reference(zero, eri, fields, observables, report, counts):
    """Solve A U = -h_ai and check it with a fresh AO density response.

    A is assembled from transformed ERIs. The Krylov solver and the physical
    residual check instead use PySCF's AO J/K. Neither consumes a GQC vector.
    """
    occ = zero.mo_occ > 0
    co, cv = zero.mo_coeff[:, occ], zero.mo_coeff[:, ~occ]
    gap = zero.mo_energy[~occ, None] - zero.mo_energy[None, occ]
    nvir, nocc = gap.shape
    n = gap.size
    report.update(dimension=n, nvir=nvir, nocc=nocc)
    if n > MAX_DIMENSION or not n or not np.all(gap > 0):
        raise ValueError('outside dense reference dimensions or positive-gap RHF convention')
    h = np.einsum('ua,kuv,vi->kai', cv, fields, co)
    w = (4 * np.einsum('ua,quv,vi->qai', cv, observables, co)).reshape(-1, n)

    def density(u):
        half = 2 * np.einsum('ua,kai,vi->kuv', cv, u, co)
        return half + half.transpose(0, 2, 1)

    def potential(u):
        counts['jk_calls'] += 1
        counts['density_columns'] += len(u)
        j, k = zero.get_jk(dm=density(u), hermi=1)
        return np.einsum('ua,kuv,vi->kai', cv, j - 0.5 * k, co)

    # (ai|bj), (ab|ij) in the independent canonical zero-field MO basis
    start = time.perf_counter()
    counts['ao_to_mo_transforms'] += 1
    aibj = np.einsum('pqrs,pa,qi,rb,sj->aibj', eri, cv, co, cv, co, optimize=True)
    counts['ao_to_mo_transforms'] += 1
    abij = np.einsum('pqrs,pa,qb,ri,sj->abij', eri, cv, cv, co, co, optimize=True)
    a = (4 * aibj - aibj.transpose(0, 3, 2, 1) - abij.transpose(0, 2, 1, 3)).reshape(n, n)
    a += np.diag(gap.ravel())
    counts['singular_value_decompositions'] += 1
    s = np.linalg.svd(a, compute_uv=False)
    eps = np.finfo(float).eps
    symmetry = float(np.max(abs(a - a.T)))
    report.update(sigma_min=float(s[-1]), sigma_max=float(s[0]), symmetry_error=symmetry,
                  assembly_and_svd_seconds=time.perf_counter() - start)
    if symmetry > RESIDUAL_TOL or not np.isfinite(s).all() or s[-1] <= n * eps * s[0]:
        raise ValueError('asymmetric or numerically singular dense CPHF equation')
    report.update(condition_number=float(s[0] / s[-1]), rhs_minus_h_ai=(-h).tolist(),
                  readout_rows_ai=w.tolist(), gaps_ai=gap.tolist())

    def inspect_solution(u):
        if not np.isfinite(u).all():
            raise ValueError('nonfinite CPHF solution')
        x = u.reshape(len(h), n)
        # Check against both the assembled matrix and an independently applied
        # unpreconditioned AO operator, with the physical sign of h(F)=h0+F*r.
        r = h + gap * u + potential(u)
        physical = np.linalg.norm(r.reshape(len(h), n), axis=1)
        assembled = np.linalg.norm(x @ a.T + h.reshape(len(h), n), axis=1)
        q = np.einsum('quv,kvu->kq', observables, density(u))
        contraction = abs(q - x @ w.T)
        # For the represented linear system |dQ| <= ||w|| ||r|| / sigma_min.
        # Use both measured residuals, the observed contraction discrepancy,
        # and a rounding allowance for the dense matvec and dot product.
        gamma = (n + 1) * eps / (1 - (n + 1) * eps)
        rounding = gamma * np.linalg.norm(abs(x) @ abs(a.T) + abs(h.reshape(len(h), n)), axis=1)
        estimate = ((np.maximum(physical, assembled) + rounding)[:, None] * np.linalg.norm(w, axis=1) / s[-1]
                    + contraction + gamma * (abs(x) @ abs(w.T)))
        preconditioned = np.linalg.norm((r / gap).reshape(len(h), n), axis=1)
        if not all(np.isfinite(v).all() for v in (q, physical, assembled, preconditioned, estimate)):
            raise ValueError('nonfinite CPHF residual or readout evidence')
        return dict(solution_ai=u.tolist(), labels=q.tolist(), physical_residual_l2=physical.tolist(),
                    assembled_residual_l2=assembled.tolist(), preconditioned_residual_l2=preconditioned.tolist(),
                    readout_error_estimate=estimate.tolist())

    # Keep the published solver as a diagnostic even when it fails to return.
    trace = KrylovTrace()
    tol = 1e-12
    lindep = inspect.signature(lib.krylov).parameters['lindep'].default
    qr_cutoff = inspect.signature(lib.linalg_helper._qr).parameters['lindep'].default
    legacy = dict(tol=tol, lindep_squared_norm=lindep, block_qr_squared_norm=qr_cutoff,
                  max_cycle=200, effective_max_cycle=min(n, 200))
    report['krylov'] = legacy
    before = counts.copy()
    start = time.perf_counter()
    try:
        counts['krylov_solves'] += 1
        u, _ = cphf.solve(potential, zero.mo_energy, zero.mo_occ, h, tol=tol, max_cycle=200, verbose=trace)
        if trace.norms:
            last = trace.norms[-1]
            legacy['termination'] = 'trial norm below tolerance and/or QR truncation' if last < tol else 'linear dependence threshold'
        else:
            legacy['termination'] = 'initial trial space below threshold'
        legacy.update(inspect_solution(u))
    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
        legacy.update(termination='exception', error=str(exc))
    legacy.update(trial_norms=trace.norms, counts=dict(counts - before), seconds=time.perf_counter() - start)

    before = counts.copy()
    start = time.perf_counter()
    counts['dense_solves'] += 1
    counts['dense_rhs'] += len(h)
    x = np.linalg.solve(a, -h.reshape(len(h), n).T).T.reshape(h.shape)
    dense = inspect_solution(x)
    dense.update(termination='dense solve returned, measured residual and readout gates per target',
                 counts=dict(counts - before), seconds=time.perf_counter() - start)
    report['dense'] = dense
    return dense['labels']
