#!/usr/bin/env python3
"""Match each scheduled readout to VeloxChem, retaining failed requests and refinements."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from verify_cross_engine_hessians import check, metric, observations


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p):
    return json.loads(p.read_bytes())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--root",
        type=Path,
        required=True,
        help="contains serial/shared/failures and veloxchem",
    )
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--refinement", type=Path)
    p.add_argument("--serial-refinement", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    spec = load(a.protocol)
    seal = digest(a.protocol)
    refs = observations(a.root, "veloxchem", spec["cases"], seal)
    queue = spec["shared_queue"]
    thresholds = spec["spectroscopy"]["atol"]
    names = {q["id"] for q in queue}
    unqualified = set()
    history = {}
    source_paths = {}
    cases = {c["id"]: c for c in spec["cases"]}
    per_mode = {}
    for kind in ("serial", "shared"):
        file = a.root / kind / "result.json"
        run = load(file)
        check(
            run["mode"] == kind and run["protocol_sha256"] == seal,
            "mismatched scheduler protocol",
        )
        candidates = {r["request_id"]: r for r in run["requests"]}
        check(
            len(candidates) == len(run["requests"]) and set(candidates) == names,
            "denominator",
        )
        source_paths[kind] = digest(file)
        per_mode[kind] = {}
        for req in queue:
            name, prop, rid = req["molecule"], req["property"], req["id"]
            cand = candidates[rid]
            reference = refs[name]
            if cand["status"] != "accepted":
                per_mode[kind][rid] = dict(
                    status="producer-failed", reason=cand["reason"]
                )
                continue
            row = cand["result"]
            check(
                (row["molecule"], row["property"]) == (name, prop),
                "property identity mismatch",
            )
            result = row["result"]
            measurements = {
                "scf_energy": metric(
                    [reference["energy"]],
                    [row["energy_hartree"]],
                    spec["energy_atol_hartree"],
                )
            }
            if prop == "hessian":
                n = len(cases[name]["symbols"]) * 3
                check(
                    len(result["hessian"]) == n
                    and all(len(v) == n for v in result["hessian"]),
                    "Hessian axes",
                )
                measurements["hessian"] = metric(
                    sum(reference["hessian"], []),
                    sum(result["hessian"], []),
                    spec["hessian_atol"],
                )
            else:
                expected = [k for k in thresholds if k.startswith(prop + "_")]
                check(
                    set(expected) == set(result),
                    "missing or unplanned spectral readout",
                )
                for key in expected:
                    measurements[key] = metric(
                        reference["spectroscopy"][key], result[key], thresholds[key]
                    )
            failed = [k for k, v in measurements.items() if not v["accepted"]]
            per_mode[kind][rid] = dict(
                status="default-rejected" if failed else "accepted",
                failed=failed,
                components=measurements,
            )
            if (
                failed
                and prop == "raman"
                and set(failed) <= {"raman_A4_amu", "raman_depolarization"}
            ):
                unqualified.add(name)
        records = run["history"]
        history[kind] = dict(
            scf_started=sum(
                r["kind"] == "SCF" and r.get("status") == "started" for r in records
            ),
            scf_finished=sum(
                r["kind"] == "SCF" and r.get("status") == "finished" for r in records
            ),
            geometric_cphf_solves=sum(
                r["kind"] == "geometric-CPHF" and not r["reused"] for r in records
            ),
            geometric_rhs=sum(r.get("newly_solved_cartesian_rhs", 0) for r in records),
            geometric_cphf_hits=sum(
                r["kind"] == "geometric-CPHF" and r["reused"] for r in records
            ),
            hessian_reuses=sum(r["kind"] == "hessian" and r["reused"] for r in records),
            total_s=run["elapsed_seconds"],
        )
    failure = load(a.root / "failures/result.json")
    check(failure["protocol_sha256"] == seal, "failure protocol")
    fail_rows = {r["request_id"]: r for r in failure["requests"]}
    expected = {
        "single-request-scf-failure": "scf_nonconvergence",
        "allocator-oom": "OutOfMemoryError",
        "unsupported-property": "unsupported_property",
        "restricted-H2-stretched-gap": "restricted_state_near_degenerate",
    }
    check(
        set(fail_rows) == set(spec["failure_controls"])
        and len(failure["requests"]) == len(fail_rows),
        "failure denominator",
    )
    failures = {}
    for rid, reason in expected.items():
        r = fail_rows[rid]
        failures[rid] = dict(
            disposition=r["status"],
            reason=r.get("reason"),
            matched=reason in r.get("reason", "")
            or (
                reason == "OutOfMemoryError"
                and "out of memory" in r.get("reason", "").lower()
            ),
        )
    healthy = fail_rows["healthy-after-failures"]
    if healthy["status"] == "accepted":
        h = healthy["result"]["result"]["hessian"]
        failures["healthy-after-failures"] = metric(
            sum(refs["h2o"]["hessian"], []), sum(h, []), spec["hessian_atol"]
        )
    else:
        failures["healthy-after-failures"] = dict(
            accepted=False, reason=healthy.get("reason")
        )
    refined = {"shared": {}, "serial": {}}
    correction_cost = {"shared": {}, "serial": {}}
    for mode, root in (("shared", a.refinement), ("serial", a.serial_refinement)):
        if root is None:
            continue
        for req in queue:
            name, rid = req["molecule"], req["id"]
            if (
                name not in unqualified
                or req["property"] != "raman"
                or per_mode[mode][rid]["status"] != "default-rejected"
            ):
                continue
            key = name if mode == "shared" else rid
            if key in refined[mode]:
                continue
            directory = root / key
            run = load(directory / "run.json")
            check(
                run["protocol_sha256"] == seal
                and run["source_" + mode + "_sha256"] == source_paths[mode],
                "refinement identity",
            )
            log = directory / "displacements.jsonl"
            check(digest(log) == run["displacements_sha256"], "displacement journal")
            expected_steps = spec["refinement_steps_bohr_sqrt_amu"]
            check(
                [v["step"] for v in run["steps"]] == expected_steps,
                "refinement step set",
            )
            n = len(refs[name]["spectroscopy"]["raman_frequency_cm1"])
            displacement_rows = [
                json.loads(line) for line in log.read_bytes().splitlines()
            ]
            pairs = [
                (r["step"], r["mode"], r["sign"], r["status"])
                for r in displacement_rows
            ]
            expected_pairs = [
                (step, i, sign, status)
                for step in expected_steps
                for i in range(n)
                for sign in (-1, 1)
                for status in ("started", "produced")
            ]
            check(
                pairs == expected_pairs,
                "incomplete or duplicated directional Raman calculation",
            )
            corrected = []
            for item in run["steps"]:
                metrics = {
                    quantity: metric(
                        refs[name]["spectroscopy"][quantity],
                        [v[quantity] for v in item["modes"]],
                        thresholds[quantity],
                    )
                    for quantity in ("raman_A4_amu", "raman_depolarization")
                }
                corrected.append(
                    dict(
                        step=item["step"],
                        passed=all(v["accepted"] for v in metrics.values()),
                        metrics=metrics,
                    )
                )
            refined[mode][key] = corrected
            correction_cost[mode][key] = dict(
                displaced_scf_calls=len(pairs) // 2,
                electric_rhs=3 * len(pairs) // 2,
                seconds=run["elapsed_seconds"],
                job=run["slurm_job"],
            )
    final = {}
    for mode, items in per_mode.items():
        dispositions = {}
        for req in queue:
            r = items[req["id"]]
            name = req["molecule"]
            ok = r["status"] == "accepted" or (
                r["status"] == "default-rejected"
                and req["property"] == "raman"
                and set(r["failed"]) <= {"raman_A4_amu", "raman_depolarization"}
                and (name if mode == "shared" else req["id"]) in refined[mode]
                and all(
                    x["passed"]
                    for x in refined[mode][name if mode == "shared" else req["id"]]
                )
            )
            dispositions[req["id"]] = "accepted" if ok else r["status"]
        final[mode] = dict(
            dispositions=dispositions, counts=dict(Counter(dispositions.values()))
        )
    imaginary = {
        n: [v for v in r["spectroscopy"]["ir_frequency_cm1"] if v < 0]
        for n, r in refs.items()
    }
    neighbors = {
        n: [
            (x, y)
            for x, y in zip(
                r["spectroscopy"]["ir_frequency_cm1"],
                r["spectroscopy"]["ir_frequency_cm1"][1:],
            )
            if abs(x - y) < 5
        ]
        for n, r in refs.items()
    }
    output = dict(
        schema="vibedataset.shared_spectroscopy_score.v1",
        inputs=source_paths,
        protocol_sha256=seal,
        defaults=per_mode,
        history=history,
        refinement_required=sorted(unqualified),
        refinement=refined,
        correction_cost=correction_cost,
        final=final,
        controls=failures,
        gap_control=failure["controls"],
        imaginary_modes_cm1=imaginary,
        neighbors_within_5_cm1=neighbors,
        veloxchem_reference_sha256=digest(a.root / "veloxchem/events.jsonl"),
    )
    a.out.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            dict(
                measured=history,
                refinement_required=sorted(unqualified),
                final={m: r["counts"] for m, r in final.items()},
            )
        )
    )


if __name__ == "__main__":
    main()
