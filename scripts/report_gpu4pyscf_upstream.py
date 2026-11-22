#!/usr/bin/env python3
"""Report all pinned test files, scheduler attempts, per-case results and unknowns."""

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observed(path):
    return sha(path) if path.is_file() else None


def junit(path):
    if not path.is_file():
        return None
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    counts = Counter()
    failures = []
    for case in root.iter("testcase"):
        child = next(
            (x for x in case if x.tag in {"failure", "error", "skipped"}), None
        )
        state = child.tag if child is not None else "passed"
        counts[state] += 1
        if state in ("failure", "error"):
            failures.append([case.get("classname"), case.get("name"), state])
    return {"testcase_counts": dict(counts), "failures": failures}


def attempt(job, code, log, xml):
    return {
        "job": job,
        "exit": code,
        "log_sha256": observed(log),
        "xml_sha256": observed(xml),
        "junit": junit(xml),
    }


def summarize(root, inputs):
    attempts = defaultdict(list)
    dispatch = defaultdict(list)
    for folder in root.glob("suite-*"):
        if not re.fullmatch("suite-[0-9]+", folder.name):
            continue
        job = int(folder.name.split("-")[1])
        sent = folder / "dispatched.txt"
        if sent.is_file():
            for path in sent.read_text().splitlines():
                dispatch[path].append(job)
        exits = folder / "exits.txt"
        if exits.is_file():
            for line in exits.read_text().splitlines():
                code, path = line.split(maxsplit=1)
                stem = folder / path.replace("/", "_")
                attempts[path].append(
                    attempt(
                        job,
                        int(code),
                        Path(str(stem) + ".log"),
                        Path(str(stem) + ".xml"),
                    )
                )
    for folder in root.glob("retry-*"):
        if not re.fullmatch("retry-[0-9]+", folder.name):
            continue
        args = (folder / "argv.txt").read_text().splitlines()
        path = next(k for k in args if k.startswith("gpu4pyscf/") and k.endswith(".py"))
        job = int(folder.name.split("-")[1])
        dispatch[path].append(job)
        if (folder / "exit.txt").is_file():
            attempts[path].append(
                attempt(
                    job,
                    int((folder / "exit.txt").read_text()),
                    folder / "pytest.log",
                    folder / "junit.xml",
                )
            )
    if (set(dispatch) | set(attempts)) - set(inputs):
        raise ValueError("scheduler output contains an unplanned test file")
    files = {}
    for path, checksum in sorted(inputs.items()):
        trials = sorted(attempts[path], key=lambda a: a["job"])
        if not trials:
            state = (
                "dispatched-no-terminal-receipt"
                if dispatch[path]
                else "not-yet-dispatched"
            )
        else:
            last = trials[-1]
            counts = (last["junit"] or {}).get("testcase_counts", {})
            if (
                last["exit"] == 0
                and last["log_sha256"]
                and last["junit"] is not None
                and not (counts.get("failure") or counts.get("error"))
            ):
                state = "completed"
            elif last["exit"] == 5 and last["junit"] is not None and not counts:
                state = "no-test-items"
            elif last["exit"] in (124, 137):
                state = "timeout-or-kill"
            else:
                state = "failed-or-incomplete-output"
        files[path] = dict(
            source_sha256=checksum,
            status=state,
            dispatched=sorted(dispatch[path]),
            attempts=trials,
        )
    states = Counter(row["status"] for row in files.values())
    outcomes = Counter()
    for v in files.values():
        if v["attempts"] and v["attempts"][-1]["junit"]:
            outcomes.update(v["attempts"][-1]["junit"]["testcase_counts"])
    return {
        "schema": "vibedataset.upstream_gpu4pyscf_files.v1",
        "source_files": len(inputs),
        "files": files,
        "file_states": dict(states),
        "latest_observed_case_counts": dict(outcomes),
        "attempts_with_exit": sum(len(v["attempts"]) for v in files.values()),
        "scope": "tag gpu4pyscf/test_*.py (including nested directories); benchmark harness timing disabled in these file jobs",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    report = summarize(a.root, json.loads(gzip.decompress(a.inputs.read_bytes())))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(
        gzip.compress(
            json.dumps(
                report, allow_nan=False, sort_keys=True, separators=(",", ":")
            ).encode(),
            mtime=0,
        )
    )
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "source_files",
                    "file_states",
                    "latest_observed_case_counts",
                    "attempts_with_exit",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
