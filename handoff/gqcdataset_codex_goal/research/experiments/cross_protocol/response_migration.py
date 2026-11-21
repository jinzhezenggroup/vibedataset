"""Blind response-asset migration producer and independent scorer for #27."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from pyscf import gto, scf
from pyscf.scf import cphf


ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
WATER = "O 0.000000 0.000000 0.000000; H 0.000000 -1.432336 1.107153; H 0.000000 1.432336 1.107153"
H2PLUS = "H 0.000000 0.000000 0.000000; H 0.000000 0.000000 1.400000"
H2_STRETCHED = "H 0.000000 0.000000 0.000000; H 0.000000 0.000000 10.000000"
TARGET_TOLERANCE = 1e-8
RESIDUAL_TOLERANCE = 1e-10


def sha(value):
    return hashlib.sha256(value).hexdigest()


def make_molecule(atom, basis, charge=0, spin=0):
    return gto.M(atom=atom, unit="Bohr", basis=basis, charge=charge, spin=spin, cart=False, verbose=0)


def make_scf(mol, method):
    if method == "rhf":
        mf = scf.RHF(mol)
    elif method == "b3lyp":
        mf = scf.RKS(mol)
        mf.xc = "b3lyp"
    elif method == "uhf":
        mf = scf.UHF(mol)
    else:
        raise ValueError(method)
    mf.conv_tol = 1e-10
    mf.conv_tol_grad = 1e-8
    mf.max_cycle = 100
    mf.verbose = 0
    return mf


def operators(mol):
    overlap = mol.intor_symmetric("int1e_ovlp")
    with mol.with_common_orig((0., 0., 0.)):
        field = mol.intor("int1e_r", comp=3)
        moments = mol.intor("int1e_rr", comp=9).reshape(3, 3, mol.nao_nr(), mol.nao_nr())
    lo, hi = mol.aoslice_by_atom()[0, 2:]
    mask = np.zeros(mol.nao_nr())
    mask[lo:hi] = 1
    q0 = -0.5 * (mask[:, None] + mask[None, :]) * overlap
    return field, q0


def solve_response(atom, basis, method, charge=0, spin=0):
    started = time.perf_counter()
    mol = make_molecule(atom, basis, charge, spin)
    mf = make_scf(mol, method)
    energy = mf.kernel()
    record = {
        "method": method, "basis": basis, "charge": charge, "spin": spin,
        "multiplicity": spin + 1, "nelectron": mol.nelectron, "nao": mol.nao_nr(),
        "scf_converged": bool(mf.converged), "energy_hartree": float(energy),
        "scf_cycles": int(getattr(mf, "cycles", -1)),
    }
    if not mf.converged:
        record.update(status="scf_unconverged", seconds=time.perf_counter() - started)
        return record
    if method == "uhf" or spin != 0:
        record.update(status="response_evidence_unavailable", reason="restricted RHF/RKS response evaluator cannot certify open shell",
                      seconds=time.perf_counter() - started)
        return record
    occ = mf.mo_occ > 0
    co, cv = mf.mo_coeff[:, occ], mf.mo_coeff[:, ~occ]
    gap = mf.mo_energy[~occ, None] - mf.mo_energy[None, occ]
    if not np.all(gap > 0):
        record.update(status="response_evidence_unavailable", reason="nonpositive orbital gap",
                      minimum_gap_hartree=float(np.min(gap)), seconds=time.perf_counter() - started)
        return record
    fields, q0 = operators(mol)
    h = np.einsum("ua,xuv,vi->xai", cv, fields, co)
    counter = Counter()
    base_vind = mf.gen_response(hermi=1, singlet=True)

    def vind(rotations):
        counter["response_operator_actions"] += 1
        counter["density_columns"] += len(rotations)
        half = 2 * np.einsum("ua,xai,vi->xuv", cv, rotations, co)
        density = half + half.transpose(0, 2, 1)
        return np.einsum("ua,xuv,vi->xai", cv, base_vind(density), co)

    response, _ = cphf.solve(vind, mf.mo_energy, mf.mo_occ, h[:1], tol=1e-12, max_cycle=200)
    vector = np.asarray(response[0], dtype=np.float64).reshape(-1)
    half = 2 * np.einsum("ua,ai,vi->uv", cv, response[0], co)
    density = half + half.T
    residual = h[0] + (gap * response[0]) + vind(response)[0]
    label = float(np.einsum("uv,vu->", q0, density))
    record.update(status="qualified", dimension=int(vector.size), minimum_gap_hartree=float(np.min(gap)),
                  response_vector=vector.tolist(), response_vector_sha256=sha(vector.astype("<f8").tobytes()),
                  target_value=label, physical_residual_l2=float(np.linalg.norm(residual)),
                  response_counts=dict(counter), seconds=time.perf_counter() - started)
    return record


def source_asset():
    result = solve_response(WATER, "sto-3g", "rhf")
    if result["status"] != "qualified":
        raise RuntimeError(result)
    result.update(asset_id="water-rhf-sto3g-x-q0", geometry=WATER, field="x", observable="q0",
                  protocol_identity=sha(json.dumps({"geometry": WATER, "method": "rhf", "basis": "sto-3g",
                                                     "charge": 0, "spin": 0, "origin_bohr": [0, 0, 0]}, sort_keys=True).encode()))
    return result


def produce(out):
    out.mkdir(parents=True, exist_ok=False)
    asset = source_asset()
    sealed = {
        "protocol": {"target_labels_read": False, "producer": "response_migration.py",
                     "source_asset_protocol": "RHF/STO-3G, water, field x, q0, origin 0"},
        "source_asset": asset,
        "requests": [
            {"id": "direct_same_protocol", "classification": "direct_reuse", "geometry": WATER,
             "method": "rhf", "basis": "sto-3g", "charge": 0, "spin": 0, "field": "x", "observable": "q0"},
            {"id": "basis_change", "classification": "initial_guess_only", "geometry": WATER,
             "method": "rhf", "basis": "6-31g*", "charge": 0, "spin": 0, "field": "x", "observable": "q0"},
            {"id": "method_change", "classification": "refine_required", "geometry": WATER,
             "method": "b3lyp", "basis": "6-31g*", "charge": 0, "spin": 0, "field": "x", "observable": "q0"},
            {"id": "open_shell", "classification": "reject_and_recompute", "geometry": H2PLUS,
             "method": "uhf", "basis": "sto-3g", "charge": 1, "spin": 1, "field": "x", "observable": "q0"},
            {"id": "low_gap", "classification": "evidence_unavailable", "geometry": H2_STRETCHED,
             "method": "rhf", "basis": "sto-3g", "charge": 0, "spin": 0, "field": "x", "observable": "q0"},
        ],
    }
    (out / "sealed.json").write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "seal.json").write_text(json.dumps({"sealed_sha256": sha((out / "sealed.json").read_bytes()),
                                                "target_labels_read": False}, indent=2, sort_keys=True) + "\n")
    return sealed


def score(sealed_path, out):
    sealed = json.loads(sealed_path.read_bytes())
    if sealed["protocol"]["target_labels_read"]:
        raise AssertionError("producer used target labels")
    out.mkdir(parents=True, exist_ok=False)
    evaluations = []
    for request in sealed["requests"]:
        target = solve_response(request["geometry"], request["basis"], request["method"], request["charge"], request["spin"])
        row = {"id": request["id"], "classification": request["classification"], "target": target}
        if request["id"] == "direct_same_protocol":
            source = sealed["source_asset"]
            vector_error = float(np.max(np.abs(np.asarray(source["response_vector"]) - np.asarray(target["response_vector"]))))
            target_error = abs(float(source["target_value"]) - float(target["target_value"]))
            row.update(status="accepted" if vector_error <= 1e-12 and target_error <= TARGET_TOLERANCE and
                       target["physical_residual_l2"] <= RESIDUAL_TOLERANCE else "reject",
                       vector_error=vector_error, target_error=target_error,
                       residual=target["physical_residual_l2"])
        elif request["id"] == "low_gap":
            row.update(status="evidence_unavailable", reason=target.get("reason", "low gap"),
                       minimum_gap_hartree=target.get("minimum_gap_hartree"))
        elif request["id"] == "open_shell":
            row.update(status="reject_and_recompute", reason=target.get("reason", "open-shell response evaluator"),
                       target_scf_converged=target.get("scf_converged"))
        else:
            row.update(status=request["classification"], target_response_recomputed=True,
                       target_value=target.get("target_value"), target_residual=target.get("physical_residual_l2"),
                       target_scf_converged=target.get("scf_converged"))
        evaluations.append(row)
    result = {"source_asset": sealed["source_asset"], "evaluations": evaluations,
              "target_labels_read_by_producer": False,
              "counts": {status: sum(row["status"] == status for row in evaluations) for status in sorted({row["status"] for row in evaluations})}}
    (out / "score.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if not any(row["id"] == "direct_same_protocol" and row["status"] == "accepted" for row in evaluations):
        raise AssertionError("direct response asset did not pass")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("produce", "score"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sealed", type=Path)
    args = parser.parse_args()
    if args.mode == "produce":
        print(json.dumps({"status": "sealed", "asset": produce(args.out)["source_asset"]["asset_id"]}, sort_keys=True))
    else:
        if args.sealed is None:
            raise SystemExit("--sealed required")
        print(json.dumps(score(args.sealed, args.out), sort_keys=True))


if __name__ == "__main__":
    main()
