#!/usr/bin/env python3
"""Materialize the frozen end-to-end benchmark contract from the 4-arm manifest."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def geometry_hash(item):
    return hashlib.sha256(canonical({"atomic_numbers": item["atomic_numbers"], "coordinates_bohr": item["coordinates_bohr"], "charge": item["charge"], "multiplicity": item["multiplicity"]})).hexdigest()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(); manifest=json.loads(args.manifest.read_text())
    root=args.out; root.mkdir(parents=True,exist_ok=True)
    fields=["prepare","environment_startup","data_read","compile_jit","warmup","h2d","scf_fock","cp_hf_gmres","property_readout","physical_residual","independent_scorer","serialization","retry","fallback"]
    micro=[
      {"id":"h2o-rhf-sto3g","source_kind":"controlled-request","status":"measured","name":"qm9-000003","protocol":"RHF/STO-3G"},
      {"id":"nh3-rhf-sto3g","source_kind":"controlled-request","status":"measured","name":"qm9-000002","protocol":"RHF/STO-3G"},
      {"id":"lih-rhf-sto3g","source_kind":"control-only","status":"not_run","atomic_numbers":[3,1],"coordinates_bohr":[[0,0,0],[3.015,0,0]],"charge":0,"multiplicity":1,"protocol":"RHF/STO-3G"},
    ]
    by_name={m["name"]:m for m in manifest["molecules"]}
    for row in micro:
        if row.get("name") in by_name:
            m=by_name[row["name"]]; row.update({"geometry_hash":geometry_hash(m),"atomic_numbers":m["atomic_numbers"],"coordinates_bohr":m["coordinates_bohr"],"charge":m["charge"],"multiplicity":m["multiplicity"],"basis_representation":m["basis_representation"]})
    (root/"micro-workload.json").write_text(json.dumps({"schema":"vibedataset.benchmark.micro.v1","rows":micro},indent=2)+"\n")
    queue=[]
    trajectories={r["id"]:r for r in manifest["request_trajectories"]}
    for repeat in range(6):
        for m in manifest["molecules"]:
            for tid in ("cycle-one","cycle-three","cross-three"):
                t=trajectories[tid]
                queue.append({"request_id":f"middle-{repeat:02d}-{m['name']}-{tid}","queue_repeat":repeat,"source_kind":"controlled-request","status":"measured" if repeat==0 else "not_run","geometry_hash":geometry_hash(m),"name":m["name"],"atomic_numbers":m["atomic_numbers"],"coordinates_bohr":m["coordinates_bohr"],"method":manifest["protocol"]["method"],"basis":manifest["protocol"]["basis"],"charge":m["charge"],"spin":m["multiplicity"]-1,"basis_representation":m["basis_representation"],"origin":manifest["protocol"]["origin"],"unit":manifest["protocol"]["unit"],"precision":manifest["protocol"]["precision"],"convergence":{"scf":manifest["protocol"]["conv_tol"],"response":manifest["protocol"]["response_tol"]},"targets":t["targets"],"fields":t["fields"],"missingness_mask":{"fields_known":[],"fields_missing":t["fields"]},"timing":{field:None for field in fields}})
    with (root/"middle-queue.jsonl").open("w") as h:
        for row in queue:h.write(json.dumps(row,sort_keys=True)+"\n")
    ledger={"schema":"vibedataset.benchmark.source_kind.v1","counts":{"controlled-request":len(queue),"natural-request":0,"negative-control":3,"not-exported":0,"quality-insufficient":0,"compute-failed":0},"definitions":{"controlled-request":"sealed request generated from the 4-arm manifest","natural-request":"observed production request with source receipt, none available in this release","negative-control":"wrong protocol, near-singular or state mismatch","not-exported":"computed state without a released property value","quality-insufficient":"computed value failing independent quality gate","compute-failed":"failed SCF/response attempt retained in denominator"}}
    (root/"source-kind-ledger.json").write_text(json.dumps(ledger,indent=2)+"\n")
    contract={"schema":"vibedataset.benchmark_contract.v1","manifest_sha256":manifest["manifest_sha256"],"micro_workload_count":3,"middle_queue_count":len(queue),"target_scale":1000,"scale_geometry_manifest":"handoff/gqcdataset_codex_goal/research/performance/qm9-scale-manifest.json.gz","scale_geometry_count":1000,"target_scale_status":"geometry-manifest-available-response-labels-blocked","blocked_reason":"A licensed 1000-row QM9 geometry manifest is now archived. Protocol-consistent response labels, quality references and A–D execution are still unavailable. The contract keeps the 306-row controlled queue and does not treat geometry-only rows as completed labels.","timing_fields":fields,"main_metric":"end_to_end_wall_seconds","secondary_metrics":["throughput","geometric_mean_speedup","median","p95","gpu_hours","operator_rows","rhs_columns","host_device_bytes","device_memory_bytes","coverage","failure_rate"],"protocol":{"method":manifest["protocol"]["method"],"basis":manifest["protocol"]["basis"],"precision":manifest["protocol"]["precision"],"origin":manifest["protocol"]["origin"],"unit":manifest["protocol"]["unit"],"conv_tol":manifest["protocol"]["conv_tol"],"response_tol":manifest["protocol"]["response_tol"],"seed":manifest["protocol"]["seed"]},"cold_warm_separation":True,"oracle_process_separate":True,"claims_10x_status":"hypothesis-only"}
    (root/"benchmark_contract.json").write_text(json.dumps(contract,indent=2)+"\n")
    print(json.dumps({"status":"built","middle_queue_count":len(queue),"micro_workload_count":3},indent=2))

if __name__=="__main__":main()
