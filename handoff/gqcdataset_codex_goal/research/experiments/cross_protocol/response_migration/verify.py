"""Offline checks for the response migration score."""

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE / "score.json").read_bytes())
    evaluations = {row["id"]: row for row in result["evaluations"]}
    assert result["target_labels_read_by_producer"] is False
    assert evaluations["direct_same_protocol"]["status"] == "accepted"
    assert evaluations["basis_change"]["status"] == "initial_guess_only"
    assert evaluations["method_change"]["status"] == "refine_required"
    assert evaluations["open_shell"]["status"] == "reject_and_recompute"
    assert evaluations["low_gap"]["status"] == "evidence_unavailable"
    assert evaluations["direct_same_protocol"]["target"]["physical_residual_l2"] <= 1e-10
    print(json.dumps({"status_counts": result["counts"], "direct_target_error": evaluations["direct_same_protocol"]["target_error"],
                      "direct_vector_error": evaluations["direct_same_protocol"]["vector_error"]}, sort_keys=True))


if __name__ == "__main__":
    main()
