#!/usr/bin/env python3
"""Compile identity-bound GPU response assets from an archived C receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(document: dict) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--score", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    by_name = {item["name"]: item for item in manifest["molecules"]}
    score = json.loads(args.score.read_text())
    score_by_key = {(row["arm"], row["molecule"], row["trajectory"]): row for row in score["rows"]}
    assets = []
    for line in args.raw.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("arm") != "C":
            continue
        molecule = by_name[row["molecule"]]
        scorer = score_by_key.get(("C", row["molecule"], row["trajectory"]))
        if scorer is None:
            raise ValueError(f"missing independent scorer row {row['molecule']}:{row['trajectory']}")
        identity = {
            "geometry_hash": molecule["member_sha256"],
            "method": manifest["protocol"]["method"],
            "basis": manifest["protocol"]["basis"],
            "charge": molecule["charge"],
            "multiplicity": molecule["multiplicity"],
            "ao_representation": molecule["basis_representation"],
            "origin": manifest["protocol"]["origin"],
            "unit": manifest["protocol"]["unit"],
            "precision": manifest["protocol"]["precision"],
        }
        body = {
            "asset_id": f"{row['molecule']}:{row['trajectory']}",
            "disposition": "direct_reuse" if scorer["status"] == "accepted" else "reject_and_recompute",
            "identity": identity,
            "molecule": row["molecule"],
            "trajectory": row["trajectory"],
            "fields_requested": row["fields_requested"],
            "fields_computed": row["fields_computed"],
            "fields_reused": row["fields_reused"],
            "targets": row["targets"],
            "response_vectors": row["response_vectors"],
            "response_densities": row["response_densities"],
            "source": {
                "arm": "C",
                "raw_receipt_sha256": digest(row),
                "manifest_sha256": manifest["manifest_sha256"],
            },
            "certificate": {
                "independent_scorer_status": scorer["status"],
                "max_target_error": scorer["max_target_error"],
                "max_ao_density_error": scorer["max_ao_density_error"],
                "observed_residual_linf": scorer["observed_residual_linf"],
                "oracle_residual_linf": scorer["oracle_residual_linf"],
                "thresholds": score["thresholds"],
            },
        }
        body["asset_sha256"] = digest(body)
        assets.append(body)
    result = {
        "schema": "vibedataset.gpu_response_asset_compiler.v1",
        "manifest_sha256": manifest["manifest_sha256"],
        "source_arm": "C",
        "oracle_loaded": False,
        "scorer_loaded_for_certificate": True,
        "asset_count": len(assets),
        "dispositions": {
            "direct_reuse": sum(asset["disposition"] == "direct_reuse" for asset in assets),
            "reject_and_recompute": sum(asset["disposition"] == "reject_and_recompute" for asset in assets),
        },
        "assets": assets,
        "limitations": [
            "This compiler packages archived official GPU4PySCF C receipts and does not rerun CPHF.",
            "Independent scorer values are certificate metadata. The producer never loaded the scorer.",
            "Cross-protocol refine and reject dispositions remain in the separate response asset plan.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "built", "asset_count": len(assets), "dispositions": result["dispositions"]}, indent=2))


if __name__ == "__main__":
    main()
