#!/usr/bin/env python3
"""Exercise public CLI input errors and keep independent outputs when historical records cannot be read."""
from argparse import ArgumentParser
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = ArgumentParser(description=__doc__)
    p.add_argument('--work', required=True, type=Path)
    work = p.parse_args().work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    source = BASE / 'qm9_response_assets/index.json'
    requests = BASE / 'target_quality/requests.json'
    cli = ROOT / 'scripts/target_quality_batch.py'
    prefix = [sys.executable, str(cli), '--source-index', str(source), '--source-sha256', sha(source),
              '--kernel-cache', str(work/'kernels')]
    invalid, batches = {}, {}
    bad = work / 'bad.json'
    bad.write_text('[{"field":"x"}]')
    for case, argv in (
            ('missing_requests', []), ('malformed_requests', ['--requests', str(bad)]),
            ('unknown_record', ['--record', 'unavailable-id', '--requests', str(requests)]),
            ('missing_request_file', ['--requests', str(work/'absent')])):
        dest = work / case
        proc = subprocess.run(prefix + ['--out', str(dest), '--mode', 'ordinary', *argv], capture_output=True, text=True)
        assert proc.returncode == 2 and not dest.exists() and 'Traceback' not in proc.stderr, (case, proc.stderr)
        invalid[case] = proc.stderr.splitlines()[-1]

    for label, path, expected in (('bad_manifest', bad, 'reject'), ('missing_manifest', work/'missing', 'evidence_unavailable')):
        dst = work / label
        start = time.perf_counter()
        args = prefix + ['--out', str(dst), '--mode', 'mixed', '--requests', str(requests), '--record', 'qm9-000003',
                         '--history', sha(path) if path.exists() else '0' * 64, str(path)]
        subprocess.run(args, check=True, stdout=subprocess.PIPE)
        batch = json.loads((dst/'report.json').read_bytes())
        record, = batch['records']
        states = {(d['field'], d['observable']): d['final']['status'] for d in record['decisions']}
        assert states == {('x','q0'): expected, ('y','r2'): expected, ('z','zz'):'accepted'}
        batches[label] = {'batch': batch, 'seconds': time.perf_counter()-start}
    result = {'parameter_errors': invalid, 'batches': batches, 'cli_sha256': sha(cli),
              'regression_sha256': sha(Path(__file__)), 'result': 'passed'}
    raw = (json.dumps(result, sort_keys=True, allow_nan=False, separators=(',', ':')) + '\n').encode()
    (work/'input-controls.json.gz').write_bytes(gzip.compress(raw, mtime=0))


if __name__ == '__main__':
    main()
