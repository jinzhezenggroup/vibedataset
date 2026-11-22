#!/usr/bin/env python3
"""Produce FP64 RHF Hessians from one input with an independent backend."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def velox_basis(shells, out):
    name = "MATCHED-STO-3G"
    lines = [f"@BASIS_SET {name}"]
    for atom, blocks in shells.items():
        lines.append(f"@ATOMBASIS {atom.upper()}")
        for block in blocks:
            rows = block["primitives"]
            lines.append(f"{'SP'[block['angular_momentum']]} {len(rows)} 1")
            lines.extend(f"{exponent:.17g} {coefficient:.17g}" for exponent, coefficient in rows)
        lines.append("@END")
    (out / name).write_text("\n".join(lines) + "\n")
    return name


def velox(case, protocol, out):
    import veloxchem as vlx

    coords = np.asarray(case["xyz"], dtype=float)
    mol = vlx.Molecule(case["symbols"], coords, "bohr")
    mol.set_charge(protocol["charge"])
    mol.set_multiplicity(protocol["spin"] + 1)
    np.testing.assert_allclose(mol.get_coordinates_in_bohr(), coords, rtol=0, atol=1e-14)
    basis = vlx.MolecularBasis.read(mol, velox_basis(protocol["shells"], out), basis_path=str(out))
    engine = vlx.ScfRestrictedDriver()
    engine.conv_thresh = protocol["scf_threshold"]
    engine.compute(mol, basis)
    if not engine.is_converged:
        raise RuntimeError("VeloxChem SCF failed")
    start = time.perf_counter()
    cphf = {"conv_thresh": protocol["response_threshold"]}
    spectra = {}
    if case["id"] in protocol["spectroscopy"]["case_ids"]:
        vib = vlx.VibrationalAnalysis(engine)
        mass = protocol["spectroscopy"]["masses_amu"]
        vib.update_settings({}, {"do_ir": "yes", "do_raman": "yes", "numerical_hessian": "no",
                                 "numerical_raman": "no", "print_depolarization_ratio": "yes"},
                            cphf_dict=cphf, rsp_dict=cphf)
        vib.isotopes = ",".join(f"{i+1}({mass[symbol]})" for i, symbol in enumerate(case["symbols"]))
        vib.frequencies = (protocol["spectroscopy"]["external_frequency_au"],)
        vib.compute(mol, basis)
        hess = vib.hessian_driver
        spectra = {"ir_frequency_cm1": vib.vib_frequencies.tolist(),
                   "raman_frequency_cm1": vib.vib_frequencies.tolist(),
                   "ir_km_mol": vib.ir_intensities.tolist(),
                   "raman_A4_amu": vib.raman_activities[0].tolist(),
                   "raman_depolarization": vib.depol_ratio[0].tolist()}
    else:
        hess = vlx.ScfHessianDriver(engine)
        hess.update_settings({}, hess_dict={"numerical": "no"}, cphf_dict=cphf)
        hess.compute(mol, basis)
    return {
        "nao": int(engine.scf_results["C_alpha"].shape[0]),
        "energy": engine.get_scf_energy(),
        "hessian": np.asarray(hess.hessian),
        "response_and_readouts_seconds": time.perf_counter() - start,
        "spectroscopy": spectra,
        "eri_screening": engine.eri_thresh,
        "ri_jk": engine.ri_jk,
    }


def gpu(case, protocol, out):
    import cupy
    from gpu4pyscf import scf
    from pyscf import gto

    shells = {atom: [[shell["angular_momentum"], *shell["primitives"]] for shell in blocks]
              for atom, blocks in protocol["shells"].items()}
    mol = gto.M(atom=list(zip(case["symbols"], case["xyz"])), unit="Bohr", basis=shells,
                charge=protocol["charge"], spin=protocol["spin"], cart=False, verbose=4)
    np.testing.assert_allclose(mol.atom_coords(), case["xyz"], rtol=0, atol=1e-14)
    engine = scf.RHF(mol)
    engine.conv_tol = protocol["scf_threshold"]
    engine.conv_tol_cpscf = protocol["response_threshold"]
    engine.kernel()
    if not engine.converged:
        raise RuntimeError("GPU4PySCF SCF failed")
    start = time.perf_counter()
    spectra = {}
    driver = engine.Hessian()
    if case["id"] in protocol["spectroscopy"]["case_ids"]:
        from gpu4pyscf.properties import ir, raman
        np.testing.assert_allclose(mol.atom_mass_list(isotope_avg=True),
                                   [protocol["spectroscopy"]["masses_amu"][symbol] for symbol in case["symbols"]],
                                   rtol=0, atol=1e-12)
        frequencies, intensity = ir.eval_ir_freq_intensity(engine, driver)
        hess = driver.de
        rf, activity, depolar = raman.eval_raman_intensity(engine, hessian=hess)
        rf = cupy.asnumpy(rf)
        spectra = {"ir_frequency_cm1": cupy.asnumpy(frequencies).tolist(),
                   "raman_frequency_cm1": (rf.real - rf.imag).tolist(),
                   "ir_km_mol": cupy.asnumpy(intensity).tolist(),
                   "raman_A4_amu": cupy.asnumpy(activity).tolist(),
                   "raman_depolarization": cupy.asnumpy(depolar).tolist()}
    else:
        hess = driver.kernel()
    cupy.cuda.get_current_stream().synchronize()
    n = 3 * mol.natm
    return {"nao": mol.nao_nr(), "energy": float(engine.e_tot),
            "hessian": cupy.asnumpy(hess).transpose(0, 2, 1, 3).reshape(n, n),
            "response_and_readouts_seconds": time.perf_counter() - start, "spectroscopy": spectra,
            "eri_screening": engine.direct_scf_tol}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend", choices=["veloxchem", "gpu4pyscf"])
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_bytes())
    if (protocol["method"], protocol["charge"], protocol["spin"], protocol["geometry_unit"],
        protocol["precision"]) != ("RHF", 0, 0, "Bohr", "FP64"):
        parser.error("expected the closed-shell FP64 RHF protocol in Bohr")
    args.out.mkdir(parents=True, exist_ok=False)
    if args.backend == "veloxchem":
        import veloxchem
        import veloxchem.veloxchemlib as native
        from mpi4py import MPI
        identity = {"code_version": veloxchem.__version__, "native_sha256": digest(native.__file__),
                    "device": "CPU", "mpi_processes": MPI.COMM_WORLD.Get_size()}
        producer = velox
    else:
        import cupy
        import gpu4pyscf
        import pyscf
        from gpu4pyscf.scf import cphf
        identity = {"code_version": gpu4pyscf.__version__, "cupy": cupy.__version__, "pyscf": pyscf.__version__,
                    "cphf_sha256": digest(cphf.__file__),
                    "device": cupy.cuda.runtime.getDeviceProperties(0)["name"].decode()}
        producer = gpu
    inputs = {"protocol_sha256": digest(args.protocol), "driver_sha256": digest(__file__)}
    identity.update(python=platform.python_version(), numpy=np.__version__, omp=os.environ.get("OMP_NUM_THREADS"),
                    slurm_job=os.environ.get("SLURM_JOB_ID"))
    failed = 0
    with (args.out / "events.jsonl").open("x") as stream:
        for case in protocol["cases"]:
            record = {"id": case["id"], "logical_cartesian_rhs": 3 * len(case["xyz"])}
            start = time.perf_counter()
            stream.write(json.dumps(dict(record, status="started")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            try:
                result = producer(case, protocol, args.out.resolve())
                h = result.pop("hessian")
                expected = (record["logical_cartesian_rhs"],) * 2
                if h.dtype != np.float64 or h.shape != expected or not np.isfinite(h).all():
                    raise ValueError(f"invalid Hessian {h.dtype}, {h.shape}")
                if not np.isfinite(result["energy"]):
                    raise ValueError("nonfinite energy")
                record.update(result, hessian=h.tolist(), status="produced")
            except Exception as exc:
                import traceback
                traceback.print_exc()
                record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                failed += 1
            record["wall_seconds"] = time.perf_counter() - start
            stream.write(json.dumps(record, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    receipt = dict(schema="vibedataset.cross_engine_hessians.v1", backend=args.backend, inputs=inputs,
                   environment=identity, expected=len(protocol["cases"]), failed=failed,
                   events_sha256=digest(args.out / "events.jsonl"))
    (args.out / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return bool(failed)


if __name__ == "__main__":
    sys.exit(main())
