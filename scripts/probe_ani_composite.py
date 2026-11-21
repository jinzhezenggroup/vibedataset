#!/usr/bin/env python3
"""Apply the ANI-1ccx published composite equation to an identity-checked release slice."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

import numpy as np
from generativeqc_compiler.tensor import Program, TensorSpec, add, constant, divide, execute, input_tensor
from generativeqc_compiler.tensor import interpreter

from fetch_ani_composite import ASSETS, COLUMNS, FILE_ID

GQC_SHA = '2791504cc238fe83d328fc1718080642b288222a'
HF = ('hf_t', 'hf_q')
MP2 = HF + ('mp2_t', 'mp2_q')
CC = MP2 + ('normal_t', 'tight_d', 'normal_d')
TARGETS = {'hf_cbs': HF, 'mp2_cbs': MP2, 'cc_star_cbs': CC}
A3, A4 = (math.exp(-5.46 * math.sqrt(z)) for z in (3, 4))
B3, B4 = (z ** 3.05 for z in (3, 4))


def equations():
    values = {i: input_tensor(i, TensorSpec(role='input')) for i in CC}

    def extrapolate(left, right, a, b):
        numerator = add(values[left], values[right], coefficients=(Fraction(a), Fraction(-b)))
        return divide(numerator, constant(Fraction(a - b)))

    h = extrapolate('hf_t', 'hf_q', A4, A3)
    m = extrapolate('mp2_q', 'mp2_t', B4, B3)
    mp = add(h, m)
    final = add(mp, values['mp2_t'], values['normal_t'], values['tight_d'], values['normal_d'],
                coefficients=(1, -1, 1, 1, -1))
    return {'hf_cbs': h, 'mp2_cbs': mp, 'cc_star_cbs': final}


def manual(components, targets):
    if not targets:
        return {}
    h = (A4 * components['hf_t'] - A3 * components['hf_q']) / (A4 - A3)
    outputs = {'hf_cbs': h}
    if 'mp2_cbs' in targets:
        m = (B4 * components['mp2_q'] - B3 * components['mp2_t']) / (B4 - B3)
        outputs['mp2_cbs'] = h + m
    if 'cc_star_cbs' in targets:
        outputs['cc_star_cbs'] = (outputs['mp2_cbs'] - components['mp2_t'] + components['normal_t']
                                  + components['tight_d'] - components['normal_d'])
    return outputs


def load_packet(directory):
    packet = directory / 'components.npz'
    info = json.loads((directory / 'fetch.json').read_text())
    sample = json.loads((ASSETS / 'ani-v1-slice.json').read_text())
    if (info['file_id'], info['doi'], info['columns']) != (FILE_ID, sample['doi'], COLUMNS):
        raise ValueError('unexpected component schema/release')
    if hashlib.sha256(packet.read_bytes()).hexdigest() != info['components_npz_sha256']:
        raise ValueError('packet hash differs from fetch receipt')
    groups = []
    with np.load(packet, allow_pickle=False) as arrays:
        for i, (group, expected) in enumerate(zip(info['groups'], sample['groups'], strict=True)):
            lo, hi = expected['row_interval']
            if (group['group'], group['rows'], group['coordinate_slice_sha256']) != (
                    expected['group'], [lo, hi], expected['fields']['coordinates']['slice_sha256_c_order']):
                raise ValueError('coordinate identity mismatch')
            columns = {}
            for col in COLUMNS:
                key = f'g{i}_{col}'
                val = arrays[key]
                digest = hashlib.sha256(val.tobytes()).hexdigest()
                if val.shape != (hi - lo,) or val.dtype.str != '<f8' or digest != info['array_sha256_c_order'][key]:
                    raise ValueError(f'column identity mismatch for {key}')
                if col == 'published' and digest != expected['fields']['ccsd(t)_cbs.energy']['slice_sha256_c_order']:
                    raise ValueError('target column no longer matches release sampling receipt')
                columns[col] = val
            groups.append((group['group'], lo, hi, columns))
    return groups


def probe(directory):
    src = Path(interpreter.__file__).resolve().parents[3]
    actual_commit = subprocess.check_output(['git', '-C', src, 'rev-parse', 'HEAD'], text=True).strip()
    if actual_commit != GQC_SHA or subprocess.check_output(['git', '-C', src, 'status', '--porcelain']):
        raise ValueError('expected clean pinned GQC compiler checkout')
    start = time.perf_counter()
    groups = load_packet(directory)
    read_seconds = time.perf_counter() - start
    nodes = equations()
    programs, evaluations, seconds = {}, Counter(), Counter()
    rows = []

    def run_ir(names, feeds, strategy):
        t = time.perf_counter()
        if names not in programs:
            programs[names] = Program({name: nodes[name] for name in names})
        program = programs[names]
        result = execute(program, feeds, debug=True)
        # The debug interpreter emits one snapshot for each node it actually evaluates.
        evaluations[strategy] += len(result.intermediates)
        seconds[strategy] += time.perf_counter() - t
        return {key: float(val) for key, val in result.outputs.items()}

    for group, lo, hi, columns in groups:
        for offset in range(hi - lo):
            # Bind by immutable file + group + row. Never place the published target in feeds.
            data = {k: columns[k][offset] for k in CC if np.isfinite(columns[k][offset])}
            names = tuple(k for k, needs in TARGETS.items() if all(n in data for n in needs))
            joint = run_ir(names, data, 'joint') if names else {}
            single = {key: run_ir((key,), data, 'independent')[key] for key in names}
            t = time.perf_counter()
            ref = manual(data, names)
            seconds['manual'] += time.perf_counter() - t
            error = max((abs(joint[k] - ref[k]) for k in names), default=0.)
            pub = columns['published'][offset]
            rows.append({'group': group, 'row': lo + offset, 'finite_components': list(data),
                         'missing_cc_components': [k for k in CC if k not in data],
                         'computed_hartree': joint, 'manual_max_difference': float(error),
                         'separate_identical_bits': all(np.float64(single[k]).tobytes() == np.float64(joint[k]).tobytes() for k in names),
                         'published_hartree': float(pub) if np.isfinite(pub) else None})

    comparisons = [abs(r['computed_hartree']['cc_star_cbs'] - r['published_hartree']) for r in rows
                   if 'cc_star_cbs' in r['computed_hartree'] and r['published_hartree'] is not None]
    manual_error = max(r['manual_max_difference'] for r in rows)
    qualified = bool(len(comparisons) >= 2 and max(comparisons) <= 1e-8 and manual_error <= 1e-10
                     and all(r['separate_identical_bits'] for r in rows))
    coverage = Counter()
    for row in rows:
        has_reference = row['published_hartree'] is not None
        computed = 'cc_star_cbs' in row['computed_hartree']
        coverage['published' if has_reference else 'originally_missing'] += 1
        if computed:
            coverage['complete_with_published' if has_reference else 'complete_originally_missing'] += 1
        else:
            coverage['incomplete_with_published' if has_reference else 'incomplete_originally_missing'] += 1
    return {
        'compiler_commit': actual_commit, 'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'doi': '10.6084/m9.figshare.10047041.v1', 'precision': 'float64',
        'program_sha256': {'+'.join(k): hashlib.sha256(p.dumps().encode()).hexdigest() for k, p in programs.items()},
        'backend': 'GQC numpy-cpu-interpreter, debug snapshots enabled in joint and independent runs',
        'thresholds_hartree': {'manual': 1e-10, 'published': 1e-8}, 'qualification_passed': qualified,
        'row_count': len(rows), 'available_targets': {t: sum(t in r['computed_hartree'] for r in rows) for t in nodes},
        'coverage': dict(coverage), 'observed_new_cc_labels_qualified': coverage['complete_originally_missing'] if qualified else 0,
        'manual_max_abs_hartree': manual_error, 'published_max_abs_hartree': max(comparisons, default=None),
        'node_evaluations': dict(evaluations), 'execution_seconds_including_debug': dict(seconds),
        'packet_load_and_verify_seconds': read_seconds, 'total_probe_seconds_after_source_check': time.perf_counter() - start,
        'new_quantum_jobs': 0, 'rows': rows,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    report = probe(parser.parse_args().packet)
    print(json.dumps(report, indent=2, allow_nan=False))
    raise SystemExit(0 if report['qualification_passed'] else 1)
