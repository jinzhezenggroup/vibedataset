#!/usr/bin/env python3
"""Measure overlaps from actual CUPTI GPU start/end timestamps of distinct streams."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3


def intervals(items):
    merged = []
    for a, b in sorted(items):
        if b <= a:
            raise ValueError("nonpositive GPU activity")
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(b, merged[-1][1])
        else:
            merged.append([a, b])
    return merged


def overlap(left, right):
    a, b = intervals(left), intervals(right)
    i = j = total = 0
    while i < len(a) and j < len(b):
        total += max(0, min(a[i][1], b[j][1]) - max(a[i][0], b[j][0]))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def snapshot(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as d:
        kernels = d.execute(
            "SELECT k.start,k.end,k.streamId,s.value FROM CUPTI_ACTIVITY_KIND_KERNEL k "
            "JOIN StringIds s ON s.id=k.shortName ORDER BY k.start"
        ).fetchall()
        copies = d.execute(
            "SELECT start,end,streamId,copyKind,bytes FROM CUPTI_ACTIVITY_KIND_MEMCPY ORDER BY start"
        ).fetchall()
    return dict(
        kernels=kernels,
        copies=copies,
        sqlite_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def measure(data):
    ks = data["kernels"]
    cs = data["copies"]
    ragged = [k for k in ks if k[3] == "ragged_readout"]
    streams = {k[2] for k in ragged}
    if len(ragged) != 3:
        raise ValueError("incomplete ragged launch count")
    primary = max({k[2] for k in ks}, key=lambda st: sum(k[2] == st for k in ks))
    extra = streams - {primary}
    default = [k[:2] for k in ks if k[2] == primary]
    d2h = [c for c in cs if c[2] in extra and c[3] == 2]
    h2d = [c for c in cs if c[2] != primary and c[2] not in extra and c[3] == 1]
    readout = [k[:2] for k in ks if k[2] in extra]
    return dict(
        primary_stream=primary,
        readout_streams=sorted(streams),
        ragged_launch_count=len(ragged),
        primary_kernel_count=len(default),
        nonprimary_readout_D2H_bytes=sum(c[4] for c in d2h),
        independent_H2D_bytes=sum(c[4] for c in h2d),
        readout_D2H_with_primary_kernel_ns=overlap(default, [c[:2] for c in d2h]),
        independent_H2D_with_primary_kernel_ns=overlap(default, [c[:2] for c in h2d]),
        readout_stream_kernel_with_primary_kernel_ns=overlap(default, readout),
        sqlite_sha256=data["sqlite_sha256"],
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument(
        "--extract",
        type=Path,
        help="source directory containing the original per-mode SQLite traces",
    )
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    a.root.mkdir(parents=True, exist_ok=True)
    report = {}
    for mode in ("serial", "async_streams"):
        packed = a.root / (mode + "-activities.json.gz")
        if a.extract:
            data = snapshot(a.extract / mode / "trace.sqlite")
            packed.write_bytes(
                gzip.compress(json.dumps(data, separators=(",", ":")).encode(), mtime=0)
            )
        data = json.loads(gzip.decompress(packed.read_bytes()))
        report[mode] = measure(data)
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
