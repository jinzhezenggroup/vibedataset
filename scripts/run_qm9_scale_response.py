#!/usr/bin/env python3
"""Produce or independently certify one clamped-nuclei RHF response per QM9 geometry."""
import argparse
import gzip
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pyscf
from pyscf import gto, lib, scf
from pyscf.scf import cphf as cpu_cphf


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write_json(path, value):
    path.write_bytes(encoded(value) + b"\n")


def journal(path, value):
    with path.open("ab") as handle:
        handle.write(encoded(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def requests(geometries, protocol, seal):
    raw = geometries.read_bytes()
    if digest(raw) != protocol["geometry_file_sha256"]:
        raise ValueError("geometry manifest hash mismatch")
    payload = json.loads(gzip.decompress(raw))
    if payload["count"] != protocol["request_count"] or len(payload["rows"]) != payload["count"]:
        raise ValueError("geometry denominator mismatch")
    result = []
    members = set()
    for i, row in enumerate(payload["rows"], start=1):
        if (row["request_id"] != f"qm9-scale-{i:06d}" or row["member_sha256"] in members
                or row["unit"] != "Angstrom"
                or any(row[k] != protocol[k] for k in ("method", "basis", "charge", "spin"))):
            raise ValueError(f"invalid geometry identity at {i}")
        members.add(row["member_sha256"])
        geometry = {k: row[k] for k in ("request_id", "member_sha256", "atoms", "unit", "charge", "spin")}
        input_hash = digest(encoded(dict(geometry=geometry, protocol_sha256=seal)))
        result.append((row, input_hash))
    return result


def molecule(row, protocol):
    atoms = [(a["symbol"], np.array(a["xyz_angstrom"], dtype=float) / protocol["bohr_in_angstrom"])
             for a in row["atoms"]]
    return gto.M(atom=atoms, unit="Bohr", basis=protocol["basis"], cart=False,
                 charge=row["charge"], spin=row["spin"], verbose=0)


def converge(mf, cfg):
    start = time.perf_counter()
    mf.conv_tol = cfg["scf_energy_tol"]
    mf.conv_tol_grad = cfg["scf_gradient_tol"]
    mf.max_cycle = cfg["scf_cycles"]
    mf.kernel()
    if not mf.converged or not np.isfinite(float(mf.e_tot)):
        raise RuntimeError("SCF did not converge to a finite energy")
    return time.perf_counter() - start


def cpu_operators(mol, coeff, occ, energy, protocol):
    occupied = occ > 0
    co, cv = coeff[:, occupied], coeff[:, ~occupied]
    gap = energy[~occupied, None] - energy[None, occupied]
    if not gap.size or not np.isfinite(gap).all() or gap.min() <= 0:
        raise ValueError("non-positive or non-finite canonical RHF orbital gap")
    with mol.with_common_orig(tuple(protocol["origin_bohr"])):
        pos = mol.intor("int1e_r", comp=3)
    rhs = cv.T @ pos @ co
    return co, cv, gap, pos, rhs


def induced_density(x, co, cv):
    half = 2 * (cv @ x @ co.T)
    return half + half.transpose(0, 2, 1)


def induced_potential(mf, dm, co, cv):
    j, k = mf.get_jk(dm=dm, hermi=1)
    return cv.T @ (j - 0.5 * k) @ co


def reference(mol, protocol, cfg):
    mf = scf.RHF(mol)
    scf_time = converge(mf, cfg)
    start = time.perf_counter()
    co, cv, gap, pos, rhs = cpu_operators(mol, mf.mo_coeff, mf.mo_occ, mf.mo_energy, protocol)
    calls = 0

    def response(x):
        nonlocal calls
        calls += 1
        dm = induced_density(x.reshape(-1, *gap.shape), co, cv)
        return induced_potential(mf, dm, co, cv)

    x, _ = cpu_cphf.solve(response, mf.mo_energy, mf.mo_occ, -rhs,
                          tol=cfg["response_tol"], max_cycle=cfg["response_cycles"], verbose=0)
    solve_time = time.perf_counter() - start
    check_time = 0.0
    history = []
    for step in range(3):
        check = time.perf_counter()
        dm = induced_density(x, co, cv)
        defect = rhs - (x * gap + induced_potential(mf, dm, co, cv))
        scale = float(np.max(np.abs(defect)))
        history.append(scale)
        check_time += time.perf_counter() - check
        if scale <= protocol["maximum_absolute_error"]["reference_physical_residual"] or step == 2:
            break
        # The upstream Krylov implementation drops near-linearly dependent vectors.
        # Normalize the defect before solving the linear correction in the same CPU model.
        refine = time.perf_counter()
        correction, _ = cpu_cphf.solve(response, mf.mo_energy, mf.mo_occ, -defect / scale,
                                       tol=cfg["response_tol"], max_cycle=cfg["response_cycles"], verbose=0)
        x += scale * correction
        solve_time += time.perf_counter() - refine
    polar = np.einsum("duv,kvu->dk", dm, pos)
    residual = history[-1]
    arrays = dict(density=dm, polarizability=polar, coeff=mf.mo_coeff, occ=mf.mo_occ, orbital_energy=mf.mo_energy)
    facts = dict(scf_energy=float(mf.e_tot), scf_seconds=scf_time, solve_seconds=solve_time,
                 quality_seconds=check_time, residual_history=history, orbital_gap_hartree=float(gap.min()),
                 response_operator_calls=calls, reference_physical_residual=residual)
    return arrays, facts


def full_fock_retry(mol,protocol,cfg,diagnostics):
    """Converge the original tighter retry gates with full Fock rebuilds and the official SOSCF fallback."""
    from gpu4pyscf import scf as gpu_scf
    from gpu4pyscf.scf import soscf
    import cupy

    tick=time.perf_counter()
    mf=gpu_scf.RHF(mol)
    mf.direct_scf=False
    mf.direct_scf_tol=1e-16
    def watch(stage):
        entry={"stage":stage,"cycles":[]}
        diagnostics.append(entry)
        def callback(env):
            record={}
            for k in ("cycle","e_tot","last_hf_e","norm_gorb","norm_ddm"):
                if k in env and env[k] is not None:
                    record[k]=float(env[k])
            entry["cycles"].append(record)
        return callback
    mf.callback=watch("ordinary GPU warm start with full J/K")
    converge(mf,protocol["producer"])
    seed=mf.make_rdm1()
    mf.callback=watch("strict GPU full Fock")
    mf.conv_tol=cfg["scf_energy_tol"];mf.conv_tol_grad=cfg["scf_gradient_tol"];mf.max_cycle=cfg["scf_cycles"]
    mf.diis_space=12
    mf.kernel(dm0=seed)
    backend="full Fock DIIS"
    if not mf.converged:
        solver=soscf.newton(mf)
        solver.conv_tol=cfg["scf_energy_tol"];solver.conv_tol_grad=cfg["scf_gradient_tol"]
        solver.max_cycle=cfg["scf_cycles"];solver.callback=watch("official second-order GPU SCF")
        solver.kernel(mo_coeff=mf.mo_coeff,mo_occ=mf.mo_occ)
        mf=solver;backend="official GPU second-order SCF"
    if not mf.converged:
        raise RuntimeError("strict full-Fock DIIS and official GPU SOSCF did not converge")
    dm=mf.make_rdm1()
    vhf=mf.get_veff(mol,dm)
    fock=mf.get_hcore(mol)+vhf
    grad=float(cupy.linalg.norm(mf.get_grad(mf.mo_coeff,mf.mo_occ,fock)).item())
    diagnostics.append(dict(backend=backend,independent_full_fock_gradient_l2=grad,energy_hartree=float(mf.e_tot)))
    if not np.isfinite(grad) or grad>cfg["scf_gradient_tol"]:
        raise RuntimeError(f"strict full Fock gradient {grad} exceeds frozen threshold")
    return mf,time.perf_counter()-tick


def produce(mol, protocol, cfg, full_fock=False, diagnostics=None):
    import cupy
    from gpu4pyscf import scf as gpu_scf
    from gpu4pyscf.scf import cphf
    from run_gpu4pyscf_4arm import density_values, solve_fields, target_values

    if full_fock:
        mf,scf_time=full_fock_retry(mol,protocol,cfg,diagnostics)
    else:
        mf = gpu_scf.RHF(mol)
        scf_time = converge(mf, cfg)
    start = time.perf_counter()
    result = solve_fields(cupy, cphf, mf, [0, 1, 2], cfg["response_tol"], cfg["response_cycles"], None)
    residual_history = []
    correction_rows = 0
    if cfg == protocol["retry"]:
        from gpu4pyscf.properties.polarizability import gen_vind
        co = mf.mo_coeff[:, mf.mo_occ > 0]
        cv = mf.mo_coeff[:, mf.mo_occ == 0]
        gap = mf.mo_energy[mf.mo_occ == 0, None] - mf.mo_energy[None, mf.mo_occ > 0]
        with mol.with_common_orig(tuple(protocol["origin_bohr"])):
            position = cupy.asarray(mol.intor("int1e_r", comp=3))
        rhs = cv.T @ position @ co
        target_op = gen_vind(mf, mf.mo_coeff, mf.mo_occ)
        x = cupy.asarray(np.stack([result["vectors"][f] for f in protocol["fields"]]))

        def correction_operator(trial):
            nonlocal correction_rows
            correction_rows += trial.shape[0]
            return target_op(trial)

        for step in range(3):
            defect = rhs - (gap * x + target_op(x))
            strength = float(cupy.max(cupy.abs(defect)).item())
            residual_history.append(strength)
            if strength <= 1e-9 or step == 2:
                break
            correction, _ = cphf.solve(correction_operator, mf.mo_energy, mf.mo_occ, -defect/strength,
                                       tol=cfg["response_tol"], max_cycle=cfg["response_cycles"], verbose=0)
            x += strength * correction
        result["vectors"] = {f: cupy.asnumpy(v) for f,v in zip(protocol["fields"],x)}
    solve_time = time.perf_counter() - start
    readout = time.perf_counter()
    dm = density_values(cupy, mf, result["vectors"])
    targets = target_values(cupy, mf, result["vectors"], protocol["readouts"])
    cupy.cuda.Stream.null.synchronize()
    fields = protocol["fields"]
    arrays = dict(density=np.stack([dm[f] for f in fields]),
                  amplitudes=np.stack([result["vectors"][f] for f in fields]),
                  polarizability=np.array([targets[k] for k in protocol["readouts"]]).reshape(3, 3))
    facts = dict(scf_energy=float(mf.e_tot), scf_seconds=scf_time, solve_and_check_seconds=solve_time,
                 readout_seconds=time.perf_counter()-readout, response_operator_calls=result["operator_calls"],
                 response_operator_rows=result["operator_rows"], quality_operator_rows=result["quality_operator_rows"],
                 backend_preconditioned_residual=result["residual_linf"], retry_fp64_residual_history=residual_history,
                 correction_operator_rows=correction_rows)
    return arrays, facts


def load_output(root, request, input_hash, basis_hash, phase):
    folder = root / request
    facts = json.loads((folder / "receipt.json").read_bytes())
    if (facts["status"] != "computed" or facts["phase"] != phase or facts["request_id"] != request
            or facts["input_sha256"] != input_hash or facts["basis_parameters_sha256"] != basis_hash):
        raise ValueError(f"{phase} identity or disposition mismatch")
    asset = folder / "arrays.npz"
    if digest(asset.read_bytes()) != facts["arrays_sha256"]:
        raise ValueError(f"{phase} asset hash mismatch")
    with np.load(asset, allow_pickle=False) as data:
        arrays = {key: data[key] for key in data.files}
    return facts, arrays


def score(mol, protocol, request, input_hash, basis_hash, args):
    # The CPU reference is converged in its own process before it sees any candidate.
    ref, a = load_output(args.references, request, input_hash, basis_hash, "reference")
    prod, b = load_output(args.candidates, request, input_hash, basis_hash, "produce")
    co, cv, gap, pos, rhs = cpu_operators(mol, a["coeff"], a["occ"], a["orbital_energy"], protocol)
    dm = b["density"]
    if dm.shape != (3, mol.nao, mol.nao) or b["polarizability"].shape != (3, 3):
        raise ValueError("invalid candidate tensor shape")
    ovlp = mol.intor_symmetric("int1e_ovlp")
    x = (cv.T @ ovlp @ dm @ ovlp @ co) / 2
    tangent = induced_density(x, co, cv)
    residual = x * gap + induced_potential(scf.RHF(mol), tangent, co, cv) - rhs
    alpha = b["polarizability"]
    deviations = {
        "reference_physical_residual": ref["reference_physical_residual"],
        "candidate_physical_residual": np.max(abs(residual)),
        "ao_density": np.max(abs(dm - a["density"])),
        "ao_tangent": np.max(abs(dm - tangent)),
        "polarizability": np.max(abs(alpha - a["polarizability"])),
        "candidate_density_readout": np.max(abs(alpha - np.einsum("duv,kvu->dk", dm, pos))),
        "tensor_reciprocity": np.max(abs(alpha - alpha.T)),
        "scf_energy": abs(prod["scf_energy"] - ref["scf_energy"]),
    }
    errors = {key: float(value) for key, value in deviations.items()}
    limits = protocol["maximum_absolute_error"]
    if set(errors) != set(limits) or not np.isfinite(list(errors.values())).all():
        raise ValueError("invalid certificate metrics")
    failed = [key for key in limits if errors[key] > limits[key]]
    return dict(status="reject-and-recompute" if failed else "accepted", failed_gates=failed, errors=errors,
                polarizability_au=alpha.tolist(), reference_polarizability_au=a["polarizability"].tolist(),
                candidate_sha256=prod["arrays_sha256"], reference_sha256=ref["arrays_sha256"],
                rhs_sha256=digest(np.asarray(rhs, dtype="<f8").tobytes()),
                candidate_amplitudes_sha256=digest(np.asarray(b["amplitudes"], dtype="<f8").tobytes()),
                gap_hartree=float(gap.min()), gap_below_1em3=bool(gap.min()<0.001))


def environment(phase, protocol):
    if pyscf.__version__ != protocol["pyscf_version"]:
        raise ValueError("unmatched PySCF package")
    identity = dict(python=platform.python_version(), numpy=np.__version__, pyscf=pyscf.__version__,
                    cpu_threads=lib.num_threads(), slurm_job=os.getenv("SLURM_JOB_ID"),
                    driver_code_sha256=digest(Path(__file__).read_bytes()))
    if phase == "produce":
        import cupy
        import gpu4pyscf
        from gpu4pyscf.scf import cphf
        import run_gpu4pyscf_4arm as backend

        cphf_sha = digest(Path(cphf.__file__).read_bytes())
        if gpu4pyscf.__version__ != protocol["gpu4pyscf_version"] or cphf_sha != protocol["gpu4pyscf_cphf_sha256"]:
            raise ValueError("unmatched official GPU4PySCF solver")
        if not os.getenv("SLURM_JOB_ID") or cupy.cuda.runtime.getDeviceCount() != 1:
            raise ValueError("one allocated GPU is required")
        identity.update(gpu4pyscf=gpu4pyscf.__version__, cphf_sha256=cphf_sha,
                        wheel_sha256=os.environ["VERIFIED_WHEEL_SHA256"],
                        backend_code_sha256=digest(Path(backend.__file__).read_bytes()),
                        cupy=cupy.__version__, cuda_runtime=cupy.cuda.runtime.runtimeGetVersion(),
                        gpu=cupy.cuda.runtime.getDeviceProperties(0)["name"].decode())
        if identity["wheel_sha256"] != protocol["gpu4pyscf_wheel_sha256"]:
            raise ValueError("unmatched wheel")
    return identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("requests","produce","reference","score"))
    parser.add_argument("--geometries", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--stop", type=int, default=1000)
    parser.add_argument("--references", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--retry", action="store_true")
    parser.add_argument("--full-fock-repair",action="store_true",help="use official full-Fock and SOSCF routes on an already rejected request")
    args = parser.parse_args()
    if args.full_fock_repair and (args.phase!="produce" or not args.retry):
        parser.error("full Fock recovery requires a producer retry")
    begun = time.perf_counter()
    protocol = json.loads(args.protocol.read_bytes())
    seal = digest(args.protocol.read_bytes())
    queue = requests(args.geometries, protocol, seal)
    if not 1 <= args.start <= args.stop <= len(queue):
        parser.error("invalid inclusive range")
    if args.phase == "requests":
        frozen = [{"request_id":r["request_id"], "qm9_member":r["qm9_member"], "member_sha256":r["member_sha256"],
                   "input_sha256":h, "protocol_sha256":seal} for r,h in queue]
        args.out.write_bytes(gzip.compress(b"".join(encoded(r)+b"\n" for r in frozen),mtime=0))
        return
    if args.phase == "score" and (not args.references or not args.candidates):
        parser.error("score needs separate reference and candidate roots")
    args.out.mkdir(parents=True, exist_ok=True)
    role = "producer" if args.phase == "produce" else "reference"
    cfg = protocol["retry" if args.retry else role]
    identity = environment(args.phase, protocol)
    run = args.out / f"{args.phase}-{args.start:04}-{args.stop:04}.jsonl"
    with run.open("xb"):
        pass
    journal(run, dict(event="run-start", protocol_sha256=seal, identity=identity, settings=cfg,
                      startup_seconds=time.perf_counter()-begun, start=args.start, stop=args.stop))
    for row, key in queue[args.start-1:args.stop]:
        req = row["request_id"]
        start = time.perf_counter()
        folder = args.out / req
        folder.mkdir()
        journal(run, dict(event="started", request_id=req, input_sha256=key, unix_time=time.time()))
        receipt = dict(request_id=req, input_sha256=key, geometry_member_sha256=row["member_sha256"],
                       protocol_sha256=seal, phase=args.phase, run=run.name, settings=cfg, retry=args.retry)
        try:
            mol = molecule(row, protocol)
            basis_hash = digest(encoded(mol._basis))
            receipt.update(basis_parameters_sha256=basis_hash, nao=mol.nao, nocc=mol.nelectron//2,
                           prepare_seconds=time.perf_counter()-start)
            if args.phase == "score":
                receipt.update(score(mol,protocol,req,key,basis_hash,args))
            else:
                if args.phase=="produce":
                    history=[];receipt["scf_recovery_history"]=history
                    arrays,facts=produce(mol,protocol,cfg,args.full_fock_repair,history)
                else:
                    arrays,facts=reference(mol,protocol,cfg)
                if not all(np.isfinite(x).all() for x in arrays.values()):
                    raise ValueError("non-finite scientific output")
                serial = time.perf_counter()
                path = folder / "arrays.npz"
                np.savez_compressed(path, **arrays)
                receipt.update(status="computed", arrays_sha256=digest(path.read_bytes()),
                               arrays_bytes=path.stat().st_size, serialize_store_seconds=time.perf_counter()-serial,
                               **facts)
        except (ValueError, RuntimeError, OSError, MemoryError, np.linalg.LinAlgError) as exc:
            receipt.update(status="failed", error=type(exc).__name__, reason=str(exc))
        receipt["elapsed_before_receipt_s"] = time.perf_counter() - start
        write_json(folder / "receipt.json", receipt)
        journal(run, dict(event="finished", request_id=req, status=receipt["status"],
                          receipt_bytes=(folder/"receipt.json").stat().st_size,
                          wall_seconds=time.perf_counter()-start))
    journal(run, dict(event="run-finished", elapsed_seconds=time.perf_counter()-begun))


if __name__ == "__main__":
    main()
