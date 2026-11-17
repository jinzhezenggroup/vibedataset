#!/usr/bin/env python3
"""Complete a JSONL batch of pinned QM9 static RHF response requests."""
import argparse
from collections import Counter, defaultdict
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

from gqc_dual_response import ANALYTIC_TOL, FIELD_IDS, FIELD_TOL, GATE, OBSERVABLE_IDS, STEPS, DualResponseModel, assess_scalar
from probe_gqc_residual import ROOT, file_hash, json_hash
from response_cover import plan_cover

EXPERIMENTS = ROOT / 'handoff/gqcdataset_codex_goal/research/experiments'
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
    release = next(x for x in cohort['source']['verified_members'] if x['name'] == 'dsgdb9nsd.xyz.tar.bz2')
    records = {x['name']: x for x in source['rows'] if x.get('name')}
    outputs = {x['name']: x for x in oracles['strata'] if x.get('name')}
    selected = {x['selected']['name']: x['selected'] for x in cohort['strata'] if x.get('selected')}
    for name, row in records.items():
        if selected[name]['member_sha256'] != row['member_sha256']:
            raise ValueError('original QM9 member differs between cohort and source index')
    if len(records) != sum(bool(x.get('name')) for x in source['rows']) or len(outputs) != sum(bool(x.get('name')) for x in oracles['strata']):
        raise ValueError('duplicate record ID in the source or oracle index')
    return release, records, selected, outputs, hashes


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
                  'oracle_file': result['oracle'], 'oracle_sha256': result['sha256']}
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
                    and isinstance(data['fields'], dict) and isinstance(data['observables'], dict)):
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
        return (grade, origin['attempt'], origin['via']), None
    except (ValueError, KeyError, TypeError) as e:
        return None, str(e)


def run_group(db, name, ctx, requests, kernel_dir):
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
            'setup_jk': 0, 'round_jk': 0, 'rhs': 0, 'status': 'started', 'rejected_labels': []}
    start = time.perf_counter()
    # A killed process can leave a started receipt. Labels and vectors only
    # become visible together with the completed receipt below.
    db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,NULL)', (aid, name, identity, timestamp(), 'started'))
    labels, hits, model = {}, set(), None
    try:
        db.execute('BEGIN IMMEDIATE')
        work['lock_wait_seconds'] = time.perf_counter() - start
        for edge in grouped:
            saved, rejected = load_label(db, identity, edge, oracle, endpoint)
            if rejected:
                work['scalar_rejections'] += 1
                work['rejected_labels'].append({'field': edge[0], 'observable': edge[1], 'reason': rejected})
            if saved:
                labels[edge] = saved
                hits.add(edge)
        work['scalar_hits'] = len(hits)
        missing = sorted(grouped.keys() - hits)
        if missing:
            cache, bad = load_vectors(db, identity, oracle['problem_identity'])
            fields, obs = plan_cover(missing, cache['fields'], cache['observables'])
            work.update(model_started=True, setup_jk=None, vector_envelope_rejected=bad,
                        chosen_fields=list(fields), chosen_observables=list(obs))
            model = DualResponseModel(meta, array, kernel_dir, oracle=oracle)
            work['setup_jk'] = model.setup['counts']['jk_calls']
            work['setup_seconds'] = model.setup['seconds']
            measured = model.run_round(missing, fields, obs, cache)
            work.update(round_jk=measured['counts']['jk_calls'], rhs=measured['counts']['rhs_columns'],
                        counts=measured['counts'], cache_checks=measured['cache_checks'],
                        solve_and_assess_seconds=measured['elapsed_seconds'])
            for grade in measured['results']:
                edge = grade['field'], grade['observable']
                labels[edge] = grade, aid, grade['via']
                if grade['qualified']:
                    origin = {'scope': identity, 'target_identity': grade['target_identity'], 'value': grade['value'],
                              'attempt': aid, 'via': grade['via']}
                    db.execute('INSERT OR REPLACE INTO labels VALUES(?,?,?,?,?)',
                               (identity, *edge, compact(origin), json_hash(origin)))
                else:
                    db.execute('DELETE FROM labels WHERE identity=? AND field=? AND observable=?', (identity, *edge))
            db.execute('INSERT OR REPLACE INTO vectors VALUES(?,?,?)', (identity, compact(cache), json_hash(cache)))
        work.update(status='completed', seconds=time.perf_counter() - start)
        db.execute('UPDATE attempts SET status=?,receipt=? WHERE id=?', ('completed', compact(work), aid))
        db.commit()
    except Exception as e:
        db.rollback()
        if model is not None:
            work['round_jk'] = model.counts['jk_calls'] - work['setup_jk']
        work.update(status='failed', reason=str(e), seconds=time.perf_counter() - start)
        db.execute('UPDATE attempts SET status=?,receipt=? WHERE id=?', ('failed', compact(work), aid))
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
            if number:
                row.update(delivery='same_batch_duplicate', duplicate_of_line=repeated[0]['line'])
    return work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', default='-', help='one JSON object per line, or stdin')
    parser.add_argument('--cache-db', '--cache', type=Path, required=True)
    parser.add_argument('--out', '--output', required=True, help='atomic JSON batch result, or stdout (-)')
    parser.add_argument('--source-index', type=Path, default=EXPERIMENTS/'qm9_response_assets/index.json')
    parser.add_argument('--oracle-index', type=Path, default=EXPERIMENTS/'gqc_dual_response/summary.json')
    parser.add_argument('--kernel-cache', type=Path, help='GQC generated binary cache')
    args = parser.parse_args()
    start = time.perf_counter()
    release, records, members, oracles, hashes = load_catalog(args.source_index, args.oracle_index)
    protected = {args.source_index.resolve(), args.oracle_index.resolve(), args.source_index.with_name('cohort.json').resolve()}
    for source in records.values():
        for key in ('metadata_file', 'array_file'):
            if source.get(key):
                protected.add((args.source_index.parent / source[key]).resolve())
    protected.update((args.oracle_index.parent / item['oracle']).resolve() for item in oracles.values() if item.get('oracle'))
    if args.requests != '-':
        protected.add(Path(args.requests).resolve())
    if args.cache_db.resolve() in protected or (args.out != '-' and Path(args.out).resolve() in protected | {args.cache_db.resolve()}):
        parser.error('cache and output require distinct destinations outside the input files')
    request_digest, rows, groups = read_inputs(args.requests, release, records)
    args.cache_db.parent.mkdir(parents=True, exist_ok=True)
    kernel_dir = args.kernel_cache or args.cache_db.with_name(args.cache_db.name + '-gqc')
    attempts = []
    db = sqlite3.connect(args.cache_db, isolation_level=None, timeout=300)
    try:
        db.executescript(SCHEMA)
        for name, requests in groups.items():
            cohort = records[name]
            for row in requests:
                row['source'] = {'release': release['metadata_url'], 'release_sha256': release['sha256'],
                                 'record_id': name, 'member': members[name]['member'], 'member_sha256': cohort['member_sha256']}
            try:
                ctx = bound_context(name, cohort, oracles.get(name), members[name], release, args.source_index, args.oracle_index)
                receipt = run_group(db, name, ctx, requests, kernel_dir)
                if receipt:
                    attempts.append(receipt)
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as e:
                for row in requests:
                    if 'status' not in row:
                        row.update(status=getattr(e, 'status', 'read_or_store_error'), diagnostic={'reason': str(e)})
    finally:
        db.close()
    counts = Counter(r['status'] for r in rows)
    batch = {'schema': 'vibedataset.response_batch.v1', 'definition': DEFINITION, 'units': UNITS,
             **hashes,
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
