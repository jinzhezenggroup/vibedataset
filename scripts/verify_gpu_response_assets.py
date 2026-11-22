#!/usr/bin/env python3
"""Verify response assets against their sealed C-arm inputs and independent scores."""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def index(rows):
    result = {}
    for row in rows:
        key = (row["molecule"], row["trajectory"])
        if key in result:
            raise ValueError(f"duplicate source row {key}")
        result[key] = row
    return result


class Evidence:
    def __init__(self, manifest_path, raw_path, score_path):
        manifest = json.loads(manifest_path.read_bytes())
        header = manifest.copy()
        self.seal = header.pop("manifest_sha256")
        if digest(header) != self.seal:
            raise ValueError("manifest digest mismatch")
        self.protocol = manifest["protocol"]
        self.molecules = {m["name"]:m for m in manifest["molecules"]}
        self.requests = {r["id"]:r for r in manifest["request_trajectories"]}
        self.raw = index(map(json.loads, raw_path.read_text().splitlines()))
        oracle = json.loads(score_path.read_bytes())
        if oracle["manifest_sha256"] != self.seal:
            raise ValueError("score/manifest mismatch")
        self.scores = index(r for r in oracle["rows"] if r["arm"] == "C")
        self.thresholds = oracle["thresholds"]
        self.expected = {(m,q) for m in self.molecules for q in self.requests}
        if set(self.raw) != self.expected or set(self.scores) != self.expected:
            raise ValueError("source or scorer denominator mismatch")

    def errors(self, asset):
        try:
            return self._errors(asset)
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            return [str(exc)]

    def _errors(self, asset):
        key = asset["molecule"],asset["trajectory"]
        raw = self.raw[key]
        ref = self.scores[key]
        mol = self.molecules[key[0]]
        request = self.requests[key[1]]
        identity = dict(geometry_hash=mol["member_sha256"], charge=mol["charge"], multiplicity=mol["multiplicity"],
                        ao_representation=mol["basis_representation"],
                        **{k:self.protocol[k] for k in ("method","basis","unit","precision","origin")})
        if (raw["arm"] != "C" or raw["input_sha256"] != self.seal or raw["protocol"] != self.protocol
            or raw["qm9_id"] != mol["qm9_id"] or raw["fields_requested"] != request["fields"]
            or set(raw["targets"]) != set(request["targets"])):
            return ["sealed source identity"]
        body = dict(asset)
        observed = body.pop("asset_sha256")
        errors = []
        if digest(body) != observed:
            errors.append("asset checksum")
        if asset["asset_id"] != ":".join(key) or asset["identity"] != identity:
            errors.append("scientific identity")
        source = {"arm":"C","raw_receipt_sha256":digest(raw),"manifest_sha256":self.seal}
        if asset["source"] != source:
            errors.append("source binding")
        for name in ("fields_requested","fields_computed","fields_reused","targets","response_vectors","response_densities"):
            if asset[name] != raw[name]:
                errors.append(name)
        fields = set(request["fields"])
        if fields != set(asset["response_vectors"]) or fields != set(asset["response_densities"]):
            errors.append("incomplete fields")
        else:
            nocc = (sum(mol["atomic_numbers"]) - mol["charge"])//2
            for field in fields:
                d, v = asset["response_densities"][field],asset["response_vectors"][field]
                nao = math.isqrt(len(d))
                if not (nao > nocc and nao*nao == len(d) and len(v) == (nao-nocc)*nocc
                        and all(type(x) in (float,int) and math.isfinite(x) for x in [*d,*v])):
                    errors.append("nonfinite or truncated vector/density")
        certificate = {k:ref[k] for k in ("max_target_error","max_ao_density_error","observed_residual_linf","oracle_residual_linf")}
        certificate.update(independent_scorer_status=ref["status"], thresholds=self.thresholds)
        if asset["certificate"] != certificate:
            errors.append("certificate/scorer mismatch")
        expected = "direct_reuse" if ref["status"]=="accepted" else "reject_and_recompute"
        if asset["disposition"] != expected:
            errors.append("disposition")
        return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--raw", type=Path, help="sealed C JSONL (default: raw/raw-C.jsonl beside manifest)")
    p.add_argument("--score", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    evidence = Evidence(args.manifest, args.raw or args.manifest.parent/"raw/raw-C.jsonl",args.score)
    document = json.loads(args.assets.read_bytes())
    assets = document["assets"]
    errors = []
    if document["manifest_sha256"] != evidence.seal or document["source_arm"] != "C":
        errors.append("document source")
    if document["asset_count"] != len(assets) or Counter((a.get("molecule"),a.get("trajectory")) for a in assets) != Counter(evidence.expected):
        errors.append("asset denominator")
    accepted = 0
    for asset in assets:
        failures = evidence.errors(asset)
        errors.extend(f"{asset.get('asset_id')}: {v}" for v in failures)
        accepted += not failures and asset.get("disposition")=="direct_reuse"
    result = dict(schema="vibedataset.gpu_response_asset_compiler_verification.v1",
                  status="failed" if errors else "passed", asset_count=len(assets), direct_reuse=accepted,
                  independent_scorer_accepted=accepted, errors=errors, oracle_loaded=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    if errors:
        raise SystemExit(1)


if __name__=="__main__":
    main()
