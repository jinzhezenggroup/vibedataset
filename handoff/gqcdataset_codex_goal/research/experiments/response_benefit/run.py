"""Measure conditional response costs without reading independent target labels."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
from complete_response_dataset import AttemptMeter, UNITS
from gqc_dual_response import DualResponseModel, GATE, GQC_PIN, response_work, solve_many
from probe_gqc_residual import array_hash, check, file_hash, git, json_hash
from generativeqc_compiler.common.cpp_adapter import CppCompilerAdapter
from generativeqc_compiler.tensor import Program, TensorSpec, add, input_tensor
from generativeqc_compiler.tensor.cpu import NativeTensorProgram
import numpy as np
import pyscf
import scipy

from plans import ALL, FIELDS, HISTORIES, MIXED, OBS, SCENARIOS, STRATEGIES, compile_plan, ordinary, plan_cover, spec

Q_COMMIT = '18f1a095a7444ed8d3b23ba873b5cadfc54daebc'
Q_SHA = '6a09f3bc81d47180f7667ea2d986fd62c6acfa80db52e3062f8517fae2c15ee6'
clock = time.perf_counter


def payload(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, obj, compressed=False):
    start = clock()
    data = payload(obj)
    if compressed:
        data = gzip.compress(data, compresslevel=6, mtime=0)
    with path.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return {'path': path.name, 'sha256': digest(data), 'bytes': len(data), 'seconds': clock() - start}


def load(root, rec, identity):
    data = (root / rec['path']).read_bytes()
    check(len(data) == rec['bytes'] and digest(data) == rec['sha256'], 'asset bytes or digest')
    obj = json.loads(gzip.decompress(data) if rec['path'].endswith('.gz') else data)
    check(obj['identity'] == identity, 'scientific source, contract or qualification scope')
    return obj['rows']


def journal(directory, data):
    with (directory / 'events.jsonl').open('ab') as f:
        f.write(payload(data))
        f.flush()
        os.fsync(f.fileno())


def quality_code(work):
    raw = subprocess.check_output(['git', 'show', Q_COMMIT + ':scripts/target_response_quality.py'], cwd=ROOT)
    check(digest(raw) == Q_SHA, 'quality-evidence source digest')
    dest = work / 'target_response_quality.py'
    dest.write_bytes(raw)
    spec_ = importlib.util.spec_from_file_location('target_response_quality', dest)
    module = importlib.util.module_from_spec(spec_)
    sys.modules[spec_.name] = module
    spec_.loader.exec_module(module)
    return module


def refs(model, col):
    if col in MIXED:
        rhs, info = model._combined_column(spec(col), OBS)
        return rhs, info['field_identity'], model.rhs_values['observables']
    group, other = ('fields', 'observables') if col in FIELDS else ('observables', 'fields')
    return model.rhs_values[group][col], model.endpoint_identity[group][col], model.rhs_values[other]


def columns(model, quality, stability, plan, old, trace, keep=False, dense=False):
    names, outputs = plan
    contractions = {c: {} for c in names}
    for _, _, terms in outputs:
        for c, p, _ in terms:
            if c in contractions:
                contractions[c][p] = None
    new_names = [n for n in names if n not in old]
    inputs = {n: refs(model, n) for n in names}
    candidates = {}
    if new_names and dense:
        start = clock()
        rhs = np.column_stack([inputs[n][0] for n in new_names])
        trace['dense_solves'] += 1
        trace['dense_rhs'] += len(new_names)
        x = np.linalg.solve(stability.matrix, rhs)
        trace['dense_seconds'] += clock() - start
        candidates = {n: (x[:, j], None) for j, n in enumerate(new_names)}
    elif new_names:
        panel = np.column_stack([inputs[n][0] for n in new_names])
        model.counts['submitted_blocks'] += 1
        model.counts['submitted_rhs'] += len(new_names)
        start = clock()
        result = solve_many(model, panel, strategy='blocked', options=model.options,
                            raise_on_failure=True, collect_basis=False)
        trace['solve_seconds'] += clock() - start
        trace['blocks'].append(dict(columns=new_names, rhs_rank=result.rhs_rank, native_actions=result.operator_actions))
        candidates = {n: (part.solution, float(part.residual_norm))
                      for n, part in zip(new_names, result.results, strict=True)}
    projected, retained = {}, {}
    for n in names:
        b, identifier, readouts = inputs[n]
        start = clock()
        if n in old:
            saved = old[n]
            vec = np.asarray(saved['solution'], dtype=np.float64)
            check((saved['endpoint'], saved['rhs_sha256'], saved['solution_sha256']) ==
                  (identifier, array_hash(b), array_hash(vec)), 'stale retained direction')
            residual = None
        else:
            vec, residual = candidates[n]
            check((dense or residual <= GATE) and np.isfinite(vec).all(), 'new response vector or native residual')
        proof = quality.check_direction(model, stability, vec, b, {k: readouts[k] for k in sorted(contractions[n])},
                                        measured_residual=residual)
        trace['quality_seconds'] += clock() - start
        trace['quality_native_actions'] += int(residual is None)
        trace['directions'].append(dict(column=n, identity=identifier, from_store=n in old, proof=proof))
        check(proof.get('physical_residual_l2', float('inf')) <= GATE, 'physical residual or missing evidence')
        for label, evidence in proof['projections'].items():
            projected[n, label] = evidence
        if keep:
            retained[n] = {'endpoint': identifier, 'rhs_sha256': array_hash(b),
                           'solution_sha256': array_hash(vec), 'solution': vec.tolist()}
    return projected, retained


class Decoders:
    def __init__(self, kernel_dir):
        self.directory = kernel_dir
        self.loaded = {}

    def value(self, weights, values, trace):
        key = tuple(weights)
        start = clock()
        if key not in self.loaded:
            names = ['t' + str(i) for i in range(len(key))]
            inputs = [input_tensor(n, TensorSpec(role='input')) for n in names]
            kernel = Program({'target': add(*inputs, coefficients=tuple(Fraction(w) for w in weights))},
                             provenance={'purpose': 'target from measured same-readout response terms'})
            native = NativeTensorProgram(kernel, compiler=CppCompilerAdapter(Path('c++')), cache=self.directory,
                                         max_bytes=1 << 20, max_work=1000)
            self.loaded[key] = names, native
            trace['decoder_builds'].append(dict(weights=key, binary_sha256=file_hash(native.library._name),
                                               seconds=clock() - start))
        names, native = self.loaded[key]
        return float(native.execute({n: np.asarray(v) for n, v in zip(names, values)})['target'])


def evaluate(model, quality, stability, plan, history, vectors, trace, decoders, compiled=False, keep=False, dense=False):
    projected, retained = columns(model, quality, stability, plan, vectors, trace, keep, dense)
    joined = {**projected, **{('H:' + f, o): v for (f, o), v in history.items()}}
    answers = {}
    for f, o, terms in plan[1]:
        key = f + '/' + o
        trace['terms'][key] = terms
        if len(terms) == 1 and terms[0][2] == 1:
            candidate = dict(joined[terms[0][:2]])
        else:
            t = clock()
            measures = [(w, joined[c, p]) for c, p, w in terms]
            candidate = quality.linear_combination(measures)
            trace['quality_seconds'] += clock() - t
            check(candidate.get('raw_value') is not None, 'unqualified or missing term')
            w = [coef for coef, _ in measures]
            vs = [z['raw_value'] for _, z in measures]
            hand = sum(k * v for k, v in zip(w, vs))
            value = decoders.value(w, vs, trace) if compiled else hand
            error = candidate['error_estimate'] + abs(value - candidate['raw_value'])
            candidate.update(raw_value=value, implementation_vs_hand=abs(value - hand), error_estimate=error,
                             value=value if error <= quality.TOLERANCE else None,
                             status='accepted' if error <= quality.TOLERANCE else 'refine')
        check(candidate.get('status') == 'accepted' and abs(candidate['error_estimate']) <= quality.TOLERANCE,
              'target error budget ' + key)
        candidate.update(source=model.name, unit=UNITS[o], target_identity=json_hash(
            [model.endpoint_identity['fields'][f], model.endpoint_identity['observables'][o]]))
        answers[f, o] = candidate
    return answers, retained


def new_trace():
    return {'blocks': [], 'directions': [], 'terms': {}, 'quality_native_actions': 0, 'quality_seconds': 0.,
            'solve_seconds': 0., 'decoder_builds': [], 'planning_seconds': 0., 'input_bytes': 0,
            'input_seconds': 0., 'fallback': [], 'dense_solves': 0, 'dense_rhs': 0, 'dense_seconds': 0.}


def produce(ctx, kind, directory, identity, trace):
    model, quality, stability, decoders = ctx
    start = clock()
    if kind in HISTORIES:
        edges = HISTORIES[kind]
        fields, _ = plan_cover(edges)
        plan = ordinary(edges, 'cover', fields)
    else:
        plan = ordinary(ALL, 'field' if kind == 'table_dense' else kind.split('_')[1])
    rows, vectors = evaluate(model, quality, stability, plan, {}, {}, trace, decoders, keep=kind in HISTORIES, dense=kind == 'table_dense')
    trace['production_seconds_before_writes'] = clock() - start
    scalar = {f + '/' + o: val for (f, o), val in rows.items()}
    rec = {'scalars': save(directory / (kind + '.json'), {'identity': identity, 'rows': scalar}),
           'history_keys': sorted(rows), 'stored_directions': sorted(vectors)}
    if kind in HISTORIES:
        obj = {'identity': identity, 'rows': vectors}
        rec['vectors'] = save(directory / (kind + '-vectors.json'), obj)
        rec['vectors_gzip'] = save(directory / (kind + '-vectors.json.gz'), obj, compressed=True)
    trace['assets'] = rec
    return rec


def serve(ctx, scenario, method, assets, directory, identity, trace):
    model, quality, stability, decoders = ctx
    mask, requests = SCENARIOS[scenario]
    table = method.startswith('table_')
    rec = assets[method if table else mask]
    stored = tuple(rec['stored_directions']) if method.startswith('vectors') else ()
    known = tuple(map(tuple, rec['history_keys']))
    def read(kind):
        t = clock()
        receipt = rec[kind]
        trace['input_bytes'] += receipt['bytes']
        trace['input_sha256'] = receipt['sha256']
        try:
            return load(directory, receipt, identity)
        finally:
            trace['input_seconds'] += clock() - t

    try:
        if table:
            history = read('scalars')
            result = {(f, o): history[f + '/' + o] for f, o in requests}
        else:
            selector = 'vectors' if method.startswith('vectors') else method
            t = clock()
            count = compile_plan.cache_info().hits
            plan = compile_plan(selector, requests, known, stored)
            trace['planning_seconds'] = clock() - t
            trace['plan_cache_hit'] = compile_plan.cache_info().hits != count
            use_old = any(c.startswith('H:') for _, _, terms in plan[1] for c, _, _ in terms)
            hist = {tuple(k.split('/')): v for k, v in read('scalars').items()} if use_old else {}
            vectors = read(method) if set(plan[0]).intersection(stored) else {}
            result, _ = evaluate(model, quality, stability, plan, hist, vectors, trace, decoders,
                                 compiled=method in ('single', 'two'), dense=method == 'dense')
    except (ValueError, ArithmeticError, RuntimeError, OSError, KeyError) as error:
        trace['fallback'].append(dict(reason=str(error), phase='candidate', submitted=dict(model.counts)))
        result, _ = evaluate(model, quality, stability, ordinary(requests, 'field'), {}, {}, trace, decoders)
    trace['outputs'] = {f + '/' + o: v for (f, o), v in result.items()}
    for (f, o), r in result.items():
        check(r['source'] == model.name and r['unit'] == UNITS[o] and r['status'] == 'accepted'
              and 0 <= r['error_estimate'] <= quality.TOLERANCE and math.isfinite(r['value'])
              and r['target_identity'] == json_hash([model.endpoint_identity['fields'][f],
                                                      model.endpoint_identity['observables'][o]]), 'final target identity or evidence')
    trace['output_asset'] = save(directory / (scenario + '-' + method + '.json'),
                                 {'identity': identity, 'rows': trace['outputs']})


def record(out, model, base, action):
    before = model.counts.copy()
    start = clock()
    trace = new_trace()
    try:
        result = action(trace)
        trace['status'] = 'completed'
    except Exception as exc:
        trace.update(status='failed', reason=type(exc).__name__ + ': ' + str(exc))
        result = None
    trace.update(cost=response_work(model.counts - before), seconds=clock() - start)
    journal(out, {**base, **trace})
    return result


def setup(out, meta, array, cache, kind, name):
    meter = AttemptMeter()
    start = clock()
    before = len(list(cache.rglob('*.so')))
    try:
        model = DualResponseModel(meta, array, cache, meter=meter)
    except Exception as err:
        journal(out, dict(phase='setup', source=name, kind=kind, status='failed', reason=str(err),
                          cost=dict(meter.counts), stages=meter.stages, seconds=clock() - start))
        raise
    journal(out, dict(phase='setup', source=name, kind=kind, status='completed', setup=model.setup,
                      cache_libraries_before=before, cache_libraries_after=len(list(cache.rglob('*.so'))),
                      cost=dict(meter.counts), seconds=clock() - start))
    return model


def run_case(out, catalog, row, quality, budget_start, total_jk):
    name = row['name']
    meta, array = (catalog / row[k] for k in ('metadata_file', 'array_file'))
    directory = out / name
    directory.mkdir()
    start = clock()
    check((file_hash(meta), file_hash(array)) == (row['metadata_sha256'], row['array_file_sha256']), 'source digest')
    io_seconds = clock() - start
    cache = directory / 'native'
    cold = setup(out, meta, array, cache, 'first', name)
    model = setup(out, meta, array, cache, 'reopen', name)
    quality_info = quality.StabilityEvidence.from_model(model)
    journal(out, dict(phase='quality_setup', source=name, report=quality_info.report, input_bytes=meta.stat().st_size +
                      array.stat().st_size, input_hash_seconds=io_seconds))
    check(quality_info.report['status'] == 'available', 'unavailable stability evidence')
    scope = json_hash({'problem': model.problem.identity, 'source': model.source,
                       'contract': model.contract_identity, 'units': UNITS, 'quality_sha256': Q_SHA,
                       'matrix': quality_info.report['matrix_sha256']})
    ctx = model, quality, quality_info, Decoders(directory / 'decoders')
    for rep in range(4):
        where = directory / ('rep' + str(rep))
        where.mkdir()
        base = dict(source=name, repetition=rep, warmup=rep == 0, split='development' if catalog.name == 'qm9_response_assets' else 'holdout')
        assets = {}
        for h in (*HISTORIES, 'table_field', 'table_adjoint', 'table_dense'):
            assets[h] = record(out, model, dict(**base, phase='history', kind=h),
                               lambda trace: produce(ctx, h, where, scope, trace))
        for i, scenario in enumerate(SCENARIOS):
            methods = list(STRATEGIES)
            random.Random(15017 + row['qm9_id'] * 100 + i * 10 + rep).shuffle(methods)
            for order, method in enumerate(methods):
                if total_jk + model.counts['jk_calls'] > 250_000 or clock() - budget_start > 3600:
                    raise RuntimeError('preregistered compute budget reached')
                record(out, model, dict(**base, phase='future', scenario=scenario, method=method, order=order),
                       lambda trace: serve(ctx, scenario, method, assets, where, scope, trace))
    return cold.counts['jk_calls'] + model.counts['jk_calls']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cpu', type=int, default=0)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.sched_setaffinity(0, {args.cpu})
    threads = {k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}
    check(all(n == '1' for n in threads.values()), 'single-thread environment required')
    quality = quality_code(out)
    sources = (HERE.parent / 'qm9_response_assets', HERE.parent / 'qm9_extension/assets')
    protocol = dict(project=git(ROOT, 'rev-parse', 'HEAD'), gqc=GQC_PIN, scripts={k: file_hash(HERE / k)
                    for k in ('run.py', 'plans.py', 'protocol.md')}, q14_commit=Q_COMMIT, q14_sha256=Q_SHA,
                    source_indexes={str(p.relative_to(HERE.parent)): file_hash(p / 'index.json') for p in sources},
                    cpu=list(os.sched_getaffinity(0)), cpu_model=next(l.split(':', 1)[1].strip() for l in
                    Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),
                    python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__, pyscf=pyscf.__version__,
                    compiler=subprocess.check_output(['c++', '--version'], text=True).splitlines()[0], threads=threads,
                    sccache_dir=os.environ.get('SCCACHE_DIR'), sccache_server_port=os.environ.get('SCCACHE_SERVER_PORT'),
                    utc=datetime.now(timezone.utc).isoformat())
    save(out / 'protocol.json', protocol)
    start = clock()
    total = 0
    for catalog in sources:
        for row in sorted(json.loads((catalog / 'index.json').read_bytes())['rows'], key=lambda x:x.get('name') or ''):
            if not row.get('name'):
                continue
            if row['status'] != 'verified':
                journal(out, dict(source=row['name'], phase='reference_unavailable', reason=row['error'],
                                  member=row['member_sha256']))
                continue
            total += run_case(out, catalog, row, quality, start, total)
            print(row['name'], total, flush=True)
    save(out / 'finished.json', dict(seconds=clock() - start, jk=total, journal_sha256=file_hash(out / 'events.jsonl')))


if __name__ == '__main__':
    main()
