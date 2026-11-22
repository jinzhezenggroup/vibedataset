#!/usr/bin/env python3
"""Verify the frozen benchmark contract and its request asset boundaries."""
from __future__ import annotations
import argparse,hashlib,json,gzip
from pathlib import Path

def geometry_hash(item):
    multiplicity = item.get("multiplicity", item["spin"] + 1)
    return hashlib.sha256(json.dumps({"atomic_numbers":item["atomic_numbers"],"coordinates_bohr":item["coordinates_bohr"],"charge":item["charge"],"multiplicity":multiplicity},sort_keys=True,separators=(",",":")).encode()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument("--contract",type=Path,required=True);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    c=json.loads(a.contract.read_text());m=json.loads(a.manifest.read_text());q=a.contract.parent/"middle-queue.jsonl";rows=[json.loads(x) for x in q.read_text().splitlines() if x.strip()]
    errors=[]
    if c["manifest_sha256"]!=m["manifest_sha256"]:errors.append("manifest binding")
    if len(rows)!=c["middle_queue_count"] or len(rows)<100:errors.append("middle queue denominator")
    if c["target_scale_status"]!="geometry-manifest-available-response-labels-blocked":errors.append("scale status")
    scale=Path(__file__).resolve().parents[1]/c["scale_geometry_manifest"]
    if not scale.exists():errors.append("scale geometry manifest")
    else:
      with gzip.open(scale,'rt') as h: scale_data=json.load(h)
      if scale_data["count"]!=1000:errors.append("scale geometry manifest count")
    for row in rows:
      if geometry_hash(row)!=row["geometry_hash"]:errors.append("geometry hash")
      if row["source_kind"]!="controlled-request":errors.append("source kind")
      if set(row["timing"])!=set(c["timing_fields"]):errors.append("timing schema")
      for key in ("method","basis","charge","spin","origin","unit","precision","convergence","targets","fields","missingness_mask"):
        if key not in row:errors.append(f"missing {key}")
    if errors:raise SystemExit("; ".join(sorted(set(errors))))
    result={"status":"passed","middle_queue_count":len(rows),"micro_workload_count":c["micro_workload_count"],"target_scale_status":c["target_scale_status"],"natural_request_count":0}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
