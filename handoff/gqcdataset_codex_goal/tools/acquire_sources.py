#!/usr/bin/env python3
"""Fetch complete pinned Git trees without installing or running third-party code.

Writes append-only command receipts; leaves incomplete checkouts for inspection.
Submodules and LFS require separate review and acquisition. Inventory is indexing,
never an automatic acquisition/read/behavior/scientific-validation approval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def now():
    return datetime.now(timezone.utc).isoformat()


def run(argv, cwd, receipt, timeout):
    entry = {"argv": argv, "cwd": str(cwd), "started_at_utc": now()}
    receipt['commands'].append(entry)
    save(receipt)
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1')
    started = time.monotonic()
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGTERM)
        try:
            stdout, stderr = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            stdout, stderr = p.communicate()
        entry['timed_out'] = True
    entry.update(stdout=stdout, stderr=stderr, returncode=p.returncode,
                 elapsed_seconds=time.monotonic()-started, ended_at_utc=now())
    save(receipt)
    if p.returncode or entry.get('timed_out'):
        raise RuntimeError(f"command failed: {argv[0]} ({p.returncode})")
    return stdout.strip()


def save(receipt):
    path = Path(receipt['receipt_path'])
    path.write_text(json.dumps(receipt, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--ids', nargs='*')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    failures = 0
    for source in plan['repositories']:
        if args.ids and source['id'] not in args.ids:
            continue
        repo = Path(source['checkout_path'])
        receipt_dir = Path(plan['receipt_directory'])
        receipt_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        receipt = {'id': source['id'], 'source': source, 'started_at_utc': now(),
                   'status': 'started', 'commands': [],
                   'receipt_path': str(receipt_dir / f"{source['id']}-{stamp}.json")}
        save(receipt)
        try:
            if repo.exists():
                raise RuntimeError('checkout already exists; inspect it, never overwrite it')
            url = source['repository_url']
            if not url.startswith('https://github.com/'):
                raise ValueError('review non-GitHub sources before adding support')
            commit = source.get('commit')
            if not commit:
                refs = run(['git', 'ls-remote', url, 'HEAD'], '.', receipt, args.timeout)
                commit = refs.split()[0]
            if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
                raise ValueError('expected a full SHA-1 commit')
            receipt['resolved_commit'] = commit
            repo.mkdir(parents=True)
            run(['git', 'init', '--quiet'], repo, receipt, args.timeout)
            run(['git', 'remote', 'add', 'origin', url], repo, receipt, args.timeout)
            run(['git', '-c', 'protocol.file.allow=never', 'fetch', '--depth=1',
                 '--no-tags', 'origin', commit], repo, receipt, args.timeout)
            run(['git', '-c', 'core.autocrlf=false', 'checkout', '--detach', commit],
                repo, receipt, args.timeout)
            inventory = Path(plan['inventory_directory']) / (source['id'] + '.json')
            run([sys.executable, str(Path(__file__).with_name('inventory_sources.py')),
                 str(repo), '--recurse-submodules', '--json', str(inventory)],
                '.', receipt, args.timeout)
            receipt.update(status='indexed_pending_review', inventory_path=str(inventory))
        except Exception as error:
            failures += 1
            receipt.update(status='failed', error=str(error))
        receipt['ended_at_utc'] = now()
        save(receipt)
        print(source['id'], receipt['status'], receipt.get('resolved_commit', ''), flush=True)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
