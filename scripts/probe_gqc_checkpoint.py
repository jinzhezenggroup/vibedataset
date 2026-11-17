#!/usr/bin/env python3
"""Bounded, build-pinned HF checkpoint admission/target-solve experiment.

No installation or compilation. Run only inside the project's Slurm allocation.
The JSONL journal is fsynced before each operation, including failed admissions.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


class Journal:
    def __init__(self, out, limits):
        self.path = out / 'operations.jsonl'
        self.counts = Counter()
        self.limits = limits
        self.sequence = 0

    def emit(self, row):
        with self.path.open('a') as handle:
            handle.write(json.dumps(row, allow_nan=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())

    def call(self, label, kind, fn, summary=None, expected_error=None):
        if kind in self.limits and self.counts[kind] >= self.limits[kind]:
            raise RuntimeError(f'operation budget exceeded: {kind}')
        self.counts[kind] += 1
        self.sequence += 1
        base = dict(id=self.sequence, label=label, kind=kind, started_at_utc=utc())
        self.emit(dict(base, status='started'))
        start = time.perf_counter()
        try:
            result = fn()
            if expected_error is not None:
                raise AssertionError(f'{label}: expected rejection was not observed')
            packed = summary(result) if summary else None
        except Exception as error:
            expected = expected_error is not None and isinstance(error, expected_error)
            failure = dict(base, status='expected_rejection' if expected else 'failed',
                           elapsed_seconds=time.perf_counter()-start,
                           error_type=type(error).__name__, error=str(error))
            self.emit(failure)
            if expected:
                return failure
            raise
        self.emit(dict(base, status='completed', elapsed_seconds=time.perf_counter()-start,
                       result=packed))
        return result


def run(config, out, journal):
    import numpy as np
    from generativeqc import Calculator
    from generativeqc.checkpoint import CheckpointError, _HEADER, _json, _read
    from pyscf import gto, scf

    def dump(name, data):
        (out / name).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')

    observed = {}
    for name, expected in config['python_source_sha256'].items():
        module = importlib.import_module('generativeqc.' + name)
        observed[name] = sha(module.__file__)
    library_sha = sha(os.environ['GQC_NATIVE_LIBRARY'])
    if not os.environ.get('SLURM_JOB_ID'):
        raise RuntimeError('run inside Slurm only')
    dump('environment.json', dict(
        python=platform.python_version(), host=platform.node(),
        versions={p:importlib.metadata.version(p) for p in ('generativeqc','numpy','pyscf')},
        gqc_source_declaration=os.environ['GQC_SOURCE_SHA'],
        native_library_sha256=library_sha, python_source_sha256=observed,
        allocation={k:os.environ.get(k) for k in
                    ('SLURM_JOB_ID','SLURM_CPUS_PER_TASK','SLURM_MEM_PER_NODE','CUDA_VISIBLE_DEVICES')},
        protocol_sha256=sha(args.config), driver_sha256=sha(__file__),
        project_commit=os.environ.get('VIBEDATASET_CODE_SHA'),
        scope='Binary hash and Python file hashes checked; source-to-binary reproducible build not proven.'))
    for name, expected in config['python_source_sha256'].items():
        if observed[name] != expected:
            raise RuntimeError(f'installed Python source differs from pinned checkout: {name}')
    if library_sha != config['native_library_sha256']:
        raise RuntimeError('native library identity differs from predeclared build')
    if os.environ['GQC_SOURCE_SHA'] != config['gqc_source_commit']:
        raise RuntimeError('runtime source declaration differs from protocol')

    options = config['calculator']
    charge, multiplicity = config['charge'], config['multiplicity']
    assert config['coordinate_unit'] == 'Bohr'
    geometries = {name:np.asarray(xyz,dtype=float) for name,xyz in config['coordinates'].items()}
    direction = np.asarray(config['direction'],dtype=float)
    direction /= np.linalg.norm(direction)
    tol = config['tolerances']
    checks = []

    def check(name, actual, accepted):
        checks.append(dict(name=name, value=actual, passed=bool(accepted)))
        dump('checks.json', checks)
        if not accepted:
            raise AssertionError(f'predeclared check failed: {name}: {actual}')

    def atoms(xyz):
        return [(s,tuple(float(x) for x in pos)) for s,pos in zip(config['symbols'],xyz)]

    def snapshot(result):
        force = None if result.forces is None else np.array(result.forces,copy=True)
        if not result.converged or not np.isfinite(result.energy):
            raise AssertionError('SCF result not converged/finite')
        if result.executed_backend != options['device']:
            raise AssertionError('unexpected backend')
        if force is not None and not np.isfinite(force).all():
            raise AssertionError('nonfinite forces')
        data = dict(energy=float(result.energy),forces=force.tolist() if force is not None else None,
                    converged=bool(result.converged),iterations=int(result.iterations),
                    executed_backend=result.executed_backend)
        for name in ('status','restart_origin','warm_start_used','warm_start_fallback',
                     'fock_builds','physical_residual_rms','density_rms','energy_change','basis_metadata'):
            if hasattr(result,name):
                data[name] = getattr(result,name)
        return data

    def singlepoint(label, xyz, forces=True):
        def solve():
            result = Calculator(**options).singlepoint(atoms(xyz),charge=charge,
                multiplicity=multiplicity,properties=('energy','forces') if forces else ('energy',))
            return snapshot(result)
        return journal.call(label,'gqc_solve',solve,summary=lambda x:x)

    def prepare(label, xyz, count=1, overrides=None):
        return journal.call(label,'prepare',lambda: Calculator(**(options | (overrides or {}))).prepare_batch(
            [atoms(xyz)]*count,charges=[charge]*count,multiplicities=[multiplicity]*count))

    def execute(label, batch):
        return journal.call(label,'gqc_solve',
            lambda:[snapshot(r) for r in batch.execute(strict=True,properties=('energy','forces')).items],
            summary=lambda x:x)

    def matches(label, result, cold):
        ed = abs(result['energy']-cold['energy'])
        fd = float(np.max(np.abs(np.array(result['forces'])-np.array(cold['forces']))))
        check(label+'_energy_difference',ed,ed<=tol['restart_energy'])
        check(label+'_force_difference',fd,fd<=tol['restart_force'])

    # Qualification precedes all reuse experiments. Both geometries are covered.
    cold = {}
    for name,xyz in geometries.items():
        cold[name] = singlepoint(name+'_cold',xyz)
        projected = float(np.sum(np.array(cold[name]['forces'])*direction))
        for step in config['fd_steps_bohr']:
            plus = singlepoint(f'{name}_fd_{step}_plus',xyz+step*direction,False)
            minus = singlepoint(f'{name}_fd_{step}_minus',xyz-step*direction,False)
            derivative = -(plus['energy']-minus['energy'])/(2*step)
            error = abs(projected-derivative)
            check(f'{name}_directional_force_error_h={step}',error,error<=tol['directional_force'])
        mol = gto.M(atom=atoms(xyz),unit='Bohr',basis=options['basis'],charge=charge,
                    spin=multiplicity-1,cart=False,verbose=0)
        mf = scf.RHF(mol)
        mf.conv_tol = config['pyscf_conv_tol']
        mf.max_cycle = options['max_iterations']
        energy = journal.call(name+'_pyscf_scf','pyscf_scf',mf.kernel,summary=float)
        check(name+'_pyscf_converged',bool(mf.converged),mf.converged)
        forces = journal.call(name+'_pyscf_gradient','pyscf_gradient',
                              lambda:-mf.nuc_grad_method().kernel(),summary=lambda a:a.tolist())
        ed = abs(cold[name]['energy']-energy)
        fd = float(np.max(np.abs(np.array(cold[name]['forces'])-forces)))
        check(name+'_independent_energy_error',ed,ed<=tol['independent_energy'])
        check(name+'_independent_force_error',fd,fd<=tol['independent_force'])

    checkpoint = out / 'source.vqcp'
    with prepare('prepare_source',geometries['source']) as batch:
        source_result = execute('source_batch_solve',batch)[0]
        matches('source_batch',source_result,cold['source'])
        journal.call('save_source','checkpoint_save',lambda:batch.save_checkpoint(checkpoint),summary=lambda x:x)

    # A checksum-correct nonstationary seed with deliberately false diagnostics.
    def rewrite(destination, mutate):
        manifest, arrays, _ = _read(checkpoint,1<<20)
        doc = manifest.to_dict()
        arrays = {k:np.array(v,copy=True) for k,v in arrays.items()}
        mutate(doc,arrays)
        payload = []
        offset = 0
        for blob in doc['blobs']:
            raw = arrays[blob['name']].astype('<f8').tobytes()
            blob.update(offset=offset,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            offset += len(raw)
            payload.append(raw)
        metadata = _json(doc)
        destination.write_bytes(_HEADER.pack(b'VQHFCP01',len(metadata),hashlib.sha256(metadata).digest())
                                + metadata + b''.join(payload))

    tampered = out / 'nonstationary_forged_diagnostics.vqcp'
    def falsify(doc,arrays):
        arrays['density_0'][0] = np.diag([2.,0.])
        doc['items'][0]['seed'].update(energy=-100.,density_rms=0.,iterations=1)
    journal.call('make_nonstationary_seed','asset_transform',lambda:rewrite(tampered,falsify))
    results = {}
    for label,path in (('exact_restart',checkpoint),('forged_diagnostics',tampered)):
        with prepare('prepare_'+label,geometries['source']) as batch:
            admission = journal.call('load_'+label,'checkpoint_load',lambda:batch.load_checkpoint(path),summary=lambda x:x)
            check(label+'_classification',admission['items'][0]['compatibility'],
                  admission['items'][0]['compatibility']=='exact_restart')
            check(label+'_verification_pending',admission['target_verification'],
                  admission['target_verification']=='pending_execute')
            result = execute(label+'_solve',batch)[0]
            results[label] = result
            matches(label,result,cold['source'])
            check(label+'_solve_was_executed',result['iterations'],result['iterations']>0)
            check(label+'_persistent_restart',result['restart_origin'],result['restart_origin']=='persistent_restart')
            check(label+'_verification_executed',batch.checkpoint_diagnostics['target_verification'],
                  batch.checkpoint_diagnostics['target_verification']=='executed')
    check('forged_energy_not_used',results['forged_diagnostics']['energy'],
          abs(results['forged_diagnostics']['energy']+100)>1.)
    check('nonstationary_seed_requires_iterations',results['forged_diagnostics']['iterations'],
          results['forged_diagnostics']['iterations']>1)

    with prepare('prepare_changed_geometry',geometries['target']) as batch:
        journal.call('reject_implicit_changed_geometry','checkpoint_load',
                     lambda:batch.load_checkpoint(checkpoint),expected_error=CheckpointError)
        admission = journal.call('allow_changed_geometry','checkpoint_load',
                    lambda:batch.load_checkpoint(checkpoint,allow_warm=True),summary=lambda x:x)
        check('changed_geometry_is_warm_only',admission['items'][0]['compatibility'],
              admission['items'][0]['compatibility']=='warm_start_compatible')
        results['changed_geometry'] = execute('changed_geometry_solve',batch)[0]
        matches('changed_geometry',results['changed_geometry'],cold['target'])

    invalid = out / 'wrong_electron_count.vqcp'
    journal.call('make_invalid_trace','asset_transform',
                 lambda:rewrite(invalid,lambda doc,arrays:arrays['density_0'].__imul__(0.5)))
    with prepare('prepare_atomic_restore',geometries['source']) as batch:
        journal.call('load_good_before_bad','checkpoint_load',lambda:batch.load_checkpoint(checkpoint))
        before,after = out/'before_rejection.vqcp',out/'after_rejection.vqcp'
        journal.call('snapshot_before_rejection','checkpoint_save',lambda:batch.save_checkpoint(before))
        rejection = journal.call('reject_wrong_trace','checkpoint_load',
                    lambda:batch.load_checkpoint(invalid),expected_error=CheckpointError)
        check('wrong_trace_error_is_physical',rejection['error'],'electron_count' in rejection['error'])
        journal.call('snapshot_after_rejection','checkpoint_save',lambda:batch.save_checkpoint(after))
        check('rejected_import_preserves_live_seed',sha(after),sha(before)==sha(after))
        results['after_rejection'] = execute('after_rejection_solve',batch)[0]
        matches('after_rejection',results['after_rejection'],cold['source'])
    with prepare('prepare_different_basis',geometries['source'],overrides={'basis':'def2-svp'}) as batch:
        rejection = journal.call('reject_basis_mismatch','checkpoint_load',
                     lambda:batch.load_checkpoint(checkpoint,allow_warm=True),expected_error=CheckpointError)
        check('basis_mismatch_reason',rejection['error'],'basis/AO transport required' in rejection['error'])
    dump('results.json',dict(cold=cold,reuse=results,
          checkpoint_hashes={p.name:sha(p) for p in out.glob('*.vqcp')},checks=checks,
          scope='H2 RHF/STO-3G neutral singlet only; no response/Hessian qualification or speedup claim.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    config = json.loads(args.config.read_text())
    journal = Journal(args.out,config['limits'])
    started = time.perf_counter()
    metadata = dict(started_at_utc=utc(),config_sha256=sha(args.config),driver_sha256=sha(__file__),
                    input_sha256=hashlib.sha256(json.dumps({k:config[k] for k in
                       ('symbols','charge','multiplicity','coordinate_unit','coordinates','direction')},
                       sort_keys=True).encode()).hexdigest(),
                    slurm_job_id=os.environ.get('SLURM_JOB_ID'),status='started')
    journal.emit(dict(kind='run',**metadata))
    exit_code = 0
    try:
        run(config,args.out,journal)
        metadata['status'] = 'passed'
    except Exception as error:
        exit_code = 1
        metadata.update(status='failed',error_type=type(error).__name__,error=str(error))
        (args.out/'traceback.txt').write_text(traceback.format_exc())
    metadata.update(ended_at_utc=utc(),elapsed_seconds=time.perf_counter()-started,
                    operation_attempts=dict(journal.counts))
    journal.emit(dict(kind='run',**metadata))
    (args.out/'run.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps(metadata,indent=2),flush=True)
    sys.exit(exit_code)
