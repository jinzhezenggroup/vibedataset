#!/usr/bin/env python3
"""Fold measured A-arm GPU kernel durations by their containing synchronized NVTX range."""

import argparse
from bisect import bisect_right
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--renderer", type=Path, help="pinned upstream flamegraph.pl")
    a = p.parse_args()
    info = json.loads((a.root / "parts.json").read_bytes())["A-warm"]
    parts = [(a.root / "A-warm" / v["file"]).read_bytes() for v in info["parts"]]
    combined = b"".join(parts)
    if hashlib.sha256(combined).hexdigest() != info["activity_sha256"]:
        raise ValueError("bad trace seal")
    trace = json.loads(gzip.decompress(combined))
    ranges = trace["ranges"]
    starts = [r[1] for r in ranges]
    totals = Counter()
    for start, end, _, _, name, *unused in trace["kernels"]:
        i = bisect_right(starts, start) - 1
        phase = "outside named phases"
        if i >= 0 and end <= ranges[i][2]:
            names = ranges[i][0].split("/")
            phase = "SCF" if names[0] == "scf" else "response;" + names[2]
        kernel = trace["kernel_names"][str(name)].replace(";", "_").replace("\n", " ")
        totals["official GPU4PySCF;" + phase + ";" + kernel] += end - start
    folded = "".join(f"{stack} {ns}\n" for stack, ns in sorted(totals.items())).encode()
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "official-warm.folded.gz").write_bytes(gzip.compress(folded, mtime=0))
    if a.renderer:
        binary = a.renderer.read_bytes()
        options = [
            "--title",
            "Official GPU4PySCF | warm cache | 17 molecules",
            "--countname",
            "kernel ns",
            "--width",
            "1200",
            "--colors",
            "aqua",
            "--hash",
        ]
        data = subprocess.run(
            ["perl", str(a.renderer), *options],
            input=folded,
            stdout=subprocess.PIPE,
            check=True,
        ).stdout
        (a.out / "official-warm.svg").write_bytes(data)
        (a.out / "flamegraph-renderer.json").write_text(
            json.dumps(
                dict(
                    source="https://github.com/brendangregg/FlameGraph",
                    commit=subprocess.check_output(
                        ["git", "-C", str(a.renderer.parent), "rev-parse", "HEAD"],
                        text=True,
                    ).strip(),
                    script_sha256=hashlib.sha256(binary).hexdigest(),
                    options=options,
                    folded_sha256=hashlib.sha256(folded).hexdigest(),
                    kernel_time_ns=sum(totals.values()),
                    description="GPU kernel duration hierarchy, not CPU sampled call stacks or end-to-end wall time",
                ),
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
