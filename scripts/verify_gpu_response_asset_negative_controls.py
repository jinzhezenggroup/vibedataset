#!/usr/bin/env python3
"""Run mutations through the release verifier used for the unmodified GPU assets."""
import argparse
import copy
import json
from pathlib import Path

from verify_gpu_response_assets import Evidence, digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assets",type=Path,required=True)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--score",type=Path)
    p.add_argument("--raw",type=Path)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    root=args.manifest.parent
    evidence=Evidence(args.manifest,args.raw or root/"raw/raw-C.jsonl",args.score or root/"score.json")
    pristine=json.loads(args.assets.read_bytes())["assets"][0]
    if evidence.errors(pristine):
        raise ValueError("unmodified positive control failed")
    mutations = {
        "stale_asset_hash": lambda a:a.update(asset_sha256="0"*64),
        "wrong_geometry_identity": lambda a:a["identity"].update(geometry_hash="0"*64),
        "missing_response_density": lambda a:a["response_densities"].clear(),
        "truncated_vector": lambda a:a["response_vectors"]["x"].pop(),
        "nonfinite_density": lambda a:a["response_densities"]["x"].__setitem__(0,float("nan")),
        "wrong_finite_density": lambda a:a["response_densities"]["x"].__setitem__(0,0.375),
        "stale_residual": lambda a:a["certificate"].update(oracle_residual_linf=0.375),
        "residual_threshold": lambda a:a["certificate"]["thresholds"].update(operator_residual_linf=0.375),
        "wrong_basis": lambda a:a["identity"].update(basis="6-31g"),
        "wrong_unit": lambda a:a["identity"].update(unit="Angstrom"),
        "wrong_spin": lambda a:a["identity"].update(multiplicity=3),
        "wrong_charge": lambda a:a["identity"].update(charge=1),
        "wrong_source_sha": lambda a:a["source"].update(raw_receipt_sha256="0"*64),
        "wrong_rhs": lambda a:a.update(fields_requested=["z"]),
    }
    controls=[]
    for name, mutate in mutations.items():
        asset=copy.deepcopy(pristine)
        mutate(asset)
        if name not in ("stale_asset_hash","nonfinite_density"):
            body=dict(asset)
            body.pop("asset_sha256")
            asset["asset_sha256"]=digest(body)
        errors=evidence.errors(asset)
        controls.append(dict(name=name,status="reject-and-recompute" if errors else "unexpected-accept", reasons=errors))
    result=dict(schema="vibedataset.gpu_response_asset_negative_controls.v2",controls=controls,
                status="passed" if all(row["reasons"] for row in controls) else "failed", oracle_loaded=False,
                scope="Release-integrity checks against original raw production and independent scorer receipts")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+"\n")
    if result["status"]!="passed":
        raise SystemExit(1)


if __name__=="__main__":
    main()
