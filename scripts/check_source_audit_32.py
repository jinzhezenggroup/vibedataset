#!/usr/bin/env python3
"""Verify the fixed-source audit ledger without importing third-party packages."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def git_head(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("handoff/gqcdataset_codex_goal/research/audits/algorithm_audit_32.json"))
    parser.add_argument("--source-lock", type=Path, default=Path("handoff/gqcdataset_codex_goal/research/sources.lock.json"))
    args = parser.parse_args()
    ledger = json.loads(args.ledger.read_text())
    lock = json.loads(args.source_lock.read_text())
    locked = {item["id"]: item for item in lock["repositories"]}
    aliases = {"pymor": "pymor_2026_1", "openmdao": "openmdao_3_45_2", "cppad": "cppad_2026"}
    failures = []
    for source in ledger["sources"]:
        lock_item = locked.get(aliases.get(source["id"], source["id"]))
        if lock_item is None:
            failures.append(f"missing source-lock entry {source['id']}")
            continue
        if lock_item["commit"] != source["commit"] or lock_item["checkout_path"] != source["checkout"]:
            failures.append(f"source lock mismatch {source['id']}")
        checkout = Path(source["checkout"])
        if not checkout.is_dir():
            failures.append(f"missing checkout {checkout}")
        if checkout.is_dir() and git_head(checkout) != source["commit"]:
            failures.append(f"commit mismatch {source['id']}: {git_head(checkout)} != {source['commit']}")
        for license_path in [part.strip() for part in source["license"].split(";")]:
            if not (checkout / license_path).exists():
                failures.append(f"missing license {source['id']}:{license_path}")
    for observation in ledger["observations"]:
        source = next(item for item in ledger["sources"] if item["id"] == observation["source"])
        path = Path(source["checkout"]) / observation["path"]
        if not path.exists():
            failures.append(f"missing audited path {path}")
            continue
        content = path.read_text(errors="replace")
        if observation["symbol"] not in content:
            failures.append(f"missing symbol {observation['id']}:{observation['symbol']}")
        test_path = Path(source["checkout"]) / observation["test"]
        if not test_path.exists():
            failures.append(f"missing test evidence {test_path}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(json.dumps({"sources": len(ledger["sources"]), "observations": len(ledger["observations"]), "status": "passed"}, indent=2))


if __name__ == "__main__":
    main()
