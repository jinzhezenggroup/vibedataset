#!/usr/bin/env python3
"""Build the machine-readable bounded-evidence release package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import gzip
import io
import tarfile
import tempfile
import subprocess
from pathlib import Path


RELEASE_ARTIFACTS = [
    "README.md",
    "scripts/run_gpu4pyscf_4arm_telemetry.py",
    "scripts/check_gpu4pyscf_4arm_telemetry.py",
    "scripts/score_ao_density_response.py",
    "scripts/cphf_reference.py",
    "scripts/verify_gpu_response_assets.py",
    "scripts/verify_gpu_response_asset_negative_controls.py",
    "handoff/gqcdataset_codex_goal/research/experiments/response_asset_compiler/scorer-v192-ao.json.gz",
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


HESSIAN_CROSS_ENGINE = "handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/cross-engine"
RELEASE_ARTIFACTS.extend([
    "scripts/run_cross_engine_hessians.py",
    "scripts/refine_raman_modes.py",
    "scripts/verify_cross_engine_hessians.py",
])
RELEASE_ARTIFACTS.extend(f"{HESSIAN_CROSS_ENGINE}/{name}" for name in (
    "protocol.json", "raman-refinement.json", "gpu.slurm", "refine.slurm", "README.md", "verification.json",
    "veloxchem/events.jsonl", "veloxchem/run.json", "veloxchem/console.log.gz", "veloxchem/MATCHED-STO-3G",
    "veloxchem/pixi.toml", "veloxchem/pixi.lock", "veloxchem/source-lock.json", "veloxchem/source-coverage.csv.gz",
    "gpu4pyscf/events.jsonl", "gpu4pyscf/run.json", "gpu4pyscf/console.log.gz",
    "raman-refinement/displacements.jsonl", "raman-refinement/run.json", "raman-refinement/console.log.gz",
))


NSIGHT = "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122/nsight-control"
RELEASE_ARTIFACTS.extend(["scripts/trace_gpu4pyscf_requests.py", "scripts/summarize_request_traces.py",
                         "scripts/run_gpu4pyscf_4arm.py", "scripts/score_gpu4pyscf_4arm.py"])
RELEASE_ARTIFACTS.extend(f"{NSIGHT}/{name}" for name in (
    "README.md", "manifest.json", "receipt.json", "summary.json", "trace.slurm", "score.slurm", "counters.slurm",
    "ncu.log", "scientific/score-cold.json.gz", "scientific/score-warm.json.gz"))
for arm in "ABCD":
    for state in ("cold", "warm"):
        RELEASE_ARTIFACTS.extend([f"{NSIGHT}/{arm}-{state}.json.gz", f"{NSIGHT}/scientific/{arm}-{state}.jsonl.gz"])


EVIDENCE_V192 = "handoff/gqcdataset_codex_goal/research/environment/gpu4pyscf-20261122"
RELEASE_ARTIFACTS.extend([
    "handoff/gqcdataset_codex_goal/research/sources.lock.json",
    "handoff/gqcdataset_codex_goal/research/audits/gpu4pyscf_source_coverage.csv",
    "handoff/gqcdataset_codex_goal/research/audits/gpu4pyscf.md",
    "scripts/check_gpu4pyscf_audit.py", "scripts/report_gpu4pyscf_upstream.py",
    "scripts/compare_matched_single_gpus.py",
])
for folder, names in (
    ("upstream-v192", ("campaign.json", "file-checkpoint.json.gz", "fresh-source-check.json",
                       "identity.json", "paper-sources.json", "test-inputs.json.gz", "pytest.log.gz",
                       "upstream.slurm", "upstream-suite.slurm.gz", "collect-benchmark.slurm.gz", "finalize.slurm")),
    ("v190-selected", ("wheel.json", "selected.slurm", "identity.json", "receipt.json", "test-sha256.txt",
                       "pytest.log.gz", "junit.xml.gz")),
    ("single-gpu-pairs", ("paired.slurm", "summary.json", "README.md", "rtx5090/submitted.slurm")),
):
    RELEASE_ARTIFACTS.extend(f"{EVIDENCE_V192}/{folder}/{name}" for name in names)
for gpu in ("rtx5090", "pro6000"):
    folder = f"{EVIDENCE_V192}/single-gpu-pairs/{gpu}"
    RELEASE_ARTIFACTS.extend(f"{folder}/{name}" for name in ("identity.json", "attempts.txt",
                             "score.json.gz", "cpu-ao-score.json.gz"))
    for arm in "ABCD":
        RELEASE_ARTIFACTS.extend([f"{folder}/run-{arm}.json", f"{folder}/raw-{arm}.jsonl.gz"])


FRONTIER = "handoff/gqcdataset_codex_goal/research/experiments/response_asset_compiler/frontier"
RELEASE_ARTIFACTS.extend(["handoff/gqcdataset_codex_goal/research/decisions/0007-bounded-gpu-response-refinement.md", "scripts/compile_response_assets.py", "scripts/run_response_frontier.py",
                          "scripts/score_response_frontier.py", "scripts/summarize_response_frontier.py"])
RELEASE_ARTIFACTS.extend(f"{FRONTIER}/{name}" for name in ("protocol.json", "summary.json", "frontier.slurm",
    "pilot/input-sha256", "pilot/project-commit", "pilot/finished", "counterbalanced/input-sha256",
    "counterbalanced/project-commit", "counterbalanced/finished", "counterbalanced/process-wall-ns.txt"))
frontier_cases = [f"qm9-{index:06d}-{kind}" for index in range(1, 4)
                  for kind in ("exact", "split-valence", "hybrid-functional")]
frontier_cases.extend(f"water-{kind}" for kind in ("displaced", "stale-bytes", "field-swapped",
                                                  "frozen-density", "different-origin", "open-shell"))
for attempt in ("pilot", "counterbalanced/rep-1", "counterbalanced/rep-2"):
    RELEASE_ARTIFACTS.append(f"{FRONTIER}/{attempt}/independent.json")
    for mode in ("cold", "planned"):
        folder = f"{FRONTIER}/{attempt}/{mode}"
        RELEASE_ARTIFACTS.extend([f"{folder}/run.json", f"{folder}/attempts.jsonl"])
        RELEASE_ARTIFACTS.extend(f"{folder}/{case}.json.gz" for case in frontier_cases)


SHARED_SPECTRA = "handoff/gqcdataset_codex_goal/research/experiments/hessian_cphf/shared-spectroscopy"
RELEASE_ARTIFACTS.extend(["scripts/run_shared_spectroscopy.py", "scripts/score_shared_spectroscopy.py", "scripts/score_cartesian_cphf.py"])
RELEASE_ARTIFACTS.extend(f"{SHARED_SPECTRA}/{p}" for p in ("cartesian.slurm",
    "cartesian-certificate/result.json","cartesian-certificate/attempts.jsonl","cartesian-certificate/independent.json",
    "cartesian-certificate/cartesian/01-h2o-hessian.npz","cartesian-certificate/cartesian/02-nh3-hessian.npz",
    "cartesian-certificate/cartesian/03-lih-hessian.npz"))
RELEASE_ARTIFACTS.extend(f"{SHARED_SPECTRA}/{p}" for p in ("README.md", "protocol.json", "shared.slurm",
    "refine.slurm","serial-refine.slurm","console-sha256.json","input-sha256","project-commit","finished","process-wall.txt",
    "default-verification.json","verification.json","veloxchem/events.jsonl","veloxchem/run.json",
    "veloxchem/MATCHED-STO-3G","veloxchem/console.log.gz"))
for mode in ("serial","shared","failures"):
    for name in ("result.json","attempts.jsonl","console.log.gz"):
        RELEASE_ARTIFACTS.append(f"{SHARED_SPECTRA}/{mode}/{name}")
for mode, cases in (("shared",("h2o","nh3","lih")),("serial",("07-h2o-raman","08-nh3-raman","09-lih-raman","12-lih-raman"))):
    for case in cases:
        plan_prefix="refine" if mode=="shared" else "serial-refine"
        RELEASE_ARTIFACTS.append(f"{SHARED_SPECTRA}/{plan_prefix}-{case}.json")
        for name in ("run.json","displacements.jsonl","console.log.gz"):
            RELEASE_ARTIFACTS.append(f"{SHARED_SPECTRA}/{mode}-refinement/{case}/{name}")


CLAIMS = [
    {
        "claim_id": "34",
        "claim": "10x end-to-end GQC over official GPU4PySCF",
        "status": "falsified-partial",
        "evidence": "performance/attribution_profile.json",
        "condition": "17 RHF/STO-3G geometries and 51 requests",
        "unknown": "larger protocol-consistent workload, full publication cost and factorial ablations",
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
        "status": "matched-official-v190-and-v192-selected-tests",
        "evidence": "audits/gpu4pyscf.md;environment/gpu4pyscf-20261122/release-tags.json;environment/gpu4pyscf-20261122/v190-selected/receipt.json;environment/gpu4pyscf-20261122/upstream-v192/campaign.json",
        "condition": "on each v1.9.0/v1.9.2 wheel: 19 selected response-property tests passed, 3 skipped; v1.9.2 full source collection identified 2649 cases",
        "unknown": "complete v1.9.2 suite outcomes, standalone benchmark families and exact historical compiler flags",
    },
    {
        "claim_id": "37",
        "claim": "A-D request-level phase profiling baseline",
        "status": "bounded-four-arm-CUPTI-with-separate-physical-score",
        "evidence": "performance/profiling.md;environment/gpu4pyscf-20261122/a-d-telemetry/summary.json;environment/gpu4pyscf-20261122/nsight-control/receipt.json",
        "condition": "official v1.9.2 wheel, one RTX PRO 6000, 4 arms x 51 requests, 14-field schema, 204/204 target-density-residual scorer acceptance",
        "unknown": "full-queue hardware counters and separated JIT/IO costs",
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
        "status": "bounded-GPU-assets-with-executed-refinement",
        "evidence": "experiments/response_asset_compiler/gpu-assets-verification.json;experiments/response_asset_compiler/gpu-assets-negative-controls.json;experiments/response_asset_compiler/frontier/summary.json",
        "condition": "51 sealed same-protocol archived assets, 14 integrity controls, independent candidate AO residuals for 204 matched v1.9.2 rows with 6 physical controls; bounded cross-basis and RHF-to-B3LYP refinements, actual cold fallbacks and independently certified AO responses",
        "unknown": "",
    },
    {
        "claim_id": "40",
        "claim": "Hessian/CPKS main load",
        "status": "three-molecule-multi-request-shared-RHF-spectra-with-refinement",
        "evidence": "experiments/hessian_cphf/shared-spectroscopy/verification.json;experiments/hessian_cphf/cross-engine/verification.json;experiments/hessian_cphf/cpu-gpu-crosscheck.json",
        "condition": "3 direct RHF/STO-3G Hessians, multi-sample 12-request IR/Raman queue, independent VeloxChem, 40 shared or 44 serial displaced SCFs for four initially rejected readouts",
        "unknown": "",
    },
    {
        "claim_id": "41",
        "claim": "scale, ablation and amortization",
        "status": "partial-falsified-with-bounded-controls",
        "evidence": "performance/scale_ablation_plan.json;environment/gpu4pyscf-20261122/single-gpu-pairs/summary.json",
        "condition": "17 geometries and 51 requests per arm per device; 408 official and 408 independent CPU AO scores; full label publication and ablations outstanding",
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
    "historical wheel build flags and exact binary identities for early GPU4PySCF papers",
    "queue-wide Nsight traces and permission for achieved occupancy/FLOP counters",
    "dataset-scale energy and device memory profile",
    "1000-row protocol-consistent request asset",
    "A100/H100 comparison",
    "VeloxChem GPU performance and broader methods/devices in shared spectroscopy",
    "same-context GPU4PySCF stream safety",
    "ragged/fused PreparedPropertyBatch kernels",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def build(root: Path, out: Path, audited_head: str | None) -> None:
    checkout_head = current_head(root)
    if audited_head is not None and audited_head != checkout_head:
        raise ValueError("--git-head must match the checkout being packaged")
    out.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for path in RELEASE_ARTIFACTS:
        committed = subprocess.check_output(["git", "cat-file", "blob", f"{checkout_head}:{path}"], cwd=root)
        checksum = hashlib.sha256(committed).hexdigest()
        if sha(root / path) != checksum:
            raise ValueError(f"release input differs from {checkout_head}: {path}")
        artifacts.append({"path": path, "sha256": checksum})
    manifest = {
        "schema": "vibedataset.research_release.v3",
        "git_head": checkout_head,
        "git_head_kind": "payload_checkout",
        "built_from_git_head": checkout_head,
        "audited_baseline_git_head": "92d9bac6384208881827313709fc0a03f60b0bad",
        "artifacts": artifacts,
        "commands": [
            "python3 scripts/check_source_audit_32.py",
            "python3 scripts/check_attribution_ci.py --out .work/attribution-ci",
            "python3 scripts/check_response_ci.py archive --out .work/response-archive",
            "python3 scripts/check_benchmark_contract.py --contract handoff/gqcdataset_codex_goal/research/performance/benchmark_contract.json --manifest handoff/gqcdataset_codex_goal/research/experiments/attribution_4arm/manifest.json --out .work/benchmark-contract",
        ],
        "unknowns": UNKNOWNs,
    }
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
        "CI 的 attribution artifact 提供当前提交的 release_manifest.json、claims.csv 和对应原始文件。"
        "git_head 绑定打包时的 Git 提交，audited_baseline_git_head 记录最初受控实验的提交。"
        "验证器逐文件核对 Git blob 和 SHA-256。仓库内历史快照按清单记录的提交重放。\n"
    )
    manifest["metadata_sha256"] = {name: sha(out / name) for name in ("claims.csv", "release_checklist.md")}
    (out / "release_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": "built", "artifacts": len(RELEASE_ARTIFACTS), "claims": len(CLAIMS)}, indent=2))


def pack(root: Path, out: Path) -> None:
    # Use the already checked snapshot and fixed tar/gzip metadata for byte-for-byte replay.
    manifest = json.loads((out / "release_manifest.json").read_text())
    with tempfile.TemporaryDirectory(dir=out) as staging:
        bundle = Path(staging) / "research-release.tar.gz"
        with bundle.open("wb") as handle, gzip.GzipFile(
            filename="", mode="wb", fileobj=handle, mtime=0
        ) as compressed, tarfile.open(fileobj=compressed, mode="w|", format=tarfile.GNU_FORMAT) as archive:
            for name in ("release_manifest.json", *manifest["metadata_sha256"]):
                data = (out / name).read_bytes()
                if name in manifest["metadata_sha256"] and hashlib.sha256(data).hexdigest() != manifest["metadata_sha256"][name]:
                    raise ValueError(f"release metadata changed during packaging: {name}")
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            for item in manifest["artifacts"]:
                path = item["path"]
                data = subprocess.check_output(["git", "cat-file", "blob", f"{manifest['git_head']}:{path}"], cwd=root)
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ValueError(f"archived bytes differ from manifest: {path}")
                info = tarfile.TarInfo(path)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        bundle.replace(out / bundle.name)



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--git-head", default=None, help="assert the expected checkout HEAD")
    parser.add_argument("--bundle", action="store_true", help="also write the complete compressed release")
    args = parser.parse_args()
    build(args.root, args.out, args.git_head)
    if args.bundle:
        pack(args.root, args.out)


if __name__ == "__main__":
    main()
