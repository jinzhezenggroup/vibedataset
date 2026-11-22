#!/usr/bin/env python3
"""Acquire missing pinned checkouts on request and verify their complete source trees."""

import argparse
import csv
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "handoff/gqcdataset_codex_goal/research"
ENVIRONMENT = RESEARCH / "environment/gpu4pyscf-20261122"
EXPECTED = {
    "gpu4pyscf": "5a717f899cb40d64a5799ef1df7e3626c505c3bd",
    "pyscf_2_14": "c63a953ba603a5ad8c1d65d88da72aaf05ede4d8",
}
TAGS = {
    "v1.9.0": "2fdc1951670a8e173dce063e697727bbc9f97616",
    "v1.9.2": "8536a80c1e03260aab030e108ef1d181a3709057",
}


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args])


def fetch(path, url, commit):
    # Build the checkout off to the side so an interrupted fetch is retryable.
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".audit-") as tmp:
        work = Path(tmp) / "checkout"
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        git(work, "remote", "add", "origin", url)
        try:
            git(work, "fetch", "--no-tags", "--depth=1", "origin", commit)
        except subprocess.CalledProcessError:
            git(
                work,
                "-c",
                "http.version=HTTP/1.1",
                "fetch",
                "--no-tags",
                "--depth=1",
                "origin",
                commit,
            )
        git(work, "-c", "core.autocrlf=false", "checkout", "-q", "--detach", commit)
        try:
            work.rename(path)
        except OSError:
            if not path.is_dir():
                raise
            # A concurrent acquisition is verified by the caller.


def tree_check(path, objects, sha, tree, acquire, url):
    if not path.exists() and acquire:
        fetch(path, url, sha)
    if not path.is_dir():
        raise ValueError(
            f"missing {path}; use --acquire to fetch the pinned upstream revisions"
        )
    is_checkout = (path / ".git").exists()
    if is_checkout:
        objects = path
        if git(path, "rev-parse", "HEAD").decode().strip() != sha:
            raise ValueError(f"{path}: wrong HEAD")
    elif not (objects / ".git").exists():
        raise ValueError(
            f"{path}: an exported tree needs its pinned Git objects in {objects}"
        )
    if (
        acquire
        and subprocess.run(
            ["git", "-C", str(objects), "cat-file", "-e", f"{sha}^{{commit}}"],
            stderr=subprocess.DEVNULL,
        ).returncode
    ):
        git(
            objects,
            "fetch",
            "--no-tags",
            "--no-write-fetch-head",
            "--depth=1",
            url,
            sha,
        )
    if git(objects, "rev-parse", f"{sha}^{{tree}}").decode().strip() != tree:
        raise ValueError(f"{path}: pinned tree mismatch")
    records = git(objects, "ls-tree", "-rz", sha).rstrip(b"\0").split(b"\0")
    file_digests = {}
    for entry in records:
        meta, encoded = entry.split(b"\t", 1)
        mode, kind, blob = meta.split()
        name = os.fsdecode(encoded)
        file = path / name
        if kind != b"blob":
            raise ValueError(f"{path}/{name}: unresolved submodule")
        info = file.lstat()
        if mode == b"120000" and stat.S_ISLNK(info.st_mode):
            data = os.fsencode(os.readlink(file))
        elif mode in (b"100644", b"100755") and stat.S_ISREG(info.st_mode):
            data = file.read_bytes()
            if bool(info.st_mode & stat.S_IXUSR) != (mode == b"100755"):
                raise ValueError(f"{path}/{name}: executable mode mismatch")
        else:
            raise ValueError(f"{path}/{name}: file type mismatch")
        actual = hashlib.sha1(
            b"blob " + str(len(data)).encode() + b"\0" + data
        ).hexdigest()
        if actual != blob.decode() or data.startswith(
            b"version https://git-lfs.github.com/spec/v1\n"
        ):
            raise ValueError(f"{path}/{name}: modified blob or unhydrated LFS object")
        file_digests[name] = actual
    return file_digests


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--coverage",
        type=Path,
        default=RESEARCH / "audits/gpu4pyscf_source_coverage.csv",
    )
    p.add_argument("--sources-lock", type=Path, default=RESEARCH / "sources.lock.json")
    p.add_argument("--baseline", type=Path, default=ENVIRONMENT / "baseline.json")
    p.add_argument("--references-dir", type=Path, default=ROOT / "_references")
    p.add_argument(
        "--acquire", action="store_true", help="fetch missing pinned public sources"
    )
    p.add_argument("--out", type=Path, default=ROOT / ".work/gpu4pyscf-audit.json")
    args = p.parse_args()
    repos = {
        r["id"]: r for r in json.loads(args.sources_lock.read_bytes())["repositories"]
    }
    pinned = {}
    for key, name in (("gpu4pyscf", "GPU4PySCF"), ("pyscf_2_14", "PySCF")):
        r = repos[key]
        if r["commit"] != EXPECTED[key]:
            p.error(f"unexpected version lock for {key}")
        pinned[name] = (key, key, r["commit"], r["tree"], r["repository_url"])
    for r in repos["gpu4pyscf"]["release_variants"]:
        tag = r["tag"]
        if tag not in TAGS:
            continue
        if r["commit"] != TAGS[tag]:
            p.error(f"invalid commit lock: {tag}")
        pinned[f"GPU4PySCF-{tag}"] = (
            f"gpu4pyscf-{tag}",
            "gpu4pyscf",
            r["commit"],
            r["tree"],
            repos["gpu4pyscf"]["repository_url"],
        )
    if len(pinned) != 4:
        p.error("both official release tags must be locked")
    with args.coverage.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    errors = []
    trees = {}
    for name, (key, objects, commit, tree, url) in pinned.items():
        try:
            files = tree_check(
                args.references_dir / key,
                args.references_dir / objects,
                commit,
                tree,
                args.acquire,
                url,
            )
            related = [r for r in rows if r["source"] == name]
            if not related or any(
                r["commit"] != commit or r["path"] not in files for r in related
            ):
                raise ValueError(f"{name}: coverage path/version mismatch")
            trees[name] = dict(
                commit=commit, tree=tree, verified_tracked_files=len(files)
            )
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            errors.append(str(exc))
    if set(r["source"] for r in rows) != set(pinned) or len(rows) < 15:
        errors.append("source coverage")
    baseline = json.loads(args.baseline.read_bytes())
    if (
        baseline["gpu4pyscf_source_commit"] != EXPECTED["gpu4pyscf"]
        or baseline["pyscf_source_commit"] != EXPECTED["pyscf_2_14"]
    ):
        errors.append("original baseline identity")
    result = dict(
        status="failed" if errors else "passed",
        trees=trees,
        coverage_rows=len(rows),
        executed_rows=sum(r["executed"] == "true" for r in rows),
        unknowns=baseline["unknowns"],
        unknowns_scope="historical baseline.json, separate from later release-tag executions",
        errors=errors,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
