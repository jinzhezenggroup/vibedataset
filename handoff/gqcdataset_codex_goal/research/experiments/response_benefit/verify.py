"""Score sealed proposals against v2 and verify all retained data, counts, masks and sums with the standard library."""
import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import gzip
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
from statistics import median
import struct
import tarfile

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
Q_SCHEMA = 'vibedataset.discrete_response_error.v1'
FIELDS = ('x', 'y', 'z')
OBS = ('q0', 'r2', 'zz')
DIAG = ('x/q0', 'y/r2', 'z/zz')
SCENARIOS = {'cycle-one': DIAG[:1], 'cycle-three': DIAG, 'cross-three': DIAG}
METHODS = ('direct', 'adjoint', 'single', 'two', 'hand_field', 'hand_adjoint',
           'vectors', 'vectors_gzip', 'table_field', 'table_adjoint', 'dense', 'table_dense')


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(obj):
    return (json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def csv_bytes(rows):
    buff = io.StringIO(newline='')
    writer = csv.DictWriter(buff, fieldnames=rows[0], lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return buff.getvalue().encode()


def package(work, dest):
    dest.mkdir(parents=True, exist_ok=True)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for path in sorted(work.glob('qm9-*/rep*/*')):
            data = path.read_bytes()
            meta = tarfile.TarInfo(str(path.relative_to(work)))
            meta.size = len(data)
            tar.addfile(meta, io.BytesIO(data))
    raw = {'assets.tar.gz': gzip.compress(archive.getvalue(), mtime=0),
           'events.jsonl.gz': gzip.compress((work / 'events.jsonl').read_bytes(), mtime=0),
           'protocol.json': (work / 'protocol.json').read_bytes(), 'finished.json': (work / 'finished.json').read_bytes(),
           'quality.py.gz': gzip.compress((work / 'target_response_quality.py').read_bytes(), mtime=0)}
    for name, data in raw.items():
        with (dest / name).open('xb') as f:
            f.write(data)
    with (dest / 'manifest.json').open('xb') as f:
        f.write(dump({k: {'sha256': sha(v), 'bytes': len(v)} for k, v in raw.items()}))


def catalog():
    oracles, source = {}, {}
    for split, base, subset in [('development', 'qm9_response_assets', 'seed'), ('holdout', 'qm9_extension/assets', 'extension')]:
        input_file = EXP / base / 'index.json'
        src = json.loads(input_file.read_bytes())
        index = EXP / 'cphf_v2' / subset / 'index.json'
        catalog = json.loads(index.read_bytes())
        require(catalog['index_sha256'] == sha(input_file.read_bytes()), 'source catalog')
        for row in src['rows']:
            if row['name']:
                source[row['name']] = split, row
        for r in catalog['strata']:
            if r['status'] == 'completed':
                data = (index.parent / r['oracle']).read_bytes()
                require(sha(data) == r['sha256'], 'v2 oracle bytes')
                oracles[r['name']] = json.loads(data)
    return source, oracles


def scientific(key, result, oracle):
    f, o = key.split('/')
    ref = oracle['targets'][f][o]
    require(ref['status'] == 'qualified' and ref['reference_precision']['physical_residual_l2'] <= 1e-10
            and ref['reference_precision']['readout_error_estimate'] <= 1e-9, 'unqualified v2 evaluation')
    v = result['value']
    require(result['schema'] == Q_SCHEMA and result['status'] == 'accepted' and v == result['raw_value']
            and math.isfinite(v) and 0 <= result['error_estimate'] <= 1e-8 and result['source'] == oracle['name'],
            'unqualified production scalar')
    endpoint = oracle['setup']['endpoint_identities']
    target = sha(json.dumps([endpoint['fields'][f], endpoint['observables'][o]], separators=(',', ':')).encode())
    require(result['unit'] == ('e / au_field' if o == 'q0' else 'bohr^2 / au_field') and
            result['target_identity'] == target, 'scientific target identity or units')
    direct, adjoint, independent = (abs(v - ref[k]) for k in ('direct', 'adjoint', 'cphf'))
    fd = [abs(v - ref['finite_fields'][h]) for h in ('0.0005', '0.0002')]
    qualified = max(direct, adjoint, independent + ref['reference_precision']['readout_error_estimate']) <= 1e-8 and max(fd) <= 1e-4
    ref_estimate = ref['reference_precision']['readout_error_estimate']
    return dict(v2_passed=qualified, native_direct_error=direct, native_adjoint_error=adjoint,
                reference_error_estimate=ref_estimate,
                reference_difference_lower=max(0., independent - ref_estimate),
                reference_difference_upper=independent + ref_estimate,
                reference_error=independent, fd_5e4_error=fd[0], fd_2e4_error=fd[1], error_estimate=result['error_estimate'])


def readout_terms(e, history, output, calibrator=None):
    projections = {(d['column'], o): term for d in e['directions'] for o, term in d['proof']['projections'].items()}
    for key, terms in e['terms'].items():
        f, o = key.split('/')
        signature = [Fraction() for _ in FIELDS]
        measured = []
        for col, partner, weight in terms:
            if col.startswith('H:'):
                h = col[2:]
                term = history[h + '/' + partner]
            elif col in OBS:
                require((col, partner) == (o, f), 'wrong adjoint readout')
                h, term = f, projections[col, partner]
            else:
                h, term = col, projections[col, partner]
            require(col in OBS or partner == o, 'mixed observable')
            require(term.get('schema') == Q_SCHEMA and term['status'] in ('accepted', 'refine')
                    and math.isfinite(term['raw_value']) and math.isfinite(term['error_estimate'])
                    and term['error_estimate'] >= 0, 'unverified operand')
            for i, axis in enumerate(FIELDS):
                signature[i] += Fraction(weight) * (axis in h)
            measured.append((weight, term))
        require(tuple(signature) == tuple(int(k == f) for k in FIELDS), 'wrong linear identity')
        scalar = output[key]
        products = [w * t['raw_value'] for w, t in measured]
        require(abs(math.fsum(products) - scalar['value']) <= 1e-12 + 1e-13 * math.fsum(map(abs, products)), 'wrong decoded value')
        if len(terms) == 1:
            require(scalar['error_estimate'] == measured[0][1]['error_estimate'], 'single projection uncertainty')
        else:
            if calibrator is not None:
                current = calibrator(measured)
                require(current['status'] == scalar['status'] and current['error_estimate'] + abs(
                    scalar['raw_value'] - current['raw_value']) == scalar['error_estimate'], 'updated #14 target qualification')
            propagated = math.fsum(abs(w) * t['error_estimate'] for w, t in measured)
            require(scalar['propagated_error'] == propagated and scalar['error_estimate'] >= propagated,
                    'history error propagation')


def conditioning(dest):
    records = {}
    for e in (json.loads(l) for l in gzip.decompress((dest / 'events.jsonl.gz').read_bytes()).splitlines()):
        if e['phase'] != 'future':
            continue
        for target, terms in e['terms'].items():
            if len(terms) <= 1:
                continue
            key = e['scenario'], e['method'], target, json.dumps(terms, separators=(',',':'))
            if key not in records:
                # For independent input rows R, kappa_2(R) <= sqrt(kappa_inf(R R^T)).
                # Exact rational inversion suffices for these two- or three-row recipes.
                signatures = [[int(f in c.removeprefix('H:')) for f in FIELDS] for c, _, _ in terms]
                gram = [[sum(a*b for a,b in zip(u,v)) for v in signatures] for u in signatures]
                n = len(gram)
                rows = [[Fraction(v) for v in row] + [Fraction(i == j) for j in range(n)] for i,row in enumerate(gram)]
                for j in range(n):
                    pivot = rows[j][j]
                    require(pivot != 0, 'dependent recovery basis')
                    rows[j] = [v / pivot for v in rows[j]]
                    for i in range(n):
                        if i != j:
                            factor = rows[i][j]
                            rows[i] = [v-factor*w for v,w in zip(rows[i],rows[j])]
                inf = max(sum(map(abs, row)) for row in gram)
                inv_inf = max(sum(map(abs, row[n:])) for row in rows)
                records[key] = dict(scenario=key[0], method=key[1], target=target, terms=key[3],
                                    error_amplification_l1=sum(abs(t[2]) for t in terms),
                                    spectral_condition_upper=math.sqrt(inf*inv_inf), max_observed_cancellation=0.)
            ratio = e['outputs'][target]['cancellation_ratio']
            if ratio is not None:
                records[key]['max_observed_cancellation'] = max(records[key]['max_observed_cancellation'], ratio)
    return [records[k] for k in sorted(records)]


def archive_objects(dest):
    with tarfile.open(dest / 'assets.tar.gz', 'r:gz') as tar:
        contents = {}
        for entry in tar:
            require(entry.isfile() and entry.name not in contents and '..' not in Path(entry.name).parts, 'archive member')
            contents[entry.name] = tar.extractfile(entry).read()
    return contents


def asset(contents, event, receipt, seen):
    path = f"{event['source']}/rep{event['repetition']}/{receipt['path']}"
    data = contents[path]
    require(len(data) == receipt['bytes'] and sha(data) == receipt['sha256'], 'archived asset digest ' + path)
    seen.add(path)
    return json.loads(gzip.decompress(data) if path.endswith('.gz') else data)


def verify(dest, calibrator=None):
    for name, rec in json.loads((dest / 'manifest.json').read_bytes()).items():
        data = (dest / name).read_bytes()
        require(len(data) == rec['bytes'] and sha(data) == rec['sha256'], name)
    raw = gzip.decompress((dest / 'events.jsonl.gz').read_bytes())
    finish = json.loads((dest / 'finished.json').read_bytes())
    require(sha(raw) == finish['journal_sha256'], 'pre-score journal seal')
    protocol = json.loads((dest / 'protocol.json').read_bytes())
    require(sha(gzip.decompress((dest / 'quality.py.gz').read_bytes())) == protocol['q14_sha256'], 'measured quality program')
    source, oracles = catalog()
    contents, seen = archive_objects(dest), set()
    events = [json.loads(l) for l in raw.splitlines()]
    setup, qa, history = {}, {}, {}
    builds = {(e['source'], tuple(b['weights'])): b['seconds'] for e in events for b in e.get('decoder_builds', [])}
    scored, costs, rejected, histories = [], [], [], []
    phases = Counter()
    jk = rhs = dense_rhs = proof_actions = 0
    expected = set(itertools.product(oracles, range(4), SCENARIOS, METHODS))
    for e in events:
        name, phase = e['source'], e['phase']
        split, src = source[name]
        phases[phase] += 1
        if phase == 'reference_unavailable':
            require(src['error'] == e['reason'] and name not in oracles, 'missing reference reason')
            for rep, s, m in itertools.product(range(4), SCENARIOS, METHODS):
                for key in SCENARIOS[s]:
                    scored.append(dict(source=name, split=split, rep=rep, scenario=s, method=m, target=key, status=phase))
            continue
        jk += e.get('cost', {}).get('jk_calls', 0)
        if phase == 'setup':
            setup[name, e['kind']] = e
            continue
        if phase == 'quality_setup':
            qa[name] = e
            continue
        rhs += e['cost']['rhs_columns']
        dense_rhs += e['dense_rhs']
        proof_actions += e['quality_native_actions']
        if e['status'] != 'completed':
            rejected.append(e)
        require(e['cost']['jk_calls'] == sum(b['native_actions'] for b in e['blocks']) + e['quality_native_actions'],
                'physical work, including validation')
        require(e['cost']['rhs_columns'] == sum(len(b['columns']) for b in e['blocks']), 'submitted GQC columns')
        for d in e['directions']:
            proof = d['proof']
            require(proof['physical_residual_l2'] <= 1e-10 and proof['status'] in ('accepted', 'refine'), 'physical column check')
        rep = e['repetition']
        if phase == 'history':
            recs = e['assets']
            labels = asset(contents, e, recs['scalars'], seen)
            for k, val in labels['rows'].items():
                histories.append(dict(source=name, rep=rep, producer=e['kind'], target=k, **scientific(k, val, oracles[name])))
            readout_terms(e, {}, labels['rows'])
            if 'vectors' in recs:
                plain = asset(contents, e, recs['vectors'], seen)
                require(plain == asset(contents, e, recs['vectors_gzip'], seen) and plain['identity'] == labels['identity'],
                        'lossless vector retention or identity')
                for col, data in plain['rows'].items():
                    require(sha(b''.join(struct.pack('<d', x) for x in data['solution'])) == data['solution_sha256'], 'vector contents')
                    d = next(d for d in e['directions'] if d['column'] == col)
                    require((d['identity'], d['proof']['rhs_sha256'], d['proof']['vector_sha256']) ==
                            (data['endpoint'], data['rhs_sha256'], data['solution_sha256']), 'direction identity')
            history[name, rep, e['kind']] = e, labels
            continue
        s, m = e['scenario'], e['method']
        expected.remove((name, rep, s, m))
        producer = m if m.startswith('table_') else s.split('-')[0]
        h, labels = history[name, rep, producer]
        recs = h['assets']
        outputs = asset(contents, e, e['output_asset'], seen)
        require(outputs['rows'] == e['outputs'] and outputs['identity'] == labels['identity']
                and set(outputs['rows']) == set(SCENARIOS[s]), 'output bound to source/history')
        if e['input_bytes']:
            input_ = recs[m if m.startswith('vectors') else 'scalars']
            require((input_['bytes'], input_['sha256']) == (e['input_bytes'], e['input_sha256']), 'actual inputs')
        if m.startswith('table_'):
            require(all(labels['rows'][k] == v for k, v in outputs['rows'].items()), 'precomputed table values')
        readout_terms(e, labels['rows'], outputs['rows'], calibrator)
        for k, val in outputs['rows'].items():
            score = scientific(k, val, oracles[name])
            scored.append(dict(source=name, split=split, rep=rep, scenario=s, method=m, target=k,
                               status='passed' if score['v2_passed'] else 'false_accept', **score))
        stored = [recs['scalars']]
        if m.startswith('vectors'):
            stored.append(recs[m])
        ready = setup[name, 'first']['seconds'] + qa[name]['input_hash_seconds'] + qa[name]['report']['seconds']
        first_seconds = h['production_seconds_before_writes'] + sum(r['seconds'] for r in stored)
        shapes = {tuple(w for _, _, w in recipe) for recipe in e['terms'].values() if len(recipe) > 1} if m in ('single','two') else set()
        first_decoder = sum(builds[name, shape] for shape in shapes)
        paid_decoder = sum(b['seconds'] for b in e['decoder_builds'])
        costs.append(dict(source=name, split=split, repetition=rep, scenario=s, method=m, order=e['order'],
                          history_jk=h['cost']['jk_calls'], marginal_jk=e['cost']['jk_calls'], marg_rhs=e['cost']['rhs_columns'],
                          dense_rhs=e['dense_rhs'], history_dense_rhs=h['dense_rhs'], quality_jk=e['quality_native_actions'],
                          quality_seconds=e['quality_seconds'], planning_seconds=e['planning_seconds'],
                          history_seconds=first_seconds, service_seconds=e['seconds'], setup_and_stability_seconds=ready,
                          total_seconds=ready + first_seconds + e['seconds'], isolated_decoder_setup_seconds=first_decoder,
                          first_use_total_seconds=ready + first_seconds + e['seconds'] + first_decoder - paid_decoder,
                          validation_seconds_with_shared_stability=
                          qa[name]['report']['seconds'] + h['quality_seconds'] + e['quality_seconds'],
                          total_jk=setup[name, 'first']['cost']['jk_calls']+h['cost']['jk_calls']+e['cost']['jk_calls'],
                          retained_bytes=sum(r['bytes'] for r in stored), input_bytes=e['input_bytes'],
                          output_bytes=e['output_asset']['bytes'], input_seconds=e['input_seconds'],
                          output_seconds=e['output_asset']['seconds'], physical_blocks=e['cost']['submitted_blocks'],
                          native_block_actions=sum(b['native_actions'] for b in e['blocks']),
                          native_stored_vector_checks=sum(d['from_store'] for d in e['directions']),
                          cold_decoder_seconds=sum(b['seconds'] for b in e['decoder_builds']), dense_seconds=e['dense_seconds']))
    require(not expected and seen == set(contents) and len(source) == 17 and len(oracles) == 12, 'cohort or assets missing')
    require(len(scored) == len(source) * 4 * len(METHODS) * sum(map(len, SCENARIOS.values())), 'target denominator')
    require(jk == finish['jk'], 'actual total physical cost')
    require(all(v['v2_passed'] for v in histories), 'false historical acceptance')
    allowed = [r for r in scored if r['status'] != 'reference_unavailable']
    actual = dict(statuses=dict(Counter(r['status'] for r in scored)), counts=dict(phases), candidates=len(source),
                  measured_molecules=len(oracles), methods=len(METHODS), repetitions=4, warmups=1, persisted_files=len(contents),
                  observed_fallbacks=sum(bool(r.get('fallback')) for r in events), failures=len(rejected),
                  gqc_jk=jk, native_rhs=rhs, dense_rhs=dense_rhs, native_quality_checks=proof_actions,
                  blind_seconds=finish['seconds'],
                  independent_differences_over_numerical_estimate=sum(r['reference_error'] > r['error_estimate'] for r in allowed))
    by_readout = {}
    for o in OBS:
        rows = [r for r in allowed if r['target'].split('/')[1] == o]
        key = lambda r: (r['source'], r['target'])
        above = [r for r in rows if r['reference_error'] > r['error_estimate']]
        disjoint = [r for r in rows if r['reference_error'] > r['error_estimate'] + r['reference_error_estimate']]
        by_readout[o] = dict(unit='e / au_field' if o == 'q0' else 'bohr^2 / au_field',
                             trials=len(rows), unique_targets=len(set(map(key, rows))),
                             nominal_excess=len(above), unique_nominal_excess=len(set(map(key, above))),
                             two_estimates_disjoint=len(disjoint), unique_disjoint=len(set(map(key, disjoint))),
                             maximum_nominal_difference=max(r['reference_error'] for r in rows),
                             maximum_difference_lower=max(r['reference_difference_lower'] for r in rows),
                             maximum_difference_upper=max(r['reference_difference_upper'] for r in rows),
                             maximum_online_estimate=max(r['error_estimate'] for r in rows),
                             maximum_reference_estimate=max(r['reference_error_estimate'] for r in rows))
    actual['readout_calibration'] = by_readout
    actual['decoder_first_load_seconds'] = sum(builds.values())
    actual['decoder_first_loads'] = len(builds)
    actual['uncached_structural_planning_seconds'] = sum(r['planning_seconds'] for r in events if r.get('plan_cache_hit') is False)
    actual['cold_model_seconds'] = sum(r['seconds'] for r in setup.values() if r['kind'] == 'first')
    actual['reopened_model_seconds'] = sum(r['seconds'] for r in setup.values() if r['kind'] == 'reopen')
    actual['stability_seconds'] = sum(r['report']['seconds'] for r in qa.values())
    actual['matrix_bytes_per_molecule'] = [min(r['report']['matrix_bytes'] for r in qa.values()), max(r['report']['matrix_bytes'] for r in qa.values())]
    fields = list(dict.fromkeys(k for r in scored for k in r))
    scored = [{k: r.get(k, '') for k in fields} for r in scored]
    return actual, costs, scored, histories


def aggregates(costs):
    grouped = defaultdict(list)
    for row in costs:
        if row['repetition']:
            grouped[row['split'], row['scenario'], row['method'], row['repetition']].append(row)
    result = []
    for split, scenario, method in sorted({k[:3] for k in grouped}):
        samples = [grouped[split, scenario, method, i] for i in (1, 2, 3)]
        record = {'split': split, 'scenario': scenario, 'method': method, 'with_state': len(samples[0]),
                  'all_candidates': 6 if split == 'development' else 11}
        for k in ('history_jk','marginal_jk','marg_rhs','dense_rhs','history_dense_rhs','quality_jk','total_jk','retained_bytes',
                  'input_bytes','output_bytes','history_seconds','service_seconds','total_seconds',
                  'validation_seconds_with_shared_stability','cold_decoder_seconds','isolated_decoder_setup_seconds','first_use_total_seconds','dense_seconds'):
            values = [sum(r[k] for r in batch) for batch in samples]
            record[k] = median(values)
            if k.endswith('seconds'):
                record[k + '_min'], record[k + '_max'] = min(values), max(values)
        result.append(record)
    return result


def frontiers(groups):
    out = []
    for split in ('development', 'holdout'):
        scenarios = {(r['scenario'], r['method']): r for r in groups if r['split'] == split}
        for history, demand in [('cycle', (0, .5, 1)), ('cross', (1,))]:
            available = [scenarios[history + '-three', m] for m in sorted({m for scenario, m in scenarios if scenario == history + '-three'})]
            caps = sorted({r['retained_bytes'] for r in available})
            for cap, density, metric in itertools.product(caps, demand, ('seconds', 'first_use_seconds', 'jk')):
                lines = []
                for row in available:
                    if row['retained_bytes'] > cap:
                        continue
                    m = row['method']
                    low = scenarios.get((history + '-one', m), row)
                    # Independent sums of paired warm median costs for the first phase
                    # and for the sparse/dense second phase. Common setup cancels.
                    marginal = 'marginal_jk' if metric == 'jk' else 'service_seconds'
                    intercept = row['history_jk' if metric == 'jk' else 'history_seconds']
                    slope = (1-density)*low[marginal] + density*row[marginal]
                    if metric == 'first_use_seconds':
                        slope += (1-density)*low['isolated_decoder_setup_seconds'] + density*row['isolated_decoder_setup_seconds']
                    lines.append((m, intercept, slope))
                points = {0., 1.}
                for (_, a, b), (_, c, d) in itertools.combinations(lines, 2):
                    if b != d and 0 < (c-a)/(b-d) < 1:
                        points.add((c-a)/(b-d))
                intervals = []
                for left, right in zip(sorted(points)[:-1], sorted(points)[1:]):
                    vals = [(a + (left + right) / 2 * b, m) for m, a, b in lines]
                    best = min(v for v, _ in vals)
                    names = ','.join(sorted(m for v, m in vals if math.isclose(v, best, rel_tol=1e-13, abs_tol=1e-15)))
                    if intervals and intervals[-1][2] == names:
                        intervals[-1][1] = right
                    else:
                        intervals.append([left, right, names])
                def ties(p):
                    vals = [(a+p*b, m) for m, a, b in lines]
                    best = min(v for v, _ in vals)
                    return ','.join(sorted(m for v, m in vals if math.isclose(v, best, rel_tol=1e-13, abs_tol=1e-15)))
                for left, right, names in intervals:
                    out.append(dict(split=split, history=history, dense_weight_given_request=density,
                                    total_history_byte_cap=cap, metric=metric, request_probability_low=left,
                                    request_probability_high=right, minimum_on_open_interval=names,
                                    minima_at_low=ties(left), minima_at_high=ties(right)))
    return out


def main():
    import time
    t = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, help='completed sealed blind measurement directory')
    parser.add_argument('--directory', type=Path, default=HERE / 'evidence')
    args = parser.parse_args()
    if args.package:
        package(args.package, args.directory)
    summary, costs, scores, history = verify(args.directory)
    groups = aggregates(costs)
    data = {'summary.json':dump(summary), 'paired-costs.csv.gz':csv_bytes(costs), 'target-scores.csv.gz':csv_bytes(scores),
            'history-scores.csv.gz':csv_bytes(history), 'recovery-conditioning.csv':csv_bytes(conditioning(args.directory)),
            'cohort-costs.csv':csv_bytes(groups), 'frontiers.csv':csv_bytes(frontiers(groups))}
    for name, raw in data.items():
        path = args.directory / name
        if args.package:
            with path.open('xb') as file:
                file.write(gzip.compress(raw, mtime=0) if name.endswith('.gz') else raw)
        actual = gzip.decompress(path.read_bytes()) if name.endswith('.gz') else path.read_bytes()
        require(actual == raw, name)
    print(json.dumps(summary, sort_keys=True), 'offline seconds', time.perf_counter() - t)


if __name__ == '__main__':
    main()
