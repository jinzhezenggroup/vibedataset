"""Offline checks for the cross-protocol identity matrix."""

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE / "result.json").read_bytes())
    psi4 = json.loads((HERE / "psi4_result.json").read_bytes())
    states = result["states"]
    assert len(states) == 7
    assert all(row["converged"] and row["density_finite"] for row in states.values())
    classes = {row["classification"] for row in result["classification_matrix"]}
    assert {"direct_reuse", "initial_guess_only", "refine_required", "reject", "reject_and_recompute"} <= classes
    controls = result["controls"]
    assert controls["basis_change_energy_difference"] > 1e-6
    assert controls["method_change_energy_difference"] > 1e-6
    assert controls["response"]["frozen_vs_relaxed_max_abs"] > 1e-8
    assert controls["representation"]["unknown_permutation_dipole_difference"] > 1e-8
    assert controls["representation"]["known_permutation_roundtrip_difference"] == 0.0
    assert states["h2plus_uhf_sto3g"]["charge"] == 1
    assert states["h2plus_uhf_sto3g"]["multiplicity"] == 2
    assert psi4["protocol"]["psi4_version"] == "1.10"
    assert psi4["protocol"]["psi4_source_commit"] == "f2492db10de56b30b188239bdc6b4cfbc4a23bd5"
    assert len(psi4["results"]) == 4
    assert psi4["maximum_energy_difference"] <= 1e-6
    assert psi4["maximum_dipole_difference"] <= 1e-6
    print(json.dumps({
        "states": len(states),
        "classifications": sorted(classes),
        "basis_change_energy_difference": controls["basis_change_energy_difference"],
        "method_change_energy_difference": controls["method_change_energy_difference"],
        "frozen_vs_relaxed_max_abs": controls["response"]["frozen_vs_relaxed_max_abs"],
        "unknown_permutation_dipole_difference": controls["representation"]["unknown_permutation_dipole_difference"],
        "psi4_cases": len(psi4["results"]),
        "psi4_maximum_energy_difference": psi4["maximum_energy_difference"],
        "psi4_maximum_dipole_difference": psi4["maximum_dipole_difference"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
