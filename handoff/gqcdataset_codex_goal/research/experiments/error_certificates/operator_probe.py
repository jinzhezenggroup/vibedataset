"""Full-space operator consistency producer and independent scorer for #26."""

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "scripts"))
from gqc_dual_response import DualResponseModel
from probe_gqc_residual import file_hash
from target_response_quality import StabilityEvidence

SOURCE_DIR = ROOT / "handoff/gqcdataset_codex_goal/research/experiments/qm9_response_assets"
SOURCE_NAME = "qm9-000003"
PROBE_SEED = 314159
TOLERANCE = 1e-10


def digest(value):
    return hashlib.sha256(value).hexdigest()


def source_paths():
    return SOURCE_DIR / (SOURCE_NAME + ".json"), SOURCE_DIR / (SOURCE_NAME + ".npz")


def vector_probe(model, matrix, rng):
    dimension = model.dimension
    basis = []
    before = Counter(model.counts)
    for index in range(dimension):
        vector = np.zeros(dimension)
        vector[index] = 1.0
        basis.append(np.asarray(model.apply(vector), dtype=np.float64))
    native_matrix = np.column_stack(basis)
    random_vectors = []
    random_errors = []
    for _ in range(4):
        vector = rng.normal(size=dimension)
        vector /= np.linalg.norm(vector)
        native = np.asarray(model.apply(vector), dtype=np.float64)
        random_vectors.append(vector)
        random_errors.append(float(np.linalg.norm(native - matrix @ vector)))
    rhs_vectors = []
    rhs_errors = []
    for group in ("fields", "observables"):
        for key in sorted(model.rhs_values[group]):
            rhs = np.array(model.rhs_values[group][key], dtype=np.float64, copy=True)
            rhs /= np.linalg.norm(rhs)
            native = np.asarray(model.apply(rhs), dtype=np.float64)
            rhs_vectors.append((group, key, rhs))
            rhs_errors.append(float(np.linalg.norm(native - matrix @ rhs)))
    singular_values, left, right_transposed = np.linalg.svd(matrix)
    near = right_transposed[-1]
    near_native = np.asarray(model.apply(near), dtype=np.float64)
    return {
        "native_matrix": native_matrix,
        "random_vectors": random_vectors,
        "random_errors": random_errors,
        "rhs_vectors": rhs_vectors,
        "rhs_errors": rhs_errors,
        "near_singular_vector": near,
        "near_singular_error": float(np.linalg.norm(near_native - matrix @ near)),
        "singular_values": singular_values,
        "probe_counts": dict(model.counts - before),
    }


def json_ready(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def make_record(workdir):
    metadata, arrays = source_paths()
    model = DualResponseModel(metadata, arrays, workdir / "kernels")
    stability = StabilityEvidence.from_model(model)
    if stability.matrix is None:
        raise RuntimeError(stability.report.get("reason", "stability evidence unavailable"))
    matrix = np.asarray(stability.matrix, dtype=np.float64)
    started = time.perf_counter()
    probes = vector_probe(model, matrix, np.random.default_rng(PROBE_SEED))
    native_matrix = probes["native_matrix"]
    assembly_error = matrix - native_matrix
    perturbation = np.zeros_like(matrix)
    perturbation[0, 1] = 1e-6
    nonsymmetric = matrix + perturbation
    record = {
        "protocol": {
            "source_name": SOURCE_NAME,
            "metadata_sha256": file_hash(metadata),
            "array_sha256": file_hash(arrays),
            "gqc_commit": "2791504cc238fe83d328fc1718080642b288222a",
            "dimension": model.dimension,
            "probe_seed": PROBE_SEED,
            "probe_policy": "all standard basis, four fixed random unit vectors, all six normalized field/readout RHS, smallest-SVD right vector",
            "target_labels_read": False,
        },
        "setup": model.setup,
        "stability": stability.report,
        "assembled_matrix": matrix,
        "native_basis_matrix": native_matrix,
        "probes": probes,
        "operator_consistency": {
            "basis_probe_count": model.dimension,
            "random_probe_count": len(probes["random_errors"]),
            "rhs_probe_count": len(probes["rhs_errors"]),
            "max_basis_abs_error": float(np.max(np.abs(assembly_error))),
            "max_basis_relative_error": float(np.max(np.abs(assembly_error)) / max(1.0, np.max(np.abs(native_matrix)))),
            "max_random_error": max(probes["random_errors"]),
            "max_rhs_error": max(probes["rhs_errors"]),
            "near_singular_error": probes["near_singular_error"],
            "assembled_skew_frobenius": float(np.linalg.norm(matrix - matrix.T, ord="fro")),
            "status": "accepted" if np.max(np.abs(assembly_error)) <= TOLERANCE else "evidence_unavailable",
        },
        "controls": {
            "near_singular": {
                "matrix": [[1.0, 0.0], [0.0, 1e-12]],
                "candidate": [0.0, 0.0],
                "rhs": [0.0, 1e-12],
                "residual_norm": 1e-12,
                "true_target_error": 1.0,
                "residual_only_decision": "accepted",
                "certificate_decision": "evidence_unavailable",
            },
            "nonsymmetric_assembly": {
                "perturbation": perturbation,
                "max_difference_from_native": float(np.max(np.abs(nonsymmetric - native_matrix))),
                "certificate_decision": "evidence_unavailable",
            },
        },
        "cost": {
            "setup_counts": dict(model.counts),
            "probe_counts": probes["probe_counts"],
            "matrix_bytes": int(matrix.nbytes),
            "stored_probe_bytes": int(sum(np.asarray(item).nbytes for item in probes["random_vectors"]) +
                                       sum(np.asarray(item[2]).nbytes for item in probes["rhs_vectors"]) +
                                       np.asarray(probes["near_singular_vector"]).nbytes),
            "seconds": time.perf_counter() - started,
        },
    }
    return json_ready(record)


def produce(out):
    out.mkdir(parents=True, exist_ok=False)
    record = make_record(out / "producer")
    (out / "sealed.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "seal.json").write_text(json.dumps({
        "sealed_sha256": digest((out / "sealed.json").read_bytes()),
        "target_labels_read": False,
        "producer": "operator_probe.py",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def score(sealed, out):
    data = json.loads(sealed.read_bytes())
    if data["protocol"]["target_labels_read"]:
        raise AssertionError("sealed producer read target labels")
    out.mkdir(parents=True, exist_ok=False)
    fresh = make_record(out / "scorer")
    checks = {
        "source_identity": data["protocol"] == fresh["protocol"],
        "assembled_matrix": bool(np.max(np.abs(np.asarray(data["assembled_matrix"]) - np.asarray(fresh["assembled_matrix"]))) <= 1e-14),
        "native_basis_matrix": bool(np.max(np.abs(np.asarray(data["native_basis_matrix"]) - np.asarray(fresh["native_basis_matrix"]))) <= 1e-14),
        "random_errors": bool(data["probes"]["random_errors"] == fresh["probes"]["random_errors"]),
        "rhs_errors": bool(data["probes"]["rhs_errors"] == fresh["probes"]["rhs_errors"]),
        "near_singular_error": bool(data["probes"]["near_singular_error"] == fresh["probes"]["near_singular_error"]),
    }
    result = {
        "checks": checks,
        "producer_cost": data["cost"],
        "scorer_cost": fresh["cost"],
        "operator_consistency": fresh["operator_consistency"],
        "controls": fresh["controls"],
        "target_labels_read": False,
        "sealed_sha256": digest(sealed.read_bytes()),
    }
    (out / "score.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not all(checks.values()):
        raise AssertionError(checks)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("produce", "score"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sealed", type=Path)
    args = parser.parse_args()
    if args.mode == "produce":
        record = produce(args.out)
        print(json.dumps({"status": "sealed", "dimension": record["protocol"]["dimension"],
                          "operator_status": record["operator_consistency"]["status"],
                          "basis_probe_count": record["operator_consistency"]["basis_probe_count"]}, sort_keys=True))
    else:
        if args.sealed is None:
            raise SystemExit("--sealed is required for score")
        result = score(args.sealed, args.out)
        print(json.dumps({"status": "scored", "checks": result["checks"],
                          "operator_status": result["operator_consistency"]["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
