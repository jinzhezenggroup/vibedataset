"""Plan one field superposition and ordinary endpoints using observable-specific archived scalars."""
from dataclasses import dataclass
from itertools import combinations

from response_cover import plan_cover

AXES = ('x', 'y', 'z')
SUPPORTS = (*combinations(AXES, 2), AXES)


@dataclass
class FieldPlan:
    ordinary_requests: tuple
    fields: tuple
    observables: tuple
    support: tuple
    operands: dict

    @property
    def new_rhs(self):
        return len(self.fields) + len(self.observables) + bool(self.support)


def plan_field_block(requests, known, cached_fields=(), cached_observables=(), *, supports=SUPPORTS):
    """Minimize fresh RHS in the class with one optional 0/1 mixed field.

    A subtraction may consume only previously measured entries of its own readout.
    Physical acceptance, cache validation and block iteration costs belong to execution.
    """
    missing = set(map(tuple, requests)) - set(known)
    cached_fields = set(cached_fields)
    cached_observables = set(cached_observables)
    if any(f not in AXES for f, _ in missing):
        raise ValueError('unsupported field axis')
    plain_fields, plain_obs = plan_cover(missing, cached_fields, cached_observables)
    best = FieldPlan(tuple(sorted(missing)), plain_fields, plain_obs, (), {})
    best_score = (best.new_rhs, 0, 0, ())
    if best.new_rhs < 2:
        return best

    for support in supports:
        if support not in SUPPORTS:
            raise ValueError('unsupported mixed-field direction')
        candidates = {}
        for field, observable in missing:
            if field not in support or field in cached_fields or observable in cached_observables:
                continue
            terms = tuple((axis, observable) for axis in support if axis != field)
            if all(term in known for term in terms):
                candidates[field, observable] = terms
        if not candidates:
            continue
        fields, obs = plan_cover(missing - candidates.keys(), cached_fields, cached_observables)
        # An ordinary endpoint obtained for another request also covers this edge.
        operands = {edge: terms for edge, terms in sorted(candidates.items()) if edge[0] not in fields and edge[1] not in obs}
        if not operands:
            continue
        ordinary = tuple(sorted(missing - operands.keys()))
        plan = FieldPlan(ordinary, fields, obs, support, operands)
        score = (plan.new_rhs, sum(map(len, operands.values())), len(support), support)
        if score < best_score:
            best, best_score = plan, score
    return best
