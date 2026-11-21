"""Recompute the exact decisions first, then independently score them against the pinned v2 release."""
from argparse import ArgumentParser
from collections import Counter
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from struct import pack, unpack_from
import tarfile
from zipfile import ZipFile

from bound import TOLERANCE, exact_bound

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


def require(ok, msg):
    if not ok:
        raise ValueError(msg)


def score(directory):
    raw = (directory/'decisions.json').read_bytes()
    data = json.loads(raw)
    vectors = EXP/'partial_response_blocks/cohort/assets.tar.gz'
    systems = directory/'systems.zip'
    require(sha256(vectors.read_bytes()).hexdigest() == data['archive_sha256'] and
            sha256(systems.read_bytes()).hexdigest() == data['systems_sha256'], 'input digest')
    frozen = {}
    counts = Counter()
    with ZipFile(systems) as z, tarfile.open(vectors, 'r:gz') as source:
        for rec in data['decisions']:
            name = rec['name']
            require(name not in frozen, 'duplicate source')
            frozen[name] = dict(status=rec['status'])
            counts[rec['status']] += 1
            if 'bound' not in rec:
                continue
            payload = z.read(name + '.f64')
            bound = exact_bound(payload)
            n = bound['dimension']
            require(bound == rec['bound'] and rec['status'] == bound['status'], name + ' bound')
            vector = json.load(source.extractfile(rec['vector_member']))['fields']['x']
            end = 8*n*n
            require(sha256(payload[:end]).hexdigest() == rec['assembly']['matrix_sha256'] and
                    sha256(payload[end:end+8*n]).hexdigest() == vector['rhs_sha256'] and
                    sha256(payload[-8*n-8:-8]).hexdigest() == vector['solution_sha256'] == rec['vector_sha256'],
                    name + ' physical assets')
            q = unpack_from('<d', payload, len(payload)-8)[0]
            require(q == rec['raw_readout'] and vector['endpoint_identity'] == rec['field_identity'] and
                    vector['problem_identity'] == rec['setup']['problem_identity'] and
                    rec['vector_checks']['decision'] == 'accepted', name + ' identity or projection')
            frozen[name].update(raw_value=q, minimum_margin=float(Fraction(bound['minimum_margin'])))
            if 'absolute_bound' in bound:
                frozen[name]['represented_absolute_bound'] = float(Fraction(bound['absolute_bound']))
        require(set(z.namelist()) == {r['name']+'.f64' for r in data['decisions'] if 'bound' in r},
                'unaccounted matrices')
    require(len(frozen) == 17 and dict(counts) == data['statuses'], 'frozen denominator')
    # No release values enter any of the decisions recomputed above.
    seen = set()
    false = 0
    for phase in ('seed', 'extension'):
        catalog = EXP/'cphf_v2'/phase/'index.json'
        for row in json.loads(catalog.read_bytes())['strata']:
            name = row['name']
            if not name:
                continue
            candidate = frozen[name]
            seen.add(name)
            if row['status'] != 'completed':
                require(candidate['status'] == 'reference_unavailable', name + ' unavailable ground state')
                continue
            path = catalog.parent/row['oracle']
            require(sha256(path.read_bytes()).hexdigest() == row['sha256'], 'evaluation reference digest')
            oracle = json.loads(path.read_bytes())['targets']['x']['q0']
            require(oracle['qualified'], 'unqualified evaluation reference')
            if 'raw_value' not in candidate:
                continue
            error = abs(candidate['raw_value'] - oracle['cphf'])
            discrepancy = max(abs(candidate['raw_value'] - v) for v in oracle['finite_fields'].values())
            ok = error + oracle['reference_precision']['readout_error_estimate'] <= float(TOLERANCE) and discrepancy <= 1e-4
            candidate.update(oracle_sha256=row['sha256'], cphf_difference=error, maximum_fd_difference=discrepancy,
                             v2_check=ok)
            false += int(candidate['status'] == 'accepted' and not ok)
    require(seen == set(frozen), 'independent evaluation sources')
    solved = [r for r in data['decisions'] if 'setup' in r]
    return dict(decision_sha256=sha256(raw).hexdigest(), statuses=counts, available_ground_states=len(solved),
                false_accepts_vs_v2=false, setup_jk=sum(r['setup']['counts']['jk_calls'] for r in solved),
                validation_jk=sum(r['validation_counts'].get('jk_calls',0) for r in solved),
                ao_to_mo_transforms=sum(r['assembly']['ao_to_mo_transforms'] for r in solved),
                svds=sum(r['assembly']['svd_calls'] for r in solved),
                rational_check_seconds=sum(r.get('bound_seconds', 0.) for r in solved), molecules=frozen)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=HERE)
    parser.add_argument('--out', type=Path, help='write a new independent score; default compares the archived score')
    args = parser.parse_args()
    # Even an arbitrarily small residual can imply a 1/4 output error.
    packed = pack('<11d', 1.,0.,0.,2.**-33, 1.,2.**-35, 0.,1., 1.,0.,0.)
    control = exact_bound(packed)
    require(control['status'] == 'refine' and Fraction(control['absolute_bound']) == Fraction(1,4),
            'near-singular represented system')
    report = score(args.bundle)
    if args.out:
        with args.out.open('x') as h:
            json.dump(report, h, sort_keys=True, indent=2, allow_nan=False)
            h.write('\n')
    else:
        require(report == json.loads((args.bundle/'score.json').read_bytes()), 'published evaluation score differs')
    print(json.dumps(report['statuses'], sort_keys=True))


if __name__ == '__main__':
    main()
