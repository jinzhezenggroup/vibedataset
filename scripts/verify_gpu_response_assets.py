#!/usr/bin/env python3
"""Independently verify identity and scorer coverage for compiled GPU assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(document: dict) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.assets.read_text())
    manifest = json.loads(args.manifest.read_text())
    score = json.loads(args.score.read_text())
    by_name = {item["name"]: item for item in manifest["molecules"]}
    scored = {(row["arm"], row["molecule"], row["trajectory"]): row for row in score["rows"]}
    errors = []
    ids = set()
    assets = document.get("assets", [])
    if document.get("manifest_sha256") != manifest.get("manifest_sha256"):
        errors.append("manifest binding")
    if document.get("asset_count") != len(assets) or len(assets) != 51:
        errors.append("asset denominator")
    for asset in assets:
        asset_id = asset.get("asset_id")
        if asset_id in ids:
            errors.append(f"duplicate {asset_id}")
        ids.add(asset_id)
        molecule = by_name.get(asset.get("molecule"))
        if molecule is None:
            errors.append(f"unknown molecule {asset.get('molecule')}")
            continue
        identity = asset.get("identity", {})
        if identity.get("geometry_hash") != molecule["member_sha256"]:
            errors.append(f"geometry identity {asset_id}")
        key = ("C", asset["molecule"], asset["trajectory"])
        scorer = scored.get(key)
        if scorer is None or scorer.get("status") != "accepted":
            errors.append(f"scorer coverage {asset_id}")
        if asset.get("disposition") != "direct_reuse":
            errors.append(f"unexpected disposition {asset_id}")
        if asset.get("certificate", {}).get("independent_scorer_status") != "accepted":
            errors.append(f"certificate status {asset_id}")
        body = dict(asset)
        observed = body.pop("asset_sha256", None)
        if observed != digest(body):
            errors.append(f"asset hash {asset_id}")
        requested = set(asset.get("fields_requested", []))
        if requested != set(asset.get("response_vectors", {})) or requested != set(asset.get("response_densities", {})):
            errors.append(f"field coverage {asset_id}")
    result = {
        "schema": "vibedataset.gpu_response_asset_compiler_verification.v1",
        "status": "passed" if not errors else "failed",
        "asset_count": len(assets),
        "direct_reuse": sum(asset.get("disposition") == "direct_reuse" for asset in assets),
        "independent_scorer_accepted": sum(
            asset.get("certificate", {}).get("independent_scorer_status") == "accepted" for asset in assets
        ),
        "errors": errors,
        "oracle_loaded": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
