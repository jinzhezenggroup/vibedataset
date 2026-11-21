#!/usr/bin/env python3
"""Build the sealed request manifest used by the four-arm attribution run.

The manifest is intentionally derived from the already committed QM9 cohort
records.  It contains no response values or scoring output.  Production jobs
can therefore consume it before any target truth is generated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "handoff" / "gqcdataset_codex_goal" / "research"
COHORTS = [
    RESEARCH / "experiments" / "qm9_response_assets" / "cohort.json",
    RESEARCH / "experiments" / "qm9_extension" / "cohort.json",
]
ASSET_DIRS = [
    RESEARCH / "experiments" / "qm9_response_assets",
    RESEARCH / "experiments" / "qm9_extension" / "assets",
]


def read_json(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def find_asset(name: str) -> Path:
    for directory in ASSET_DIRS:
        candidate = directory / f"{name}.json"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(name)


def selected_records() -> list[dict]:
    rows: dict[str, dict] = {}
    for cohort_path in COHORTS:
        for stratum in read_json(cohort_path)["strata"]:
            selected = stratum.get("selected")
            if selected:
                rows[selected["name"]] = selected
    result = []
    for name in sorted(rows, key=lambda item: int(item.split("-")[-1])):
        selected = rows[name]
        asset_path = next(
            (directory / f"{name}.json" for directory in ASSET_DIRS
             if (directory / f"{name}.json").exists()),
            None,
        )
        inputs = read_json(asset_path)["inputs"] if asset_path else {
            "atomic_numbers": [
                {"H": 1, "C": 6, "N": 7, "O": 8, "F": 9}[symbol]
                for symbol in selected["symbols"]
            ],
            "coordinates": selected["coordinates_bohr"],
            "charge": 0,
            "multiplicity": 1,
            "basis_representation": "real_spherical",
        }
        result.append(
            {
                "name": name,
                "qm9_id": selected["qm9_id"],
                "member_sha256": selected["member_sha256"],
                "atomic_numbers": inputs["atomic_numbers"],
                "coordinates_bohr": inputs["coordinates"],
                "charge": inputs["charge"],
                "multiplicity": inputs["multiplicity"],
                "basis_representation": inputs["basis_representation"],
            }
        )
    return result


def build_manifest() -> dict:
    molecules = selected_records()
    manifest = {
        "schema": "vibedataset.attribution_4arm.v1",
        "source": {
            "qm9_cohorts": [str(path.relative_to(ROOT)) for path in COHORTS],
            "asset_directories": [str(path.relative_to(ROOT)) for path in ASSET_DIRS],
            "generator": "scripts/build_4arm_manifest.py",
        },
        "protocol": {
            "method": "RHF",
            "basis": "sto-3g",
            "basis_representation": "real_spherical",
            "unit": "Bohr",
            "precision": "FP64",
            "origin": [0.0, 0.0, 0.0],
            "conv_tol": 1e-10,
            "max_cycle": 100,
            "response_tol": 1e-8,
            "response_max_cycle": 50,
            "device": "cuda",
            "seed": 20261122,
        },
        "request_trajectories": [
            {
                "id": "cycle-one",
                "order": 1,
                "fields": ["x"],
                "targets": ["xx"],
            },
            {
                "id": "cycle-three",
                "order": 2,
                "fields": ["x", "y", "z"],
                "targets": ["xx", "yy", "zz", "xy", "xz", "yz"],
            },
            {
                "id": "cross-three",
                "order": 3,
                "fields": ["x", "z"],
                "targets": ["xz", "zx"],
            },
        ],
        "molecules": molecules,
    }
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(build_manifest(), indent=2) + "\n")


if __name__ == "__main__":
    main()
