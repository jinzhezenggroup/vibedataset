#!/usr/bin/env python3
"""Export portable CUPTI activity records and account for synchronized NVTX phases."""
import argparse
import gzip
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(directory, out):
    sql = directory / "trace.sqlite"
    with sqlite3.connect(sql.resolve().as_uri() + "?mode=ro", uri=True) as db:
        query = db.execute
        ranges = list(query("""SELECT text,start,end FROM NVTX_EVENTS
                               WHERE text LIKE 'scf/%' OR text LIKE 'request/%' ORDER BY start"""))
        kernels = list(query("""SELECT k.start,k.end,k.streamId,k.correlationId,k.shortName,
                                       k.gridX,k.gridY,k.gridZ,k.blockX,k.blockY,k.blockZ
                                FROM CUPTI_ACTIVITY_KIND_KERNEL k ORDER BY k.start"""))
        ids = {row[4] for row in kernels}
        names = {i: name for i,name in query("SELECT id,value FROM StringIds") if i in ids}
        copies = list(query("""SELECT start,end,streamId,correlationId,copyKind,bytes
                               FROM CUPTI_ACTIVITY_KIND_MEMCPY ORDER BY start"""))
        operations = dict(query("SELECT id,label FROM ENUM_CUDA_MEMCPY_OPER"))
        allocs = list(query("""SELECT start,memoryOperationType,bytes FROM CUDA_GPU_MEMORY_USAGE_EVENTS
                               WHERE memKind=(SELECT id FROM ENUM_CUDA_MEM_KIND WHERE label='Device')
                               ORDER BY start"""))
        devices = list(query("SELECT DISTINCT globalPid, deviceId, contextId FROM CUPTI_ACTIVITY_KIND_KERNEL"))
        allocation_kinds = dict(query("SELECT id,label FROM ENUM_CUDA_DEV_MEM_EVENT_OPER"))
    if len(devices) != 1 or allocation_kinds != {0: "Allocation", 1: "Deallocation"}:
        raise ValueError("expected one CUDA process/device/context and the known memory-event schema")
    producer = directory / "producer"
    data = dict(schema="vibedataset.cupti_activities.v1", ranges=ranges, kernel_names=names, kernels=kernels,
                memcpy_kind=operations, copies=copies, device_allocations=allocs,
                producer=json.loads((producer/"run.json").read_text()), observer=json.loads((producer/"trace-identity.json").read_text()),
                phases=[json.loads(s) for s in (producer/"phases.jsonl").read_text().splitlines()],
                scientific_raw_sha256=digest(producer/"raw.jsonl"), native_report_sha256=digest(directory/"trace.nsys-rep"),
                sqlite_sha256=digest(sql))
    # A portable evidence file needs numerical identity; machine-local checkout paths are not part of it.
    data["producer"]["manifest"] = Path(data["producer"]["manifest"]).name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":"), allow_nan=False).encode(),mtime=0))


def summarize_file(path, manifest, arm):
    data = json.loads(gzip.decompress(path.read_bytes()))
    runs = data["ranges"]
    expected = [label for row in manifest["molecules"] for label in
                [f"scf/{row['name']}", *[f"request/{row['name']}/{q['id']}" for q in
                                         sorted(manifest["request_trajectories"], key=lambda x: x["order"])]]]
    if [r[0] for r in runs] != expected or any(end <= start for _,start,end in runs):
        raise ValueError(f"incomplete NVTX phases in {path}")
    phases = data["phases"]
    if [(r["name"],r["status"]) for r in phases] != [(name,s) for name in expected for s in ("started","finished")]:
        raise ValueError("NVML journal differs from NVTX phase identities")
    producer = data["producer"]
    if (producer["arm"] != arm or data["observer"]["arm"] != arm or
        producer["manifest_sha256"] != manifest["manifest_sha256"] or
        producer["record_count"] != sum(name.startswith("request/") for name in expected)):
        raise ValueError("producer request denominator")
    if bool(producer["patch_sha256"]) != (arm in "BD"):
        raise ValueError("backend mismatch")
    total = available = 0
    memory_timeline = []
    for tick, op, size in data["device_allocations"]:
        total += size if op == 0 else -size
        available = min(available, total)
        memory_timeline.append((tick,total))
    if available < 0:
        raise ValueError("device-allocation history begins after allocations")
    result = []
    for (name,t0,t1), phase in zip(runs,phases[1::2]):
        kernels = [k for k in data["kernels"] if t0 <= k[0] and k[1] <= t1]
        copies = [c for c in data["copies"] if t0 <= c[0] and c[1] <= t1]
        if any(k[0]<edge<k[1] for k in data["kernels"] for edge in (t0,t1)):
            raise ValueError("kernel crosses a synchronized request boundary")
        directions = Counter()
        times = Counter()
        for start,end,_,_,kind,size in copies:
            key = data["memcpy_kind"][str(kind)]
            directions[key] += size
            times[key] += end-start
        initial = next((n for t,n in reversed(memory_timeline) if t<t0),0)
        peak = max([initial,*[n for t,n in memory_timeline if t0<=t<=t1]])
        moments = Counter(data["kernel_names"][str(k[4])] for k in kernels)
        result.append(dict(name=name, kernel_launches=len(kernels), sum_kernel_ns=sum(k[1]-k[0] for k in kernels),
            kernel_counts=dict(sorted(moments.items())), transfer_bytes=dict(directions), sum_transfer_ns=dict(times),
            peak_traced_device_allocation_bytes=peak, nvtx_wall_ns=t1-t0,
            cuda_event_seconds=phase["cuda_event_seconds"], board_energy_joules=phase["board_joules"],
            sampled_board_memory_peak_bytes=phase["sampled_board_memory_peak_bytes"], valid_memory_samples=phase["valid_memory_samples"]))
    return dict(arm=arm, observed_on=data["observer"]["gpu"], pci=data["observer"]["pci"],
                payload_sha256=digest(path), rows=result, total_kernel_launches=len(data["kernels"]),
                outside_named_phases=len(data["kernels"])-sum(r["kernel_launches"] for r in result))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest="mode", required=True)
    export = modes.add_parser("extract")
    export.add_argument("directory",type=Path)
    export.add_argument("out",type=Path)
    replay = modes.add_parser("summarize")
    replay.add_argument("root",type=Path)
    replay.add_argument("out",type=Path)
    args = p.parse_args()
    if args.mode == "extract":
        extract(args.directory,args.out)
        return
    manifest = json.loads((args.root/"manifest.json").read_text())
    data = {arm:{state:summarize_file(args.root/f"{arm}-{state}.json.gz",manifest,arm)
                 for state in ("cold","warm")} for arm in "ABCD"}
    score_counts = {}
    for state in ("cold", "warm"):
        scientific = args.root / "scientific"
        score = json.loads(gzip.decompress((scientific/f"score-{state}.json.gz").read_bytes()))
        if score["manifest_sha256"] != manifest["manifest_sha256"] or score["oracle_loaded_gqc_planner"]:
            raise ValueError("unmatched or dependent scorer")
        decisions = {(r["arm"],r["molecule"],r["trajectory"]):r["status"] for r in score["rows"]}
        expected = {(arm, m["name"], q["id"]) for arm in "ABCD" for m in manifest["molecules"]
                    for q in manifest["request_trajectories"]}
        if set(decisions) != expected or len(score["rows"]) != len(expected):
            raise ValueError("score denominator")
        for arm in "ABCD":
            raw = gzip.decompress((scientific/f"{arm}-{state}.jsonl.gz").read_bytes())
            recorded = json.loads(gzip.decompress((args.root/f"{arm}-{state}.json.gz").read_bytes()))
            if hashlib.sha256(raw).hexdigest() != recorded["scientific_raw_sha256"]:
                raise ValueError("scientific output differs from profiled receipt")
            keys = [(r["arm"],r["molecule"],r["trajectory"]) for r in map(json.loads,raw.splitlines())]
            if len(set(keys)) != len(keys) or set(keys) != {key for key in expected if key[0]==arm}:
                raise ValueError("profiled scientific output denominator")
        score_counts[state] = dict(Counter(decisions.values()))
    pcis = {r["pci"] for states in data.values() for r in states.values()}
    if len(pcis) != 1:
        raise ValueError("expected all phases on the same physical device")
    result = {"schema":"vibedataset.nsight_matrix.v1","source_manifest_sha256":manifest["manifest_sha256"],
              "arms":data, "independent_scores":score_counts, "scope":"instrumented SCF/request phases; cold/warm refers to private on-disk CuPy and CUDA caches",
              "achieved_occupancy":None,"hardware_flops":None}
    args.out.write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    main()
