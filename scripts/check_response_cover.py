#!/usr/bin/env python3
"""Compare the endpoint planner with enumeration for every 3x3 unit-seed problem."""
import json
from itertools import combinations, product

from response_cover import plan_cover


def subsets(items):
    return [set(s) for n in range(len(items) + 1) for s in combinations(items, n)]


def audit():
    # Overlapping names deliberately exercise the distinction between the two vertex sets.
    fields, observables = ('a', 'b', 'c'), ('a', 'b', 'c')
    possible = tuple(product(fields, observables))
    candidate_covers = sorted(product(subsets(fields), subsets(observables)), key=lambda sides: sum(map(len, sides)))
    graphs = [frozenset(s) for s in subsets(possible)]
    minima = {}
    for edges in graphs:
        left, right = next((f, o) for f, o in candidate_covers if all(a in f or b in o for a, b in edges))
        minima[edges] = len(left) + len(right)
    checked = 0
    for edges in graphs:
        for old_left, old_right in candidate_covers:
            remaining = frozenset((f, o) for f, o in edges if f not in old_left and o not in old_right)
            left, right = plan_cover(edges, old_left, old_right)
            assert all(f in left or o in right for f, o in remaining)
            assert not old_left.intersection(left) and not old_right.intersection(right)
            assert len(left) + len(right) == minima[remaining]
            checked += 1
    witness = [('x', 'r2'), ('x', 'zz'), ('y', 'q0'), ('z', 'q0')]
    assert plan_cover(witness) == plan_cover(witness[::-1] + witness) == (('x',), ('q0',))
    return {'graphs': len(graphs), 'cached_endpoint_sets': len(candidate_covers), 'combinations_checked': checked,
            'cross_stars': {'fields': ['x'], 'observables': ['q0']},
            'scope': 'Exact minimum number of additional unit endpoints, with independent scalar/molecular checks elsewhere.'}


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
