#!/usr/bin/env python3
"""Inventory a local Git checkout without fetching or executing repository code.

Python >= 3.10, standard library and Git only. JSON is written to stdout unless
--json is supplied. Output files must be outside the checkout being inspected.
An inventory is indexing evidence; it is never evidence that source was read.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from datetime import datetime, timezone


def git(repo: Path, *args: str, data: bytes | None = None, optional=False) -> bytes:
    env = os.environ.copy()
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1",
               GIT_ALLOW_PROTOCOL="")
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
         "-c", "protocol.allow=never", "-C", str(repo), *args],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if result.returncode and not optional:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout if result.returncode == 0 else b""


def name(raw: bytes) -> str:
    return os.fsdecode(raw)


def status_records(raw: bytes) -> list[dict]:
    fields = raw.split(b"\0")
    result, i = [], 0
    while i < len(fields) and fields[i]:
        record = fields[i]
        item = {"status": record[:2].decode("ascii"), "path": name(record[3:])}
        i += 1
        if b"R" in record[:2] or b"C" in record[:2]:
            item["original_path"] = name(fields[i])
            i += 1
        result.append(item)
    return result


def tree_entries(repo: Path) -> list[dict]:
    entries = []
    for raw in git(repo, "ls-tree", "-r", "-l", "-z", "--full-tree", "HEAD").split(b"\0"):
        if not raw:
            continue
        header, path = raw.split(b"\t", 1)
        mode, kind, oid, size = header.split()
        entries.append({"path": name(path), "mode": mode.decode(),
                        "git_type": kind.decode(), "commit_object_id": oid.decode(),
                        "commit_size": int(size) if size != b"-" else None})
    return entries


def small_blobs(repo: Path, entries: list[dict]) -> dict[str, bytes]:
    """Read possible LFS pointer blobs from the pinned tree in one Git process."""
    ids = sorted({e["commit_object_id"] for e in entries
                  if e["git_type"] == "blob" and e["commit_size"] <= 1024})
    if not ids:
        return {}
    raw = git(repo, "cat-file", "--batch", data=("\n".join(ids) + "\n").encode())
    result, offset = {}, 0
    for expected in ids:
        end = raw.find(b"\n", offset)
        if end < 0:
            raise RuntimeError("Incomplete git cat-file response")
        header = raw[offset:end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise RuntimeError(f"Local blob unavailable: {expected}")
        length = int(header[2])
        start = end + 1
        if raw[start + length:start + length + 1] != b"\n":
            raise RuntimeError("Invalid git cat-file framing")
        result[expected] = raw[start:start + length]
        offset = start + length + 1
    return result


def lfs_pointer(raw: bytes) -> dict | None:
    if not raw.startswith(b"version https://git-lfs.github.com/spec/v1\n"):
        return None
    fields = {}
    for line in raw.splitlines()[1:]:
        key, _, value = line.partition(b" ")
        fields[key] = value
    oid = fields.get(b"oid", b"").decode("ascii", "replace")
    size = fields.get(b"size", b"")
    return {"oid": oid, "size": int(size) if size.isdigit() else None}


def safe_checkout_path(repo: Path, path: str) -> Path:
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("unsafe repository path")
    parent = repo
    for part in relative.parts[:-1]:
        parent = parent / part
        if parent.is_symlink():
            raise ValueError("parent directory is a symlink; content not read")
    return repo / relative


def inspect_file(repo: Path, entry: dict, object_format: str, pointer: dict | None) -> dict:
    result = dict(entry)
    path = repo / entry["path"]
    result["lfs"] = {"pointer": pointer, "hydrated": False} if pointer else None
    try:
        # A modified checkout must not redirect reads outside the inspected tree.
        path = safe_checkout_path(repo, entry["path"])
        info = path.lstat()
        expected_link = entry["mode"] == "120000"
        if stat.S_ISLNK(info.st_mode):
            if not expected_link:
                raise ValueError("expected regular file, found symlink; content not read")
            raw = os.fsencode(os.readlink(path))
            parts = [raw]
            size = len(raw)
            current_kind = "symlink"
        elif stat.S_ISREG(info.st_mode):
            if expected_link:
                raise ValueError("expected symlink, found regular file")
            parts = None
            size = info.st_size
            current_kind = "regular"
        else:
            raise ValueError("expected file, found unsupported filesystem object")
        sha256 = hashlib.sha256()
        blob = hashlib.new(object_format)
        blob.update(f"blob {size}\0".encode())
        if parts is not None:
            for part in parts:
                sha256.update(part)
                blob.update(part)
        else:
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    sha256.update(chunk)
                    blob.update(chunk)
        result.update(present=True, worktree_kind=current_kind, worktree_size=size,
                      worktree_sha256=sha256.hexdigest(), worktree_git_blob=blob.hexdigest(),
                      worktree_matches_commit_blob=blob.hexdigest() == entry["commit_object_id"])
        if pointer:
            hydrated = (pointer["oid"] == "sha256:" + sha256.hexdigest()
                        and pointer["size"] == size)
            result["lfs"]["hydrated"] = hydrated
            result["lfs"]["pointer_only"] = result["worktree_matches_commit_blob"]
        return result
    except (OSError, ValueError) as error:
        result.update(present=False, error=str(error))
        return result


def inspect(repo: Path, recurse: bool, visited: set[Path]) -> dict:
    repo = repo.resolve()
    if repo in visited:
        raise RuntimeError(f"Repeated repository path: {repo}")
    visited.add(repo)
    actual_root = Path(name(git(repo, "rev-parse", "--show-toplevel").rstrip(b"\n"))).resolve()
    if actual_root != repo:
        raise RuntimeError(f"Provide the checkout root, not a subdirectory: {actual_root}")
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    tree = git(repo, "rev-parse", "HEAD^{tree}").decode().strip()
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", optional=True).decode().strip()
    object_format = git(repo, "rev-parse", "--show-object-format").decode().strip()
    entries = tree_entries(repo)
    blobs = small_blobs(repo, entries)
    status = status_records(git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=normal"))
    files, submodules = [], []
    for entry in entries:
        if entry["mode"] != "160000":
            pointer = lfs_pointer(blobs.get(entry["commit_object_id"], b""))
            files.append(inspect_file(repo, entry, object_format, pointer))
            continue
        child = dict(entry, initialized=False, matches_pin=False)
        try:
            path = safe_checkout_path(repo, entry["path"])
        except ValueError as error:
            child["error"] = str(error)
            submodules.append(child)
            continue
        if path.is_dir() and not path.is_symlink():
            child_root = git(path, "rev-parse", "--show-toplevel", optional=True).rstrip(b"\n")
            if child_root and Path(name(child_root)).resolve() == path.resolve():
                child["initialized"] = True
                child["checked_out_commit"] = git(path, "rev-parse", "HEAD").decode().strip()
                child["matches_pin"] = child["checked_out_commit"] == entry["commit_object_id"]
                if recurse:
                    child["inventory"] = inspect(path, recurse, visited)
        submodules.append(child)
    blockers = []
    for file in files:
        if not file["present"]:
            blockers.append({"path": file["path"], "reason": file["error"]})
        elif file["lfs"] and not file["lfs"]["hydrated"]:
            blockers.append({"path": file["path"], "reason": "LFS object not hydrated or hash mismatch"})
        elif not file["lfs"] and not file["worktree_matches_commit_blob"]:
            blockers.append({"path": file["path"], "reason": "worktree differs from pinned blob (including possible checkout filters)"})
    for child in submodules:
        if not child["initialized"] or not child["matches_pin"]:
            blockers.append({"path": child["path"], "reason": "submodule missing or differs from pinned commit"})
        elif not recurse:
            blockers.append({"path": child["path"], "reason": "submodule contents not inventoried; use --recurse-submodules"})
        elif child["inventory"]["acquisition_blockers"]:
            blockers.append({"path": child["path"], "reason": "submodule has acquisition blockers"})
    if status:
        blockers.append({"path": ".", "reason": "dirty checkout; inspect status before attributing evidence to HEAD"})
    return {"repository_path": str(repo), "commit": head, "tree": tree,
            "branch": branch or None, "object_format": object_format, "dirty": bool(status),
            "status": status, "files": files, "submodules": submodules,
            "acquisition_blockers": blockers,
            "evidence_status": {"indexed": True, "acquired": "requires_human_review",
                                "read": False, "behavior_traced": False, "executed": False}}


def csv_rows(inventory: dict, prefix=""):
    for file in inventory["files"]:
        yield {"repository_commit": inventory["commit"], "path": prefix + file["path"],
               "mode": file["mode"], "commit_object_id": file["commit_object_id"],
               "present": file["present"], "worktree_size": file.get("worktree_size", ""),
               "worktree_sha256": file.get("worktree_sha256", ""),
               "lfs_hydrated": file["lfs"]["hydrated"] if file["lfs"] else "",
               "error": file.get("error", ""), "indexed": True, "read": False,
               "behavior_traced": False, "executed": False}
    for child in inventory["submodules"]:
        if "inventory" in child:
            yield from csv_rows(child["inventory"], prefix + child["path"] + "/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--csv", dest="csv_path", type=Path)
    parser.add_argument("--recurse-submodules", action="store_true")
    args = parser.parse_args()
    repo = args.repository.resolve()
    try:
        for target in (args.json_path, args.csv_path):
            if target and target.resolve().is_relative_to(repo):
                raise ValueError("Write inventories outside the inspected checkout")
        result = inspect(repo, args.recurse_submodules, set())
        document = {"schema_version": 1,
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "notice": "Index only: no source reading, behavior tracing or execution is inferred.",
                    "inventory": result}
        output = json.dumps(document, ensure_ascii=True, indent=2) + "\n"
        if args.json_path:
            args.json_path.parent.mkdir(parents=True, exist_ok=True)
            args.json_path.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        if args.csv_path:
            args.csv_path.parent.mkdir(parents=True, exist_ok=True)
            rows = list(csv_rows(result))
            fields = ["repository_commit", "path", "mode", "commit_object_id", "present",
                      "worktree_size", "worktree_sha256", "lfs_hydrated", "error",
                      "indexed", "read", "behavior_traced", "executed"]
            with args.csv_path.open("w", encoding="utf-8", errors="backslashreplace", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"inventory_sources: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
