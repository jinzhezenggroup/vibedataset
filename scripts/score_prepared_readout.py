#!/usr/bin/env python3
"""Certify all candidate AO densities/readouts against new dense CPU RHF oracles."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

from run_gpu4pyscf_4arm import load_manifest
from score_ao_density_response import reference, score


NAMES = ("qm9-000003", "qm9-000009", "qm9-000011", "qm9-000001")
FAULTS = {
    "qm9-000003:cycle-one": "scf_nonconvergence",
    "qm9-000009:cycle-three": "OutOfMemoryError",
    "qm9-000011:cross-three": "unsupported_property",
}
FULL = (
    "serial",
    "async",
    "ragged",
    "async-ragged",
    "allocate",
    "batch-one",
    "single-rhs",
    "no-asset",
    "budget",
    "isolation",
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--extended", choices=("dense", "adjoint"))
    a = p.parse_args()
    started = time.perf_counter()
    manifest = load_manifest(a.manifest)
    by_name = {m["name"]: m for m in manifest["molecules"]}
    models = {name: reference(by_name[name], manifest["protocol"]) for name in NAMES}
    traj = sorted(manifest["request_trajectories"], key=lambda x: x["order"])
    planned = [(name + ":" + t["id"], name, t) for t in traj for name in NAMES]
    begin, wall = {}, {}
    for line in (a.root / "process-wall.txt").read_text().splitlines():
        mode, event, value, *code = line.split()
        if event == "started":
            begin[mode] = int(value)
        elif event == "finished" and code == ["0"]:
            wall[mode] = (int(value) - begin[mode]) / 1e9
    modes = ("serial", "async-ragged") if a.pilot else FULL
    if a.extended == "dense":
        modes = ("official", "dense-separated", "dense-fused", "mixed", "dense-budget")
    elif a.extended == "adjoint":
        modes = ("direct", "adjoint", "direct-no-asset", "adjoint-no-asset")
    if set(wall) != set(modes):
        raise ValueError("external process timing denominator")
    results = {}
    errors = []
    for mode in modes:
        run = json.loads((a.root / (mode + ".json")).read_bytes())
        if (
            run["manifest_sha256"] != manifest["manifest_sha256"]
            or run["gpu4pyscf_source_commit"]
            != "8536a80c1e03260aab030e108ef1d181a3709057"
        ):
            raise ValueError("wrong producer identity")
        if [r["request_id"] for r in run["receipts"]] != [
            rid for rid, _, _ in planned
        ] or run["scientific_stream"] != 0:
            raise ValueError("request order or scientific stream mismatch")
        observed = []
        for receipt, (rid, name, t) in zip(run["receipts"], planned):
            if receipt["status"] != "accepted":
                quality = dict(status="reject-and-recompute", reason=receipt["reason"])
                if (
                    mode != "isolation"
                    or FAULTS.get(rid, "unplanned-failure") not in receipt["reason"]
                ):
                    errors.append([mode, rid, "unexpected producer failure"])
            else:
                q = receipt["result"]
                if (
                    q["qm9_id"] != by_name[name]["qm9_id"]
                    or q["geometry_sha256"] != by_name[name]["member_sha256"]
                ):
                    raise ValueError("wrong physical identity")
                if a.extended == "adjoint":
                    directions = q["readout_directions"]
                    if len(directions) != len(t["targets"]) or any(
                        b not in (a, a[::-1]) for a, b in zip(t["targets"], directions)
                    ):
                        raise ValueError("invalid scalar readout map")
                    projected = dict(
                        q,
                        targets={
                            b: q["targets"][a] for a, b in zip(t["targets"], directions)
                        },
                    )
                    selected = dict(
                        fields=q["fields_requested"],
                        targets=list(dict.fromkeys(directions)),
                    )
                    quality = score(projected, selected, manifest, models[name])
                    error = max(
                        abs(
                            q["targets"][target]
                            - models[name]["targets"][
                                "xyz".index(target[0]), "xyz".index(target[1])
                            ]
                        )
                        for target in t["targets"]
                    )
                    quality["original_mask_max_error"] = float(error)
                    if error > 1e-5:
                        quality["status"] = "reject-and-recompute"
                else:
                    quality = score(q, t, manifest, models[name])
                if quality["status"] != "accepted" or (
                    mode == "isolation" and rid in FAULTS
                ):
                    errors.append(
                        [mode, rid, "unexpected independent quality disposition"]
                    )
            observed.append(dict(request_id=rid, **quality))
        block_shapes = [b["shapes"] for b in run["readout_blocks"]]
        if (
            run["ragged"]
            and not run["workspace_budget_fallback"]
            and run["batch_size"] > 1
            and not any(len(set(shapes)) > 1 for shapes in block_shapes)
        ):
            errors.append([mode, "no mixed-length GPU launch"])
        if run["runtime_mode"] == "async_streams" and any(
            b["readout_stream"] == 0 for b in run["readout_blocks"]
        ):
            errors.append([mode, "missing independent stream"])
        if mode == "budget" and (
            not run["workspace_budget_fallback"] or run["readout_slot_allocations"]
        ):
            errors.append([mode, "budget fallback did not execute"])
        results[mode] = dict(
            external_process_wall_s=wall[mode],
            receipts=observed,
            counts=dict(Counter(r["status"] for r in observed)),
            density_readout_shapes=block_shapes,
            compile_s=run["compile_seconds"],
            staging_allocations=run["readout_slot_allocations"],
            staging_capacity_bytes=run["readout_gpu_workspace_capacity_bytes"],
            response_operator_rows=sum(
                r.get("result", {}).get("operator_rows", 0) for r in run["receipts"]
            ),
        )
    summary = dict(
        schema="vibedataset.independent_prepared_readout.v1",
        status="failed" if errors else "passed",
        errors=errors,
        modes=results,
        independent_scorer_seconds=time.perf_counter() - started,
    )
    a.out.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(summary["status"], {m: v["counts"] for m, v in results.items()})
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
