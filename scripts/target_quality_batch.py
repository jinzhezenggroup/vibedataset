#!/usr/bin/env python3
"""Produce sparse QC response decisions from a pinned source index and optional measured history."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import contextmanager, nullcontext
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np

from gqc_dual_response import DualResponseModel, FIELD_IDS, OBSERVABLE_IDS, GQC_PIN
from generativeqc.response_problem import ResponseSolveError
from generativeqc.response_solver import solve_many
from probe_gqc_residual import array_hash, file_hash, json_hash
from target_response_quality import (SCHEMA, TOLERANCE, StabilityEvidence, check_direction,
                                     disposition, finite, linear_combination, scalar_result)

HISTORY = (('y', 'q0'), ('x', 'r2'))
UNITS = {'q0': 'e / au_field', 'r2': 'bohr^2 / au_field', 'zz': 'bohr^2 / au_field'}


def save(path, obj):
    data = (json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    path.write_bytes(data)
    return {'file': path.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


class Costs:
    def __init__(self):
        self.counts, self.native_kernels, self.stages = Counter(), [], []

    def measure(self, phase):
        return nullcontext()  # Explicit physical submissions below bypass run_round's projections.

    @contextmanager
    def stage(self, phase, **details):
        start = time.perf_counter()
        before = self.counts.copy()
        outcome = dict(phase=phase, status='completed', **details)
        try:
            yield outcome
        except Exception as error:
            outcome.update(status='failed', error=f'{type(error).__name__}: {error}')
            raise
        finally:
            outcome.update(seconds=time.perf_counter() - start, operations=dict(self.counts - before))
            self.stages.append(outcome)


def native_solve(model, columns, costs, phase):
    if not columns:
        return {}
    rhs = np.column_stack(list(columns.values()))
    with costs.stage(phase, columns=list(columns)):
        costs.counts['submitted_rhs'] += len(columns)
        costs.counts['submitted_blocks'] += 1
        result = solve_many(model, rhs, strategy='blocked', options=model.options, raise_on_failure=True,
                            collect_basis=False)
    return {k: (p.solution, float(p.residual_norm)) for k, p in zip(columns, result.results, strict=True)}


def solve_or_retry(model, columns, costs, phase):
    try:
        return native_solve(model, columns, costs, phase)
    except ResponseSolveError:
        if len(columns) <= 1:
            raise
        result = {}
        for key, value in columns.items():
            result.update(native_solve(model, {key: value}, costs, phase + '_single_retry'))
        return result


def scope_of(model):
    return {'problem': model.problem.identity, 'reference': model.ref.identity, 'operators': model.contract_identity,
            'source': model.source, 'units': UNITS, 'protocol': SCHEMA, 'target_absolute': TOLERANCE}


def produce(model, stability, costs, out):
    fields, obs = model.rhs_values['fields'], model.rhs_values['observables']
    directions = solve_or_retry(model, {k: fields[k] for k in ('x', 'y')}, costs, 'historical_solve')
    scalars, old_vectors, rounded, unrated = {}, {}, {}, {}
    scope = scope_of(model)
    for f, o in HISTORY:
        vector, _ = directions[f]
        with costs.stage('history_evidence', endpoint=[f, o]):
            evidence = check_direction(model, stability, vector, fields[f], {o: obs[o]})
        grade = evidence['projections'][o]
        if grade['status'] != 'accepted':
            raise ValueError('historical projection failed the numerical target budget')
        key = f + '/' + o
        binding = dict(field=model.endpoint_identity['fields'][f], readout=model.endpoint_identity['observables'][o],
                       unit=UNITS[o], rhs_sha256=array_hash(fields[f]), vector_sha256=array_hash(vector))
        scalars[key] = dict(grade, source=binding, direction_evidence=evidence)
        # Measured mid-rise decimal quantization in the control archive.
        q0 = grade['value']
        q1 = (math.floor(q0 * 1e6) + 0.5) / 1e6
        rounded[key] = dict(scalar_result(q1, grade['error_estimate'] + abs(q1 - q0), TOLERANCE),
                            source=binding, direction_evidence=evidence, quantization_delta=abs(q1 - q0))
        unrated[key] = dict(raw_value=q0, status='evidence_unavailable', source=binding)
        old_vectors[f] = dict(solution=vector.tolist(), source=binding)
    with costs.stage('store_history') as log:
        groups = {'scalars': scalars, 'vectors': old_vectors, 'quantized': rounded, 'unrated': unrated}
        files = {k: save(out / f'{model.name}-{k}.json', {'scope': scope, 'kind': k, 'assets': group})
                 for k, group in groups.items()}
        log['bytes_written'] = {k: v['bytes'] for k, v in files.items()}
    return files


def load_assets(root, entry, kind, model, costs):
    with costs.stage('read_history', kind=kind) as log:
        descriptor = entry['files'][kind]
        if descriptor['file'] != f'{model.name}-{kind}.json':
            raise ValueError('unexpected historical asset path')
        path = root / descriptor['file']
        data = path.read_bytes()
        log.update(bytes_read=len(data), expected_sha256=descriptor['sha256'])
        if (len(data) != descriptor['bytes'] or hashlib.sha256(data).hexdigest() != descriptor['sha256']):
            raise ValueError('historical bytes disagree with trusted producer digest')
        saved = json.loads(data)
        if (not isinstance(saved, dict) or saved.get('scope') != scope_of(model) or saved.get('kind') != kind or
                not isinstance(saved.get('assets'), dict)):
            raise ValueError('historical protocol, problem, operators, units or source differ')
        verified = {}
        for key, item in saved['assets'].items():
            try:
                binding = item['source']
                f = key.split('/')[0]
                if (binding['field'] != model.endpoint_identity['fields'][f] or
                        binding['rhs_sha256'] != array_hash(model.rhs_values['fields'][f])):
                    raise ValueError('historical RHS identity differs')
                if kind == 'vectors':
                    x = np.asarray(item['solution'], dtype=np.float64)
                    if x.shape != (model.dimension,) or not np.isfinite(x).all() or array_hash(x) != binding['vector_sha256']:
                        raise ValueError('historical vector content differs')
                else:
                    _, o = key.split('/')
                    if binding['readout'] != model.endpoint_identity['observables'][o] or binding['unit'] != UNITS[o]:
                        raise ValueError('historical readout or unit differs')
                    if 'error_estimate' not in item or 'direction_evidence' not in item:
                        verified[key] = disposition('evidence_unavailable', 'historical readout lacks measured error evidence')
                        continue
                    evidence = item['direction_evidence']
                    original = evidence['projections'][o]
                    if (item['schema'] != SCHEMA or item['status'] not in ('accepted', 'refine') or
                            evidence['schema'] != SCHEMA or evidence['rhs_sha256'] != binding['rhs_sha256'] or
                            evidence['vector_sha256'] != binding['vector_sha256'] or original['status'] != 'accepted' or
                            original['readout_sha256'] != array_hash(model.rhs_values['observables'][o]) or
                            not all(finite(x) for x in (item['raw_value'], item['error_estimate'], original['error_estimate'],
                                                        original['value'])) or original['error_estimate'] < 0 or
                            item['error_estimate'] < original['error_estimate'] + abs(item['raw_value'] - original['value'])):
                        raise ValueError('historical error, producer measurement or output identity differs')
                verified[key] = item
            except (TypeError, ValueError, KeyError, OverflowError) as error:
                verified[key] = disposition('reject', str(error))
        return verified


def complete(model, stability, costs, requests, method, assets):
    fields, obs = model.rhs_values['fields'], model.rhs_values['observables']
    columns = {f: fields[f] for f, _ in requests}
    want = {f: {o for field, o in requests if field == f} for f in columns}
    combinations, retained = {}, {}
    # Fixed x+y trial is eligible only when both axes are requested and every
    # affected observable has an independently bound same-readout operand.
    if method in ('mixed', 'quantized', 'unrated') and {'x', 'y'} <= columns.keys():
        for f, o in requests:
            if f in ('x', 'y'):
                other = 'y' if f == 'x' else 'x'
                combinations[(f, o)] = other + '/' + o
        if all(dep in assets for dep in combinations.values()):
            del columns['x'], columns['y']
            columns['x+y'] = fields['x'] + fields['y']
            want['x+y'] = {o for _, o in combinations}
        else:
            combinations.clear()
    if method == 'retained':
        retained = {f: (np.asarray(assets[f]['solution'], dtype=np.float64), None)
                    for f in columns if f in assets and 'solution' in assets[f]}
    invalid_vectors = {f for f in columns if method == 'retained' and f in assets and f not in retained}
    new = {k: v for k, v in columns.items() if k not in retained and k not in invalid_vectors}
    if method == 'dense':
        with costs.stage('dense_requested_solve', rhs=len(new)):
            costs.counts['dense_solve_rhs'] += len(new)
            x = np.linalg.solve(stability.matrix, np.column_stack(list(new.values())))
            solved = {k: (x[:, j], None) for j, k in enumerate(new)}
    else:
        solved = solve_or_retry(model, new, costs, 'requested_solve')
    directions = {**retained, **solved}
    checked = {(f, o): assets[f] for f, o in requests if f in invalid_vectors}
    evidence = {}
    budget = len({f for f, _ in requests})
    new_actions = 0
    for key, (vector, reported) in directions.items():
        if new_actions >= budget:
            raise ValueError('plan exceeds allocated physical validation actions')
        with costs.stage('target_evidence', column=key, vector_bytes=vector.nbytes, rhs_bytes=columns[key].nbytes,
                         readout_bytes=sum(obs[o].nbytes for o in want[key])):
            result = check_direction(model, stability, vector, columns[key], {o: obs[o] for o in sorted(want[key])})
        result['solution'] = vector.tolist()
        new_actions += result.get('extra_native_actions', 0)
        evidence[key] = result
        for o, projection in result['projections'].items():
            checked[(key, o)] = projection
    initial, final = {}, {}
    for f, o in requests:
        if (f, o) in combinations:
            old = assets[combinations[(f, o)]]
            candidate = linear_combination([(1., checked[('x+y', o)]), (-1., old)])
            candidate.update(history_operand=combinations[(f, o)], historical_error=old.get('error_estimate'))
        else:
            candidate = checked[(f, o)]
        initial[(f, o)] = candidate
    retry = {f: fields[f] for (f, o), row in initial.items() if row['status'] == 'refine'}
    retried = solve_or_retry(model, retry, costs, 'ordinary_refinement')
    for f, (vector, reported) in retried.items():
        use_reported = new_actions >= budget
        with costs.stage('refinement_evidence', column=f, uses_solver_true_residual=use_reported,
                         vector_bytes=vector.nbytes, rhs_bytes=fields[f].nbytes):
            result = check_direction(model, stability, vector, fields[f],
                                     {o: obs[o] for (field, o), row in initial.items()
                                      if field == f and row['status'] == 'refine'},
                                     measured_residual=reported if use_reported else None)
        new_actions += result.get('extra_native_actions', 0)
        result['solution'] = vector.tolist()
        evidence['refine/' + f] = result
        final.update({(f, o): row for o, row in result['projections'].items()})
    decisions = [{'field': f, 'observable': o, 'initial': row, 'final': final.get((f, o), row)}
                 for (f, o), row in initial.items()]
    return decisions, evidence, {'physical_actions': new_actions, 'limit': budget}


def main():
    p = ArgumentParser(description=__doc__)
    p.add_argument('--source-index', type=Path, required=True)
    p.add_argument('--source-sha256', required=True)
    p.add_argument('--record', help='optional individual source ID')
    p.add_argument('--mode', choices=('history', 'mixed', 'retained', 'ordinary', 'dense', 'quantized', 'unrated'),
                   required=True)
    p.add_argument('--requests', type=Path, help='JSON list of [field,observable] pairs for completion')
    p.add_argument('--history', nargs=2, metavar=('SHA256', 'MANIFEST'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--kernel-cache', type=Path, required=True)
    args = p.parse_args()
    started = time.perf_counter()
    try:
        raw_source = args.source_index.read_bytes()
        if hashlib.sha256(raw_source).hexdigest() != args.source_sha256:
            p.error('source index digest mismatch')
        source = json.loads(raw_source)
        if (not isinstance(source, dict) or not isinstance(source.get('rows'), list) or
                not all(isinstance(r, dict) and isinstance(r.get('status'), str) for r in source['rows'])):
            p.error('invalid source index rows')
        names = [r['name'] for r in source['rows'] if r.get('name') is not None]
        if not all(isinstance(n, str) for n in names) or len(set(names)) != len(names):
            p.error('invalid or ambiguous source record IDs')
        if args.record is not None and args.record not in names:
            p.error('requested record is absent from source index')
        requests = []
        if args.mode != 'history':
            if args.requests is None:
                p.error('completion requires --requests')
            requests = json.loads(args.requests.read_bytes())
            if (not isinstance(requests, list) or not requests or
                    not all(isinstance(r, list) and len(r) == 2 and r[0] in FIELD_IDS and r[1] in OBSERVABLE_IDS
                            for r in requests) or len(set(map(tuple, requests))) != len(requests)):
                p.error('completion requires distinct [field, observable] request pairs')
    except (OSError, ValueError, UnicodeError) as error:
        p.error(str(error))
    needs_history = args.mode in ('retained', 'mixed', 'quantized', 'unrated')
    prior, history_error = None, None
    if needs_history:
        if not args.history:
            p.error('a producer manifest and separate trusted digest are required')
        digest, filename = args.history
        path = Path(filename)
        try:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('historical producer manifest digest mismatch')
            prior = json.loads(raw)
            if (not isinstance(prior, dict) or prior.get('source_index_sha256') != args.source_sha256 or
                    prior.get('mode') != 'history' or not isinstance(prior.get('records'), list) or
                    not all(isinstance(r, dict) and isinstance(r.get('name'), str) for r in prior['records'])):
                raise ValueError('invalid producer manifest or different historical catalog')
            ids = [r['name'] for r in prior['records']]
            if len(set(ids)) != len(ids):
                raise ValueError('ambiguous history record ID')
        except (OSError, ValueError) as error:
            history_error = error
    try:
        args.out.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        p.error(str(error))
    records = []
    for row in source['rows']:
        name = row.get('name')
        if not name or (args.record and name != args.record):
            continue
        record = {'name': name, 'source_status': row['status']}
        costs = Costs()
        try:
            if row['status'] != 'verified':
                raise LookupError(row.get('error', 'source state unavailable'))
            meta, array = (args.source_index.parent / row[k] for k in ('metadata_file', 'array_file'))
            with costs.stage('source_hashes') as step:
                step['bytes_read'] = meta.stat().st_size + array.stat().st_size
                if file_hash(meta) != row['metadata_sha256'] or file_hash(array) != row['array_file_sha256']:
                    raise ValueError('source metadata or array digest mismatch')
            with costs.stage('model_setup') as step:
                model = DualResponseModel(meta, array, args.kernel_cache, meter=costs)
                step['input_file_bytes'] = meta.stat().st_size + array.stat().st_size
                if model.ref.identity != row['reference_identity'] or model.name != name:
                    raise ValueError('state identity mismatch')
            record['scope'] = scope_of(model)
            with costs.stage('stability_evidence'):
                stability = StabilityEvidence.from_model(model)
            record['stability'] = stability.report
            if stability.matrix is None:
                raise LookupError(stability.report['reason'])
            if args.mode == 'history':
                record['files'] = produce(model, stability, costs, args.out)
            else:
                assets = {}
                if needs_history:
                    kind = {'mixed': 'scalars', 'retained': 'vectors'}.get(args.mode, args.mode)
                    try:
                        if history_error:
                            raise history_error
                        produced = next((r for r in prior['records'] if r['name'] == name), {})
                        if not produced.get('files'):
                            raise LookupError('no measured historical asset for this state')
                        assets = load_assets(path.parent, produced, kind, model, costs)
                    except (OSError, KeyError, LookupError, TypeError, ValueError, OverflowError) as error:
                        status = 'evidence_unavailable' if isinstance(error, (OSError, LookupError)) else 'reject'
                        # Preserve independent ordinary requests when an external archive is unusable.
                        keys = [f for f, _ in HISTORY] if kind == 'vectors' else [f + '/' + o for f, o in HISTORY]
                        assets = {key: disposition(status, str(error)) for key in keys}
                record['decisions'], record['directions'], record['validation_budget'] = complete(
                    model, stability, costs, requests, args.mode, assets)
            record['status'] = 'completed'
        except (OSError, ValueError, KeyError, LookupError, ArithmeticError, ResponseSolveError, np.linalg.LinAlgError) as e:
            status = 'evidence_unavailable' if isinstance(e, (LookupError, ResponseSolveError, np.linalg.LinAlgError)) else 'reject'
            record.update(status=status, reason=str(e), decisions=[dict(field=f, observable=o,
                          initial=disposition(status, str(e)), final=disposition(status, str(e))) for f, o in requests])
        record.update(costs=costs.stages, operations=dict(costs.counts))
        records.append(record)
    report = {'schema': SCHEMA, 'mode': args.mode, 'source_index_sha256': args.source_sha256,
              'history_manifest_sha256': args.history[0] if args.history else None,
              'requests': requests, 'record_filter': args.record, 'records': records, 'gqc': GQC_PIN,
              'code': {p.name: file_hash(p) for p in map(Path, (__file__, __import__('target_response_quality').__file__,
                        __import__('gqc_dual_response').__file__, __import__('probe_gqc_residual').__file__))},
              'python': sys.version, 'numpy': np.__version__,
              'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
              'seconds': time.perf_counter() - started}
    print(save(args.out / 'report.json', report)['sha256'], args.mode)


if __name__ == '__main__':
    main()
