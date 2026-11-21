"""Minimum additional unit field/observable solutions for a sparse response request."""
from collections import deque


def _alternating_paths(neighbors, field_match, observable_match):
    """Search from all unmatched fields, following unmatched edges out of fields."""
    reached_fields = {f for f in neighbors if f not in field_match}
    queue = deque(sorted(reached_fields))
    parents = {}
    while queue:
        field = queue.popleft()
        for observable in neighbors[field]:
            if observable == field_match.get(field) or observable in parents:
                continue
            parents[observable] = field
            if observable not in observable_match:
                return observable, reached_fields, parents
            matched_field = observable_match[observable]
            if matched_field not in reached_fields:
                reached_fields.add(matched_field)
                queue.append(matched_field)
    return None, reached_fields, parents


def plan_cover(requests, cached_fields=(), cached_observables=()):
    """Return sorted (fields, observables) covering the as-yet unsatisfied pairs.

    Each remaining edge needs one endpoint. Unit costs count response RHS only.
    Callers admit vectors under a physical problem identity and handle labels,
    block solver costs, convergence and persistence outside this combinatorial step.
    """
    if isinstance(cached_fields, str) or isinstance(cached_observables, str):
        raise ValueError('supply a collection of cached endpoint IDs')
    field_cache, observable_cache = set(cached_fields), set(cached_observables)
    if not all(isinstance(key, str) and key for key in field_cache | observable_cache):
        raise ValueError('cached response IDs must be nonempty strings')
    neighbors = {}
    for pair in requests:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('each request needs a field ID and an observable ID')
        field, observable = pair
        if not all(isinstance(name, str) and name for name in pair):
            raise ValueError('response IDs must be nonempty strings')
        if field not in field_cache and observable not in observable_cache:
            neighbors.setdefault(field, set()).add(observable)
    neighbors = {field: sorted(names) for field, names in neighbors.items()}

    field_match, observable_match = {}, {}
    while True:
        tip, reached_fields, parents = _alternating_paths(neighbors, field_match, observable_match)
        if tip is None:
            # König's cover: unreached left vertices and reached right vertices.
            return tuple(sorted(neighbors.keys() - reached_fields)), tuple(sorted(parents))
        while tip is not None:
            field = parents[tip]
            previous = field_match.get(field)
            field_match[field] = tip
            observable_match[tip] = field
            tip = previous
