"""Exact row-space checks for the finite three-field comparison."""
from fractions import Fraction
from functools import lru_cache
from itertools import combinations, product

import numpy as np
from response_cover import plan_cover
from response_field_plan import plan_field_block

FIELDS = ('x', 'y', 'z')
OBS = ('q0', 'r2', 'zz')
SINGLE = tuple(zip(FIELDS, OBS))
ALL = tuple(product(FIELDS, OBS))
CYCLE = (('y', 'q0'), ('z', 'r2'), ('x', 'zz'))
CROSS = (('y', 'q0'), ('x', 'r2'))
SCENARIOS = {'cycle-one': ('cycle', SINGLE[:1]), 'cycle-three': ('cycle', SINGLE), 'cross-three': ('cross', SINGLE)}
HISTORIES = {'cycle': CYCLE, 'cross': CROSS}
MIXED = ('xy', 'yz', 'xz', 'xyz')
STRATEGIES = ('direct', 'adjoint', 'single', 'two', 'hand_field', 'hand_adjoint',
              'vectors', 'vectors_gzip', 'table_field', 'table_adjoint', 'dense', 'table_dense')


def spec(axis):
    return tuple(int(f in axis) for f in FIELDS)


def ordinary(requests, axis, names=None):
    outputs = []
    for f, o in requests:
        col, partner = (f, o) if (axis == 'field' or (axis == 'cover' and f in names)) else (o, f)
        outputs.append((f, o, ((col, partner, 1),)))
    return make(outputs)


def make(outputs):
    columns = set()
    for f, o, terms in outputs:
        identity = [0, 0, 0]
        for col, partner, weight in terms:
            if col in OBS:
                if (col, partner) != (o, f):
                    raise ValueError('wrong adjoint contraction')
                row = spec(f)
            else:
                if partner != o:
                    raise ValueError('unrelated observable')
                row = spec(col.removeprefix('H:'))
            identity = [i + weight * j for i, j in zip(identity, row)]
            if not col.startswith('H:'):
                columns.add(col)
        if tuple(identity) != spec(f):
            raise ValueError(f'reconstruction changes {f}/{o}')
    order = (*MIXED, *FIELDS, *OBS)
    return tuple(k for k in order if k in columns), tuple(outputs)


def decode_for(f, o, columns, known):
    # Any independent subset of at most three binary rows suffices in R^3.
    # The determinant of a 3x3 0/1 matrix has magnitude at most two. Check
    # each reconstructed rational identity exactly, including smaller ranks.
    names = (*columns, *('H:' + a for a, readout in known if readout == o))
    for n in range(1, min(3, len(names)) + 1):
        choices = []
        for subset in combinations(names, n):
            m = np.array([spec(c.removeprefix('H:')) for c in subset]).T
            x, _, rank, _ = np.linalg.lstsq(m, spec(f), rcond=None)
            if rank < n:
                continue
            w = tuple(Fraction(float(t)).limit_denominator(2) for t in x)
            if any(t == 0 for t in w) or tuple(sum(int(a) * b for a, b in zip(row, w)) for row in m) != spec(f):
                continue
            terms = tuple((c, o, float(t)) for c, t in zip(subset, w))
            choices.append((sum(not c.startswith('H:') for c in subset), sum(map(abs, w)), terms))
        if choices:
            return min(choices)[-1]
    return None


def single(requests, known):
    p = plan_field_block(requests, known)
    outputs = list(ordinary(p.ordinary_requests, 'cover', p.fields)[1])
    for (f, o), old in p.operands.items():
        terms = ((''.join(p.support), o, 1), *(('H:' + a, b, -1) for a, b in old))
        outputs.append((f, o, terms))
    return make(sorted(outputs))


def score(plan):
    cols, outputs = plan
    projections = {(c, p) for _, _, terms in outputs for c, p, _ in terms if not c.startswith('H:')}
    return len(cols), len(projections), sum(len(terms) for _, _, terms in outputs)


def two(requests, known):
    best = single(requests, known)
    if len(best[0]) < 2:
        return best
    for cols in combinations(MIXED, 2):
        outputs = []
        for f, o in requests:
            terms = decode_for(f, o, cols, known)
            if terms is None:
                break
            outputs.append((f, o, terms))
        else:
            proposal = make(outputs)
            if score(proposal) < score(best):
                best = proposal
    return best


def multi(requests, known):
    """Search the finite one-, two- and three-mixed-field candidate set.

    The response lives in a three-dimensional field space.  This bounded
    search therefore includes every subset of the four registered binary
    fields up to three columns.  It is intentionally separate from ``two``
    so that a finite multi-field claim can be checked even when the selected
    plan is unchanged.
    """
    best = single(requests, known)
    for size in range(1, min(3, len(MIXED)) + 1):
        for cols in combinations(MIXED, size):
            outputs = []
            for f, o in requests:
                terms = decode_for(f, o, cols, known)
                if terms is None:
                    break
                outputs.append((f, o, terms))
            else:
                proposal = make(outputs)
                if score(proposal) < score(best):
                    best = proposal
    return best


def hand(requests, known, orientation):
    if len(requests) == 1:
        return ordinary(requests, orientation)
    if set(CYCLE) <= set(known):
        return make([('x', 'q0', (('xy', 'q0', 1), ('H:y', 'q0', -1))),
                     ('y', 'r2', (('yz', 'r2', 1), ('H:z', 'r2', -1))),
                     ('z', 'zz', (('yz', 'zz', 1), ('xy', 'zz', -1), ('H:x', 'zz', 1)))])
    if set(CROSS) <= set(known):
        return make([('x', 'q0', (('xy', 'q0', 1), ('H:y', 'q0', -1))),
                     ('y', 'r2', (('xy', 'r2', 1), ('H:x', 'r2', -1))),
                     *ordinary(requests[-1:], orientation)[1]])
    return ordinary(requests, orientation)


@lru_cache(maxsize=256)
def compile_plan(method, requests, known, stored):
    if method == 'single':
        return single(requests, known)
    if method == 'two':
        return two(requests, known)
    if method == 'multi':
        return multi(requests, known)
    if method.startswith('hand_'):
        return hand(requests, known, method.split('_')[1])
    if method == 'vectors':
        stored = set(stored)
        free_f, free_o = stored.intersection(FIELDS), stored.intersection(OBS)
        fnew, onew = plan_cover(requests, free_f, free_o)
        required = [(f, o) for f, o in requests if f not in fnew and o not in onew]
        cover = next(set(s) for n in range(len(stored) + 1) for s in combinations(sorted(stored), n)
                     if all(f in s or o in s for f, o in required))
        return ordinary(requests, 'cover', set(fnew) | cover.intersection(FIELDS))
    return ordinary(requests, {'direct': 'field', 'adjoint': 'observable', 'dense': 'field'}[method])
