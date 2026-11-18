#!/usr/bin/env python3
"""Complete a JSONL batch of pinned QM9 static RHF response requests."""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from uuid import uuid4

import numpy as np

from cphf_reference import SCHEMA as CPHF_SCHEMA
from gqc_dual_response import ANALYTIC_TOL, FIELD_IDS, FIELD_TOL, GATE, GQC_PIN, OBSERVABLE_IDS, STEPS, DualResponseModel, assess_scalar
from gqc_dual_response import response_work
from probe_gqc_residual import ROOT, file_hash, json_hash
from probe_scalar_response import DIAGONAL, decoder, recoverable
from response_cover import plan_cover
from response_field_plan import SUPPORTS, plan_field_block
from generativeqc.response_solver import ResponseSolveError

EXPERIMENTS = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
LEGACY_CATALOGS = (
    (EXPERIMENTS/'qm9_response_assets/index.json', EXPERIMENTS/'gqc_dual_response/summary.json'),
    (EXPERIMENTS/'qm9_extension/assets/index.json', EXPERIMENTS/'qm9_extension/oracle-index.json'),
)
DEFAULT_CATALOGS = (
    (LEGACY_CATALOGS[0][0], EXPERIMENTS/'cphf_v2/seed/index.json'),
    (LEGACY_CATALOGS[1][0], EXPERIMENTS/'cphf_v2/extension/index.json'),
)
UNITS = {'q0': 'e / au_field', 'r2': 'bohr^2 / au_field', 'zz': 'bohr^2 / au_field'}
DEFINITION = {'method': 'conventional closed-shell all-electron RHF/STO-3G', 'precision': 'float64',
              'clamped_nuclei': True, 'reference_field_au': [0, 0, 0], 'origin_bohr': [0, 0, 0],
              'field_coupling': 'h0 + F*r', 'order': 1, 'q0': 'net Mulliken charge of atom 0',
              'r2': 'electronic sum of squared radii', 'zz': 'electronic sum of squared z coordinates'}


class RequestError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def compact(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False)


def strict_json(data):
    def invalid(token):
        raise ValueError(f'nonfinite JSON number: {token}')
    def unique(items):
        out = dict(items)
        if len(out) != len(items):
            raise ValueError('duplicate JSON object key')
        return out
    return json.loads(data, parse_constant=invalid, object_pairs_hook=unique)


def load_catalog(source_index, oracle_index):
    raw_source, raw_oracle = source_index.read_bytes(), oracle_index.read_bytes()
    raw_cohort = source_index.with_name('cohort.json').read_bytes()
    source, oracles, cohort = map(strict_json, (raw_source, raw_oracle, raw_cohort))
    hashes = {'source_index_sha256': hashlib.sha256(raw_source).hexdigest(),
              'oracle_index_sha256': hashlib.sha256(raw_oracle).hexdigest()}
    if source['cohort_sha256'] != hashlib.sha256(raw_cohort).hexdigest() or oracles['index_sha256'] != hashes['source_index_sha256']:
        raise ValueError('source index, cohort and oracle catalog refer to different inputs')
    release = next((x for x in cohort['source']['verified_members'] if x['name'] == 'dsgdb9nsd.xyz.tar.bz2'), None)
    if not release:
        raise ValueError('cohort does not identify the versioned QM9 coordinate release')
    records = {x['name']: x for x in source['rows'] if x.get('name')}
    outputs = {x['name']: x for x in oracles['strata'] if x.get('name')}
    selected = {x['selected']['name']: x['selected'] for x in cohort['strata'] if x.get('selected')}
    for name, row in records.items():
        if selected[name]['member_sha256'] != row['member_sha256']:
            raise ValueError('original QM9 member differs between cohort and source index')
    if len(records) != sum(bool(x.get('name')) for x in source['rows']) or len(outputs) != sum(bool(x.get('name')) for x in oracles['strata']):
        raise ValueError('duplicate record ID in the source or oracle index')
    return release, records, selected, outputs, hashes


def route_catalogs(index_pairs):
    """Keep each record bound to its original pair of source/qualification catalogs."""
    release = None
    routes, protected, catalogs = {}, set(), []
    for source_index, oracle_index in index_pairs:
        origin, rows, selected, oracles, hashes = load_catalog(source_index, oracle_index)
        if release and (origin['metadata_url'], origin['sha256']) != (release['metadata_url'], release['sha256']):
            raise ValueError('catalogs identify different versions of the QM9 coordinates')
        release = origin
        protected.update(p.resolve() for p in (source_index, oracle_index, source_index.with_name('cohort.json')))
        catalogs.append({**hashes, 'record_ids': sorted(rows)})
        for name, row in rows.items():
            if name in routes:
                raise ValueError(f'ambiguous QM9 record in multiple catalogs: {name}')
            routes[name] = (row, oracles.get(name), selected[name], source_index, oracle_index, hashes)
            protected.update((source_index.parent / row[k]).resolve() for k in ('metadata_file', 'array_file') if row.get(k))
        protected.update((oracle_index.parent / o['oracle']).resolve() for o in oracles.values() if o.get('oracle'))
    return release, routes, protected, catalogs


def bound_context(name, source, result, member, release, source_index, oracle_index):
    if source['status'] != 'verified':
        raise RequestError('reference_unavailable', source.get('error') or source['status'])
    if not result or result['status'] != 'completed':
        raise RequestError('oracle_unavailable', 'no completed independent response oracle')
    meta, array = (source_index.parent / source[k] for k in ('metadata_file', 'array_file'))
    oracle_path = oracle_index.parent / result['oracle']
    expected = {'metadata_file': meta.name, 'array_file': array.name, 'metadata_sha256': source['metadata_sha256'],
                'array_sha256': source['array_file_sha256']}
    raw_meta, raw_oracle = meta.read_bytes(), oracle_path.read_bytes()
    if hashlib.sha256(raw_meta).hexdigest() != expected['metadata_sha256'] or file_hash(array) != expected['array_sha256'] or hashlib.sha256(raw_oracle).hexdigest() != result['sha256']:
        raise RequestError('source_digest_mismatch', 'reference artifact or independently measured oracle changed')
    o = strict_json(raw_oracle)
    if o.get('schema') != CPHF_SCHEMA:
        raise RequestError('oracle_unqualified', 'reference lacks the v2 physical residual and readout qualification')
    reference = strict_json(raw_meta)
    if (o['name'] != name or o['source'] != expected or o['reference_identity'] != source['reference_identity']
            or reference['source_qm9']['member_sha256'] != member['member_sha256']):
        raise RequestError('source_identity_mismatch', 'linked QM9 record, reference or operator identity disagrees')
    attest = o.get('operator_attestation', o['setup'])
    endpoint = attest['endpoint_identities']
    if json_hash(endpoint) != attest['contract_identity']:
        raise RequestError('source_identity_mismatch', 'inconsistent readout or field definition digest')
    provenance = {'release': release['metadata_url'], 'release_sha256': release['sha256'],
                  'record_id': name, 'member': member['member'], 'member_sha256': member['member_sha256'],
                  'reference_identity': o['reference_identity'], 'problem_identity': o['problem_identity'],
                  'geometry_hash': o['setup']['geometry_hash'], 'basis_hash': o['setup']['basis_hash'],
                  'operator_contract': attest['contract_identity'], 'reference_files': expected,
                  'oracle_schema': CPHF_SCHEMA, 'oracle_file': result['oracle'], 'oracle_sha256': result['sha256']}
    identity = json_hash({'schema': 1, 'provenance': provenance, 'definition': DEFINITION, 'units': UNITS,
                          'residual': GATE, 'analytic': ANALYTIC_TOL, 'finite_field': FIELD_TOL, 'steps': STEPS})
    return meta, array, o, endpoint, provenance, identity


def publish(path, obj):
    if path == '-':
        print(json.dumps(obj, ensure_ascii=False, allow_nan=False))
        return
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=dest.parent, delete=False) as handle:
        temp = Path(handle.name)
        try:
            json.dump(obj, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)


def read_inputs(path, release, records):
    raw = sys.stdin.buffer.read() if path == '-' else Path(path).read_bytes()
    rows, groups = [], defaultdict(list)
    for lineno, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        row = {'line': lineno, 'request_sha256': hashlib.sha256(line).hexdigest(), 'value': None, 'unit': None}
        rows.append(row)
        try:
            req = strict_json(line)
            if not isinstance(req, dict):
                raise ValueError('expected a JSON object')
            # Reject even overflow to infinity that JSON decoders may allow in 1e400.
            compact(req)
            row['request'] = req
            permitted = {'source', 'record_id', 'field', 'observable', 'request_id', 'expected_problem_identity'}
            if set(req) - permitted:
                raise ValueError('unsupported request fields: ' + ', '.join(sorted(set(req) - permitted)))
            if req.get('source') != release['metadata_url']:
                raise RequestError('unsupported_source', 'expected the versioned QM9 coordinate-file source URL')
            field, obs = req.get('field'), req.get('observable')
            if field not in FIELD_IDS or obs not in OBSERVABLE_IDS:
                raise RequestError('unsupported_target', 'supported fields: x,y,z; observables: q0,r2,zz')
            row['unit'] = UNITS[obs]
            name = req.get('record_id')
            if type(name) is int and name > 0:
                name = f'qm9-{name:06d}'
            if not isinstance(name, str) or name not in records:
                raise RequestError('record_not_indexed', 'record is not present in this reference source index')
            if 'expected_problem_identity' in req and not isinstance(req['expected_problem_identity'], str):
                raise ValueError('expected_problem_identity must be a string')
            groups[name].append(row)
        except (ValueError, UnicodeDecodeError) as e:
            row.update(status=getattr(e, 'status', 'invalid_request'), diagnostic={'reason': str(e)})
    return hashlib.sha256(raw).hexdigest(), rows, groups


SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
    identity TEXT NOT NULL, field TEXT NOT NULL, observable TEXT NOT NULL,
    record TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(identity, field, observable)
);
CREATE TABLE IF NOT EXISTS vectors (
    identity TEXT PRIMARY KEY, record TEXT NOT NULL, digest TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY, record_id TEXT NOT NULL, identity TEXT NOT NULL,
    started TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT
);
"""


def load_vectors(db, identity, problem):
    stored = db.execute('SELECT record,digest FROM vectors WHERE identity=?', (identity,)).fetchone()
    if stored is not None:
        try:
            data = strict_json(stored[0])
            if (json_hash(data) == stored[1] and data['problem_identity'] == problem
                    and isinstance(data['fields'], dict) and isinstance(data['observables'], dict)
                    and set(data['fields']) <= set(FIELD_IDS) and set(data['observables']) <= set(OBSERVABLE_IDS)):
                return data, False
        except (ValueError, KeyError, TypeError):
            pass
    return {'problem_identity': problem, 'fields': {}, 'observables': {}}, stored is not None


def load_label(db, identity, edge, o, endpoint):
    stored = db.execute('SELECT record,digest FROM labels WHERE identity=? AND field=? AND observable=?',
                        (identity, *edge)).fetchone()
    if stored is None:
        return None, None
    try:
        origin = strict_json(stored[0])
        grade = assess_scalar(o, endpoint, *edge, origin['value'])
        if json_hash(origin) != stored[1]:
            return None, 'scalar content digest mismatch'
        if origin['scope'] != identity or origin['target_identity'] != grade['target_identity']:
            return None, 'scalar scientific identity mismatch'
        if not grade['qualified']:
            return None, ', '.join(grade['reasons'])
        if 'historical_batch_sha256' in origin:
            grade['historical_batch_sha256'] = origin['historical_batch_sha256']
        return (grade, origin['attempt'], origin['via']), None
    except (ValueError, KeyError, TypeError) as e:
        return None, str(e)


def save_label(db, identity, edge, grade, attempt, via):
    origin = {'scope': identity, 'target_identity': grade['target_identity'], 'value': grade['value'],
              'attempt': attempt, 'via': via}
    if 'historical_batch_sha256' in grade:
        origin['historical_batch_sha256'] = grade['historical_batch_sha256']
    db.execute('INSERT OR REPLACE INTO labels VALUES(?,?,?,?,?)', (identity, *edge, compact(origin), json_hash(origin)))


def load_history(spec, catalog_by_record):
    """Only caller-pinned completed batches are accepted as external scalar evidence."""
    if spec is None:
        return None, {}
    start = time.perf_counter()
    expected, path = spec
    info = {'expected_sha256': expected, 'status': 'rejected'}
    try:
        raw = Path(path).read_bytes()
        info.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if info['sha256'] != expected:
            raise ValueError('historical batch digest mismatch')
        batch = strict_json(raw)
        if batch['schema'] != 'vibedataset.response_batch.v1' or batch['definition'] != DEFINITION or batch['units'] != UNITS:
            raise ValueError('historical publication or units differ')
        keys = ('source_index_sha256', 'oracle_index_sha256')
        single = {k: batch.get(k) for k in keys} if any(k in batch for k in keys) else None
        if single is not None and single not in catalog_by_record.values():
            raise ValueError('historical source catalog pair differs')
        # The initial CLI wrote one hash pair in its batch header. A composite
        # result provides the exact source pair both on the record and in the manifest.
        declared = {}
        for catalog in batch.get('catalogs', []):
            for name in catalog['record_ids']:
                if name in declared:
                    raise ValueError('duplicate historical record-to-catalog binding')
                declared[name] = {k: catalog[k] for k in keys}
        production = {r['id']: r for r in batch['work'] if r['model_started']}
        by_attempt = {aid: r for aid, r in production.items() if r['status'] == 'completed'}

        def total_cost(key):
            total = 0
            for attempt in production.values():
                value = attempt.get(key)
                if (attempt['status'] not in ('completed', 'failed') or attempt.get('setup_jk') is None or
                        type(value) is not int or value < 0):
                    return None
                total += value
            return total

        grouped = defaultdict(list)
        excluded = []
        for row in batch['records']:
            if (row.get('status') == 'qualified' and row.get('delivery') == 'computed'
                    and row.get('via') in ('direct', 'adjoint', 'compiled_scalar_relation')
                    and row.get('source_attempt') in by_attempt):
                producer = by_attempt[row['source_attempt']]
                name = producer['record_id']
                pair = row.get('catalog', single)
                if (pair is None or pair != catalog_by_record.get(name) or
                        (declared and declared.get(name) != pair) or (single is not None and single != pair)):
                    excluded.append({'line': row.get('line'), 'record_id': name, 'reason': 'source catalog binding mismatch'})
                    continue
                grouped[name].append((row, producer['identity'], expected))
        info.update(status='read', input_rows=len(batch['records']), eligible_rows=sum(map(len, grouped.values())),
                    excluded_catalog_records=excluded,
                    producer_failed_attempts=[aid for aid, r in production.items() if r['status'] == 'failed'],
                    producer_setup_jk=total_cost('setup_jk'), producer_round_jk=total_cost('round_jk'))
    except (OSError, ValueError, KeyError, TypeError) as e:
        info['reason'] = str(e)
        grouped = {}
    info['seconds'] = time.perf_counter() - start
    return info, grouped


def historical_scalars(history, ctx):
    _, _, oracle, endpoint, provenance, identity = ctx
    good, rejected, conflicts = {}, [], set()
    for record, source_identity, digest in history:
        try:
            edge = record['request']['field'], record['request']['observable']
            if (source_identity != identity or record['source'] != provenance or
                    record['unit'] != UNITS[edge[1]] or record['request']['source'] != provenance['release']):
                raise ValueError('historical record, scientific identity or unit mismatch')
            grade = assess_scalar(oracle, endpoint, *edge, record['value'])
            if grade['target_identity'] != record['target_identity'] or not grade['qualified']:
                raise ValueError('historical scalar failed target identity or independent quality gate')
            if (record['diagnostic']['raw_value'] != grade['raw_value'] or record['diagnostic']['reasons']
                    or record['diagnostic']['errors'] != grade['errors']):
                raise ValueError('historical measured value or qualification diagnostics disagree')
            if edge in good and good[edge][0]['value'] != grade['value']:
                conflicts.add(edge)
                raise ValueError('conflicting published values for one target')
            grade['historical_batch_sha256'] = digest
            good[edge] = grade, record['source_attempt'], record['via']
        except (ValueError, KeyError, TypeError) as e:
            rejected.append({'line': record.get('line'), 'reason': str(e)})
    for edge in conflicts:
        good.pop(edge, None)
    return good, rejected


def complete_missing(model, missing, cache, kernel_dir, known):
    """Use the bounded PLAN-002 rule only when it reduces the RHS count."""
    def cover(edges, vector_cache):
        return plan_cover(edges, vector_cache['fields'], vector_cache['observables'])
    fields, obs = cover(missing, cache)
    candidates = {edge: deps for edge, deps in recoverable(known).items() if edge in missing}
    unserved = sorted(set(missing) - candidates.keys())
    cold_fields, cold_obs = plan_cover(unserved)
    unit_count = len(fields) + len(obs)
    use_relation = bool(candidates and 1 + len(cold_fields) + len(cold_obs) < unit_count)
    relation = {'ordinary_cover_rhs_lower_bound': unit_count, 'eligible_diagonals': sorted(candidates),
                'combined_plus_cold_remainder_upper_bound': 1 + len(cold_fields) + len(cold_obs),
                'used': use_relation, 'reconstructions': []}
    computed, combo_counts = [], Counter()
    if use_relation:
        start = time.perf_counter()
        with model.measure('decoder_setup'):
            kernel = decoder(kernel_dir)
        relation['decoder_setup_seconds'] = time.perf_counter() - start
        relation['decoder_binary_sha256'] = file_hash(kernel.library._name)
        combined = model.combined_field([1, 1, 1], [o for _, o in candidates])
        combo_counts.update(combined['counts'])
        relation['combined'] = combined
        retry = []
        for (field, observable), deps in sorted(candidates.items()):
            values = [combined['values'][observable]] + [known[p][0]['value'] for p in deps]
            feeds = {name: np.asarray(v, dtype=np.float64) for name, v in zip(('combined', 'first', 'second'), values, strict=True)}
            candidate = float(kernel.execute(feeds)['missing'])
            grade = model.assess(field, observable, candidate)
            grade['via'] = 'compiled_scalar_relation'
            relation['reconstructions'].append({'field': field, 'observable': observable, 'operands': [
                {'pair': p, 'value': known[p][0]['value'], 'target_identity': known[p][0]['target_identity'],
                 'source_attempt': known[p][1]} for p in deps], 'candidate': grade})
            if grade['qualified'] is None and model.oracle is None and grade['raw_value'] is not None:
                grade['status'] = 'residual_verified'
            if grade['qualified'] or grade['status'] == 'residual_verified':
                computed.append(grade)
            else:
                retry.append((field, observable))
        missing = sorted(set(unserved + retry))
        # Starting with a cold cover bounds work despite a corrupt old vector.
        # Reassess a numerically rejected recovered scalar on the ordinary path.
        fields, obs = plan_cover(missing)
        relation['ordinary_retries'] = retry
    ordinary = model.run_round(missing, fields, obs, cache)
    total = Counter(ordinary['counts'])
    total.update(combo_counts)
    total['requests'] = len(computed) + len(ordinary['results'])
    ordinary.update(results=computed + ordinary['results'], counts=dict(total), relation=relation,
                    chosen_fields=list(fields), chosen_observables=list(obs))
    return ordinary


# The original split route remains a measurable same-protocol comparator.
complete_missing_split = complete_missing


def complete_field_block(model, missing, cache, kernel_dir, known, *, supports=SUPPORTS):
    """Execute the selected field sum together with all remaining ordinary endpoints."""
    cached = cache['fields'], cache['observables']
    plan = plan_field_block(missing, known, *cached, supports=supports)
    baseline_fields, baseline_obs = plan_cover(missing, *cached)
    relation = {'used': bool(plan.support), 'support': list(plan.support),
                'ordinary_cover_rhs_lower_bound': len(baseline_fields) + len(baseline_obs),
                'planned_new_rhs': plan.new_rhs, 'reconstructions': [], 'ordinary_retries': []}
    if not plan.support:
        measured = model.run_round(plan.ordinary_requests, plan.fields, plan.observables, cache)
        measured.update(relation=relation, chosen_fields=list(plan.fields), chosen_observables=list(plan.observables))
        return measured

    start = time.perf_counter()
    with model.measure('decoder_setup'):
        kernel = decoder(kernel_dir, len(plan.support) - 1)
    relation.update(decoder_setup_seconds=time.perf_counter() - start,
                    decoder_binary_sha256=file_hash(kernel.library._name))
    before = model.counts.copy()
    try:
        measured = model.run_round(plan.ordinary_requests, plan.fields, plan.observables, cache,
                                   combined_coefficients=tuple(int(f in plan.support) for f in FIELD_IDS),
                                   combined_observables={obs for _, obs in plan.operands})
    except ResponseSolveError as error:
        # Count the unsuccessful joint solve before reverting to the unmodified physical problem.
        spent = model.counts - before
        lost = response_work(spent)
        relation.update(failed_block={'reason': str(error), 'counts': lost, 'submitted_blocks': spent['submitted_blocks']},
                        ordinary_retries=sorted(missing))
        measured = model.run_round(missing, baseline_fields, baseline_obs, cache)
        for key, n in lost.items():
            measured['counts'][key] += n
        measured.update(relation=relation, chosen_fields=list(baseline_fields), chosen_observables=list(baseline_obs))
        return measured
    combined = measured['combined']
    relation['combined'] = combined
    for (field, obs), deps in plan.operands.items():
        prior = [known[edge][0]['value'] for edge in deps]
        values = [combined['values'][obs], *prior]
        feeds = {k: np.asarray(v, dtype=np.float64) for k, v in zip(('combined', 'first', 'second')[:len(values)], values, strict=True)}
        decoded = float(kernel.execute(feeds)['missing'])
        grade = model.assess(field, obs, decoded)
        grade['via'] = 'compiled_scalar_relation'
        if grade['qualified'] is None and model.oracle is None and grade['raw_value'] is not None:
            grade['status'] = 'residual_verified'
        relation['reconstructions'].append({'field': field, 'observable': obs, 'operands': [
            {'pair': edge, 'value': known[edge][0]['value'], 'target_identity': known[edge][0]['target_identity'],
             'source_attempt': known[edge][1]} for edge in deps], 'candidate': grade})
        if grade['qualified'] is False:
            relation['ordinary_retries'].append((field, obs))
        else:
            measured['results'].append(grade)
    if relation['ordinary_retries']:
        retries = relation['ordinary_retries']
        retry_fields, retry_obs = plan_cover(retries, cache['fields'], cache['observables'])
        retry = model.run_round(retries, retry_fields, retry_obs, cache)
        relation['retry_block'] = retry['block']
        measured['results'].extend(retry['results'])
        measured['cache_checks'].extend(retry['cache_checks'])
        for key, n in retry['counts'].items():
            measured['counts'][key] += n
        measured['new_fields'].extend(retry['new_fields'])
        measured['new_observables'].extend(retry['new_observables'])
    measured['counts']['requests'] = len(measured['results'])
    measured.update(relation=relation, chosen_fields=list(plan.fields), chosen_observables=list(plan.observables))
    return measured


class AttemptMeter:
    """Own the live operation counters before construction and through every retry."""

    def __init__(self):
        self.counts = Counter()
        self.native_kernels = []
        self.stages = []

    @contextmanager
    def measure(self, phase):
        start = time.perf_counter()
        before = self.counts.copy()
        stage = {'phase': phase, 'status': 'completed'}
        try:
            yield
        except Exception as error:
            stage.update(status='failed', reason=str(error))
            raise
        finally:
            stage['seconds'] = time.perf_counter() - start
            stage['operations'] = dict(self.counts - before)
            self.stages.append(stage)

    def finish(self, work):
        setup = next((s for s in self.stages if s['phase'] == 'model_setup'), None)
        setup_ops = Counter(setup['operations']) if setup else Counter()
        remaining = self.counts - setup_ops
        counts = work.setdefault('counts', {})
        counts.update(response_work(remaining))
        # An interrupt between projections and the returned batch can leave the
        # number of assessed outputs unknown even though every submission is metered.
        counts.setdefault('requests', None if work.get('failed_stage') == 'solve_and_assess' else 0)
        work.update(cost_schema='vibedataset.response_work.v2', cost_stages=self.stages,
                    setup_status=setup['status'] if setup else 'skipped', setup_jk=setup_ops['jk_calls'],
                    setup_seconds=setup['seconds'] if setup else 0., round_jk=counts['jk_calls'], rhs=counts['rhs_columns'])
        if setup:
            work['native_kernel_attempts'] = [{k: entry[k] for k in ('source', 'elapsed_seconds', 'binary_sha256')}
                                              for entry in self.native_kernels]
            work['native_kernel_sha256'] = [k['binary_sha256'] for k in self.native_kernels if k['binary_sha256']]
            # NativeTensorProgram may load a cached binary. Its inclusive elapsed
            # time is observed, its compiler-only share for this call is unknown.
            work['setup_compile_only_seconds'] = None if self.native_kernels else 0.


def run_group(db, name, ctx, requests, kernel_dir, history, relations, scalar_plan='blocked'):
    meta, array, oracle, endpoint, provenance, identity = ctx
    grouped = defaultdict(list)
    for row in requests:
        row['source'] = provenance
        expected = row['request'].get('expected_problem_identity', oracle['problem_identity'])
        if expected != oracle['problem_identity']:
            row.update(status='problem_mismatch', diagnostic={'reason': 'requested response problem differs from source'})
        else:
            grouped[(row['request']['field'], row['request']['observable'])].append(row)
    if not grouped:
        return None
    aid = uuid4().hex
    work = {'id': aid, 'record_id': name, 'identity': identity, 'requested_lines': sum(map(len, grouped.values())),
            'distinct_targets': len(grouped), 'scalar_hits': 0, 'scalar_rejections': 0, 'model_started': False,
            'status': 'started', 'rejected_labels': []}
    start = time.perf_counter()
    meter = AttemptMeter()

    def persist_receipt(status):
        meter.finish(work)
        work.update(status=status, seconds=time.perf_counter() - start)
        db.execute('UPDATE attempts SET status=?,receipt=? WHERE id=?', (status, compact(work), aid))

    # A killed process can leave a started receipt. Labels and vectors only
    # become visible together with the completed receipt below.
    db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,NULL)', (aid, name, identity, timestamp(), 'started'))
    labels, hits = {}, set()
    historical_hits = set()
    stage = 'acquire_lock'
    try:
        db.execute('BEGIN IMMEDIATE')
        work['lock_wait_seconds'] = time.perf_counter() - start
        stage = 'load_assets'
        imported, work['rejected_history'] = historical_scalars(history, ctx)
        work['validated_history_scalars'] = len(imported)
        use_relations = relations and scalar_plan != 'ordinary'
        operands = {(other, observable) for field, observable in grouped
                    for other in FIELD_IDS if other != field} if use_relations else set()
        known = {}
        for edge in sorted(grouped.keys() | operands):
            saved, rejected = load_label(db, identity, edge, oracle, endpoint)
            if rejected:
                work['scalar_rejections'] += 1
                work['rejected_labels'].append({'field': edge[0], 'observable': edge[1], 'reason': rejected})
            if saved:
                known[edge] = saved
            elif edge in imported:
                known[edge] = imported[edge]
                save_label(db, identity, edge, *imported[edge])
                if edge in grouped:
                    historical_hits.add(edge)
            if edge in known and edge in grouped:
                labels[edge] = known[edge]
                hits.add(edge)
        work['scalar_hits'] = len(hits)
        work['historical_hits'] = len(historical_hits)
        missing = sorted(grouped.keys() - hits)
        if missing:
            cache, bad = load_vectors(db, identity, oracle['problem_identity'])
            work.update(model_started=True, vector_envelope_rejected=bad)
            stage = 'model_setup'
            with meter.measure(stage):
                model = DualResponseModel(meta, array, kernel_dir, oracle=oracle, meter=meter)
            solve_start = time.perf_counter()
            stage = 'solve_and_assess'
            work['scalar_plan'] = scalar_plan if relations else 'ordinary'
            if use_relations:
                complete = complete_field_block if scalar_plan == 'blocked' else complete_missing_split
                measured = complete(model, missing, cache, kernel_dir, known)
                work.update(relation=measured['relation'], chosen_fields=measured['chosen_fields'],
                            chosen_observables=measured['chosen_observables'])
            else:
                fields, obs = plan_cover(missing, cache['fields'], cache['observables'])
                work.update(chosen_fields=list(fields), chosen_observables=list(obs))
                measured = model.run_round(missing, fields, obs, cache)
            work.update(counts=measured['counts'], block=measured['block'], cache_checks=measured['cache_checks'],
                        solve_and_assess_seconds=time.perf_counter() - solve_start)
            stage = 'store_assets'
            for grade in measured['results']:
                edge = grade['field'], grade['observable']
                labels[edge] = grade, aid, grade['via']
                if grade['qualified']:
                    save_label(db, identity, edge, grade, aid, grade['via'])
                else:
                    db.execute('DELETE FROM labels WHERE identity=? AND field=? AND observable=?', (identity, *edge))
            db.execute('INSERT OR REPLACE INTO vectors VALUES(?,?,?)', (identity, compact(cache), json_hash(cache)))
        stage = 'commit'
        persist_receipt('completed')
        db.commit()
    except Exception as e:
        if stage == 'solve_and_assess':
            work['solve_and_assess_seconds'] = time.perf_counter() - solve_start
        db.rollback()
        work.update(failed_stage=stage, reason=str(e))
        persist_receipt('failed')
        db.commit()
    for edge, repeated in grouped.items():
        for number, row in enumerate(repeated):
            row['attempt'] = aid
            if work['status'] == 'failed' and edge not in hits:
                row.update(status='execution_failed', diagnostic={'reason': work['reason']})
                continue
            grade, origin, via = labels[edge]
            row.update(status=grade['status'], value=grade['value'], target_identity=grade['target_identity'],
                       source_attempt=origin, via=via, delivery='scalar_cache' if edge in hits else 'computed',
                       diagnostic={'raw_value': grade['raw_value'], 'reasons': grade['reasons'], 'errors': grade['errors']})
            if 'historical_batch_sha256' in grade:
                row['historical_batch_sha256'] = grade['historical_batch_sha256']
            if edge in historical_hits:
                row['delivery'] = 'historical_scalar'
            if number:
                row.update(delivery='same_batch_duplicate', duplicate_of_line=repeated[0]['line'])
    return work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', default='-', help='one JSON object per line, or stdin')
    parser.add_argument('--cache-db', '--cache', type=Path, required=True)
    parser.add_argument('--out', '--output', required=True, help='atomic JSON batch result, or stdout (-)')
    parser.add_argument('--source-index', type=Path, help='select one source catalog; defaults to both released QM9 batches')
    parser.add_argument('--oracle-index', type=Path, help='select the independent oracle catalog for an explicit source')
    parser.add_argument('--kernel-cache', type=Path, help='GQC generated binary cache')
    parser.add_argument('--decode-known-scalars', action='store_true', help='enable exact 3x3 scalar relations using qualified cached operands')
    parser.add_argument('--scalar-plan', choices=('blocked', 'ordinary', 'split-xyz'), default='blocked',
                        help='execution for scalar relations enabled by --history or --decode-known-scalars')
    parser.add_argument('--history', nargs=2, metavar=('SHA256', 'JSON'), help='accept producer-computed labels from this checksum-pinned earlier batch; enables scalar relations')
    args = parser.parse_args()
    start = time.perf_counter()
    pairs = DEFAULT_CATALOGS
    if args.source_index is not None or args.oracle_index is not None:
        pairs = [(args.source_index or DEFAULT_CATALOGS[0][0], args.oracle_index or DEFAULT_CATALOGS[0][1])]
    release, routes, protected, catalogs = route_catalogs(pairs)
    if args.requests != '-':
        protected.add(Path(args.requests).resolve())
    if args.history:
        protected.add(Path(args.history[1]).resolve())
    if args.cache_db.resolve() in protected or (args.out != '-' and Path(args.out).resolve() in protected | {args.cache_db.resolve()}):
        parser.error('cache and output require distinct destinations outside the input files')
    request_digest, rows, groups = read_inputs(args.requests, release, routes)
    history_info, history = load_history(args.history, {name: route[-1] for name, route in routes.items()})
    args.cache_db.parent.mkdir(parents=True, exist_ok=True)
    kernel_dir = args.kernel_cache or args.cache_db.with_name(args.cache_db.name + '-gqc')
    attempts = []
    db = sqlite3.connect(args.cache_db, isolation_level=None, timeout=300)
    try:
        db.executescript(SCHEMA)
        for name, requests in groups.items():
            cohort, oracle, member, source_index, oracle_index, hashes = routes[name]
            for row in requests:
                row['catalog'] = hashes
                row['source'] = {'release': release['metadata_url'], 'release_sha256': release['sha256'],
                                 'record_id': name, 'member': member['member'], 'member_sha256': cohort['member_sha256']}
            try:
                ctx = bound_context(name, cohort, oracle, member, release, source_index, oracle_index)
                receipt = run_group(db, name, ctx, requests, kernel_dir, history.get(name, []),
                                    args.decode_known_scalars or args.history is not None, args.scalar_plan)
                if receipt:
                    attempts.append(receipt)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as e:
                for row in requests:
                    if 'status' not in row:
                        row.update(status=getattr(e, 'status', 'read_or_store_error'), diagnostic={'reason': str(e)})
    finally:
        db.close()
    counts = Counter(r['status'] for r in rows)
    # Preserve the v1 single-pair header when a batch uses just one catalog.
    used = {tuple(sorted(routes[name][-1].items())) for name in groups}
    single_hashes = dict(next(iter(used))) if len(used) == 1 else {}
    if not used and len(catalogs) == 1:
        single_hashes = {k: v for k, v in catalogs[0].items() if k != 'record_ids'}
    batch = {'schema': 'vibedataset.response_batch.v1', 'definition': DEFINITION, 'units': UNITS,
             **single_hashes, 'catalogs': catalogs, 'history': history_info, 'gqc_commit': GQC_PIN,
             'cli_sha256': file_hash(__file__), 'model_source_sha256': file_hash(ROOT/'scripts/gqc_dual_response.py'),
             'planning_sources': {name:file_hash(ROOT/'scripts'/name) for name in
                                  ('response_cover.py', 'response_field_plan.py', 'probe_scalar_response.py')},
             'input_sha256': request_digest, 'counts_by_status': counts, 'work': attempts,
             'seconds': time.perf_counter() - start, 'records': rows}
    publish(args.out, batch)
    return int(any(s != 'qualified' for s in counts))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(f'response completion failed: {error}', file=sys.stderr)
        sys.exit(2)
