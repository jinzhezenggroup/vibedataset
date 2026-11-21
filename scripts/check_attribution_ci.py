#!/usr/bin/env python3
"""Archive-level checks for Issues #31 and #33."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "handoff/gqcdataset_codex_goal/research/experiments/attribution_4arm"
SCRIPTS = ROOT / "scripts"


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = read(EXP / "manifest.json")
    score = read(EXP / "score.json")
    summary = read(EXP / "summary.json")
    negative = read(EXP / "negative-controls.json")
    expansion = read(EXP / "expansion.json")
    require(len(manifest["molecules"]) == 17, "four-arm molecule denominator")
    require(manifest["manifest_sha256"] == score["manifest_sha256"] == summary["negative_controls"]["manifest_sha256"], "manifest binding")
    for arm in ("A", "B", "C", "D"):
        raw = EXP / "raw" / f"raw-{arm}.jsonl"
        rows = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
        require(len(rows) == 51 and all(row["arm"] == arm for row in rows), f"raw denominator {arm}")
        run = read(EXP / "runs" / f"run-{arm}.json")
        require(run["blind"] and not run["oracle_loaded"] and not run["scorer_loaded"], f"blind flags {arm}")
        require(run["manifest_sha256"] == manifest["manifest_sha256"], f"run manifest {arm}")
        require(score["counts"][arm]["accepted"] == 51, f"score acceptance {arm}")
        require(summary["arms"][arm]["accepted"] == 51, f"summary acceptance {arm}")
    require(len(score["rows"]) == 204 and not score["oracle_loaded_gqc_planner"], "independent score denominator")
    require(all(control["status"] == "reject-and-recompute" for control in negative["controls"]), "negative controls")
    expansion_rows = expansion["rows"]
    require(len(expansion_rows) == 12, "expansion denominator")
    require(sum(row["status"] == "direct-reference" for row in expansion_rows) == 4, "larger-basis direct control")
    require(sum(row["status"] == "reject-and-recompute" for row in expansion_rows) == 8, "DFT/open-shell rejection controls")
    with tempfile.TemporaryDirectory(dir=args.out) as temp:
        temp_path = Path(temp)
        generated_controls = temp_path / "algorithm-controls.json"
        subprocess.check_call([sys.executable, str(SCRIPTS / "run_algorithm_controls_32.py"), "--out", str(generated_controls)], cwd=ROOT, stdout=subprocess.DEVNULL)
        require(generated_controls.read_bytes() == (ROOT / "handoff/gqcdataset_codex_goal/research/audits/algorithm_controls_32.json").read_bytes(), "algorithm control replay")
        generated_planner = temp_path / "planner.json"
        subprocess.check_call([sys.executable, str(SCRIPTS / "target_response_planner.py"), "--manifest", str(EXP / "manifest.json"), "--raw-dir", str(EXP / "raw"), "--out", str(generated_planner)], cwd=ROOT)
        require(generated_planner.read_bytes() == (EXP / "planner.json").read_bytes(), "planner deterministic replay")
        subprocess.check_call([sys.executable, str(SCRIPTS / "verify_target_response_planner.py"), "--planner", str(EXP / "planner.json"), "--out", str(temp_path / "planner-check.json")], cwd=ROOT)
    result = {"status": "passed", "molecules": 17, "raw_rows_per_arm": 51, "scored_rows": 204, "planner_decisions": read(EXP / "planner.json")["request_count"], "planner_candidates": read(EXP / "planner.json")["candidate_count"]}
    (args.out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
