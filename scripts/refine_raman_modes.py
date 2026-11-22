#!/usr/bin/env python3
"""Recompute Raman invariants from static polarizabilities on displaced geometries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invariants(derivative, bohr):
    symmetric = (derivative + derivative.T) * 0.5
    mean = np.trace(symmetric) / 3
    anisotropy_sq = 1.5 * np.sum((symmetric - np.eye(3) * mean) ** 2)
    denominator = 45 * mean**2 + 4 * anisotropy_sq
    if denominator <= 0 or not np.isfinite(denominator):
        raise ValueError("undefined depolarization ratio")
    return {"raman_A4_amu": (45 * mean**2 + 7 * anisotropy_sq) * bohr**4,
            "raman_depolarization": 3 * anisotropy_sq / denominator}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--gpu-run", type=Path)
    source.add_argument("--shared-result", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    protocol = json.loads(args.protocol.read_text())
    case = next(item for item in protocol["cases"] if item["id"] == plan["case_id"])
    if sha(args.protocol) != plan["parent_protocol_sha256"]:
        raise ValueError("refinement protocol mismatch")
    if args.shared_result:
        run = json.loads(args.shared_result.read_bytes())
        mode = plan.get("source_mode", "shared")
        source_digest = plan.get("source_run_sha256", plan.get("source_shared_sha256"))
        if (run["mode"] != mode or mode not in {"serial", "shared"} or run["protocol_sha256"] != sha(args.protocol)
                or sha(args.shared_result) != source_digest):
            raise ValueError("mismatched shared Hessian")
        candidates = [r["result"]["result"]["hessian"] for r in run["requests"]
                      if r["status"] == "accepted" and r["result"]["molecule"] == case["id"]
                      and r["result"]["property"] == "hessian"]
        if not candidates or any(not np.allclose(v,candidates[0],rtol=0,atol=1e-12) for v in candidates[1:]):
            raise ValueError("missing or ambiguous shared Hessian")
        observed = candidates[0]
        source_hashes = {"source_"+mode+"_sha256": sha(args.shared_result)}
    else:
        receipt = json.loads((args.gpu_run / "run.json").read_text())
        events = args.gpu_run / "events.jsonl"
        if not (sha(args.protocol) == receipt["inputs"]["protocol_sha256"]
                and receipt["backend"] == "gpu4pyscf" and sha(events) == receipt["events_sha256"]):
            raise ValueError("mismatched Hessian source")
        rows = [r for r in map(json.loads, events.read_text().splitlines())
                if r["id"] == case["id"] and r["status"] == "produced"]
        if len(rows) != 1:
            raise ValueError("expected one produced Hessian")
        observed = rows[0]["hessian"]
        source_hashes = dict(input_gpu_events_sha256=sha(events))
    from gpu4pyscf import scf
    from gpu4pyscf.properties import polarizability
    from pyscf import gto
    from pyscf.data import nist
    from pyscf.hessian.thermo import harmonic_analysis

    args.out.mkdir(parents=True, exist_ok=False)
    shells = {s: [[v["angular_momentum"], *v["primitives"]] for v in blocks]
              for s, blocks in protocol["shells"].items()}
    origin = np.asarray(case["xyz"])
    mol = gto.M(atom=list(zip(case["symbols"], origin)), basis=shells, unit="Bohr",
                charge=protocol["charge"], spin=protocol["spin"], cart=False, verbose=0)
    hessian = np.asarray(observed).reshape(mol.natm, 3, mol.natm, 3).transpose(0, 2, 1, 3)
    normal = harmonic_analysis(mol, hessian, imaginary_freq=False)
    steps = []
    start = perf_counter()
    with (args.out / "displacements.jsonl").open("x") as log:
        for step in plan["steps_bohr_sqrt_amu"]:
            result = []
            for index, mode in enumerate(normal["norm_mode"]):
                polar = []
                for sign in (-1, 1):
                    xyz = origin + sign * step * mode
                    row = dict(mode=index, step=step, sign=sign, xyz_bohr=xyz.tolist())
                    log.write(json.dumps(dict(row, status="started")) + "\n")
                    log.flush()
                    os.fsync(log.fileno())
                    displaced = mol.set_geom_(xyz, unit="Bohr", inplace=False)
                    mf = scf.RHF(displaced).set(conv_tol=protocol["scf_threshold"])
                    tick = perf_counter()
                    mf.kernel()
                    if not mf.converged:
                        raise RuntimeError(f"displaced SCF failed for mode {index} and sign {sign}")
                    value = np.asarray(polarizability.eval_polarizability(mf, tol=protocol["response_threshold"]))
                    if value.shape != (3, 3) or not np.isfinite(value).all():
                        raise ValueError("invalid static polarizability")
                    polar.append(value)
                    log.write(json.dumps(dict(row, status="produced", polarizability=value.tolist(),
                                              seconds=perf_counter()-tick, energy_hartree=float(mf.e_tot))) + "\n")
                    log.flush()
                result.append(invariants((polar[1] - polar[0]) / (2*step), nist.BOHR))
            steps.append(dict(step=step, modes=result))
    report = dict(schema="vibedataset.directional_raman_refinement.v1", protocol_sha256=sha(args.protocol),
                  plan_sha256=sha(args.plan), **source_hashes, driver_sha256=sha(Path(__file__)),
                  displacements_sha256=sha(args.out / "displacements.jsonl"), steps=steps,
                  signed_frequencies_cm1=normal["freq_wavenumber"].tolist(), elapsed_seconds=perf_counter()-start,
                  slurm_job=os.environ.get("SLURM_JOB_ID"))
    (args.out / "run.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
