#!/usr/bin/env python3
"""Build the machine-readable bounded-evidence release package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path


RELEASE_ARTIFACTS = [
    "README.md",
    "scripts/run_gpu4pyscf_4arm_telemetry.py",
    "scripts/check_gpu4pyscf_4arm_telemetry.py",
    "scripts/summarize_gpu4pyscf_4arm_telemetry.py",
    "scripts/prepared_property_batch.py",
    "scripts/run_prepared_gpu4pyscf_async.py",
    "scripts/run_prepared_gpu4pyscf_processes.py",
    "scripts/check_prepared_gpu4pyscf_runtime.py",
    "scripts/probe_gpu4pyscf_process_concurrency.py",
    "handoff/gqcdataset_codex_goal/research/experiments/attribution_4arm/manifest.json",
    "handoff/gqcdataset_codex_goal/research/experiments/attribution_4arm/score.json",
    "handoff/gqcdataset_codex_goal/research/experiments/attribution_4arm/summary.json",
    "handoff/gqcdataset_codex_goal/research/performance/benchmark_contract.json",
    "handoff/gqcdataset_codex_goal/research/performance/qm9-scale-manifest.json.gz",
    "handoff/gqcdataset_codex_goal/research/performance/attribution_profile.json",
    "handoff/gqcdataset_codex_goal/research/performance/profiling.md",
    "handoff/gqcdataset_codex_goal/research/performance/scale_ablation.md",
    "handoff/gqcdataset_codex_goal/research/performance/scale_ablation_plan.json",
    "handoff/gqcdataset_codex_goal/research/audits/SOURCE_AUDIT_32.md",
    "handoff/gqcdataset_codex_goal/research/audits/ALGORITHM_MATRIX.md",
    "handoff/gqcdataset_codex_goal/research/experiments/prepared_property_batch/README.md",
    "handoff/gqcdataset_codex_goal/research/experiments/prepared_property_batch/gpu-control.json",
    "handoff/gqcdataset_codex_goal/research/experiments/prepared_property_batch/gpu-control-verification.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/run-prepared-runtime.slurm",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/run-process-probe.slurm",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/run-process-runtime.slurm",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/serial.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/process-runtime.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/process-probe.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/check.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/async-probe-receipt.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/runtime-summary.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/slurm-5584.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/slurm-5584.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/slurm-5588.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/slurm-5588.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/slurm-5594.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/slurm-5594.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/slurm-5600.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/prepared-runtime/slurm-5600.err",
    "handoff/gqcdataset_codex_goal/research/experiments/response_asset_compiler/plan.json",
    "handoff/gqcdataset_codex_goal/research/experiments/response_asset_compiler/gpu-assets.json",
    "handoff/gqcdataset_codex_goal/research/experiments/response_asset_compiler/gpu-assets-verification.json",
    "handoff/gqcdataset_codex_goal/research/experiments/response_asset_compiler/gpu-assets-negative-controls.json",
    "handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/results.json",
    "handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/cpu-rks.json",
    "handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/gpu-results.json",
    "handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/gpu-spectroscopy.json",
    "handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/finite-difference.json",
    "handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/cpu-gpu-crosscheck.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/release-tags.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/baseline.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/result.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/slurm-5530.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/slurm-5530.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-build-attempt.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/slurm-5550.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/slurm-5550.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/v1.9.2-wheel-test-receipt.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/run-tests.slurm",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/run-benchmark-properties.slurm",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/run-runtime-identity.slurm",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5552.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5552.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5553.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5553.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5554.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5554.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5555.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5555.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5556.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5556.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5557.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5557.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5558.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5558.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5560.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5560.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5561.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/slurm-5561.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/run-arm-telemetry.slurm",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/run-independent-scorer.slurm",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/check.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/summary.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/raw/A/run.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/raw/A/raw.jsonl",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/raw/B/run.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/raw/B/raw.jsonl",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/raw/C/run.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/raw/C/raw.jsonl",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/raw/D/run.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/raw/D/raw.jsonl",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/independent-score/score.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/independent-score/slurm-5571.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/independent-score/slurm-5571.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5564.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5564.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5565.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5565.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5567.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5567.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5568.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5568.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5569.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5569.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5570.out",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/a-d-telemetry/slurm-5570.err",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/phase-profile-control/README.md",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/phase-profile-control/profile-A.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/phase-profile-control/profile-C.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/phase-profile-control/receipt.json",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/upstream-polarizability-pytest.log",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/upstream-ir-raman-pytest.log",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/upstream-cphf-pytest.log",
    "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/upstream-benchmark-properties-pytest8.log",
]


CLAIMS = [
    {
        "claim_id": "34",
        "claim": "10x end-to-end GQC over official GPU4PySCF",
        "status": "falsified-partial",
        "evidence": "performance/attribution_profile.json",
        "condition": "17 RHF/STO-3G geometries and 51 requests",
        "unknown": "larger protocol-consistent workload and second GPU",
    },
    {
        "claim_id": "31",
        "claim": "request-level GQC asset planning reduces operator work",
        "status": "supported-in-domain",
        "evidence": "experiments/attribution_4arm/score.json",
        "condition": "204/204 independent rows accepted",
        "unknown": "",
    },
    {
        "claim_id": "32",
        "claim": "fixed-source behavior boundary",
        "status": "supported",
        "evidence": "audits/SOURCE_AUDIT_32.md",
        "condition": "10 sources and 37 observations",
        "unknown": "",
    },
    {
        "claim_id": "33",
        "claim": "cost-coverage-risk planner replay",
        "status": "supported-as-planner",
        "evidence": "experiments/attribution_4arm/planner.json",
        "condition": "564 decisions, no oracle",
        "unknown": "",
    },
    {
        "claim_id": "35",
        "claim": "frozen end-to-end benchmark contract",
        "status": "supported-with-scale-blocker",
        "evidence": "performance/benchmark_contract.json",
        "condition": "306 controlled requests, natural flow 0",
        "unknown": "",
    },
    {
        "claim_id": "36",
        "claim": "GPU4PySCF/PySCF source audit and selected upstream execution",
        "status": "partial-official-v192-wheel-subset",
        "evidence": "audits/gpu4pyscf.md;environment/gpu4pyscf-20261122/release-tags.json;environment/gpu4pyscf-20261122/v1.9.2-wheel-tests/v1.9.2-wheel-test-receipt.json",
        "condition": "official v1.9.2 wheel selected tests passed: 19 response-property tests passed, 3 skipped, and 8 benchmark-property tests passed",
        "unknown": "complete v1.9.2 suite, executable v1.9.0 runtime, full benchmark and paper-version mapping",
    },
    {
        "claim_id": "37",
        "claim": "A-D request-level phase profiling baseline",
        "status": "partial-small-queue-with-independent-score",
        "evidence": "performance/profiling.md;environment/gpu4pyscf-20261122/a-d-telemetry/summary.json;environment/gpu4pyscf-20261122/a-d-telemetry/check.json",
        "condition": "official v1.9.2 wheel, one RTX PRO 6000, 4 arms x 51 requests, 14-field schema, 204/204 target-density-residual scorer acceptance",
        "unknown": "compile/JIT, producer scorer cost, kernel metrics, CUPTI/Nsight, energy, second GPU and larger queue",
    },
    {
        "claim_id": "38",
        "claim": "cross-sample resident and process-isolated runtime",
        "status": "partial-process-runtime-stream-falsified",
        "evidence": "experiments/prepared_property_batch/gpu-control-verification.json;environment/gpu4pyscf-20261122/prepared-runtime/runtime-summary.json",
        "condition": "3 same-shape molecules, 9 requests, one bucket; process-isolated runtime 9/9 with max target difference 5.78e-12 and same-context streams rejected by cudaErrorIllegalAddress",
        "unknown": "same-context stream safety, ragged/fused kernels, cross-molecule operator reuse, independent scorer and end-to-end speedup",
    },
    {
        "claim_id": "39",
        "claim": "response asset compiler and certificate dispositions",
        "status": "bounded-GPU-assets",
        "evidence": "experiments/response_asset_compiler/gpu-assets-verification.json;experiments/response_asset_compiler/gpu-assets-negative-controls.json",
        "condition": "51 same-protocol direct assets and three reject controls; cross-protocol refine/reject frontier remains",
        "unknown": "",
    },
    {
        "claim_id": "40",
        "claim": "Hessian/CPKS main load",
        "status": "CPU-GPU-DFT-micro-control",
        "evidence": "experiments/hessian_cphf/cpu-gpu-crosscheck.json",
        "condition": "RHF/DFT/FD micro controls; VeloxChem/multi-sample shared runtime unavailable",
        "unknown": "",
    },
    {
        "claim_id": "41",
        "claim": "scale, ablation and amortization",
        "status": "partial-falsified-with-bounded-controls",
        "evidence": "performance/scale_ablation_plan.json",
        "condition": "17 measured, 1000 target blocked; shape/residency bounded control only",
        "unknown": "",
    },
    {
        "claim_id": "42",
        "claim": "reproducible release and claim gate",
        "status": "partial",
        "evidence": "release/release_manifest.json",
        "condition": "unknown costs and unavailable upstream assets listed",
        "unknown": "",
    },
]


UNKNOWNs = [
    "complete upstream GPU4PySCF v1.9.2 source test and benchmark suite",
    "executable GPU4PySCF v1.9.0 runtime and selected tests",
    "paper-version mapping for v1.9.0/v1.9.2",
    "CUPTI/Nsight traces",
    "energy and peak-memory telemetry",
    "1000-row protocol-consistent request asset",
    "A100/H100 comparison",
    "VeloxChem cross-check",
    "same-context GPU4PySCF stream safety",
    "ragged/fused PreparedPropertyBatch kernels",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def build(root: Path, out: Path, audited_head: str | None) -> None:
    checkout_head = current_head(root)
    source_head = audited_head or checkout_head
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "vibedataset.research_release.v2",
        "git_head": source_head,
        "git_head_kind": "audited_source_commit",
        "built_from_git_head": checkout_head,
        "artifacts": [{"path": path, "sha256": sha(root / path)} for path in RELEASE_ARTIFACTS],
        "commands": [
            "python3 scripts/check_source_audit_32.py",
            "python3 scripts/check_attribution_ci.py --out .work/attribution-ci",
            "python3 scripts/check_response_ci.py archive --out .work/response-archive",
            "python3 scripts/check_benchmark_contract.py --contract handoff/gqcdataset_codex_goal/research/performance/benchmark_contract.json --manifest handoff/gqcdataset_codex_goal/research/experiments/attribution_4arm/manifest.json --out .work/benchmark-contract",
        ],
        "unknowns": UNKNOWNs,
    }
    (out / "release_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (out / "claims.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["claim_id", "claim", "status", "evidence", "condition", "unknown"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(CLAIMS)
    (out / "release_checklist.md").write_text(
        "# 可复现发布包与 claim gate（Issue #42）\n\n"
        "机器可读发布清单是 `release_manifest.json`，主张表是 `claims.csv`。"
        "`git_head` 指向被审计的 source commit，`built_from_git_head` 记录生成该快照时的 checkout。"
        "CI 还会在当前 checkout 临时重建 release manifest，并用 strict-head 检查当前 HEAD 与新 manifest 一致。"
        "每条主张绑定固定 artifact SHA、条件和未知成本。官方 GPU4PySCF 1.9.2 wheel 的选定上游测试已通过，"
        "但完整上游 suite、1.9.0 可执行环境和论文版本映射仍保持 unknown。10× 仍写成 `falsified-partial`，"
        "没有把未知 telemetry 填成零。\n\n"
        "发布前必须补齐清单中的 unknowns，或按 claims.csv 的 partial/falsified 状态发布。\n"
    )
    print(json.dumps({"status": "built", "artifacts": len(RELEASE_ARTIFACTS), "claims": len(CLAIMS)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--git-head", default=None, help="audited source commit, defaults to current checkout HEAD")
    args = parser.parse_args()
    build(args.root, args.out, args.git_head)


if __name__ == "__main__":
    main()
