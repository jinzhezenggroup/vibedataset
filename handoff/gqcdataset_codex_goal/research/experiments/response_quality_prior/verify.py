"""Check the published DWR observations against the exact diagonal control using the standard library."""
import gzip
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def require(result, name):
    if not result:
        raise ValueError(name)


def main():
    source = (HERE / 'pymor.json').read_bytes()
    data = json.loads(source)
    audit = json.loads((HERE / 'verification.json').read_bytes())
    require(sha256(source).hexdigest() == audit['pymor_report_sha256'], 'published pyMOR report')
    require(sha256(gzip.decompress((HERE / 'pymor.log.gz').read_bytes())).hexdigest() ==
            audit['pymor_log_sha256_uncompressed'], 'upstream solver log')
    require(sha256((HERE / 'compare.py').read_bytes()).hexdigest() == data['code_sha256'], 'producer source')
    spectrum = [Fraction(data['matrix'][i][i]) for i in range(3)]
    truth = sum(Fraction(w) * Fraction(b) / diag for w, b, diag in zip(data['readout'], data['rhs'], spectrum))
    require(str(min(spectrum)) == data['represented_exact_minimum'] and str(truth) == data['exact_target'],
            'exact represented spectrum or target')
    residual = data['residual_only']
    require(residual['physical_residual'] == data['rhs'][1] < residual['residual_gate'] and
            residual['observed_error'] == abs(truth - Fraction(residual['candidate'])) > data['tolerance'],
            'residual-only false acceptance')
    observed = set()
    for case in data['cases']:
        basis, alpha = case['dual_basis'], Fraction(case['supplied_alpha'])
        observed.add((basis, alpha))
        exact_error = abs(truth - Fraction(case['q_corrected']))
        expected_estimate = abs(Fraction(data['rhs'][1])) / alpha if basis == 'unresolved_output_mode' else 0
        require(exact_error == case['error'] and expected_estimate == case['dwr_estimate'], 'DWR result')
        require(case['accepted'] == (expected_estimate <= data['tolerance']) and
                case['false_accept'] == (case['accepted'] and exact_error > data['tolerance']), 'decision')
    require(len(data['cases']) == 4 and observed == {(basis, alpha) for basis in
            ('resolved_output_mode', 'unresolved_output_mode') for alpha in (min(spectrum), Fraction(1))},
            'control denominator')
    require(sum(r['false_accept'] for r in data['cases']) == 1, 'expected false-accept control')
    print('4 pyMOR output controls and the residual-only false acceptance agree with the exact diagonal equation')


if __name__ == '__main__':
    main()
