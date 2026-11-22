#!/usr/bin/env python3
"""Verify release artifacts and their source provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def valid_commit(root: Path, commit: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def ancestor(root: Path, source: str, target: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", source, target],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--strict-head", action="store_true", help="require manifest git_head to equal the current checkout HEAD")
    parser.add_argument("--expected-head", help="require manifest git_head to equal this commit")
    parser.add_argument("--allow-missing-commits", action="store_true", help="record pinned commit objects unavailable in a shallow checkout")
    args = parser.parse_args()

    manifest = json.loads((args.release / "release_manifest.json").read_text())
    current = git_head(args.root)
    errors: list[str] = []
    provenance_unknowns: list[str] = []
    source = manifest.get("git_head")
    source_object_available = isinstance(source, str) and valid_commit(args.root, source)
    source_sha_shape = isinstance(source, str) and bool(re.fullmatch(r"[0-9a-f]{40}", source))
    if not source_object_available:
        if args.allow_missing_commits and source_sha_shape and not args.strict_head:
            provenance_unknowns.append("git_head_commit_object_unavailable")
        else:
            errors.append("invalid git_head")
    elif args.strict_head and source != current:
        errors.append(f"strict git_head mismatch: {source} != {current}")
    elif not args.strict_head and not ancestor(args.root, source, current):
        errors.append(f"git_head is not an ancestor of current HEAD: {source} !<= {current}")
    if args.expected_head and source != args.expected_head:
        errors.append(f"expected git_head mismatch: {source} != {args.expected_head}")
    built_from = manifest.get("built_from_git_head")
    if built_from is not None:
        built_object_available = isinstance(built_from, str) and valid_commit(args.root, built_from)
        built_sha_shape = isinstance(built_from, str) and bool(re.fullmatch(r"[0-9a-f]{40}", built_from))
        if not built_object_available:
            if args.allow_missing_commits and built_sha_shape and not args.strict_head:
                provenance_unknowns.append("built_from_git_head_commit_object_unavailable")
            else:
                errors.append("invalid built_from_git_head")
        elif args.strict_head and built_from != current:
            errors.append(f"strict built_from_git_head mismatch: {built_from} != {current}")
        elif not args.strict_head and not ancestor(args.root, built_from, current):
            errors.append(f"built_from_git_head is not an ancestor of current HEAD: {built_from} !<= {current}")
    for artifact in manifest.get("artifacts", []):
        path = args.root / artifact["path"]
        observed = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if observed != artifact.get("sha256"):
            errors.append(artifact["path"])
    claims = (args.release / "claims.csv").read_text().splitlines()
    if len(claims) < 10:
        errors.append("claims")
    out = {
        "status": "passed" if not errors else "failed",
        "artifacts": len(manifest.get("artifacts", [])),
        "claims": len(claims) - 1,
        "unknowns": len(manifest.get("unknowns", [])),
        "manifest_git_head": source,
        "current_git_head": current,
        "strict_head": args.strict_head,
        "allow_missing_commits": args.allow_missing_commits,
        "provenance_unknowns": provenance_unknowns,
        "errors": errors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    if errors:
        raise SystemExit("; ".join(errors))


if __name__ == "__main__":
    main()
