#!/usr/bin/env python3
"""Index a fixed external XYZ inventory for planner-only OOD decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def first_frame_atoms(text: str) -> int:
    lines = [line for line in text.splitlines() if line.strip()]
    try:
        return int(lines[0])
    except (IndexError, ValueError):
        return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("_references/qhnet/OpenMol/PACE/dataset/rmd17"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    files = sorted(args.root.rglob("*.xyz"))[: args.limit]
    if len(files) < args.limit:
        raise SystemExit(f"only {len(files)} XYZ files found")
    rows = []
    for path in files:
        data = path.read_bytes()
        rows.append({
            "case_id": f"qhnet-ood-{len(rows):03d}",
            "source_relpath": str(path),
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "first_frame_atom_count": first_frame_atoms(data.decode(errors="replace")),
            "protocol_status": "external-geometry-only",
            "disposition": "reject-and-recompute",
        })
    result = {
        "schema": "vibedataset.target_response_ood_inventory.v1",
        "source": {"repository": "QHNet/AIRS", "commit": "594e8bad8cd0b24a207c818e09b39ccc0aebcd4d", "root": str(args.root), "selection": "lexicographically first 100 tracked XYZ files under RMD17"},
        "count": len(rows),
        "rows": rows,
        "response_labels_included": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
