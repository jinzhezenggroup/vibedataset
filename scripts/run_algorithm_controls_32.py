#!/usr/bin/env python3
"""Small runnable controls for the external algorithm comparisons in Issue #32."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    exact_source = {"geometry": "g", "method": "RHF", "basis": "sto-3g", "operator": "A"}
    exact_target = dict(exact_source)
    wrong_target = {**exact_source, "basis": "6-31g*"}
    # A diagonal primal/dual problem gives a reproducible DWR scalar estimate.
    matrix_diag = [2.0, 3.0]
    rhs = [2.0, 3.0]
    approximate = [0.9, 1.0]
    residual = [rhs[i] - matrix_diag[i] * approximate[i] for i in range(2)]
    dual = [1.0 / value for value in matrix_diag]
    dwr_estimate = abs(dot(dual, residual))
    # A rank-one 2x2 completion with only diagonal observations is ambiguous.
    ambiguous_completions = [[1.0, 1.0], [1.0, -1.0]]
    # Low/high fidelity records expose a costed difference instead of a CPHF label.
    low = [1.0, 2.0]
    high = [1.1, 2.2]
    delta = [b - a for a, b in zip(low, high)]
    # Greedy coloring of a small column-intersection graph.
    supports = [{0, 1}, {1, 2}, {3}]
    colors = []
    for support in supports:
        forbidden = {colors[i] for i, other in enumerate(supports[:len(colors)]) if support & other}
        color = 0
        while color in forbidden:
            color += 1
        colors.append(color)
    result = {
        "schema": "vibedataset.algorithm_controls_32.v1",
        "controls": {
            "exact_identity": {
                "same_protocol": "accepted" if exact_source == exact_target else "reject",
                "wrong_basis": "reject" if exact_source != wrong_target else "accepted",
            },
            "dwr": {
                "matrix_diagonal": matrix_diag,
                "residual": residual,
                "dual": dual,
                "goal_error_estimate": dwr_estimate,
                "status": "estimated-on-fixed-discrete-problem",
            },
            "matrix_completion": {
                "observed_diagonal": [1.0, 1.0],
                "compatible_off_diagonals": [row[1] for row in ambiguous_completions],
                "status": "evidence-unavailable",
            },
            "multifidelity": {
                "low": low,
                "high": high,
                "difference": delta,
                "status": "statistical-difference-only",
            },
            "coloring": {"supports": [sorted(s) for s in supports], "colors": colors, "status": "sparsity-only"},
            "sparse_ad": {
                "function": ["x0*x2", "x1"],
                "jacobian_nonzero_pattern": [[0, 2], [1]],
                "forward_columns": 2,
                "reverse_rows": 2,
                "status": "derivative-pattern-only",
            },
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
