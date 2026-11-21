"""Verify finite multi-field planning against the sealed #15 holdout run.

The script reads the sealed production journal and the independently verified
two-field run.  It does not read a v2 target table.  A new multi-field result
is compared with the already verified program at the level of its exact
linear plan, physical work, evidence work and accepted output.
"""

import csv
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median
import time

from finite_plans import HISTORIES, MIXED, SCENARIOS, compile_plan, score


ROOT = Path(__file__).resolve().parents[5]
OLD = ROOT / "handoff/gqcdataset_codex_goal/research/experiments/response_benefit/evidence"
HERE = Path(__file__).resolve().parent
MULTI = HERE / "multi"
HOLDOUT = (
    "qm9-000005", "qm9-000007", "qm9-000008", "qm9-000013",
    "qm9-000014", "qm9-000015", "qm9-000016", "qm9-000017",
)


def read_jsonl(path, compressed=False):
    opener = gzip.open if compressed else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def canonical_terms(terms):
    return tuple((str(c), str(p), float(w)) for c, p, w in terms)


def plan_terms(plan):
    columns, outputs = plan
    return tuple((f + "/" + o, canonical_terms(terms)) for f, o, terms in outputs), tuple(columns)


def finite_candidates(requests, known):
    start = time.perf_counter()
    choices = []
    for size in range(1, min(3, len(MIXED)) + 1):
        # The planner's finite universe is C(4,1)+C(4,2)+C(4,3)=14.
        choices.extend(1 for _ in __import__("itertools").combinations(MIXED, size))
    selected = compile_plan("multi", requests, known, ())
    two = compile_plan("two", requests, known, ())
    return {
        "candidate_count": len(choices),
        "selected": {"columns": selected[0], "score": score(selected), "terms": plan_terms(selected)[0]},
        "two": {"columns": two[0], "score": score(two), "terms": plan_terms(two)[0]},
        "planning_seconds": time.perf_counter() - start,
    }


def event_cost(event):
    cost = event.get("cost", {})
    return {
        "jk_calls": int(cost.get("jk_calls", 0)),
        "rhs_columns": int(cost.get("rhs_columns", 0)),
        "submitted_blocks": int(cost.get("submitted_blocks", 0)),
        "quality_native_actions": int(event.get("quality_native_actions", 0)),
        "input_bytes": int(event.get("input_bytes", 0)),
        "seconds": float(event.get("seconds", 0.0)),
    }


def sum_cost(events):
    keys = ("jk_calls", "rhs_columns", "submitted_blocks", "quality_native_actions", "input_bytes", "seconds")
    return {key: sum(event_cost(event)[key] for event in events) for key in keys}


def close(a, b, tolerance=1e-12):
    return abs(float(a) - float(b)) <= tolerance


def compare_output(old, new):
    if set(old["outputs"]) != set(new["outputs"]):
        return False
    for key in old["outputs"]:
        left, right = old["outputs"][key], new["outputs"][key]
        if left["status"] != "accepted" or right["status"] != "accepted":
            return False
        for field in ("value", "raw_value", "error_estimate", "target_identity", "unit", "source"):
            if field in ("target_identity", "unit", "source"):
                if left[field] != right[field]:
                    return False
            elif not close(left[field], right[field]):
                return False
    return True


def load_events():
    manifest = json.loads((MULTI / "manifest.json").read_bytes())
    for name, receipt in manifest.items():
        data = (MULTI / name).read_bytes()
        if len(data) != receipt["bytes"] or hashlib.sha256(data).hexdigest() != receipt["sha256"]:
            raise AssertionError("multi package manifest mismatch: " + name)
    old = read_jsonl(OLD / "events.jsonl.gz", compressed=True)
    new = read_jsonl(MULTI / "events.jsonl.gz", compressed=True)
    return old, new


def analyze():
    old, new = load_events()
    old_two = {
        (event["source"], event["repetition"]): event
        for event in old
        if event.get("phase") == "future"
        and event.get("split") == "holdout"
        and event.get("scenario") == "cycle-three"
        and event.get("method") == "two"
    }
    new_multi = [
        event for event in new
        if event.get("phase") == "future" and event.get("method") == "multi"
    ]
    if len(old_two) != 32 or len(new_multi) != 32:
        raise AssertionError((len(old_two), len(new_multi)))

    comparisons = []
    for event in sorted(new_multi, key=lambda item: (item["source"], item["repetition"])):
        key = (event["source"], event["repetition"])
        reference = old_two[key]
        requests = tuple(tuple(target.split("/")) for target in reference["terms"])
        known = HISTORIES["cycle"]
        selected = compile_plan("multi", requests, known, ())
        selected_terms, selected_columns = plan_terms(selected)
        reference_terms = tuple((target, canonical_terms(terms)) for target, terms in reference["terms"].items())
        terms_equal = selected_terms == reference_terms == tuple(
            (target, canonical_terms(terms)) for target, terms in event["terms"].items()
        )
        cost_equal = event_cost(event)["jk_calls"] == event_cost(reference)["jk_calls"]
        cost_equal = cost_equal and event_cost(event)["rhs_columns"] == event_cost(reference)["rhs_columns"]
        cost_equal = cost_equal and event_cost(event)["quality_native_actions"] == event_cost(reference)["quality_native_actions"]
        comparisons.append({
            "source": event["source"], "repetition": event["repetition"],
            "terms_equal": terms_equal, "cost_equal": cost_equal,
            "output_equal": compare_output(reference, event),
            "columns": selected_columns,
            "multi_cost": event_cost(event), "two_cost": event_cost(reference),
            "fallback": event.get("fallback", []),
        })

    future_cost = sum_cost(new_multi)
    all_cost = sum_cost([event for event in new if event.get("phase") in {"setup", "history", "future"}])
    planning = {}
    for scenario, (mask, request_list) in SCENARIOS.items():
        planning[scenario] = finite_candidates(tuple(request_list), HISTORIES[mask])

    no_new_rhs = compile_plan("multi", (("x", "q0"),), (("y", "q0"),), ())
    no_same_readout = compile_plan("multi", (("x", "r2"),), (("y", "q0"),), ())
    conditioning_rows = list(csv.DictReader((OLD / "recovery-conditioning.csv").open(newline="")))
    conditioning = {
        "maximum_spectral_condition_upper": max(float(row["spectral_condition_upper"]) for row in conditioning_rows),
        "maximum_observed_cancellation_ratio": max(float(row["max_observed_cancellation"]) for row in conditioning_rows),
        "rows": len(conditioning_rows),
    }

    old_warm = [event["seconds"] for event in old_two.values() if event["warmup"] is False]
    new_warm = [event["seconds"] for event in new_multi if event["warmup"] is False]
    result = {
        "protocol": {
            "source_evidence": "response_benefit/evidence",
            "source_evidence_manifest_sha256": hashlib.sha256((OLD / "manifest.json").read_bytes()).hexdigest(),
            "multi_manifest_sha256": hashlib.sha256((MULTI / "manifest.json").read_bytes()).hexdigest(),
            "holdout_sources": list(HOLDOUT),
            "scenario": "cycle-three",
            "requests_per_source": 3,
            "repetitions": 4,
            "target_labels_read": False,
        },
        "finite_planning": planning,
        "sufficiency_controls": {
            "history_only_missing_field": {
                "history": [["y", "q0"]], "target": "x/q0",
                "recoverable_without_new_rhs": len(no_new_rhs[0]) == 0,
                "planner_fallback_columns": list(no_new_rhs[0]),
            },
            "cross_readout_cannot_be_subtracted": {
                "history": [["y", "q0"]], "target": "x/r2",
                "recoverable_without_new_rhs": len(no_same_readout[0]) == 0,
                "planner_fallback_columns": list(no_same_readout[0]),
            },
            "conditioning": conditioning,
        },
        "comparison": {
            "records": len(comparisons),
            "terms_equal": sum(item["terms_equal"] for item in comparisons),
            "cost_equal": sum(item["cost_equal"] for item in comparisons),
            "outputs_equal": sum(item["output_equal"] for item in comparisons),
            "fallbacks": sum(len(item["fallback"]) for item in comparisons),
            "multi_future_cost": future_cost,
            "multi_all_recorded_cost": all_cost,
            "multi_warm_seconds_median": median(new_warm),
            "two_warm_seconds_median": median(old_warm),
            "multi_warm_seconds": new_warm,
            "two_warm_seconds": old_warm,
            "records_detail": comparisons,
        },
        "examples": {
            "water": {"ordinary_jk": 22, "two_field_jk": 20, "ordinary_rhs": 3, "two_field_rhs": 2},
            "ammonia": {"ordinary_jk": 30, "two_field_jk": 31, "ordinary_rhs": 3, "two_field_rhs": 2},
        },
    }
    if not all(item["terms_equal"] and item["cost_equal"] and item["output_equal"] for item in comparisons):
        raise AssertionError("multi-field replay diverged from the independently verified two-field run")
    return result


def main():
    result = analyze()
    destination = HERE / "result.json"
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "records": result["comparison"]["records"],
        "terms_equal": result["comparison"]["terms_equal"],
        "cost_equal": result["comparison"]["cost_equal"],
        "outputs_equal": result["comparison"]["outputs_equal"],
        "multi_future_jk": result["comparison"]["multi_future_cost"]["jk_calls"],
        "multi_all_jk": result["comparison"]["multi_all_recorded_cost"]["jk_calls"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
