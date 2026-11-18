#!/usr/bin/env python3
"""Inventory CLI attempts in every JSON member of the reviewed experiment tree."""
import argparse
from collections import Counter
import gzip
from io import BytesIO
import json
import subprocess
import tarfile
from pathlib import Path

REVIEW = 'faf93dd4a95d9a12ee06bdcf85040ecb38d9107b'
EXPERIMENTS = 'handoff/gqcdataset_codex_goal/research/experiments'


def objects(path, data):
    if path.endswith(('.tar', '.tar.gz')):
        with tarfile.open(fileobj=BytesIO(data), mode='r:*') as archive:
            for entry in archive:
                if entry.isfile():
                    yield from objects(path + '!' + entry.name, archive.extractfile(entry).read())
        return
    name = path.removesuffix('.gz')
    if name != path:
        data = gzip.decompress(data)
    if name.endswith('.json'):
        yield path, json.loads(data)
    elif name.endswith('.jsonl'):
        for line in data.splitlines():
            if line.strip():
                yield path, json.loads(line)


def attempts(value):
    if isinstance(value, list):
        for item in value:
            yield from attempts(item)
    elif isinstance(value, dict):
        if {'id', 'status', 'record_id', 'identity', 'model_started', 'round_jk'} <= value.keys():
            yield value
        else:
            for item in value.values():
                yield from attempts(item)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    output = p.parse_args().out
    tree = subprocess.check_output(['git', 'archive', '--format=tar', REVIEW + ':' + EXPERIMENTS])
    rows, references = {}, {}
    for path, item in objects('experiments.tar', tree):
        for record in attempts(item):
            aid = record['id']
            if aid in rows:
                assert rows[aid] == record
            rows[aid] = record
            references.setdefault(aid, []).append(path.removeprefix('experiments.tar!'))
    failed = []
    for key, row in rows.items():
        if row['status'] == 'failed':
            failed.append(dict(id=key, evidence=references[key], reason=row['reason'], setup_jk=row['setup_jk'],
                               round_jk=row['round_jk'], rhs=row['rhs'], counts=row.get('counts'),
                               submitted_blocks=(row.get('counts') or {}).get('submitted_blocks')))
    result = dict(review=REVIEW, root=EXPERIMENTS, unique_attempts=len(rows),
                  appearances=sum(map(len, references.values())), states=Counter(x['status'] for x in rows.values()),
                  failed=failed)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    main()
