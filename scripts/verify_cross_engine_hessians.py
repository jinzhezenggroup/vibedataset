#!/usr/bin/env python3
"""Independently score matched Hessians and the pre-specified Raman refinement."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def metric(reference, measured, tolerance):
    check(len(measured) == len(reference) > 0, "component count mismatch")
    check(all(finite(x) for x in [*reference, *measured]), "nonfinite component")
    errors = [abs(x-y) for x, y in zip(reference, measured)]
    return {"components": len(errors), "max_abs": max(errors), "worst_flat_index": errors.index(max(errors)),
            "rejected_indices": [i for i, err in enumerate(errors) if err > tolerance],
            "atol": tolerance, "accepted": max(errors) <= tolerance}


def observations(root, backend, cases, protocol_hash):
    folder = root / backend
    run = read(folder / "run.json")
    path = folder / "events.jsonl"
    check(run["backend"] == backend and run["inputs"]["protocol_sha256"] == protocol_hash and
          run["events_sha256"] == sha(path), f"{backend} identity mismatch")
    events = list(map(json.loads, path.read_text().splitlines()))
    check([(r["id"], r["status"]) for r in events] ==
          [(case["id"], stage) for case in cases for stage in ("started", "produced")],
          f"{backend} incomplete or duplicated rows")
    check(run["expected"] == len(cases) and run["failed"] == 0, "run denominator mismatch")
    return {r["id"]: r for r in events if r["status"] == "produced"}


def score_default(protocol, a, b):
    scores = {}
    for case in protocol["cases"]:
        name = case["id"]
        n = len(case["xyz"]) * 3
        x, y = a[name], b[name]
        check(x["nao"] == y["nao"] and x["logical_cartesian_rhs"] == y["logical_cartesian_rhs"] == n,
              f"{name} dimension mismatch")
        for row in (x, y):
            h = row["hessian"]
            check(len(h) == n and all(len(v) == n for v in h), "Hessian shape mismatch")
        props = {"energy_hartree": metric([x["energy"]], [y["energy"]], protocol["energy_atol_hartree"]),
                 "hessian_Eh_bohr2": metric(sum(x["hessian"], []), sum(y["hessian"], []), protocol["hessian_atol"])}
        sc = protocol["spectroscopy"]
        if name in sc["case_ids"]:
            check(set(x["spectroscopy"]) == set(y["spectroscopy"]) == set(sc["atol"]), "missing spectrum")
            for key, tol in sc["atol"].items():
                check(len(x["spectroscopy"][key]) == n-6, "unexpected nonlinear molecule mode count")
                props[key] = metric(x["spectroscopy"][key], y["spectroscopy"][key], tol)
            for row in (x, y):
                freq = row["spectroscopy"]["ir_frequency_cm1"]
                check(freq == sorted(freq), "mode ordering differs")
        scores[name] = props
    return scores


def refinement(root, protocol, protocol_hash, reference, initial):
    folder = root / "raman-refinement"
    plan = read(root / "raman-refinement.json")
    result = read(folder / "run.json")
    case = plan["case_id"]
    check(result["protocol_sha256"] == plan["parent_protocol_sha256"] == protocol_hash, "refinement protocol")
    check(result["plan_sha256"] == sha(root / "raman-refinement.json") and
          result["input_gpu_events_sha256"] == sha(root / "gpu4pyscf/events.jsonl"), "refinement input identity")
    path = folder / "displacements.jsonl"
    check(sha(path) == result["displacements_sha256"], "refinement journal hash")
    keys = ("raman_depolarization", "raman_A4_amu")
    check(not initial[case]["raman_depolarization"]["accepted"], "refinement trigger")
    events = list(map(json.loads, path.read_text().splitlines()))
    ref = reference[case]["spectroscopy"]
    geom = next(item for item in protocol["cases"] if item["id"] == case)
    n = len(ref[keys[0]])
    n_atom = len(geom["xyz"])
    steps = plan["steps_bohr_sqrt_amu"]
    check(len(steps) == 2 and 0 < steps[1] < steps[0] and plan["publish_index"] == 1, "step policy")
    check([(x["step"], x["mode"], x["sign"], x["status"]) for x in events] ==
          [(h, i, s, k) for h in steps for i in range(n) for s in (-1, 1) for k in ("started", "produced")],
          "incomplete displacement denominator")
    check([q["step"] for q in result["steps"]] == steps, "step identity")
    produced = {(r["step"], r["mode"], r["sign"]): r for r in events if r["status"] == "produced"}
    recomputed = []
    directions = {}
    for h, reported in zip(steps, result["steps"]):
        values = {key: [] for key in keys}
        for i in range(n):
            minus, plus = [produced[h, i, sign] for sign in (-1, 1)]
            coords = [r["xyz_bohr"] for r in (minus, plus)]
            check(all(len(z) == n_atom and all(len(v) == 3 for v in z) for z in coords), "coordinate shape")
            mode = [(v-u)/(2*h) for row1,row2 in zip(*coords) for u,v in zip(row1,row2)]
            center = [(u+v)/2 for row1,row2 in zip(*coords) for u,v in zip(row1,row2)]
            check(metric(sum(geom["xyz"], []), center, 1e-12)["accepted"], "displacement origin")
            masses = protocol["spectroscopy"]["masses_amu"]
            check(abs(sum(masses[geom["symbols"][j//3]] * v*v for j,v in enumerate(mode))-1) < 1e-9,
                  "normal-mode mass normalization")
            if i in directions:
                check(metric(directions[i], mode, 1e-9)["accepted"], "refinement displaced a different mode")
            directions[i] = mode
            tensors = [r["polarizability"] for r in (minus,plus)]
            check(all(len(t) == 3 and all(len(v)==3 and all(map(finite,v)) for v in t) for t in tensors), "tensor shape")
            diff = [[(tensors[1][j][k]-tensors[0][j][k])/(2*h) for k in range(3)] for j in range(3)]
            mean = math.fsum(diff[j][j] for j in range(3))/3
            anis = math.fsum((diff[j][j]-diff[k][k])**2/2 + 3*((diff[j][k]+diff[k][j])/2)**2
                       for j,k in ((0,1),(0,2),(1,2)))
            # PySCF 2.14.0 data/nist.py supplies the Bohr-to-angstrom conversion.
            values["raman_A4_amu"].append((45*mean**2+7*anis)*0.52917721092**4)
            values["raman_depolarization"].append(3*anis/(45*mean**2+4*anis))
        for key in keys:
            check(metric(values[key], [m[key] for m in reported["modes"]], 1e-7)["accepted"], "Raman invariant replay")
        recomputed.append(values)
    checks = {key: {"fine_vs_veloxchem": metric(ref[key], recomputed[1][key], initial[case][key]["atol"]),
                    "fine_vs_coarse": metric(recomputed[0][key], recomputed[1][key], initial[case][key]["atol"])}
              for key in keys}
    return {"accepted": all(m["accepted"] for pair in checks.values() for m in pair.values()),
            "scf_calculations": len(produced), "electric_rhs": 3*len(produced),
            "elapsed_seconds": result["elapsed_seconds"], "properties": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    protocol = read(args.root / "protocol.json")
    expected = sha(args.root / "protocol.json")
    a, b = (observations(args.root, k, protocol["cases"], expected) for k in ("veloxchem", "gpu4pyscf"))
    default = score_default(protocol, a, b)
    refined = refinement(args.root, protocol, expected, a, default)
    target = read(args.root / "raman-refinement.json")["case_id"]
    accepted = all(m["accepted"] or
                   (name == target and key in refined["properties"] and refined["accepted"])
                   for name, props in default.items() for key, m in props.items())
    frequencies = a[target]["spectroscopy"]["ir_frequency_cm1"]
    result = dict(schema="vibedataset.hessian_cross_engine_score.v1", protocol_sha256=expected,
                  nominal_cartesian_rhs=sum(row["logical_cartesian_rhs"] for row in a.values()),
                  hessian_components=sum(row["hessian_Eh_bohr2"]["components"] for row in default.values()),
                  default=default, raman_refinement=refined, all_requested_properties_accepted=accepted,
                  imaginary_modes={target:[i for i, x in enumerate(frequencies) if x < 0]})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(f'{result["hessian_components"]} Hessian components, accepted after refinement = {accepted}')
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
