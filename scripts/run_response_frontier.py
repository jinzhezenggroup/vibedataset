#!/usr/bin/env python3
"""Execute identity-bound reuse, projected refinements and ordinary recomputations."""

import argparse
import gzip
import hashlib
import json
import os
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
from pyscf import dft, gto
from pyscf.data.elements import ELEMENTS

from compile_response_assets import classify
from run_gpu4pyscf_4arm import load_manifest


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def float_hash(a):
    return sha(np.ascontiguousarray(a, dtype="<f8").tobytes())


def target(item, protocol, change):
    item, protocol = deepcopy(item), deepcopy(protocol)
    if change == "split-valence":
        protocol["basis"] = "6-31g*"
    elif change == "hybrid-functional":
        protocol["method"] = "B3LYP"
    elif change == "displaced":
        item["coordinates_bohr"][-1][0] += 0.02
    elif change == "different-origin":
        protocol["origin"] = [0.1, 0.0, 0.0]
    elif change == "open-shell":
        item["charge"] = 1
        item["multiplicity"] = 2
    atoms = [
        (ELEMENTS[z], coords)
        for z, coords in zip(item["atomic_numbers"], item["coordinates_bohr"])
    ]
    mol = gto.M(
        atom=atoms,
        basis=protocol["basis"],
        unit=protocol["unit"],
        cart=False,
        spin=item["multiplicity"] - 1,
        charge=item["charge"],
        verbose=0,
    )
    grids = None
    if protocol["method"] == "B3LYP":
        grids = dft.gen_grid.Grids(mol)
        grids.level = 3
        grids.build()
    identity = dict(
        protocol,
        charge=item["charge"],
        multiplicity=item["multiplicity"],
        ordered_geometry_sha256=sha(canonical(atoms)),
        basis_parameters_sha256=sha(canonical(mol._basis)),
        grid_sha256=None
        if grids is None
        else sha(canonical([float_hash(grids.coords), float_hash(grids.weights)])),
        rhs=["electric-field-x", "electric-field-y", "electric-field-z"],
        state="lowest converged canonical restricted SCF",
    )
    return mol, identity, grids


def sealed_sources(raw_path, certificates, manifest, trajectory):
    data = raw_path.read_bytes()
    cert = json.loads(gzip.decompress(certificates.read_bytes()))
    if (
        sha(data) != cert["input_files"]["C"]
        or cert["manifest_sha256"] != manifest["manifest_sha256"]
    ):
        raise ValueError("sealed source stream mismatch")
    scores = {
        row["molecule"]: row
        for row in cert["rows"]
        if row["arm"] == "C" and row["trajectory"] == trajectory
    }
    assets = {}
    for line in data.splitlines():
        row = json.loads(line)
        if row["trajectory"] != trajectory:
            continue
        score = scores[row["molecule"]]
        checksum = sha(line)
        if (
            score["status"] != "accepted"
            or checksum != score["raw_line_sha256"]
            or row["protocol"] != manifest["protocol"]
        ):
            raise ValueError("source lacks a matching independent AO certificate")
        assets[row["molecule"]] = row, checksum, score["geometry_sha256"]
    return assets


def gpu_case(
    mol, identity, grids, source_mol, source_identity, source, mode, change, limits
):
    import cupy as cp
    from gpu4pyscf import dft as gpu_dft, scf
    from gpu4pyscf.scf import cphf
    from gpu4pyscf.properties.polarizability import gen_vind

    started = time.perf_counter()
    if identity["multiplicity"] != 1:
        return dict(
            status="evidence-unavailable",
            action="reject-and-recompute",
            reason="restricted_solver_unsupported",
            attempted_target_solves=0,
            fields_requested=3,
        )
    if grids is None:
        mf = scf.RHF(mol)
    else:
        mf = gpu_dft.RKS(mol)
        mf.xc = "b3lyp"
        mf.grids.coords, mf.grids.weights = (
            cp.asarray(grids.coords),
            cp.asarray(grids.weights),
        )
        mf.small_rho_cutoff = 0
    mf.conv_tol, mf.conv_tol_grad, mf.max_cycle = (
        identity["conv_tol"],
        1e-8,
        identity["max_cycle"],
    )
    mf.kernel()
    if not mf.converged:
        raise RuntimeError("target SCF nonconvergence")
    scf_seconds = time.perf_counter() - started
    prepare = time.perf_counter()
    mo, occ, energies = mf.mo_coeff, mf.mo_occ, mf.mo_energy
    co, cv = mo[:, occ > 0], mo[:, occ == 0]
    gap = energies[occ == 0, None] - energies[None, occ > 0]
    with mol.with_common_orig(tuple(identity["origin"])):
        pos = cp.asarray(mol.intor("int1e_r", comp=3))
    rhs = cv.T @ pos @ co
    op = gen_vind(mf, mo, occ)
    solver_rows = 0

    def counted(x):
        nonlocal solver_rows
        solver_rows += x.shape[0]
        return op(x)

    def residual(x):
        return float(cp.max(cp.abs(gap * x + op(x) - rhs)).item())

    planning = {
        "requested_action": "cold-solve",
        "reason": "ordinary_official_baseline",
    }
    guess = None
    before = None
    source_row, source_sha, _ = source
    if mode == "planned":
        action, reason = classify(source_identity, identity)
        planning.update(requested_action=action, reason=reason)
        if change == "stale-bytes":
            corrupt = deepcopy(source_row)
            corrupt["response_densities"]["x"][0] += 0.1
            # The certifier signed the SHA of the original line, serialized with sorted keys.
            if sha(json.dumps(corrupt, sort_keys=True).encode()) != source_sha:
                action, reason = "reject-and-recompute", "stale_source_seal"
        if action in ("direct_reuse", "refine_required"):
            dm = np.asarray(
                [source_row["response_densities"][f] for f in "xyz"]
            ).reshape(3, source_mol.nao, source_mol.nao)
            if change == "field-swapped":
                dm = dm[[1, 0, 2]]
            if change == "frozen-density":
                dm = np.zeros_like(dm)
            overlap = mol.intor_symmetric("int1e_ovlp")
            if (
                identity["basis_parameters_sha256"]
                != source_identity["basis_parameters_sha256"]
            ):
                transform = np.linalg.solve(
                    overlap, gto.intor_cross("int1e_ovlp", mol, source_mol)
                )
                dm = transform @ dm @ transform.T
            sg = cp.asarray(overlap)
            guess = (cv.T @ sg @ cp.asarray(dm) @ sg @ co) / 2
            before = residual(guess)
            if not np.isfinite(before):
                action, reason, guess = (
                    "reject-and-recompute",
                    "nonfinite_target_residual",
                    None,
                )
            elif action == "direct_reuse" and before > limits["gpu_residual_linf"]:
                action, reason, guess = (
                    "reject-and-recompute",
                    "failed_target_residual",
                    None,
                )
        planning.update(action=action, decision_reason=reason)
    else:
        action = "cold-solve"
    prepare_seconds = time.perf_counter() - prepare
    solve = time.perf_counter()
    x = guess
    solves = 0
    if action != "direct_reuse":
        x, _ = cphf.solve(
            counted,
            energies,
            occ,
            -rhs,
            mo10=guess,
            max_cycle=identity["response_max_cycle"],
            tol=identity["response_tol"],
            verbose=0,
        )
        solves = 1
    cp.cuda.Stream.null.synchronize()
    solve_seconds = time.perf_counter() - solve
    check = time.perf_counter()
    final = residual(x)
    fallback_seconds = 0.0
    if (
        not np.isfinite(final) or final > limits["gpu_residual_linf"]
    ) and action == "refine_required":
        retry = time.perf_counter()
        x, _ = cphf.solve(
            counted, energies, occ, -rhs, max_cycle=100, tol=1e-12, verbose=0
        )
        cp.cuda.Stream.null.synchronize()
        fallback_seconds = time.perf_counter() - retry
        solves += 1
        planning.update(
            fallback_reason="refined_candidate_failed_target_residual",
            failed_refined_residual=final,
        )
        final = residual(x)
    half = 2 * (cv @ x @ co.T)
    response = half + half.transpose(0, 2, 1)
    polar = cp.einsum("duv,kvu->dk", response, pos)
    host_dm, host_q, host_x = cp.asnumpy(response), cp.asnumpy(polar), cp.asnumpy(x)
    arrays_finite = all(np.isfinite(v).all() for v in (host_dm, host_q, host_x))
    if not arrays_finite:
        raise ValueError("nonfinite scientific output")
    quality_seconds = time.perf_counter() - check - fallback_seconds
    return dict(
        status="computed"
        if np.isfinite(final) and final <= limits["gpu_residual_linf"]
        else "reject-and-recompute",
        action=action,
        planning=planning,
        fields_requested=3,
        attempted_target_solves=solves,
        solver_operator_rows=solver_rows,
        pre_solve_residual=before,
        target_residual=final,
        scf_energy=float(mf.e_tot),
        scf_seconds=scf_seconds,
        prepare_verify_projection_seconds=prepare_seconds,
        solve_seconds=solve_seconds,
        quality_readout_seconds=quality_seconds,
        fallback_seconds=fallback_seconds,
        source_raw_row_sha256=source_sha,
        orbital_gauge_sha256=float_hash(cp.asnumpy(mo)),
        rhs_sha256=float_hash(cp.asnumpy(rhs)),
        solution_sha256=float_hash(host_x),
        density_sha256=float_hash(host_dm),
        density=host_dm.tolist(),
        polarizability=host_q.tolist(),
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "protocol", "source", "certificates", "out"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--mode", choices=("cold", "planned"), required=True)
    args = ap.parse_args()
    started = time.perf_counter()
    manifest = load_manifest(args.manifest)
    spec = json.loads(args.protocol.read_bytes())
    if manifest["manifest_sha256"] != spec["manifest_sha256"]:
        raise ValueError("frontier manifest mismatch")
    sources = (
        sealed_sources(
            args.source, args.certificates, manifest, spec["source_trajectory"]
        )
        if args.mode == "planned"
        else {}
    )
    by_name = {m["name"]: m for m in manifest["molecules"]}
    import cupy, gpu4pyscf, pyscf
    from gpu4pyscf.scf import cphf

    cphf_sha = sha(Path(cphf.__file__).read_bytes())
    if (
        gpu4pyscf.__version__ != "1.9.2"
        or pyscf.__version__ != "2.14.0"
        or cupy.cuda.runtime.getDeviceCount() != 1
        or cphf_sha
        != "1010af1ff5cb62e424223e6c65bad9344e7a6e37bf6882ff574efddb9e2839de"
    ):
        raise RuntimeError("mismatched official solver")
    args.out.mkdir(parents=True, exist_ok=False)
    run = dict(
        mode=args.mode,
        job=os.environ["SLURM_JOB_ID"],
        gpu=cupy.cuda.runtime.getDeviceProperties(0)["name"].decode(),
        cupy=cupy.__version__,
        gpu4pyscf=gpu4pyscf.__version__,
        pyscf=pyscf.__version__,
        cphf_sha256=cphf_sha,
        code_sha256=sha(Path(__file__).read_bytes()),
        protocol_sha256=sha(args.protocol.read_bytes()),
        source_raw_sha256=sha(args.source.read_bytes())
        if args.mode == "planned"
        else None,
        cases=len(spec["cases"]),
    )
    with (args.out / "attempts.jsonl").open("x") as journal:
        for case in spec["cases"]:
            clock = time.perf_counter()
            identifier = case["id"]
            item = by_name[case["molecule"]]
            journal.write(
                json.dumps(
                    dict(case=identifier, event="started", unix_time=time.time())
                )
                + "\n"
            )
            journal.flush()
            row = dict(
                case=identifier,
                mode=args.mode,
                geometry_member_sha256=item["member_sha256"],
            )
            try:
                m0, p0, _ = target(item, manifest["protocol"], "exact")
                mol, target_id, grids = target(
                    item, manifest["protocol"], case["change"]
                )
                source = sources.get(item["name"], (None, None, None))
                if args.mode == "planned" and source[2] != item["member_sha256"]:
                    raise ValueError("source geometry mismatch")
                result = gpu_case(
                    mol,
                    target_id,
                    grids,
                    m0,
                    p0,
                    source,
                    args.mode,
                    case["change"],
                    spec["limits"],
                )
                row.update(
                    target_identity=target_id,
                    target_identity_sha256=sha(canonical(target_id)),
                    source_identity_sha256=sha(canonical(p0)),
                    **result,
                )
            except (
                ValueError,
                RuntimeError,
                MemoryError,
                np.linalg.LinAlgError,
            ) as exc:
                row.update(status="failed", error=type(exc).__name__, reason=str(exc))
            row["elapsed_before_io_s"] = time.perf_counter() - clock
            out = args.out / (identifier + ".json.gz")
            out.write_bytes(gzip.compress(canonical(row), mtime=0))
            journal.write(
                json.dumps(
                    dict(
                        case=identifier,
                        event="finished",
                        status=row["status"],
                        payload_bytes=out.stat().st_size,
                        wall_seconds=time.perf_counter() - clock,
                    )
                )
                + "\n"
            )
            journal.flush()
    run["elapsed_seconds"] = time.perf_counter() - started
    (args.out / "run.json").write_bytes(canonical(run) + b"\n")


if __name__ == "__main__":
    main()
