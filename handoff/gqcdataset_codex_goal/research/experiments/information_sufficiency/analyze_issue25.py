"""Audit the independent hand baseline and four-column search replay."""

import csv
import gzip
import hashlib
import itertools
import json
import argparse
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
NEW = HERE / "issue25"
OLD = ROOT / "handoff/gqcdataset_codex_goal/research/experiments/response_benefit/evidence"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "handoff/gqcdataset_codex_goal/research/experiments/response_benefit"))
sys.path.insert(0, str(HERE))
from independent_hand_plans import CYCLE, plan as hand_plan
from plans import HISTORIES, MIXED, SCENARIOS, compile_plan, multi, score

HOLDOUT = (
    "qm9-000005", "qm9-000007", "qm9-000008", "qm9-000013",
    "qm9-000014", "qm9-000015", "qm9-000016", "qm9-000017",
)
METHODS = ("multi4", "hand_field_independent", "hand_adjoint_independent")
SCENARIO_KEYS = tuple(SCENARIOS)


def events(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def canonical_terms(terms):
    return tuple((str(c), str(p), float(w)) for c, p, w in terms)


def close(a, b, tolerance=1e-12):
    return abs(float(a) - float(b)) <= tolerance


def output_equal(left, right):
    if set(left["outputs"]) != set(right["outputs"]):
        return False
    for key in left["outputs"]:
        a, b = left["outputs"][key], right["outputs"][key]
        if a.get("status") != "accepted" or b.get("status") != "accepted":
            return False
        for field in ("value", "raw_value", "error_estimate"):
            if not close(a[field], b[field]):
                return False
        for field in ("unit", "source", "target_identity"):
            if a[field] != b[field]:
                return False
    return True


def event_cost(event):
    cost = event.get("cost", {})
    return {
        "jk_calls": int(cost.get("jk_calls", 0)),
        "rhs_columns": int(cost.get("rhs_columns", 0)),
        "submitted_blocks": int(cost.get("submitted_blocks", 0)),
        "quality_native_actions": int(event.get("quality_native_actions", 0)),
        "input_bytes": int(event.get("input_bytes", 0)),
        "output_bytes": int(event.get("output_asset", {}).get("bytes", 0)),
        "seconds": float(event.get("seconds", 0.0)),
    }


def total_cost(rows):
    keys = ("jk_calls", "rhs_columns", "submitted_blocks", "quality_native_actions", "input_bytes", "output_bytes", "seconds")
    return {key: sum(event_cost(row)[key] for row in rows) for key in keys}


def old_costs():
    rows = list(csv.DictReader(gzip.open(OLD / "paired-costs.csv.gz", "rt", encoding="utf-8")))
    out = {}
    for scenario in SCENARIO_KEYS:
        for method in ("direct", "adjoint", "two", "hand_field", "hand_adjoint", "vectors", "dense"):
            selected = [row for row in rows if row["split"] == "holdout" and row["scenario"] == scenario and row["method"] == method]
            if not selected:
                continue
            fields = ("total_jk", "marg_rhs", "total_seconds", "input_bytes", "output_bytes", "retained_bytes", "quality_jk")
            out[scenario + "/" + method] = {
                field: sum(float(row[field]) for row in selected) for field in fields
            }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result",
        type=Path,
        default=HERE / "issue25_result.json",
        help="where to write the deterministic replay result",
    )
    args = parser.parse_args()
    manifest = json.loads((NEW / "manifest.json").read_bytes())
    for name, receipt in manifest.items():
        data = (NEW / name).read_bytes()
        if len(data) != receipt["bytes"] or hashlib.sha256(data).hexdigest() != receipt["sha256"]:
            raise AssertionError("manifest mismatch: " + name)
    fresh = events(NEW / "events.jsonl.gz")
    archived = events(OLD / "events.jsonl.gz")
    old_two = {
        (row["source"], row["repetition"], row["scenario"]): row
        for row in archived
        if row.get("phase") == "future" and row.get("split") == "holdout" and row.get("method") == "two"
    }
    current = {
        (row["source"], row["repetition"], row["scenario"], row["method"]): row
        for row in fresh
        if row.get("phase") == "future"
    }
    expected_records = len(HOLDOUT) * 4 * len(SCENARIO_KEYS)
    if any(sum(key[3] == method for key in current) != expected_records for method in METHODS):
        raise AssertionError("future record denominator")

    comparison = {method: {"records": 0, "terms_vs_two": 0, "outputs_vs_two": 0,
                           "accepted_outputs": 0, "max_value_difference_vs_two": 0.0,
                           "cost_vs_two": 0, "fallbacks": 0, "cost": total_cost([])} for method in METHODS}
    for method in METHODS:
        rows = [row for key, row in current.items() if key[3] == method]
        comparison[method]["cost"] = total_cost(rows)
        comparison[method]["fallbacks"] = sum(len(row.get("fallback", [])) for row in rows)
        for row in rows:
            key = row["source"], row["repetition"], row["scenario"]
            reference = old_two[key]
            comparison[method]["records"] += 1
            terms_match = row["terms"] == reference["terms"]
            output_match = output_equal(row, reference)
            value_difference = max(abs(row["outputs"][target]["value"] - reference["outputs"][target]["value"])
                                   for target in row["outputs"])
            accepted = all(output.get("status") == "accepted" and output.get("value") is not None
                           and output.get("error_estimate", float("inf")) <= 1e-8
                           for output in row["outputs"].values())
            cost_match = event_cost(row)["jk_calls"] == event_cost(reference)["jk_calls"] and event_cost(row)["rhs_columns"] == event_cost(reference)["rhs_columns"]
            comparison[method]["terms_vs_two"] += int(terms_match)
            comparison[method]["outputs_vs_two"] += int(output_match)
            comparison[method]["accepted_outputs"] += int(accepted)
            comparison[method]["max_value_difference_vs_two"] = max(comparison[method]["max_value_difference_vs_two"], value_difference)
            comparison[method]["cost_vs_two"] += int(cost_match)
        if comparison[method]["fallbacks"]:
            raise AssertionError(method + " fallback")

    # Verify the independent formulas without importing the candidate planner.
    hand_terms = {"hand_field_independent": 0, "hand_adjoint_independent": 0}
    for method in hand_terms:
        for key, row in current.items():
            if key[3] != method:
                continue
            scenario = row["scenario"]
            requests = tuple(SCENARIOS[scenario][1])
            expected = hand_plan(requests, HISTORIES[SCENARIOS[scenario][0]], "field" if method.startswith("hand_field") else "observable")
            actual = tuple((target.split("/", 1)[0], target.split("/", 1)[1], canonical_terms(terms))
                           for target, terms in row["terms"].items())
            expected_terms = tuple((f, o, canonical_terms(terms)) for f, o, terms in expected[1])
            hand_terms[method] += int(actual == expected_terms)

    # The four-column planner enumerates all 15 nonempty subsets.  It is
    # physically run for the selected plan, while every candidate is checked
    # algebraically and ranked before execution.
    candidate_count = sum(1 for size in range(1, len(MIXED) + 1) for _ in itertools.combinations(MIXED, size))
    candidate_summary = {}
    for scenario, (mask, request_list) in SCENARIOS.items():
        chosen4 = compile_plan("multi4", tuple(request_list), HISTORIES[mask], ())
        chosen3 = multi(tuple(request_list), HISTORIES[mask])
        candidate_summary[scenario] = {
            "candidate_count": candidate_count,
            "multi4_score": score(chosen4),
            "multi3_score": score(chosen3),
            "selected_columns": chosen4[0],
            "selected_plan_equal_to_multi3": chosen4 == chosen3,
        }

    all_recorded = [row for row in fresh if row.get("phase") in {"setup", "history", "future"}]
    result = {
        "protocol": {
            "holdout_sources": list(HOLDOUT),
            "repetitions": 4,
            "scenarios": list(SCENARIO_KEYS),
            "methods": list(METHODS),
            "target_labels_read_by_production": False,
            "independent_hand_module_sha256": hashlib.sha256((HERE / "independent_hand_plans.py").read_bytes()).hexdigest(),
            "candidate_planner_sha256": hashlib.sha256((ROOT / "handoff/gqcdataset_codex_goal/research/experiments/response_benefit/plans.py").read_bytes()).hexdigest(),
        },
        "candidate_search": candidate_summary,
        "comparison": comparison,
        "independent_hand_terms": hand_terms,
        "shared_run_cost": total_cost(all_recorded),
        "archived_strong_baselines": old_costs(),
        "conditioning_and_cancellation": {
            "max_cancellation_ratio": max(
                float(output["cancellation_ratio"])
                for row in fresh if row.get("phase") == "future"
                for output in row.get("outputs", {}).values()
                if output.get("cancellation_ratio") is not None
            ),
        },
    }
    for method in METHODS:
        if comparison[method]["records"] != expected_records or comparison[method]["accepted_outputs"] != expected_records:
            raise AssertionError(method + " comparison")
    if comparison["multi4"]["terms_vs_two"] != expected_records:
        raise AssertionError("multi4 terms comparison")
    if any(count != expected_records for count in hand_terms.values()):
        raise AssertionError("independent hand plan comparison")
    if any(not data["selected_plan_equal_to_multi3"] for data in candidate_summary.values()):
        raise AssertionError("four-column plan differs from three-column selected plan")
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate_count": candidate_count,
        "future_records_per_method": expected_records,
        "hand_terms": hand_terms,
        "multi4_future_jk": comparison["multi4"]["cost"]["jk_calls"],
        "hand_field_future_jk": comparison["hand_field_independent"]["cost"]["jk_calls"],
        "hand_adjoint_future_jk": comparison["hand_adjoint_independent"]["cost"]["jk_calls"],
        "max_cancellation_ratio": result["conditioning_and_cancellation"]["max_cancellation_ratio"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
