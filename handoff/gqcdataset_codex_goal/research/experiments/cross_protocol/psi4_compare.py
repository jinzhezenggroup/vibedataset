"""Run fresh Psi4 1.10 targets for the cross-protocol identity matrix."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import time

import numpy as np
import psi4


ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
PYSCF_RESULT = HERE / "result.json"
WATER = "O 0.000000 0.000000 0.000000; H 0.000000 -1.432336 1.107153; H 0.000000 1.432336 1.107153"
H2PLUS = "H 0.000000 0.000000 0.000000; H 0.000000 0.000000 1.400000"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def conda_version(name, fallback):
    prefix = os.environ.get("CONDA_PREFIX")
    if prefix:
        for path in (Path(prefix) / "conda-meta").glob(name + "-*.json"):
            try:
                return json.loads(path.read_bytes())["version"]
            except (OSError, ValueError, KeyError):
                pass
    return fallback


def geometry(atom, charge, multiplicity):
    lines = [f"{charge} {multiplicity}"]
    for item in atom.split(";"):
        lines.append(item.strip())
    lines.extend(("units bohr", "no_reorient", "no_com", "symmetry c1"))
    return psi4.geometry("\n".join(lines))


def run_case(name, atom, basis, method, charge, multiplicity):
    molecule = geometry(atom, charge, multiplicity)
    options = {
        "basis": basis,
        "scf_type": "pk",
        "guess": "core",
        "e_convergence": 1e-10,
        "d_convergence": 1e-10,
        "maxiter": 100,
        "puream": True,
        "reference": "uhf" if multiplicity != 1 else "rhf",
    }
    psi4.set_options(options)
    started = time.perf_counter()
    energy, wavefunction = psi4.energy(method, molecule=molecule, return_wfn=True)
    psi4.oeprop(wavefunction, "DIPOLE")
    dipole = np.asarray(wavefunction.variable("CURRENT DIPOLE"), dtype=float)
    variables = wavefunction.variables()
    iterations = variables.get("SCF ITERATIONS")
    return {
        "name": name,
        "method": method,
        "basis": basis,
        "charge": charge,
        "multiplicity": multiplicity,
        "energy_hartree": float(energy),
        "dipole_au": dipole.tolist(),
        "scf_iterations": int(iterations) if iterations is not None else None,
        "seconds": time.perf_counter() - started,
        "converged": bool(wavefunction.variable("SCF ITERATIONS") is not None),
    }


def main():
    psi4.set_num_threads(1)
    psi4.core.be_quiet()
    py = json.loads(PYSCF_RESULT.read_bytes())["states"]
    cases = [
        ("water_rhf_sto3g", WATER, "sto-3g", "scf", 0, 1),
        ("water_rhf_631g_star", WATER, "6-31g*", "scf", 0, 1),
        ("water_b3lyp_631g_star", WATER, "6-31g*", "b3lyp", 0, 1),
        ("h2plus_uhf_sto3g", H2PLUS, "sto-3g", "scf", 1, 2),
    ]
    results = {}
    for name, atom, basis, method, charge, multiplicity in cases:
        psi = run_case(name, atom, basis, method, charge, multiplicity)
        reference = py[name]
        psi["pyscf_energy_difference"] = abs(psi["energy_hartree"] - reference["energy_hartree"])
        psi["pyscf_dipole_difference"] = float(np.max(np.abs(np.asarray(psi["dipole_au"]) - reference["dipole_au"])))
        results[name] = psi
    output = {
        "protocol": {
            "psi4_version": psi4.__version__,
            "psi4_source_commit": "f2492db10de56b30b188239bdc6b4cfbc4a23bd5",
            "python": platform.python_version(),
            "numpy": np.__version__,
            "einsums": conda_version("einsums", "1.1.2"),
            "libxc": conda_version("libxc-c", "7.0.0"),
            "package_specs": ["python=3.13", "psi4==1.10", "einsums==1.1.2", "libxc-c==7.0.0"],
            "method_backend": "Psi4 SCF with scf_type=pk, puream=true, core guess, one thread",
            "geometry_units": "Bohr",
            "origin_bohr": [0.0, 0.0, 0.0],
            "pyscf_result_sha256": digest(PYSCF_RESULT),
            "recorded_utc": datetime.now(timezone.utc).isoformat(),
        },
        "results": results,
        "maximum_energy_difference": max(row["pyscf_energy_difference"] for row in results.values()),
        "maximum_dipole_difference": max(row["pyscf_dipole_difference"] for row in results.values()),
    }
    (HERE / "psi4_result.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "psi4": output["protocol"]["psi4_version"],
        "einsums": output["protocol"]["einsums"],
        "libxc": output["protocol"]["libxc"],
        "cases": len(results),
        "maximum_energy_difference": output["maximum_energy_difference"],
        "maximum_dipole_difference": output["maximum_dipole_difference"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
