#!/usr/bin/env python3
"""Verify a release against the checkout or an explicitly pinned historical commit."""
import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(args):
    manifest = json.loads((args.release / "release_manifest.json").read_text())
    current = git(args.root, "rev-parse", "HEAD").decode().strip()
    expected = args.archive_at or current
    if not re.fullmatch("[0-9a-f]{40}", expected):
        raise ValueError("expected a full commit SHA")
    errors = []
    if manifest.get("schema") != "vibedataset.research_release.v3":
        errors.append("release schema")
    if manifest.get("git_head") != expected or manifest.get("built_from_git_head") != expected:
        errors.append(f"release commit differs from {expected}")
    if args.expected_head and args.expected_head != expected:
        errors.append("expected commit mismatch")
    if args.archive_at and subprocess.run(["git","merge-base","--is-ancestor",expected,current],
                                         cwd=args.root).returncode:
        errors.append("archive commit unavailable or outside checkout history")
    paths = set()
    for item in manifest["artifacts"]:
        path = item["path"]
        parts = PurePosixPath(path)
        if not path or path != str(parts) or parts.is_absolute() or ".." in parts.parts or path in paths:
            errors.append(f"invalid or duplicate artifact: {path}")
            continue
        paths.add(path)
        committed = git(args.root, "cat-file", "blob", f"{expected}:{path}")
        if sha(committed) != item["sha256"]:
            errors.append(f"Git blob hash: {path}")
        if not args.archive_at and sha((args.root / path).read_bytes()) != item["sha256"]:
            errors.append(f"checkout hash: {path}")
    if not paths:
        errors.append("empty artifact list")
    metadata = manifest.get("metadata_sha256", {})
    for name in ("claims.csv", "release_checklist.md"):
        if metadata.get(name) != sha((args.release / name).read_bytes()):
            errors.append(f"release metadata: {name}")
    with (args.release / "claims.csv").open(newline="") as handle:
        claims = list(csv.DictReader(handle))
    claim_ids = [row["claim_id"] for row in claims]
    if len(set(claim_ids)) != len(claim_ids) or len(claim_ids) < 10:
        errors.append("claim identities")
    return {"status": "failed" if errors else "passed", "artifacts": len(paths),
            "claims": len(claims), "unknowns": len(manifest["unknowns"]),
            "manifest_git_head": manifest.get("git_head"), "current_git_head": current,
            "strict_head": args.archive_at is None, "archive_at": args.archive_at, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--strict-head", action="store_true", help="verify checkout HEAD (default)")
    mode.add_argument("--archive-at", help="verify the historical snapshot at this exact reachable commit")
    parser.add_argument("--expected-head")
    args = parser.parse_args()
    try:
        result = verify(args)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        result = {"status": "failed", "errors": [str(exc)]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
