"""Compare sparse simultaneous coloring with exact unit row/column coverage."""
import hashlib
from itertools import combinations
import json
from pathlib import Path
import platform
import subprocess
from time import perf_counter

import numpy as np
import openmdao
from openmdao.utils.coloring import _compute_coloring
from scipy.sparse import coo_matrix

ROOT = Path('_references/openmdao_3_45_2')
PIN = '64175aa55fb541355b2fb279a6bcfde01e17a878'
N = 6
TOL = 1e-12


def minimum_cover(mask):
    """Exhaustive unit-seed reference for this six-by-six fixture."""
    rows, cols = np.where(mask)
    for size in range(2 * N + 1):
        for choices in combinations(range(2 * N), size):
            if all(i in choices or N + j in choices for i, j in zip(rows, cols, strict=True)):
                return choices
    raise AssertionError('uncoverable edge')


class Response:
    """J = C.T A^-1 B with an exact, prescribed analytical result for validation."""
    def __init__(self, target):
        self.a = 2 * np.eye(N) + np.diag(np.full(N - 1, 0.25), 1) - np.diag(np.ones(N - 1), -1)
        self.b = np.eye(N)
        self.c = (target @ self.a).T

    def product(self, mode, seed):
        if mode == 'fwd':
            return self.c.T @ np.linalg.solve(self.a, self.b @ seed)
        return self.b.T @ np.linalg.solve(self.a.T, self.c @ seed)


def colored(response, support, direct, known=None):
    coloring = _compute_coloring(coo_matrix(support), mode='auto', direct=direct)
    result = np.zeros(support.shape)
    groups = {}
    for mode in ('fwd', 'rev'):
        count = coloring.total_solves(fwd=mode == 'fwd', rev=mode == 'rev')
        if not count:
            groups[mode] = []
            continue
        seeds = coloring.tangent_matrix(mode)
        groups[mode] = [np.flatnonzero(seed).tolist() for seed in seeds]
        products = []
        for seed in seeds:
            product = response.product(mode, seed)
            if known is not None:
                product -= (known if mode == 'fwd' else known.T) @ seed
            products.append(product)
        compressed = np.stack(products, axis=1 if mode == 'fwd' else 0)
        for values, indices, position in coloring.colored_jac_iter(compressed, mode):
            if mode == 'fwd':
                result[indices, position] = values
            else:
                result[position, indices] = values
    if coloring._subtractions:
        coloring._apply_subtractions(result)
    return result, groups, len(coloring._subtractions or ())


def compare(name, target, support, requests, known=None):
    response = Response(target)
    cover = minimum_cover(requests)
    by_units = np.full((N, N), np.nan)
    eye = np.eye(N)
    for vertex in cover:
        if vertex < N:
            by_units[vertex, :] = response.product('rev', eye[vertex])
        else:
            j = vertex - N
            by_units[:, j] = response.product('fwd', eye[j])
    unit_error = float(np.max(np.abs((by_units - target)[requests])))
    if unit_error > TOL:
        raise AssertionError(f'{name} unit recovery')
    rows = []
    for direct in (True, False):
        matrix, groups, n_subs = colored(response, support, direct, known)
        if known is not None:
            matrix += known
        error = float(np.max(np.abs((matrix - target)[requests])))
        expect_valid = name != 'dense_diagonal_mislabeled_as_support'
        if (error <= TOL) != expect_valid:
            raise AssertionError(f'{name} coloring direct={direct} wrong classification')
        rows.append(dict(direct=direct, seed_indices=groups, seed_count=sum(map(len, groups.values())),
                         subtractions=n_subs, max_requested_error=error))
    return dict(case=name, requests=int(requests.sum()), physical_nonzeros=int(np.count_nonzero(target)),
                declared_coloring_pattern=int(support.sum()), prior_known_nonzeros=int(np.count_nonzero(known)) if known is not None else 0,
                eligible_unit_cover=list(cover), unit_solve_count=len(cover), unit_max_error=unit_error, coloring=rows)


def main():
    if Path(openmdao.__file__).resolve().parent != ROOT.resolve() / 'openmdao':
        raise ValueError('load the pinned OpenMDAO checkout using PYTHONPATH')
    if subprocess.check_output(['git','-C',ROOT,'rev-parse','HEAD'],text=True).strip() != PIN:
        raise ValueError('OpenMDAO source mismatch')
    if subprocess.check_output(['git','-C',ROOT,'status','--porcelain']):
        raise ValueError('OpenMDAO tree is dirty')
    start = perf_counter()
    diag = np.eye(N, dtype=bool)
    arrow = diag.copy()
    arrow[-1, :] = True
    arrow[:, -1] = True
    cross = arrow & ~diag
    cross[-1, -1] = True
    full = np.ones_like(diag)
    # Positive integer entries make unobserved off-diagonal interference unambiguous.
    dense = np.arange(1, N * N + 1).reshape(N,N).astype(float)
    cases = [
        compare('structurally_diagonal', dense * diag, diag, diag),
        compare('structurally_arrow', dense * arrow, arrow, arrow),
        compare('dense_conservative_structure_diagonal_request', dense, full, diag),
        compare('dense_diagonal_mislabeled_as_support', dense, diag, diag),
        compare('dense_known_offdiagonals_subtracted', dense, diag, diag, dense * ~diag),
        compare('dense_full_row_plus_column', dense, full, cross),
    ]
    # Reciprocity is extra information beyond the arbitrary dense matrix model.
    symmetric = np.eye(N) + np.arange(1, N+1)[:,None] * np.arange(1,N+1)
    # B=C=I gives a genuinely symmetric susceptibility for this auxiliary example.
    covector = np.linalg.solve(np.linalg.inv(symmetric), np.eye(N)[-1])
    symmetry_error = float(max(np.max(abs(covector - symmetric[-1, :])), np.max(abs(covector - symmetric[:, -1]))))
    if symmetry_error > TOL:
        raise AssertionError('symmetric example exceeded tolerance')
    print(json.dumps(dict(pin=PIN,program='OpenMDAO',version=openmdao.__version__,python=platform.python_version(),
                          numpy=np.__version__,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          tolerance=TOL, cases=cases, symmetric_cross=dict(unit_graph_cost=len(minimum_cover(cross)),
                          solves_using_reciprocity=1,max_error=symmetry_error),
                          elapsed_seconds=perf_counter()-start, qc_calls=0), indent=2,allow_nan=False))


if __name__ == '__main__':
    main()
