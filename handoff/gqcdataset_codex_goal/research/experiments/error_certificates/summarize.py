"""Assemble the independent certificate controls and blind molecular scores."""

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
QUALITY = ROOT / "handoff/gqcdataset_codex_goal/research/experiments/target_quality"
BOUND = ROOT / "handoff/gqcdataset_codex_goal/research/experiments/represented_matrix_bound"
PRIOR = ROOT / "handoff/gqcdataset_codex_goal/research/experiments/response_quality_prior"
HERE = Path(__file__).resolve().parent

NUMERIC_COST_FIELDS = (
    "jk_calls", "submitted_rhs", "submitted_blocks", "dense_solve_rhs",
    "ao_to_mo_transforms", "svd_calls", "matrix_bytes", "transformed_eri_bytes",
    "bytes_read", "input_file_bytes", "vector_bytes", "rhs_bytes", "readout_bytes",
    "asset_bytes_written", "scalars_bytes_written", "vectors_bytes_written",
    "quantized_bytes_written", "unrated_bytes_written", "seconds", "failed",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def cost_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for field in NUMERIC_COST_FIELDS:
            row[field] = float(row[field]) if field == "seconds" else int(row[field])
    return rows


def sum_cost(rows):
    return {field: sum(row[field] for row in rows) for field in NUMERIC_COST_FIELDS}


def mode_costs(split):
    rows = cost_rows(QUALITY / split / "costs.csv")
    result = {}
    for mode in sorted({row["mode"] for row in rows}):
        result[mode] = sum_cost([row for row in rows if row["mode"] == mode])
    return result


def score_summary(score, mode):
    output = score["outputs"][mode]
    targets = score["targets"][mode]
    scored = [row for row in targets if "absolute_difference" in row]
    false_accept = sum(row["terminal"] == "accepted" and row["absolute_difference"] > 1e-8 for row in scored)
    false_reject = sum(row["terminal"] in {"reject", "refine"} and row["absolute_difference"] <= 1e-8 for row in scored)
    return {
        "requests": output["requests"],
        "molecules": output["molecules"],
        "initial": output["initial"],
        "terminal": output["states"],
        "refined_to_accept": output["refined_to_accept"],
        "evidence_unavailable": output["states"].get("evidence_unavailable", 0),
        "false_accept": int(false_accept),
        "false_reject": int(false_reject),
        "outside_discrete_estimate_plus_reference_uncertainty": output["outside_discrete_estimate_plus_reference_uncertainty"],
        "max_absolute_difference": max((row["absolute_difference"] for row in scored), default=None),
    }


def certificate_summary():
    holdout = load(QUALITY / "holdout/score.json")
    seed = load(QUALITY / "seed/score.json")
    pymor = load(PRIOR / "pymor.json")
    bound = load(BOUND / "score.json")

    py_cases = pymor["cases"]
    approximate_dual = {
        "control_systems": len(py_cases),
        "accepted": sum(case["accepted"] for case in py_cases),
        "false_accept": sum(case["false_accept"] for case in py_cases),
        "false_reject": 0,
        "evidence_unavailable": 0,
        "observed_error_max": max(case["error"] for case in py_cases),
        "wall_seconds": sum(case["evaluate_seconds"] + case["reduction_seconds"] for case in py_cases),
        "molecular_coverage": "not measured by this control",
    }
    residual_only = pymor["residual_only"]
    residual = {
        "control_systems": 1,
        "accepted": int(residual_only["accepted"]),
        "false_accept": int(residual_only["accepted"] and residual_only["observed_error"] > pymor["tolerance"]),
        "false_reject": 0,
        "evidence_unavailable": 0,
        "observed_error_max": residual_only["observed_error"],
        "residual_gate": residual_only["residual_gate"],
        "molecular_coverage": "not measured by this control",
    }
    strict = {
        "available_states": bound["available_ground_states"],
        "accepted": bound["statuses"]["accepted"],
        "false_accept": bound["false_accepts_vs_v2"],
        "false_reject": 0,
        "evidence_unavailable": bound["statuses"]["evidence_unavailable"],
        "coverage_of_available_states": bound["statuses"]["accepted"] / bound["available_ground_states"],
        "coverage_of_all_candidates": bound["statuses"]["accepted"] / 17,
        "ao_to_mo_transforms": bound["ao_to_mo_transforms"],
        "svd_calls": bound["svds"],
        "validation_jk": bound["validation_jk"],
    }
    return {
        "residual_only": residual,
        "approximate_dual_weighted_residual": approximate_dual,
        "svd_discrete_response": score_summary(holdout, "mixed"),
        "direct_recompute": score_summary(holdout, "ordinary"),
        "dense_fallback": score_summary(holdout, "dense"),
        "strict_discrete_bound": strict,
        "without_history_error_evidence": score_summary(holdout, "unrated"),
        "quantized_history_refinement": score_summary(holdout, "quantized"),
        "seed_svd_discrete_response": score_summary(seed, "mixed"),
    }


def main():
    costs = {"seed": mode_costs("seed"), "holdout": mode_costs("holdout")}
    result = {
        "protocol": {
            "target_quality_holdout_sha256": digest(QUALITY / "holdout/score.json"),
            "target_quality_holdout_costs_sha256": digest(QUALITY / "holdout/costs.csv"),
            "target_quality_seed_sha256": digest(QUALITY / "seed/score.json"),
            "strict_bound_score_sha256": digest(BOUND / "score.json"),
            "approximate_dual_control_sha256": digest(PRIOR / "pymor.json"),
            "labels_read_by_summary": True,
            "labels_read_by_production": False,
        },
        "certificates": certificate_summary(),
        "costs": costs,
    }
    (HERE / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "holdout_svd": result["certificates"]["svd_discrete_response"],
        "strict_bound": result["certificates"]["strict_discrete_bound"],
        "residual_false_accept": result["certificates"]["residual_only"]["false_accept"],
        "dual_false_accept": result["certificates"]["approximate_dual_weighted_residual"]["false_accept"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
