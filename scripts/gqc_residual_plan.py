"""Exact span planning for a three-dimensional static external electric field."""
from fractions import Fraction

from generativeqc_compiler.tensor import Index, IndexSpace, Program, TensorSpec, add, constant, input_tensor


def decompose(columns, target):
    """Eliminate the independent columns in exact arithmetic and return the remainder."""
    rows = [[Fraction(col[i]) for col in columns] + [Fraction(target[i])] for i in range(3)]
    for j in range(len(columns)):
        pivot = next(i for i in range(j, 3) if rows[i][j] != 0)
        rows[j], rows[pivot] = rows[pivot], rows[j]
        scale = rows[j][j]
        rows[j] = [x / scale for x in rows[j]]
        for i in range(3):
            if i != j:
                multiplier = rows[i][j]
                rows[i] = [a - multiplier * b for a, b in zip(rows[i], rows[j], strict=True)]
    weights = [rows[j][-1] for j in range(len(columns))]
    residual = tuple(Fraction(target[i]) - sum(c[i] * a for c, a in zip(columns, weights, strict=True))
                     for i in range(3))
    return weights, residual


def plan_fields(known_directions, targets):
    if not len(targets):
        raise ValueError("response completion requires at least one target direction")
    columns, retained = [], []
    for index, direction in enumerate(known_directions):
        _, residual = decompose(columns, direction)
        if any(residual):
            columns.append(tuple(direction))
            retained.append(index)
    missing = []
    for direction in targets:
        _, residual = decompose(columns, direction)
        if any(residual):
            columns.append(residual)
            missing.append(residual)
    weights = [decompose(columns, direction)[0] for direction in targets]
    return retained, missing, weights


def recovery_program(dimension, weights):
    """Compile the exact map from solved rotation directions to every requested solution."""
    if not len(weights):
        raise ValueError("response completion requires at least one target direction")
    space = IndexSpace("occupied_virtual_rotations", "orbital", dimension)
    spec = TensorSpec((Index("k", space),), role="input")
    # A zero-valued target (or repeated column) can be satisfied by a zero
    # vector even if there are no response solves.
    inputs = [input_tensor(f"x{i}", spec) for i in range(len(weights[0]))]
    outputs = {}
    for j, row in enumerate(weights):
        live = [(node, a) for node, a in zip(inputs, row, strict=True) if a]
        if live:
            outputs[f"target{j}"] = add(*(node for node, _ in live),
                                        coefficients=tuple(a for _, a in live))
        else:
            outputs[f"target{j}"] = constant([0] * dimension, TensorSpec(spec.indices, role="constant"))
    return Program(outputs, provenance={"response": "exact-linear-field-reconstruction-v1"})
