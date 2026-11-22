#!/usr/bin/env python3
"""Certify spin-summed AO response densities in an independent RHF reference gauge."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pyscf
from pyscf import gto, lib, scf
from pyscf.data.elements import ELEMENTS

from cphf_reference import MAX_DIMENSION, solve_reference


AXES = "xyz"
TOL = 1e-5


def digest(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def reference(item, protocol):
    if (protocol["method"],protocol["unit"],protocol["precision"],protocol["basis_representation"],
        item["multiplicity"]) != ("RHF","Bohr","FP64","real_spherical",1):
        raise ValueError("unsupported reference identity")
    mol = gto.M(atom=[(ELEMENTS[z],pos) for z,pos in zip(item["atomic_numbers"],item["coordinates_bohr"])],
                basis=protocol["basis"], unit="Bohr", spin=0, charge=item["charge"], cart=False, verbose=0)
    mf = scf.RHF(mol).set(conv_tol=protocol["conv_tol"], max_cycle=protocol["max_cycle"])
    mf.kernel()
    if not mf.converged:
        raise ValueError("CPU reference SCF did not converge")
    occ = mf.mo_occ > 0
    co, cv = mf.mo_coeff[:,occ], mf.mo_coeff[:,~occ]
    if not 0 < co.shape[1]*cv.shape[1] <= MAX_DIMENSION:
        raise ValueError("outside bounded represented reference dimension")
    with mol.with_common_orig(tuple(protocol["origin"])):
        position = mol.intor("int1e_r",comp=3)
    evidence, counts = {}, Counter()
    # The GPU field RHS has h_ai = -<a|r|i>. The readout uses +r.
    targets = np.asarray(solve_reference(mf, mol.intor("int2e"), -position, position, evidence, counts))
    x = np.asarray(evidence["dense"]["solution_ai"])
    half = 2 * np.einsum("ua,dai,vi->duv",cv,x,co)
    overlap = mf.get_ovlp()
    return {"mf":mf,"co":co,"cv":cv,"s":overlap,"r":position,
            "rhs":np.einsum("ua,duv,vi->dai",cv,position,co),
            "gap":mf.mo_energy[~occ,None]-mf.mo_energy[None,occ],
            "density":half+half.transpose(0,2,1),"targets":targets,
            "sigma_min": evidence["sigma_min"],"max_ref_residual":max(evidence["dense"]["physical_residual_l2"]),
            "condition":evidence["condition_number"],"cost":dict(counts)}


def row_score(row, request, manifest, ref):
    if row.get("status","accepted") != "accepted":
        raise ValueError("producer did not produce the request")
    if row["input_sha256"] != manifest["manifest_sha256"] or row["protocol"] != manifest["protocol"]:
        raise ValueError("protocol identity mismatch")
    fields, targets = request["fields"], request["targets"]
    if (row["fields_requested"] != fields or set(row["response_densities"]) != set(fields)
        or set(row["targets"]) != set(targets)):
        raise ValueError("field or readout identity mismatch")
    idx = [AXES.index(field) for field in fields]
    n = ref["co"].shape[0]
    flat = np.asarray([row["response_densities"][f] for f in fields],dtype=np.float64)
    values = np.asarray([row["targets"][name] for name in targets],dtype=np.float64)
    if flat.shape != (len(fields),n*n) or not np.isfinite(flat).all() or not np.isfinite(values).all():
        raise ValueError("invalid candidate density or target")
    dm = flat.reshape(-1,n,n)
    # S C_v and S C_o project the *observed AO density* into this independently
    # converged MO basis. This also handles rotations of degenerate subspaces.
    cv, co, s = ref["cv"], ref["co"], ref["s"]
    x = (cv.T @ s @ dm @ s @ co) * 0.5
    half = 2 * (cv @ x @ co.T)
    jk_dm = half + half.transpose(0,2,1)
    j,k = ref["mf"].get_jk(dm=jk_dm,hermi=1)
    residual = x*ref["gap"] + cv.T@(j-0.5*k)@co - ref["rhs"][idx]
    measured = np.einsum("duv,kvu->dk",dm,ref["r"])
    physical_q = [measured[fields.index(l),AXES.index(r)] for l,r in targets]
    dense_q = [ref["targets"][AXES.index(l),AXES.index(r)] for l,r in targets]
    metrics = {
        "candidate_physical_residual_linf":float(np.max(abs(residual))),
        "dense_reference_residual_l2":ref["max_ref_residual"],
        "ao_tangent_reconstruction_linf":float(np.max(abs(dm-jk_dm))),
        "candidate_vs_dense_density_linf":float(np.max(abs(dm-ref["density"][idx]))),
        "readout_vs_candidate_density_linf":float(np.max(abs(values-physical_q))),
        "readout_vs_dense_reference_linf":float(np.max(abs(values-dense_q))),
    }
    failed = [key for key,v in metrics.items() if not np.isfinite(v) or v>TOL]
    return dict(status="reject-and-recompute" if failed else "accepted", failed_gates=failed,metrics=metrics,
                per_field_residual_linf={field:float(np.max(abs(r))) for field,r in zip(fields,residual)})


def score(row, request, manifest, ref):
    try:
        return row_score(row, request, manifest, ref)
    except (KeyError,TypeError,ValueError) as exc:
        return {"status":"reject-and-recompute","reason":str(exc)}


def controls(original, request, manifest, ref):
    field = request["fields"][0]
    trials = {}
    for kind in ("truncated_density","nan_density","wrong_finite_density","wrong_readout","wrong_unit","wrong_rhs"):
        row = deepcopy(original)
        if kind=="truncated_density":
            row["response_densities"][field].pop()
        elif kind=="nan_density":
            row["response_densities"][field][0]=float("nan")
        elif kind=="wrong_finite_density":
            row["response_densities"][field][0]+=0.1
        elif kind=="wrong_readout":
            row["targets"][request["targets"][0]]+=0.1
        elif kind=="wrong_unit":
            row["protocol"]["unit"]="Angstrom"
        else:
            axis = AXES.index(field)
            other = ref["density"][(axis + 1) % 3]
            row["response_densities"][field] = other.reshape(-1).tolist()
        trials[kind]=score(row,request,manifest,ref)
    return trials


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--raw-root",type=Path,required=True,help="contains A/raw.jsonl through D/raw.jsonl")
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    tic=time.perf_counter()
    manifest=json.loads(args.manifest.read_bytes())
    identity=dict(manifest); expected=identity.pop("manifest_sha256")
    if digest(identity)!=expected:
        raise ValueError("invalid manifest seal")
    observations=defaultdict(list)
    inputs={}
    for arm in "ABCD":
        path=args.raw_root/arm/"raw.jsonl"
        inputs[arm]=hashlib.sha256(path.read_bytes()).hexdigest()
        for line in path.read_text().splitlines():
            row=json.loads(line)
            observations[arm,row["molecule"],row["trajectory"]].append((row, hashlib.sha256(line.encode()).hexdigest()))
    results=[]; models=[]; negative={}
    for item in manifest["molecules"]:
        started=time.perf_counter()
        try:
            ref=reference(item,manifest["protocol"])
            models.append(dict(molecule=item["name"],sigma_min=ref["sigma_min"],condition=ref["condition"],
                               cpu_reference_cost=ref["cost"],seconds=time.perf_counter()-started))
        except (ValueError,RuntimeError,np.linalg.LinAlgError) as exc:
            ref=None
            models.append(dict(molecule=item["name"],failure=str(exc),seconds=time.perf_counter()-started))
        for request in manifest["request_trajectories"]:
            for arm in "ABCD":
                key=arm,item["name"],request["id"]
                candidates=observations.pop(key,[])
                start=time.perf_counter()
                if len(candidates)!=1 or candidates[0][0].get("arm")!=arm or candidates[0][0].get("qm9_id")!=item["qm9_id"]:
                    quality={"status":"reject-and-recompute","reason":"missing, duplicate or mislabeled record"}
                elif ref is None:
                    quality={"status":"evidence-unavailable","reason":models[-1]["failure"]}
                else:
                    candidate, raw_line_hash=candidates[0]
                    quality=score(candidate,request,manifest,ref)
                    quality["raw_line_sha256"]=raw_line_hash
                results.append(dict(arm=arm,molecule=item["name"],trajectory=request["id"],
                                    geometry_sha256=item["member_sha256"],validation_seconds=time.perf_counter()-start,**quality))
                if not negative and quality["status"]=="accepted":
                    negative=controls(candidate,request,manifest,ref)
    if observations:
        raise ValueError(f"unplanned candidate rows: {list(observations)[:4]}")
    receipt=dict(schema="vibedataset.cpu_ao_response_score.v1",manifest_sha256=expected,input_files=inputs,
                 code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),pyscf=pyscf.__version__,
                 cpu_threads=lib.num_threads(), threshold=TOL, scope="AO first-order density and target readouts",
                 models=models,rows=results,counts=dict(Counter(r["status"] for r in results)),negative_controls=negative,
                 full_scorer_seconds=time.perf_counter()-tic)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_bytes(gzip.compress((json.dumps(receipt,allow_nan=False,separators=(",",":"))+"\n").encode(),mtime=0))
    print(receipt["counts"], {k:v["status"] for k,v in negative.items()})
    if not negative or any(v["status"]!="reject-and-recompute" for v in negative.values()):
        raise SystemExit("unexpected negative-control decision")


if __name__=="__main__":
    main()
