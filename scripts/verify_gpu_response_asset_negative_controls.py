#!/usr/bin/env python3
"""Exercise negative controls for the identity-bound GPU asset verifier."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


def digest(document: dict) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.assets.read_text())
    manifest = json.loads(args.manifest.read_text())
    original = document["assets"][0]
    controls = []

    stale_hash = copy.deepcopy(original)
    stale_hash["targets"][next(iter(stale_hash["targets"]))] += 1e-3
    controls.append({"name": "stale_asset_hash", "accepted": stale_hash["asset_sha256"] == digest({key: value for key, value in stale_hash.items() if key != "asset_sha256"})})

    wrong_geometry = copy.deepcopy(original)
    wrong_geometry["identity"]["geometry_hash"] = "wrong-geometry"
    wrong_geometry["asset_sha256"] = digest({key: value for key, value in wrong_geometry.items() if key != "asset_sha256"})
    expected_geometry = next(item for item in manifest["molecules"] if item["name"] == wrong_geometry["molecule"])["member_sha256"]
    controls.append({"name": "wrong_geometry_identity", "accepted": wrong_geometry["identity"]["geometry_hash"] == expected_geometry})

    missing_density = copy.deepcopy(original)
    missing_density["response_densities"].pop(next(iter(missing_density["response_densities"])))
    controls.append({"name": "missing_response_density", "accepted": set(missing_density["fields_requested"]) == set(missing_density["response_densities"])})

    result = {
        "schema": "vibedataset.gpu_response_asset_negative_controls.v1",
        "status": "passed" if all(not control["accepted"] for control in controls) else "failed",
        "controls": [
            {"name": control["name"], "status": "reject-and-recompute" if not control["accepted"] else "unexpected-accept"}
            for control in controls
        ],
        "oracle_loaded": False,
        "limitations": ["These controls test verifier predicates and do not launch a GPU calculation."],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
