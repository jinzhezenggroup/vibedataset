#!/usr/bin/env python3
"""Verify PLAN-002 scalar operands through the published dataset entry point."""
from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
FIELDS = ['x', 'y', 'z']
OBS = ['q0', 'r2', 'zz']
DIAG = list(zip(FIELDS, OBS, strict=True))
HISTORY = [(f, o) for f in FIELDS for o in OBS if (f, o) not in DIAG]
URL = 'https://api.figshare.com/v2/articles/1057646/versions/2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    work = parser.parse_args().work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    runs = []
    def run(name, pairs, *, history=None, db=None, local=False, expected_digest=None):
        inp, out = work / (name + '.jsonl'), work / (name + '.json')
        inp.write_text(''.join(json.dumps({'source': URL, 'record_id': 3, 'field': f, 'observable': o}) + '\n'
                               for f, o in pairs))
        argv = [sys.executable, str(ROOT/'scripts/complete_response_dataset.py'), '--requests', str(inp),
                '--cache-db', str(work/((db or name) + '.sqlite')), '--out', str(out), '--kernel-cache', str(work/'kernels')]
        if history is not None:
            argv.extend(['--history', expected_digest or sha(history), str(history)])
        if local:
            argv.append('--decode-known-scalars')
        start = time.perf_counter()
        subprocess.run(argv, check=True, timeout=180)
        batch = json.loads(out.read_text())
        job, = batch['work']
        runs.append({'client': name, 'input_sha256': sha(inp), 'output_sha256': sha(out), 'seconds': time.perf_counter() - start,
                     'import': batch.get('history'), 'work': job, 'rows': [
                         {'edge': [r['request']['field'],r['request']['observable']], 'target_identity': r['target_identity'],
                          'via': r['via'], 'delivery': r['delivery'], 'qualified_value': r['value']}
                         for r in batch['records']]})
        return batch, job

    # Only earlier actual CLI measurements are read as the historical operands.
    _, production = run('history', HISTORY)
    baseline, ordinary = run('ordinary', DIAG)
    decoded, relation = run('decode', DIAG, history=work/'history.json')
    assert production['model_started'] and ordinary['rhs'] == 3 and relation['rhs'] == 1
    assert relation['relation']['used'] and not relation['relation']['ordinary_retries']
    diff = max(abs(a['value'] - b['value']) for a, b in zip(baseline['records'], decoded['records'], strict=True))
    assert diff <= 1e-8
    hand_errors = []
    for rec in relation['relation']['reconstructions']:
        values = [r['value'] for r in rec['operands']]
        hand = relation['relation']['combined']['values'][rec['observable']] - values[0] - values[1]
        hand_errors.append(abs(hand - rec['candidate']['value']))
    assert max(hand_errors) <= 1e-14

    repeated, hit = run('repeat', DIAG, db='decode')
    assert hit['model_started'] is False and hit['round_jk'] == 0 and hit['rhs'] == 0
    assert all(row['delivery'] == 'scalar_cache' for row in repeated['records'])
    transferred, external = run('external-hits', HISTORY, history=work/'history.json')
    assert external['historical_hits'] == 6 and external['model_started'] is False
    assert all(row['delivery'] == 'historical_scalar' for row in transferred['records'])
    _, cached_operands = run('local-decode', DIAG, db='external-hits', local=True)
    assert cached_operands['relation']['used'] and cached_operands['rhs'] == 1

    # Retaining already-paid vectors makes the regular route cost zero new RHS.
    _, retained = run('prefer-existing-vectors', DIAG, db='history', local=True)
    assert not retained['relation']['used'] and retained['rhs'] == 0
    run('two-terms', [('y','q0'),('z','q0')])
    _, partial = run('partial-tie', DIAG, history=work/'two-terms.json')
    assert not partial['relation']['used'] and partial['rhs'] == 3
    run('four-terms', [('y','q0'),('z','q0'),('x','r2'),('z','r2')])
    _, hybrid = run('partial-strict-saving', DIAG, history=work/'four-terms.json')
    assert hybrid['relation']['used'] and hybrid['rhs'] == 2

    foreign = json.loads((work/'history.json').read_text())
    for record in foreign['records']:
        record['source']['reference_identity'] = 'different-physical-state'
    bad = work/'wrong-source.json'
    bad.write_text(json.dumps(foreign))
    _, denied = run('foreign-recovery', DIAG, history=bad)
    assert denied['validated_history_scalars'] == 0 and len(denied['rejected_history']) == 6 and denied['rhs'] == 3
    ignored, w = run('bad-digest', [DIAG[0]], history=work/'history.json', expected_digest='0'*64)
    assert ignored['history']['status'] == 'rejected' and w['rhs'] == 1
    oracle = ROOT/'handoff/gqcdataset_codex_goal/research/experiments/gqc_dual_response/oracles/qm9-000003.json'
    ignored, w = run('oracle-not-an-input-archive', [DIAG[0]], history=oracle)
    assert ignored['history']['status'] == 'rejected' and w['rhs'] == 1
    result = {'status': 'passed', 'cli_sha256': sha(ROOT/'scripts/complete_response_dataset.py'),
              'compiler_gqc_sha': decoded['gqc_commit'], 'publication_grader_sha256': decoded['model_source_sha256'],
              'external_record': 'qm9-000003', 'tested_scientific_outputs': len(DIAG),
              'worst_direct_vs_decoded': diff, 'worst_hand_vs_compiled_subtraction': max(hand_errors), 'clients': runs}
    (work/'verification.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print('passed',len(runs),'processes; fresh solver J/K (ordinary, full scalar history, four-term history)',
          ordinary['round_jk'],relation['round_jk'],hybrid['round_jk'])


if __name__ == '__main__':
    main()
