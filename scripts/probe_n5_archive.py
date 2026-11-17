#!/usr/bin/env python3
"""On n5, use the exact n2 CP-001 archive and compare with n5's qualified cold result."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
from generativeqc import Calculator, _native

from probe_gqc_checkpoint import Journal


def load(path):
    return json.loads(path.read_text())


def file_sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--local-probe', type=Path, required=True)
    parser.add_argument('--source-report', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    journal = Journal(args.out, {'gqc_solve': 1})
    config = load(args.config)
    source = load(args.source_report)
    local_env = load(args.local_probe / 'environment.json')
    local = load(args.local_probe / 'results.json')
    source_env = source['environment']
    job_id = os.environ['SLURM_JOB_ID']
    if (load(args.local_probe / 'run.json')['status'] != 'passed'
            or local_env['allocation']['SLURM_JOB_ID'] != job_id
            or local_env['protocol_sha256'] != source_env['protocol_sha256']
            or file_sha(args.config) != source_env['protocol_sha256']):
        raise ValueError('local qualification or CP-001 protocol identity differs')
    cp_sha = file_sha(args.checkpoint)
    if cp_sha != source['raw_file_manifest']['outputs/job-5382/source.vqcp']['sha256']:
        raise ValueError('transferred bytes differ from n2 job 5382')
    library = journal.call('attest_cross_node_runtime', 'native_library_load',
                           lambda: _native.load_library(device='cuda'))
    loaded = Path(library._name)
    lib_sha = file_sha(loaded)
    if (not loaded.samefile(os.environ['GQC_NATIVE_LIBRARY'])
            or lib_sha != source_env['loaded_native_library_sha256']
            or lib_sha != local_env['loaded_native_library_sha256']):
        raise ValueError('cross-node runtime identity differs')
    atoms = list(zip(config['symbols'], config['coordinates']['source'], strict=True))
    calc = Calculator(**config['calculator'])
    with journal.call('prepare_same_target', 'prepare', lambda: calc.prepare_batch(
            [atoms], charges=[config['charge']], multiplicities=[config['multiplicity']])) as batch:
        admission = journal.call('import_n2_density', 'checkpoint_load',
                                 lambda: batch.load_checkpoint(args.checkpoint), summary=lambda x: x)
        if (admission['items'][0]['compatibility'] != 'exact_restart'
                or admission['target_verification'] != 'pending_execute'):
            raise ValueError('n2 archive not admitted as exact restart')
        result = journal.call('execute_target_on_n5', 'gqc_solve', lambda:
                              batch.execute(strict=True, properties=('energy', 'forces')).items[0])
        post = batch.checkpoint_diagnostics['target_verification']
        output = {'energy': float(result.energy), 'forces': np.asarray(result.forces).tolist(),
                  'iterations': int(result.iterations), 'fock_builds': int(result.fock_builds),
                  'converged': bool(result.converged), 'executed_backend': result.executed_backend,
                  'restart_origin': result.restart_origin, 'warm_start_fallback': bool(result.warm_start_fallback)}
    events = [json.loads(line) for line in (args.local_probe / 'operations.jsonl').read_text().splitlines()]
    refs = {r['label']: r['result'] for r in events if r.get('status') == 'completed'}
    references = {'n2_cold': source['results']['cold']['source'], 'n5_cold': local['cold']['source'],
                  'n5_pyscf': {'energy': refs['source_pyscf_scf'], 'forces': refs['source_pyscf_gradient']}}
    tol = config['tolerances']
    checks = {}
    for name, ref in references.items():
        level = 'independent' if name == 'n5_pyscf' else 'restart'
        energy_delta = abs(output['energy'] - ref['energy'])
        force_delta = float(np.max(np.abs(np.subtract(output['forces'], ref['forces']))))
        checks[name] = {'energy_difference_eh': energy_delta, 'max_force_difference_eh_per_bohr': force_delta,
                        'passed': bool(energy_delta <= tol[level + '_energy'] and force_delta <= tol[level + '_force'])}
    status = ('passed' if all(v['passed'] for v in checks.values()) and output['converged']
              and output['executed_backend'] == 'cuda' and output['iterations'] > 0
              and output['restart_origin'] == 'persistent_restart' and not output['warm_start_fallback']
              and post == 'executed' else 'failed')
    report = {'status': status, 'job': job_id, 'source_job': 'n2/5382',
              'checkpoint_sha256': cp_sha, 'protocol_sha256': file_sha(args.config),
              'driver_sha256': file_sha(Path(__file__)), 'loaded_library_sha256': lib_sha,
              'native_source_identity': library.generativeqc_get_source_identity().decode(),
              'source_declaration': source_env['gqc_source_declaration'],
              'compatibility': admission['items'][0]['compatibility'],
              'before_execute': admission['target_verification'], 'after_execute': post,
              'output': output, 'checks': checks, 'operations': dict(journal.counts),
              'elapsed_seconds': time.perf_counter() - start}
    (args.out / 'result.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    if status != 'passed':
        raise ValueError('cross-node scientific gate failed')


if __name__ == '__main__':
    main()
