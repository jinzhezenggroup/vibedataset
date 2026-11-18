#!/usr/bin/env python3
"""Stage only source states and production code; seal sparse decisions before running a separate scorer."""
from argparse import ArgumentParser
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPS = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
FILES = ('target_quality_batch.py', 'target_response_quality.py', 'gqc_dual_response.py', 'cphf_reference.py',
         'probe_gqc_residual.py', 'gqc_residual_plan.py')
REQUESTS = [['x', 'q0'], ['y', 'r2'], ['z', 'zz']]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def main():
    p = ArgumentParser(description=__doc__)
    p.add_argument('--split', required=True, choices=('seed', 'holdout'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--smoke', action='store_true', help='one available source, three sparse targets')
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    staged = out / 'source-only'
    scripts = staged / 'scripts'
    scripts.mkdir(parents=True)
    for f in FILES:
        shutil.copyfile(ROOT / 'scripts' / f, scripts / f)
    (staged / '_references').mkdir()
    (staged / '_references/gqc').symlink_to((ROOT / '_references/gqc').resolve())
    original = EXPS / ('qm9_response_assets' if args.split == 'seed' else 'qm9_extension/assets')
    inputs = staged / 'inputs'
    inputs.mkdir()
    index = inputs / 'index.json'
    shutil.copyfile(original / index.name, index)
    source = json.loads(index.read_bytes())
    record_filter = ('qm9-000003' if args.split == 'seed' else 'qm9-000005') if args.smoke else None
    for row in source['rows']:
        if row['status'] == 'verified' and (not record_filter or record_filter == row['name']):
            for k in ('metadata_file', 'array_file'):
                shutil.copyfile(original / row[k], inputs / row[k])
    requests = inputs / 'requests.json'
    requests.write_bytes(encoded(REQUESTS))
    # This additional access log covers Python file opens; the visible data
    # tree itself contains only source inputs and the immutable GQC code tree.
    wrapper = staged / 'launch.py'
    wrapper.write_text("""import json, os, runpy, sys
from pathlib import Path
script = Path(sys.argv.pop(1))
audit_log = Path(sys.argv.pop(1))
forbidden = Path(sys.argv.pop(1)).resolve()
snapshot = script.parents[1] / 'inputs'
touched, denied = set(), []
def hook(event, args):
    if event == 'open' and isinstance(args[0], str):
        path = Path(os.path.realpath(args[0]))
        if path.is_relative_to(forbidden):
            denied.append(str(path))
            raise PermissionError('evaluation data unavailable to producer')
        if path.is_relative_to(snapshot):
            touched.add(path.name)
sys.addaudithook(hook)
sys.path.insert(0, str(script.parent))
sys.argv[0] = str(script)
try:
    runpy.run_path(str(script), run_name='__main__')
finally:
    audit_log.write_text(json.dumps(dict(opened_source=sorted(touched), denied=denied)))
""")
    receipts, audits = {}, {}

    def run(label, mode, history=None, only=None):
        dst = out / label
        audit = out / (label + '-opens.json')
        argv = [sys.executable, str(wrapper), str(scripts / 'target_quality_batch.py'), str(audit), str(EXPS),
                '--mode', mode, '--source-index', str(index), '--source-sha256', sha(index.read_bytes()),
                '--kernel-cache', str(out / 'kernels'), '--out', str(dst)]
        if mode != 'history':
            argv.extend(['--requests', str(requests)])
        if history:
            argv.extend(['--history', sha(history.read_bytes()), str(history)])
        if only or record_filter:
            argv.extend(['--record', only or record_filter])
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
                   MKL_NUM_THREADS='1')
        subprocess.run(argv, check=True, cwd=staged, env=env)
        path = dst / 'report.json'
        receipts[label] = sha(path.read_bytes())
        audits[label] = json.loads(audit.read_bytes())
        return path

    history = run('history', 'history')
    for mode in ('mixed', 'retained', 'quantized', 'unrated'):
        run(mode, mode, history)
    if args.split == 'seed':
        # Resealed wrong scientific identities, missing measured evidence and
        # illegal FP64 values must be refused by target independently of hashes.
        for label in ('wrong-rhs', 'wrong-readout', 'no-origin', 'huge-number', 'wrong-problem', 'bad-digest'):
            root = out / ('assets-' + label)
            root.mkdir()
            manifest = json.loads(history.read_bytes())
            row = next(x for x in manifest['records'] if x['name'] == 'qm9-000003')
            descriptor = row['files']['scalars']
            asset = json.loads((history.parent / descriptor['file']).read_bytes())
            value = asset['assets']['x/r2']
            if label == 'wrong-rhs':
                value['source']['rhs_sha256'] = '0' * 64
            elif label == 'wrong-readout':
                value['source']['readout'] = asset['assets']['y/q0']['source']['readout']
            elif label == 'no-origin':
                del value['direction_evidence']
            elif label == 'huge-number':
                value['raw_value'] = 10 ** 400
            elif label == 'wrong-problem':
                asset['scope']['problem'] = 'other'
            else:
                value['raw_value'] = 123.
            raw = encoded(asset)
            (root / descriptor['file']).write_bytes(raw)
            if label != 'bad-digest':
                descriptor.update(bytes=len(raw), sha256=sha(raw))
            altered = root / 'manifest.json'
            altered.write_bytes(encoded(manifest))
            run(label, 'mixed', altered, only='qm9-000003')

    # Freeze all candidate decisions before either competing baseline is run.
    decisions_digest = sha(encoded(receipts))
    for mode in ('ordinary', 'dense'):
        run(mode, mode)
    sealed = out / 'sealed'
    sealed.mkdir()
    for k, digest in receipts.items():
        data = (out / k / 'report.json').read_bytes()
        assert sha(data) == digest
        (sealed / (k + '.json.gz')).write_bytes(gzip.compress(data, mtime=0))
    # Retain source histories for the independent reproduction of every consumed interval.
    for row in json.loads(history.read_bytes())['records']:
        for entry in row.get('files', {}).values():
            data = (history.parent / entry['file']).read_bytes()
            assert sha(data) == entry['sha256']
            (sealed / (entry['file'] + '.gz')).write_bytes(gzip.compress(data, mtime=0))
    seal = dict(split=args.split, record_filter=record_filter, requests=REQUESTS, source_sha256=sha(index.read_bytes()),
                reports=receipts, prebaseline_decisions_sha256=decisions_digest, code={k: sha((scripts/k).read_bytes()) for k in FILES},
                launcher_sha256=sha(Path(__file__).read_bytes()), visible_inputs=sorted(p.name for p in inputs.iterdir()),
                source_opens=audits, evaluated_in_producer=False)
    (sealed / 'seal.json').write_bytes(encoded(seal))
    print('sealed', sha(encoded(seal)), sealed)


if __name__ == '__main__':
    main()
