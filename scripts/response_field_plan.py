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


def endpoint_choices(required, cached_fields, cached_observables):
    """Enumerate minimum-size covers of unserved edges, keeping the usual cover first."""
    mandatory = {(f, o) for f, o in required if f not in cached_fields and o not in cached_observables}
    usual = plan_cover(mandatory)
    yield usual
    count = sum(map(len, usual))
    if count == 0:
        return
    points = [('field', f) for f in sorted({f for f, _ in mandatory})]
    points.extend(('readout', o) for o in sorted({o for _, o in mandatory}))
    for selected in combinations(points, count):
        fields = tuple(k for group, k in selected if group == 'field')
        obs = tuple(k for group, k in selected if group == 'readout')
        if (fields, obs) != usual and all(f in fields or o in obs for f, o in mandatory):
            yield fields, obs


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
        for fields, obs in endpoint_choices(missing - candidates.keys(), cached_fields, cached_observables):
            # Among minimum covers, favor ordinary endpoints that also serve decoded candidates.
            operands = {edge: terms for edge, terms in sorted(candidates.items())
                        if edge[0] not in fields and edge[1] not in obs}
            if not operands:
                continue
            ordinary = tuple(sorted(missing - operands.keys()))
            plan = FieldPlan(ordinary, fields, obs, support, operands)
            score = (plan.new_rhs, sum(map(len, operands.values())), len(support), support)
            if score < best_score:
                best, best_score = plan, score
    return best
