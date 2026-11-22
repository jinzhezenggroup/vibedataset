#!/usr/bin/env python3
"""Reconcile a timed-out upstream module with a terminal receipt for each collected node."""

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--nodes", type=Path, required=True)
    p.add_argument("--array", type=int, required=True)
    a = p.parse_args()
    nodeids = a.nodes.read_text().splitlines()
    module = "gpu4pyscf/tests/test_benchmark_rks.py"
    if len(nodeids) != len(set(nodeids)) or not all(
        s.startswith(module + "::") for s in nodeids
    ):
        raise ValueError("invalid collection")
    a.out.mkdir(exist_ok=False)
    wrapper = ET.Element("testsuites")
    attempts = []
    failed = False
    complete = True
    (a.out / "argv.txt").write_text("-m\npytest\n--benchmark-disable\n" + module + "\n")
    with (a.out / "pytest.log").open("wb") as full:
        for i, expected in enumerate(nodeids):
            d = a.root / f"case-{a.array}-{i}"
            xml = d / "junit.xml"
            exitcode = d / "exit.txt"
            if (
                not (d / "nodeid.txt").is_file()
                or (d / "nodeid.txt").read_text().strip() != expected
            ):
                complete = False
                attempts.append(dict(node=expected, status="missing dispatch"))
                continue
            log = d / "pytest.log"
            if log.is_file():
                full.write(f"\n--- {expected} ---\n".encode())
                full.write(log.read_bytes())
            valid = False
            if xml.is_file():
                root = ET.parse(xml).getroot()
                cases = list(root.iter("testcase"))
                valid = (
                    len(cases) == 1
                    and cases[0].get("name") == expected.rsplit("::", 1)[-1]
                )
                if valid:
                    for suite in root.iter("testsuite"):
                        wrapper.append(suite)
            rc = int(exitcode.read_text()) if exitcode.is_file() else None
            complete = complete and valid and rc in (0, 1)
            failed = failed or rc != 0
            attempts.append(
                dict(
                    node=expected,
                    code=rc,
                    matched_junit=valid,
                    log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()
                    if log.is_file()
                    else None,
                )
            )
    ET.ElementTree(wrapper).write(
        a.out / "junit.xml", encoding="utf-8", xml_declaration=True
    )
    (a.out / "case-reconciliation.json").write_text(
        json.dumps(
            dict(
                module=module,
                scope="one tagged test per fresh pytest process",
                complete=complete,
                attempts=attempts,
            ),
            indent=2,
        )
        + "\n"
    )
    (a.out / "exit.txt").write_text(str(124 if not complete else int(failed)) + "\n")


if __name__ == "__main__":
    main()
