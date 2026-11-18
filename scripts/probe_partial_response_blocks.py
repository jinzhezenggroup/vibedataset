#!/usr/bin/env python3
"""Execute and independently replay the two-round PLAN-004 cohort experiment."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
AXES = ('x', 'y', 'z')
READOUTS = ('q0', 'r2', 'zz')
POLICIES = ('ordinary', 'split_xyz', 'blocked_xyz', 'blocked_support', 'keep_history_vectors')
MODES = ('strict', 'diagnostic')
DIAGONAL = tuple(zip(AXES, READOUTS))
ALL_EDGES = set(itertools.product(AXES, READOUTS))
SCRIPTS = ('probe_partial_response_blocks.py', 'complete_response_dataset.py', 'gqc_dual_response.py',
           'response_field_plan.py', 'response_cover.py', 'probe_gqc_residual.py', 'probe_scalar_response.py')
GATE = 1e-10
SCALAR_TOL = 1e-8


def masks():
    def mixed(targets, left, right, full=False):
        field_a, obs_a = targets[left]
        field_b, obs_b = targets[right]
        third = next(f for f in AXES if f not in (field_a, field_b))
        rows = [(field_a, obs_b), (field_b, obs_a)]
        if full:
            rows.extend(((third, obs_a), (third, obs_b)))
        return tuple(sorted(rows))

    cases = [('empty', (), DIAGONAL), ('one_readout', (('y', 'q0'), ('z', 'q0')), DIAGONAL),
             ('six', tuple(sorted(ALL_EDGES - set(DIAGONAL))), DIAGONAL)]
    for left, right in ((0, 1), (1, 2), (2, 0)):
        for size in (2, 4):
            name = f'{AXES[left]}{AXES[right]}_{size}'
            cases.append((name, mixed(DIAGONAL, left, right, size == 4), DIAGONAL))
    shifted = tuple(zip(AXES, READOUTS[1:] + READOUTS[:1]))
    cases.append(('shifted_xy_2', mixed(shifted, 0, 1), shifted))
    return cases


def require(ok, message):
    if not ok:
        raise ValueError(message)


def dumps(obj):
    return (json.dumps(obj, separators=(',', ':'), sort_keys=True, allow_nan=False) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return {'bytes': len(data), 'sha256': digest(data)}


def read_saved(path, receipt):
    data = path.read_bytes()
    require(len(data) == receipt['bytes'] and digest(data) == receipt['sha256'], 'stored asset mismatch')
    return json.loads(data)


class Journal:
    def __init__(self, file):
        self.file = file
        self.index = 0

    def append(self, row):
        with self.file.open('ab') as stream:
            stream.write(dumps(row))
            stream.flush()
            os.fsync(stream.fileno())

    @contextmanager
    def measure(self, phase, **labels):
        self.index += 1
        event = dict(sequence=self.index, phase=phase, **labels)
        self.append({**event, 'event': 'started', 'utc': datetime.now(timezone.utc).isoformat()})
        start = time.perf_counter()
        try:
            yield event
        except BaseException as err:
            self.append({**event, 'event': 'failed', 'error': str(err), 'seconds': time.perf_counter() - start})
            raise
        self.append({**event, 'event': 'completed', 'seconds': time.perf_counter() - start})


@contextmanager
def capture_blocks(model, blocks):
    """Record each actual physical call separately, including production retries."""
    from unittest.mock import patch
    original = model.run_round

    def traced(requests, fields, observables, cache, **kwargs):
        before = model.counts.copy()
        start = time.perf_counter()
        row = dict(requests=list(requests), fields=list(fields), observables=list(observables),
                   support=kwargs.get('combined_coefficients'))
        blocks.append(row)
        try:
            output = original(row['requests'], row['fields'], row['observables'], cache, **kwargs)
        except Exception as err:
            row.update(error=f'{type(err).__name__}: {err}', jk_calls=model.counts['jk_calls'] - before['jk_calls'],
                       operator_actions=model.counts['response_operator_actions']-before['response_operator_actions'],
                       seconds=time.perf_counter()-start)
            raise
        row.update(counts=output['counts'].copy(), stats=dict(output['block']),
                   cache_checks=list(output['cache_checks']), seconds=time.perf_counter()-start)
        if 'combined' in output:
            row['combined'] = output['combined'].copy()
        return output

    with patch.object(model, 'run_round', traced):
        yield


def grade_asset(model, oracle, row, mode):
    from gqc_dual_response import assess_scalar
    edge = row['field'], row['observable']
    grade = assess_scalar(oracle if mode == 'strict' else None, model.endpoint_identity, *edge, row['raw_value'])
    if mode == 'strict' and not grade['qualified']:
        return None
    if mode == 'diagnostic':
        require(grade['qualified'] is None and grade['value'] is None and grade['raw_value'] is not None,
                'diagnostic must be unpublished')
        grade['status'] = 'residual_verified'
    grade['via'] = row['via']
    return grade


def history_phase(model, oracle, edges, name, path, identity, event):
    from response_cover import plan_cover
    event.update(history=edges, identity=identity)
    model.oracle = None
    cache = model.new_cache()
    fields, obs = plan_cover(edges)
    blocks = []
    t = time.perf_counter()
    with capture_blocks(model, blocks):
        result = model.run_round(edges, fields, obs, cache)
    solve_seconds = time.perf_counter() - t
    files = {}
    case = path.name
    producer = f'{model.name}/{case}/history'
    for mode in MODES:
        t = time.perf_counter()
        records = [g for row in result['results'] if (g := grade_asset(model, oracle, row, mode)) is not None]
        body = dict(schema='plan004.scalar_history.v1', source=name, mask=case, scope=identity, mode=mode,
                    problem=model.problem.identity, operator=model.contract_identity, producer=producer, records=records)
        receipt = save_file(path/(mode+'.json'), dumps(body))
        files[mode] = {**receipt, 'records': len(records), 'grade_and_write_seconds': time.perf_counter()-t}
    t = time.perf_counter()
    vector = save_file(path/'vectors.json', dumps(cache))
    vector['write_seconds'] = time.perf_counter() - t
    event.update(fields=fields, observables=obs, counts=result['counts'], blocks=blocks, projected=result['results'],
                 solve_seconds=solve_seconds, scalar_assets=files, vector_asset=vector, producer=producer)
    return {k:v for k,v in event.items() if k not in ('phase','sequence')}


def operands_for(model, mode, source, identity, path, receipt, producer):
    obj = read_saved(path/(mode+'.json'), receipt)
    require((obj['source'], obj['scope'], obj['problem'], obj['operator'], obj['producer'], obj['mode']) ==
            (source,identity,model.problem.identity,model.contract_identity,producer,mode), 'foreign scalar history')
    known = {}
    for row in obj['records']:
        edge = row['field'], row['observable']
        require(row['target_identity'] == model.assess(*edge,row['raw_value'])['target_identity'], 'wrong target')
        if mode == 'strict':
            require(row['qualified'] is True and row['value'] == row['raw_value'], 'unqualified operand')
        else:
            require(row['qualified'] is None and row['value'] is None and row['status'] == 'residual_verified',
                    'invalid diagnostic observation')
            # The compiler consumes an input scalar through the "value" slot. This
            # private operand view never enters a label file or obtains a passing grade.
            row = dict(row, value=row['raw_value'])
        require(edge not in known, 'duplicate operand')
        known[edge] = row, producer, row['via']
    return known


def measure_policy(model, oracle, identity, history, requests, mode, policy, path, kernel_dir, event):
    from complete_response_dataset import complete_field_block, complete_missing_split
    from gqc_dual_response import assess_scalar
    from response_cover import plan_cover
    from response_field_plan import SUPPORTS
    if mode == 'strict':
        model.attach_oracle(oracle)
    else:
        model.oracle = None
    t = time.perf_counter()
    scalars = history['scalar_assets'][mode]
    known = operands_for(model,mode,model.name,identity,path,scalars,history['producer'])
    require(not set(known).intersection(requests), 'history overlaps requests')
    keep = policy == 'keep_history_vectors'
    cache = read_saved(path/'vectors.json',history['vector_asset']) if keep else model.new_cache()
    vector_bytes = history['vector_asset']['bytes'] if keep else 0
    io_read_seconds = time.perf_counter()-t
    blocks = []
    before = model.counts.copy()
    t = time.perf_counter()
    with capture_blocks(model,blocks):
        if policy in ('ordinary','keep_history_vectors'):
            fields, obs = plan_cover(requests,cache['fields'],cache['observables'])
            result = model.run_round(requests,fields,obs,cache)
        elif policy == 'split_xyz':
            result = complete_missing_split(model, requests, cache, kernel_dir, known)
        else:
            supports = (AXES,) if policy == 'blocked_xyz' else SUPPORTS
            result = complete_field_block(model, requests, cache, kernel_dir, known, supports=supports)
    solve_seconds = time.perf_counter()-t
    counts = result['counts']
    require(counts['jk_calls'] == model.counts['jk_calls']-before['jk_calls'], 'physical counts differ')
    require({(r['field'],r['observable']) for r in result['results']} == set(requests), 'request changed')
    relation = result.get('relation', {})
    for reconstruction in relation.get('reconstructions', []):
        edge = reconstruction['field'], reconstruction['observable']
        terms = reconstruction['operands']
        total = relation['combined']['values'][edge[1]]
        for term in terms:
            key = tuple(term['pair'])
            require(key in known and key[1] == edge[1] and term['value'] == known[key][0]['raw_value'],
                    'decoder did not consume the measured same-readout operand')
            total -= term['value']
        error = abs(total - reconstruction['candidate']['raw_value'])
        require(error <= 1e-10, 'hand subtraction disagreement')
        reconstruction['hand_absolute_difference'] = error
    diagnostic_assessments = []
    for row in result['results']:
        if mode == 'diagnostic':
            require(row['qualified'] is None and row['value'] is None, 'unexpected diagnostic publication')
            assessment = assess_scalar(oracle, model.endpoint_identity,row['field'],row['observable'],row['raw_value'])
            diagnostic_assessments.append({k:assessment[k] for k in ('field','observable','qualified','status','reasons')})
    t = time.perf_counter()
    publications = [r for r in result['results'] if mode == 'diagnostic' or r['qualified']]
    output = save_file(path/'out'/f'{mode}-{policy}.json',dumps(
        dict(schema='plan004.completion.v1',scope=identity,mode=mode,policy=policy,records=publications)))
    output['write_seconds'] = time.perf_counter()-t
    event.update(counts=counts, blocks=blocks, solve_seconds=solve_seconds, read_seconds=io_read_seconds,
                 results=result['results'], independent_checks_of_diagnostics=diagnostic_assessments,
                 relation=relation, available_old_scalars=len(known), history_scalar_bytes=scalars['bytes'],
                 history_vector_bytes=vector_bytes, asset_read_bytes=scalars['bytes']+vector_bytes,
                 second_asset=output, source_setup_jk=model.setup['counts']['jk_calls'],
                 history_jk=history['counts']['jk_calls'], history_rhs=history['counts']['rhs_columns'],
                 cumulative_jk=history['counts']['jk_calls']+counts['jk_calls'],
                 cumulative_rhs=history['counts']['rhs_columns']+counts['rhs_columns'],
                 cumulative_jk_including_setup=model.setup['counts']['jk_calls']+history['counts']['jk_calls']+counts['jk_calls'],
                 history_cost_seconds=history['solve_seconds']+scalars['grade_and_write_seconds']+
                        (history['vector_asset']['write_seconds'] if keep else 0.))
    return result['results']


def execute_source(arg):
    name,route,release,out,kernel_root = arg
    from complete_response_dataset import bound_context
    from gqc_dual_response import DualResponseModel
    start = time.perf_counter()
    src,res,member,source_index,oracle_index,_ = route
    meta,arr,oracle,endpoint,provenance,identity = bound_context(name,src,res,member,release,source_index,oracle_index)
    directory = out/'sources'/name
    directory.mkdir(parents=True)
    journal = Journal(directory/'operations.jsonl')
    kernel = kernel_root/name
    with journal.measure('setup',source=name) as event:
        model = DualResponseModel(meta,arr,kernel)
        model.attach_oracle(oracle)
        require(model.endpoint_identity == endpoint, 'bound operator changed')
        event.update(setup=model.setup, identity=identity, provenance=provenance)
    case_stats = []
    for number,(mask,edges,requests) in enumerate(masks()):
        path = directory/'assets'/mask
        with journal.measure('history',source=name,mask=mask) as event:
            history = history_phase(model,oracle,edges,name,path,identity,event)
        for mode in MODES:
            reference = None
            # Always establish the ordinary values before comparisons. Rotate
            # the four remaining configurations deterministically for timing.
            tail = list(POLICIES[1:])
            cut = (number+int(name.split('-')[-1])) % len(tail)
            for policy in [POLICIES[0], *(tail[cut:]+tail[:cut])]:
                with journal.measure('completion',source=name,mask=mask,mode=mode,policy=policy) as event:
                    rows = measure_policy(model,oracle,identity,history,requests,mode,policy,path,kernel,event)
                    vals = {(r['field'],r['observable']):r['raw_value'] for r in rows}
                    if reference is None:
                        reference = vals
                    deltas = [abs(vals[key]-reference[key]) for key in vals]
                    require(max(deltas) <= SCALAR_TOL, 'ordinary block disagreement')
                    event['max_difference_from_ordinary'] = max(deltas)
                    case_stats.append({k:event[k] for k in ('mask','mode','policy','counts','cumulative_jk','cumulative_rhs',
                         'cumulative_jk_including_setup','max_difference_from_ordinary','available_old_scalars',
                         'history_scalar_bytes','history_vector_bytes','solve_seconds')})
    return {'name':name,'setup_jk':model.setup['counts']['jk_calls'],'total_jk':model.counts['jk_calls'],
            'elapsed_seconds':time.perf_counter()-start,'strategies':case_stats}


def run(out, kernel, jobs, oracle_indexes=None):
    import numpy, pyscf, scipy
    from complete_response_dataset import DEFAULT_CATALOGS, route_catalogs
    from gqc_dual_response import GQC_PIN
    out.mkdir(parents=True,exist_ok=False)
    kernel.mkdir(parents=True,exist_ok=True)
    start = time.perf_counter()
    pairs = DEFAULT_CATALOGS
    if oracle_indexes is not None:
        pairs = [(source, oracle) for (source, _), oracle in zip(DEFAULT_CATALOGS, oracle_indexes, strict=True)]
    release, routes, _, catalogs = route_catalogs(pairs)
    sources = {name:{'stratum':r[0]['stratum'],'status':r[0]['status'],'reason':r[0].get('error'),
                     'member_sha256':r[0]['member_sha256'],'catalog':r[-1]} for name,r in sorted(routes.items())}
    time_env = {k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}
    require(all(v=='1' for v in time_env.values()), 'set OMP/BLAS/MKL thread counts to one')
    metadata = {'schema':'vibedataset.plan004.cohort.v1','source_commit':subprocess.check_output(
                ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'gqc_commit':GQC_PIN,
                'source_files':{k:digest((ROOT/'scripts'/k).read_bytes()) for k in SCRIPTS},
                'python':platform.python_version(),'platform':platform.platform(),'numpy':numpy.__version__,
                'scipy':scipy.__version__,'pyscf':pyscf.__version__,'threads':time_env,'jobs':jobs,
                'qualification':{'physical_residual':GATE,'same_operator_abs':SCALAR_TOL,'independent_cphf_abs':1e-8,
                   'finite_field_abs':1e-4,'finite_field_steps':[5e-4,2e-4]},
                'catalogs':catalogs,'source_candidates':sources,'release':release,'masks':masks(),'policies':POLICIES}
    save_file(out/'protocol.json',dumps(metadata))
    work = [(name,route,release,out,kernel) for name,route in sorted(routes.items()) if route[0]['status']=='verified']
    require(len(routes)==17 and len(work)==12, 'cohort drift')
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for result in pool.map(execute_source,work):
            save_file(out/'sources'/result['name']/'summary.json',dumps(result))
            print(result['name'], len(result['strategies']),'strategy runs',flush=True)
    save_file(out/'run.json',dumps({'wall_seconds':time.perf_counter()-start,'finished_utc':datetime.now(timezone.utc).isoformat()}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--kernel-cache', required=True, type=Path)
    p.add_argument('--oracle-indexes', nargs=2, type=Path, metavar=('SEED', 'EXTENSION'),
                   help='pin both qualification catalogs for a versioned replay')
    p.add_argument('--jobs', type=int, default=1, help='independent single-threaded molecular workers')
    args = p.parse_args()
    if args.jobs < 1:
        p.error('--jobs must be positive')
    run(args.out.resolve(), args.kernel_cache.resolve(), args.jobs, args.oracle_indexes)


if __name__ == '__main__':
    main()
