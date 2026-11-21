#!/usr/bin/env python3
"""Run deterministic failure controls for the four-arm attribution report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path



def classify(source: dict, target: dict) -> dict:
    fields = ["method", "basis", "basis_representation", "unit", "precision", "origin"]
    mismatches = [field for field in fields if source.get(field) != target.get(field)]
    return {
        "status": "reject-and-recompute" if mismatches else "accepted",
        "reason": "protocol_identity_mismatch" if mismatches else "protocol_identity_match",
        "mismatches": mismatches,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    protocol = manifest["protocol"]
    wrong = dict(protocol)
    wrong["basis"] = "6-31g*"
    near_singular = [[1.0, 0.0], [0.0, 1e-12]]
    rhs = [1.0, 1.0]
    residual = [0.0, 1e-8]
    bound = 1e12 * 1e-8
    result = {
        "schema": "vibedataset.attribution_4arm.negative_controls.v1",
        "manifest_sha256": manifest["manifest_sha256"],
        "controls": [
            {
                "id": "wrong-basis-reuse",
                "source_protocol": protocol,
                "target_protocol": wrong,
                **classify(protocol, wrong),
            },
            {
                "id": "near-singular-residual",
                "matrix": near_singular,
                "rhs": rhs,
                "residual": residual,
                "condition_number": 1e12,
                "strict_residual_bound": bound,
                "tolerance": 1e-6,
                "status": "reject-and-recompute" if bound > 1e-6 else "accepted",
                "reason": "residual_bound_exceeds_target_tolerance",
            },
            {
                "id": "multiplicity-mismatch",
                "source_multiplicity": 1,
                "target_multiplicity": 3,
                "status": "reject-and-recompute",
                "reason": "state_identity_mismatch",
            },
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
