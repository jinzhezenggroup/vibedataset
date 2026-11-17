#!/usr/bin/env python3
"""Cross-node PLAN-004 on QM9 water, using pinned GQC block GMRES and native CPU kernels."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np
import pyscf


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def command(*args):
    return subprocess.check_output(args, text=True).strip()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--project', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
root, out = args.project.resolve(), args.out.resolve()
out.mkdir(parents=True, exist_ok=False)
inputs = root / 'input'
source = root / '_references/gqc'
sys.path.insert(0, str(root / 'scripts'))

from gqc_dual_response import (DualResponseModel, GATE, NativeTensorProgram, CppCompilerAdapter,
                               Program, TensorSpec, add, input_tensor, file_hash, array_hash, check)
from generativeqc import response_solver

source_commit = '2791504cc238fe83d328fc1718080642b288222a'
helper_sha = {'gqc_dual_response.py': '1756a57cabda51408d6338687d702384e03afa46eba28cb30ebc37a7c0e14a15',
              'gqc_residual_plan.py': 'f8d98989b4cd1ed0f7de1827733454474579df0a0735604c6639756643f3fc19',
              'probe_gqc_residual.py': '6959858631769158358d17f80a159112e646d10dc59cd4b473f4929496ec9df7'}
input_sha = {'qm9-000003.json': 'c0e5212e5f0def071ff6ec5dac88c0f9b893aa9c10107e73c514edba6e416e8f',
             'qm9-000003.npz': '08d0cec5d6ac38620732cb37e07955668a07576e5ca3fc424212db1e8094f4ce',
             'oracle.json': 'e5b1d3a8d5c39b1cf530b966d2a6c1f0787a18c4015ccd682425104cc7f3cb6e'}
check(all(digest(root / 'scripts' / k) == v for k, v in helper_sha.items()), 'project helper checksums')
check(all(digest(inputs / k) == v for k, v in input_sha.items()), 'reference asset or oracle checksum')
check(command('git','-C',str(source),'rev-parse','HEAD') == source_commit, 'wrong GQC commit')
check(Path(response_solver.__file__).resolve().is_relative_to(source.resolve()), 'solver from other installation')
clock_start = time.perf_counter()
evidence = {'schema': 'vibedataset.plan004.n5.v1', 'status': 'started', 'attempts': [],
            'record': 'qm9-000003', 'gqc_commit': source_commit, 'gqc_tree': command('git','-C',str(source),'rev-parse','HEAD^{tree}'),
            'gqc_solver_blob': command('git','-C',str(source),'rev-parse','HEAD:python/generativeqc/response_solver.py'),
            'helper_commit': 'dbfde3ec34e9338c4fc6a0801c1251cf3cb22b6a', 'helpers_sha256': helper_sha,
            'inputs_sha256': input_sha, 'driver_sha256': digest(Path(__file__)),
            'environment': {'python': sys.version, 'numpy': np.__version__, 'pyscf': pyscf.__version__,
                            'scipy': __import__('scipy').__version__, 'host': platform.node(),
                            'cxx': command('c++','--version').splitlines()[0], 'sccache': command('sccache','--version'),
                            'sccache_sha256': digest(root/'bin/sccache'),
                            'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
                            'slurm_job': os.environ.get('SLURM_JOB_ID'), 'slurm_cpus': os.environ.get('SLURM_CPUS_PER_TASK'),
                            'slurm_gpus': os.environ.get('SLURM_JOB_GPUS'), 'cuda_visible': os.environ.get('CUDA_VISIBLE_DEVICES')}}
model = None
trace = []


class ObservedModel(DualResponseModel):
    def apply(self, vector):
        # Provenance only. Both call sites are frozen data in the verified solver Git blob.
        frame = sys._getframe(1)
        site = 'outside_block'
        while frame:
            if frame.f_code.co_filename == response_solver.__file__ and frame.f_lineno in (1602, 1642):
                site = {1602:'extension', 1642:'true_residual'}[frame.f_lineno]
                break
            frame = frame.f_back
        trace.append(site)
        return super().apply(vector)


def event(stage, state, **fields):
    row = dict(stage=stage, state=state, utc=datetime.now(timezone.utc).isoformat(),
               elapsed_seconds=time.perf_counter()-clock_start, **fields)
    with (out/'events.jsonl').open('a') as f:
        print(json.dumps(row, allow_nan=False), file=f, flush=True)


def stage(name, function):
    position = len(trace)
    before = model.counts.copy() if model is not None else Counter()
    t = time.perf_counter()
    event(name, 'start')
    result = {}
    try:
        result['output'] = function()
        result['status'] = 'completed'
        return result['output']
    except Exception as error:
        result['status'] = 'failed'
        result['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        delta = dict(model.counts-before) if model is not None else {}
        result.update(stage=name, seconds=time.perf_counter()-t, counts=delta, action_sites=trace[position:])
        evidence['attempts'].append(result)
        event(name, result['status'], counts=delta, seconds=result['seconds'])
        write(out/'result.json',evidence)


def setup():
    global model
    model = ObservedModel(inputs/'qm9-000003.json', inputs/'qm9-000003.npz', out/'native')
    model.attach_oracle(inputs/'oracle.json')
    return model.setup


def kernel(n):
    names = ['combined', 'first', 'second'][:1+n]
    terms = [input_tensor(name, TensorSpec(role='input')) for name in names]
    program = Program({'missing': add(*terms, coefficients=(1,)+(-1,)*n)})
    return NativeTensorProgram(program, compiler=CppCompilerAdapter(Path('c++')), cache=out/'native'/'decoder',
                               max_bytes=1 << 20, max_work=1000)


history_edges = [('y','q0'),('z','q0'),('x','r2'),('z','r2')]
targets = [('x','q0'),('y','r2'),('z','zz')]
history_path, vector_path = out/'history.json', out/'producer-vectors.json'


def produce():
    cache = model.new_cache()
    run = model.run_round(history_edges, [], ['q0','r2'], cache)
    rows = [{key: row[key] for key in ('field','observable','target_identity','qualified','value','errors','reasons')}
            for row in run['results']]
    check(all(row['qualified'] for row in rows), 'history failed its independent gate')
    write(history_path, {'problem': model.problem.identity, 'contract': model.contract_identity, 'rows': rows})
    model.save_cache(cache, vector_path)
    return {'raw': run, 'history_sha256': digest(history_path), 'history_bytes': history_path.stat().st_size,
            'vectors_sha256': digest(vector_path), 'vector_bytes': vector_path.stat().st_size}


def read_history(receipt):
    check(digest(history_path) == receipt['history_sha256'], 'history byte identity')
    item = json.loads(history_path.read_bytes())
    check((item['problem'],item['contract']) == (model.problem.identity, model.contract_identity), 'history scientific identity')
    prior = {}
    for row in item['rows']:
        edge = row['field'], row['observable']
        grade = model.assess(*edge, row['value'])
        check(grade['qualified'] and grade['target_identity'] == row['target_identity'], 'stored history grade')
        prior[edge] = row['value']
    check(set(prior) == set(history_edges), 'wrong historical operands')
    return prior


def panel(names):
    b = np.column_stack([columns[k] for k in names])
    start = len(trace)
    t = time.perf_counter()
    outcome = response_solver.solve_many(model, b, strategy='blocked', options=model.options,
                                         raise_on_failure=True, collect_basis=False)
    actions = trace[start:]
    check(len(actions) == outcome.operator_actions and 'outside_block' not in actions, 'solver action attribution')
    blocks = [(k, len(list(v))) for k,v in itertools.groupby(actions)]
    for part in outcome.results:
        check(part.converged and part.residual_norm <= GATE, 'physical block residual')
    raw = dict(columns=names, rhs_sha256=[array_hash(x) for x in b.T], initial_rank=outcome.rhs_rank,
               rank_deficient=outcome.rank_deficient_rhs, actions=outcome.operator_actions,
               extensions=actions.count('extension'), residual_checks=actions.count('true_residual'),
               action_runs=blocks, true_residuals=[float(p.residual_norm) for p in outcome.results],
               reasons=[p.reason for p in outcome.results], solution_sha256=[array_hash(p.solution) for p in outcome.results],
               wall_seconds=time.perf_counter()-t, operator_seconds=outcome.operator_seconds,
               orthogonalization_seconds=outcome.orthogonalization_seconds, workspace_bytes=outcome.peak_workspace_bytes)
    return dict(zip(names, outcome.solution.T,strict=True)), raw


def measure(groups, support, receipt):
    prior = read_history(receipt)
    vectors, logs = {}, []
    for names in groups:
        solved, facts = panel(names)
        logs.append(facts)
        vectors.update(solved)
    grades = []
    for f,o in targets:
        deps = []
        if support and f in 'xy':
            value = float(readouts[o] @ vectors[support])
            deps = [(g,o) for g in support if g != f]
            operands = [value] + [prior[e] for e in deps]
            feeds = {k:np.asarray(v, dtype=np.float64) for k,v in zip(('combined','first','second'),operands)}
            candidate = float(kernels[len(deps)].execute(feeds)['missing'])
            hand = value
            for edge in deps:
                hand -= prior[edge]
            check(abs(hand-candidate) <= 1e-14, 'compiled versus independent handwritten decoder')
        else:
            hand = float(readouts[o] @ vectors[f]) if f in vectors else float(columns[f] @ vectors['c_zz'])
            candidate = hand
        grade = model.assess(f,o,candidate)
        grade.update(operand_edges=deps, hand=hand)
        grades.append(grade)
    return dict(panels=logs, rows=grades, rhs=sum(map(len,groups)), jk=sum(p['actions'] for p in logs),
                qualified=sum(r['qualified'] is True for r in grades))


def reuse_vectors(receipt):
    check(digest(vector_path) == receipt['vectors_sha256'], 'stored vector identity')
    cache = model.load_cache(vector_path)
    return model.run_round(targets, ['z'], ['q0','r2'], cache)


try:
    stage('shared_setup', setup)
    receipt = stage('four_scalar_producer', produce)
    kernels = {}
    def compile_decoders():
        for n in (1,2):
            kernels[n] = kernel(n)
        return {n: {'binary_sha256':file_hash(k.library._name), 'lowered':k.identity} for n,k in kernels.items()}
    stage('shared_decoders', compile_decoders)
    fields, readouts = model.rhs_values['fields'], model.rhs_values['observables']
    stacked = np.column_stack([fields[k] for k in 'xyz'])
    columns = dict(fields, xy=stacked @ np.array([1.,1.,0.]), xyz=stacked @ np.ones(3), c_zz=readouts['zz'])
    plans = [('ordinary_xyz',[['x','y','z']],None), ('separate_xyz_z',[['xyz'],['z']],'xyz'),
             ('joint_xyz_z',[['xyz','z']],'xyz'), ('joint_xy_z',[['xy','z']],'xy'),
             ('joint_xy_adjoint_zz',[['xy','c_zz']],'xy'), ('joint_xyz_adjoint_zz',[['xyz','c_zz']],'xyz')]
    compared = {}
    for name,groups,support in plans:
        compared[name] = stage(name, lambda: measure(groups,support,receipt))
    stored = stage('kept_historical_adjoint_vectors', lambda: reuse_vectors(receipt))
    ordinary = [r['raw_value'] for r in compared['ordinary_xyz']['rows']]
    evidence['differences_from_direct'] = {
        name: [abs(r['raw_value']-d) for r,d in zip(value['rows'], ordinary, strict=True)] for name,value in compared.items()}
    evidence['all_counts'] = dict(model.counts)
    evidence['status'] = 'passed' if all(r['qualified']==3 for r in compared.values()) and all(
        g['qualified'] for g in stored['results']) else 'completed_with_withheld'
except Exception:
    evidence.update(status='failed', traceback=traceback.format_exc(), all_counts=dict(model.counts) if model else {})
    raise
finally:
    evidence['seconds'] = time.perf_counter()-clock_start
    write(out/'result.json',evidence)
    print(json.dumps({k:evidence.get(k) for k in ('status','all_counts','seconds')}, allow_nan=False))
