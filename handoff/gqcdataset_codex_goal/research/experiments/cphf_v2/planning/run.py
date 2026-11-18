"""Run the original fixed queues with v2 qualification; keep all outputs under a new directory."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
ROOT = HERE.parents[5]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=1, help='single-threaded molecule processes for PLAN-004')
    parser.add_argument('--kernel-cache', type=Path, help='reuse an existing content-addressed PLAN-004 compiler cache')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
           'PYTHONDONTWRITEBYTECODE': '1'}
    inputs = {}
    for name, source in [('seed', 'qm9_response_assets'), ('extension', 'qm9_extension/assets')]:
        directory = HERE.parent / name
        index = json.loads((directory / 'index.json').read_bytes())
        if index.get('schema') != 'vibedataset.cphf_reference.v2':
            raise ValueError(f'{name} must use the v2 qualification index')
        inputs[name] = ('--assets', EXP / source, '--oracles', directory / 'oracles')

    def run(script, *arguments):
        cmd = [sys.executable, str(script), *map(str, arguments)]
        start = time.perf_counter()
        began = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(cmd, cwd=ROOT, env=env)
        receipt = dict(argv=cmd, utc=began, seconds=time.perf_counter() - start, exit_code=result.returncode)
        with (work / 'commands.jsonl').open('a') as file:
            print(json.dumps(receipt), file=file)
        result.check_returncode()

    scripts = ROOT / 'scripts'
    run(scripts / 'probe_partial_response_blocks.py', '--out', work / 'partial', '--jobs', args.jobs,
        '--kernel-cache', args.kernel_cache or work / 'partial-kernels', '--oracle-indexes',
        HERE.parent / 'seed/index.json', HERE.parent / 'extension/index.json')
    for catalog, inputs_for_catalog in inputs.items():
        run(scripts / 'probe_scalar_response.py', *inputs_for_catalog, '--out', work / (catalog + '-scalar'))
    run(scripts / 'probe_response_planning.py', *inputs['seed'], '--out', work / 'seed-remember',
        '--remember-reference-rejections')
    run(scripts / 'probe_response_planning.py', *inputs['seed'], '--out', work / 'seed-retry')
    run(scripts / 'probe_response_equivalence.py', *inputs['extension'], '--out', work / 'extension-diagnostic')
    run(HERE.parent / 'cohort/verify.py', '--package', work / 'partial', '--directory', work / 'evidence/cohort')
    run(HERE / 'verify.py', '--package', work, '--directory', work / 'evidence/planning')


if __name__ == '__main__':
    main()
