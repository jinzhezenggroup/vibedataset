#!/usr/bin/env python3
"""Use exact rational span tests and an independent exhaustive cover to check field plans."""
from fractions import Fraction
from itertools import combinations, product
import json

from response_field_plan import AXES, SUPPORTS, plan_field_block

OBS = ('q0','r2','zz')
PAIRS = tuple(product(AXES, OBS))
UNITS = tuple(tuple(int(j == i) for j in range(3)) for i in range(3))
ALL = (1 << len(PAIRS))-1


def rank(rows):
    matrix = [[Fraction(x) for x in r] for r in rows]
    found = 0
    for j in range(3):
        pivot = next((i for i in range(found,len(matrix)) if matrix[i][j]), None)
        if pivot is None:
            continue
        matrix[found],matrix[pivot] = matrix[pivot],matrix[found]
        scale = matrix[found][j]
        matrix[found] = [x/scale for x in matrix[found]]
        for i in range(found+1,len(matrix)):
            weight = matrix[i][j]
            matrix[i] = [a-weight*b for a,b in zip(matrix[i],matrix[found])]
        found += 1
    return found


def mask(pairs):
    return sum(1 << PAIRS.index(x) for x in pairs)


def unmask(bits):
    return {edge for i,edge in enumerate(PAIRS) if bits & (1 << i)}


def endpoint_mask(fields, observables):
    return mask(e for e in PAIRS if e[0] in fields or e[1] in observables)


def compare(known, desired, cached_fields, cached_obs, spare, plain, convertible):
    k,d = mask(known),mask(desired)
    remaining = d & ~spare
    bounds = [plain[remaining]] + [1+plain[remaining & ~cover] for cover in convertible[k]]
    selected = plan_field_block(desired, known, cached_fields, cached_obs)
    assert selected.new_rhs == min(bounds), (known,desired,cached_fields,cached_obs,selected,bounds)
    assert set(selected.ordinary_requests).isdisjoint(selected.operands)
    assert set(selected.ordinary_requests).union(selected.operands) == desired
    available = spare | endpoint_mask(selected.fields, selected.observables)
    assert (mask(selected.ordinary_requests) & ~available) == 0
    # Reproduce every reconstructed value on all nine scalar matrix basis elements.
    for (f,o), archived in selected.operands.items():
        assert set(archived) <= known
        for pivot in PAIRS:
            combo = sum((axis,o) == pivot for axis in selected.support)
            assert combo - sum(edge == pivot for edge in archived) == ((f,o) == pivot)
    return selected


def main():
    pts = [(n,endpoint_mask([a for a in subset if a in AXES],[o for o in subset if o in OBS]))
           for n in range(7) for subset in combinations(AXES+OBS,n)]
    plain = [min(n for n,cover in pts if not graph & ~cover) for graph in range(ALL+1)]
    span = {}
    for subset in range(8):
        archived = [u for i,u in enumerate(UNITS) if subset & (1 << i)]
        for support in SUPPORTS:
            rows = archived + [tuple(int(axis in support) for axis in AXES)]
            span[subset,support] = {f for f,u in zip(AXES,UNITS) if rank(rows+[u]) == rank(rows)}
    convertible = {}
    examined = fallback = savings = 0
    for old in range(ALL+1):
        known = unmask(old)
        covers = [set() for _ in SUPPORTS]
        for obs in OBS:
            flags = sum(1<<j for j,a in enumerate(AXES) if (a,obs) in known)
            for i,support in enumerate(SUPPORTS):
                covers[i].update((f,obs) for f in span[flags,support])
        convertible[old] = list(map(mask,covers))
        subset = ALL ^ old
        while True:
            p = compare(known,unmask(subset),(),(),0,plain,convertible)
            examined += 1
            if p.support:
                savings += 1
            else:
                fallback += 1
            if subset == 0:
                break
            subset = (subset-1) & ~old
    diag = set(zip(AXES,OBS))
    shifts = [set(zip(AXES,OBS[i:]+OBS[:i])) for i in range(3)]
    cases = [(target,known) for target in shifts for known in
             [set(), set(PAIRS)-target, {e for e in PAIRS if e not in target and e[0] != 'z'},
              {e for e in PAIRS if e not in target and e[1] == 'r2'}]]
    cache_checks = 0
    for n in range(7):
        for subset in combinations(AXES+OBS,n):
            fields = set(subset) & set(AXES)
            obs = set(subset) & set(OBS)
            covered = endpoint_mask(fields,obs)
            for target,known in cases:
                compare(known,target,fields,obs,covered,plain,convertible)
                cache_checks += 1
    known = {('y','q0'),('z','r2'),('x','zz')}
    witness = plan_field_block(diag,known)
    assert witness.new_rhs == 3
    rows = [(1,1,0),(0,1,1)]
    assert all(rank(rows + [UNITS[AXES.index(f)]]) == 3 for f,_ in known)
    print(json.dumps({'disjoint_known_requested_masks':examined,'ordinary_ties_or_wins':fallback,
                      'strict_rhs_reductions':savings,'cached_control_combinations':cache_checks,
                      'counterexample_outside_one_superposition_class':{
                          'known':sorted(known),'requested':sorted(diag),'one_sum_class_rhs':witness.new_rhs,
                          'two_sum_full_rank_with_each_single_known_field':rows}},indent=2))


if __name__=='__main__':
    main()
