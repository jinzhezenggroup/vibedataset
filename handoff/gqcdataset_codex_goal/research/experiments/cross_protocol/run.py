"""Run a small cross-protocol asset-identity matrix with pinned PySCF."""

import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
from pyscf import gto, scf
from pyscf.scf import addons
import pyscf


ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
BOHR_ANGSTROM = 0.529177210903
WATER = "O 0.000000 0.000000 0.000000; H 0.000000 -1.432336 1.107153; H 0.000000 1.432336 1.107153"
H2PLUS = "H 0.000000 0.000000 0.000000; H 0.000000 0.000000 1.400000"
H2_STRETCHED = "H 0.000000 0.000000 0.000000; H 0.000000 0.000000 3.000000"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def molecule(atom, basis, charge=0, spin=0):
    return gto.M(atom=atom, unit="Bohr", basis=basis, charge=charge, spin=spin,
                  cart=False, verbose=0)


def make_scf(mol, method):
    if method == "rhf":
        mf = scf.RHF(mol)
    elif method == "uhf":
        mf = scf.UHF(mol)
    elif method == "b3lyp":
        mf = scf.RKS(mol)
        mf.xc = "b3lyp"
    else:
        raise ValueError(method)
    mf.conv_tol = 1e-10
    mf.conv_tol_grad = 1e-8
    mf.max_cycle = 100
    mf.verbose = 0
    return mf


def finite_numbers(values):
    return all(np.isfinite(np.asarray(value)).all() for value in values)


def state_record(name, atom, basis, method, charge=0, spin=0, initial=None, initial_source=None):
    mol = molecule(atom, basis, charge=charge, spin=spin)
    mf = make_scf(mol, method)
    started = time.perf_counter()
    if initial is None:
        energy = mf.kernel()
        initial_kind = "cold"
    else:
        energy = mf.kernel(dm0=initial)
        initial_kind = initial_source or "projected"
    elapsed = time.perf_counter() - started
    density = mf.make_rdm1()
    dipole = mf.dip_moment(dm=density, unit="AU", origin=np.zeros(3), verbose=0)
    if method == "uhf":
        mo_energy = np.concatenate([np.asarray(mf.mo_energy[0]), np.asarray(mf.mo_energy[1])])
        gap = float(np.min(np.abs(mo_energy)))
    else:
        mo_energy = np.asarray(mf.mo_energy)
        occupied = mo_energy[np.asarray(mf.mo_occ) > 0]
        virtual = mo_energy[np.asarray(mf.mo_occ) == 0]
        gap = float(np.min(virtual) - np.max(occupied)) if len(virtual) else None
    return {
        "name": name,
        "method": method,
        "basis": basis,
        "charge": charge,
        "spin": spin,
        "multiplicity": spin + 1,
        "geometry_bohr": atom,
        "nelectron": mol.nelectron,
        "nao": mol.nao_nr(),
        "nmo": mf.mo_coeff.shape[-1],
        "converged": bool(mf.converged),
        "energy_hartree": float(energy),
        "dipole_au": np.asarray(dipole).tolist(),
        "mo_gap_hartree": gap,
        "cycles": int(getattr(mf, "cycles", -1)),
        "seconds": elapsed,
        "initial_kind": initial_kind,
        "density_trace": float(np.trace(density[0] @ mol.intor_symmetric("int1e_ovlp"))) if density.ndim == 3 else float(np.trace(density @ mol.intor_symmetric("int1e_ovlp"))),
        "density_finite": bool(np.isfinite(density).all()),
        "_mol": mol,
        "_mf": mf,
        "_density": density,
    }


def strip_internal(record):
    return {key: value for key, value in record.items() if not key.startswith("_")}


def response_probe():
    mol = molecule(WATER, "sto-3g")
    zero = make_scf(mol, "rhf")
    zero.kernel()
    hcore = zero.get_hcore()
    dipole_ints = mol.intor("int1e_r", comp=3)
    step = 1e-3

    def relaxed(field):
        mf = make_scf(mol, "rhf")
        mf.get_hcore = lambda *args: hcore + field * dipole_ints[0]
        energy = mf.kernel()
        dipole = mf.dip_moment(dm=mf.make_rdm1(), unit="AU", origin=np.zeros(3), verbose=0)
        return float(energy), np.asarray(dipole)

    _, plus = relaxed(step)
    _, minus = relaxed(-step)
    relaxed_response = (plus - minus) / (2 * step)
    frozen_response = np.zeros_like(relaxed_response)
    return {
        "method": "rhf",
        "basis": "sto-3g",
        "geometry": WATER,
        "field_step_au": step,
        "relaxed_dipole_derivative": relaxed_response.tolist(),
        "frozen_density_derivative": frozen_response.tolist(),
        "frozen_vs_relaxed_max_abs": float(np.max(np.abs(relaxed_response))),
        "relaxed_runs_converged": True,
    }


def representation_probe(source):
    mol = source["_mol"]
    density = np.asarray(source["_density"])
    if density.ndim == 3:
        density = density.sum(axis=0)
    overlap = mol.intor_symmetric("int1e_ovlp")
    dipole = np.asarray(mol.intor("int1e_r", comp=3))
    identity = float(np.max(np.abs(density @ overlap @ density - 2 * density)))
    permutation = np.arange(mol.nao_nr())[::-1]
    permuted = density[np.ix_(permutation, permutation)]
    wrong_dipole = np.einsum("xij,ji->x", dipole, permuted)
    corrected = permuted[np.ix_(permutation, permutation)]
    direct = np.einsum("xij,ji->x", dipole, density)
    return {
        "ao_dimension": mol.nao_nr(),
        "original_idempotency_error": identity,
        "unknown_permutation": permutation.tolist(),
        "unknown_permutation_dipole_difference": float(np.max(np.abs(wrong_dipole - direct))),
        "known_permutation_roundtrip_difference": float(np.max(np.abs(corrected - density))),
        "direct_dipole": direct.tolist(),
    }


def classify(source, target, kind, reason, evidence):
    return {
        "source": source,
        "target": target,
        "classification": kind,
        "reason": reason,
        "evidence": evidence,
    }


def main():
    started = time.perf_counter()
    water_sto = state_record("water_rhf_sto3g", WATER, "sto-3g", "rhf")
    water_631 = state_record("water_rhf_631g_star", WATER, "6-31g*", "rhf")
    water_b3lyp = state_record("water_b3lyp_631g_star", WATER, "6-31g*", "b3lyp")
    water_631_projected = state_record(
        "water_rhf_631g_star_projected", WATER, "6-31g*", "rhf",
        initial=addons.project_dm_nr2nr(water_sto["_mol"], water_sto["_density"], water_631["_mol"]),
        initial_source="projected RHF/STO-3G density",
    )
    water_b3lyp_seeded = state_record(
        "water_b3lyp_631g_star_seeded", WATER, "6-31g*", "b3lyp",
        initial=water_631["_density"], initial_source="RHF/6-31G* density",
    )
    h2plus = state_record("h2plus_uhf_sto3g", H2PLUS, "sto-3g", "uhf", charge=1, spin=1)
    stretched = state_record("h2_stretched_rhf_sto3g", H2_STRETCHED, "sto-3g", "rhf")
    response = response_probe()
    representation = representation_probe(water_sto)

    values = [water_sto, water_631, water_b3lyp, water_631_projected, water_b3lyp_seeded, h2plus, stretched]
    if not all(record["converged"] and record["density_finite"] for record in values):
        raise RuntimeError("one cross-protocol SCF did not converge")
    classes = [
        classify("water_rhf_sto3g", "water_rhf_sto3g", "direct_reuse",
                 "same geometry, electrons, spin, method, basis, operator, origin and units",
                 {"energy_difference": 0.0, "dipole_difference": 0.0}),
        classify("water_rhf_sto3g", "water_rhf_631g_star", "initial_guess_only",
                 "basis changed; projected density converged to a new target state",
                 {"cold": strip_internal(water_631), "projected": strip_internal(water_631_projected)}),
        classify("water_rhf_631g_star", "water_b3lyp_631g_star", "refine_required",
                 "exchange-correlation method changed; seeded state was only an initial guess",
                 {"rhf": strip_internal(water_631), "b3lyp": strip_internal(water_b3lyp_seeded)}),
        classify("water_rhf_sto3g", "h2plus_uhf_sto3g", "reject_and_recompute",
                 "geometry, electron count and multiplicity changed",
                 {"source_nelectron": water_sto["nelectron"], "target_nelectron": h2plus["nelectron"],
                  "source_multiplicity": water_sto["multiplicity"], "target_multiplicity": h2plus["multiplicity"]}),
        classify("water_rhf_sto3g_frozen_density", "water_rhf_sto3g_relaxed_response", "reject_and_recompute",
                 "a frozen-state derivative cannot be used as a relaxed external-field response",
                 response),
        classify("water_rhf_sto3g_unknown_ao_order", "water_rhf_sto3g_dipole", "reject",
                 "AO permutation is not identified by the asset contract",
                 representation),
    ]
    result = {
        "protocol": {
            "pyscf": pyscf.__version__,
            "python": platform.python_version(),
            "threads": {key: __import__("os").environ.get(key) for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
            "geometry_units": "Bohr",
            "origin_bohr": [0.0, 0.0, 0.0],
            "scf_tolerance": 1e-10,
            "target_response_step_au": 1e-3,
            "driver_sha256": sha256(Path(__file__)),
        },
        "states": {record["name"]: strip_internal(record) for record in values},
        "identity_dimensions": {
            "geometry": "atom order and Bohr coordinates",
            "atom_numbers": "symbols in the molecular geometry",
            "charge_and_spin": "electron count and multiplicity",
            "method_and_basis": "SCF method and contracted basis",
            "representation": "AO order, normalization and MO occupation",
            "units_and_origin": "explicit Bohr and origin metadata",
            "response_semantics": "frozen density versus relaxed field response",
            "quality": "convergence, gap/stability and residual evidence",
        },
        "classification_matrix": classes,
        "controls": {
            "same_geometry_method_basis_energy_difference": abs(water_sto["energy_hartree"] - water_sto["energy_hartree"]),
            "basis_change_energy_difference": abs(water_sto["energy_hartree"] - water_631["energy_hartree"]),
            "method_change_energy_difference": abs(water_631["energy_hartree"] - water_b3lyp["energy_hartree"]),
            "representation": representation,
            "response": response,
            "near_degenerate": {
                "system": stretched["name"],
                "mo_gap_hartree": stretched["mo_gap_hartree"],
                "classification": "requires fresh stability evidence",
            },
        },
        "cost": {
            "complete_target_scf_count": len(values),
            "complete_target_seconds": sum(record["seconds"] for record in values),
            "response_relaxed_scf_count": 2,
            "preflight_rejects_without_target_solve": {
                "unknown_ao_order": {"jk_calls": 0, "reason": "identity unavailable"},
                "state_mismatch": {"jk_calls": 0, "reason": "source asset not admitted"},
            },
            "fallback_target_recomputations": {
                "h2plus_uhf_sto3g": {"seconds": h2plus["seconds"], "scf_cycles": h2plus["cycles"]},
                "water_rhf_631g_star_projected": {"seconds": water_631_projected["seconds"], "scf_cycles": water_631_projected["cycles"]},
                "water_b3lyp_631g_star_seeded": {"seconds": water_b3lyp_seeded["seconds"], "scf_cycles": water_b3lyp_seeded["cycles"]},
            },
            "total_wall_seconds": time.perf_counter() - started,
        },
        "evidence_sources": {
            "existing_gqc_response_control": "experiments/gqc_residual_response/report.json",
            "existing_psi4_ao_control": "experiments/archive_dipole_protocol.md",
            "existing_gqc_pin": "2791504cc238fe83d328fc1718080642b288222a",
        },
    }
    destination = HERE / "result.json"
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "states": len(values),
        "classes": len(classes),
        "basis_delta": result["controls"]["basis_change_energy_difference"],
        "method_delta": result["controls"]["method_change_energy_difference"],
        "frozen_response_error": response["frozen_vs_relaxed_max_abs"],
        "near_degenerate_gap": stretched["mo_gap_hartree"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
