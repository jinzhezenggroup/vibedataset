#!/usr/bin/env python3
"""PLAN-002. Complete missing static derivatives using measured, typed scalar constraints."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from gqc_dual_response import DualResponseModel, FIELD_IDS, OBSERVABLE_IDS
from generativeqc_compiler.common.cpp_adapter import CppCompilerAdapter
from generativeqc_compiler.tensor import Program, TensorSpec, add, input_tensor
from generativeqc_compiler.tensor.cpu import NativeTensorProgram

from probe_gqc_residual import file_hash, write_json
from probe_response_planning import EDGES, ROOT, journal, read_scalars, scalar_identity, write_scalars

DIAGONAL = tuple(zip(FIELD_IDS, OBSERVABLE_IDS, strict=True))
HISTORY = tuple(edge for edge in EDGES if edge not in DIAGONAL)
POLICIES = ('legacy_recompute', 'legacy_decode', 'keep_vectors', 'eager_table', 'remove_history')


def decoder(kernel_cache):
    vars_ = [input_tensor(name, TensorSpec(role='input')) for name in ('combined', 'first', 'second')]
    program = Program({'missing': add(*vars_, coefficients=(1, -1, -1))},
                      provenance={'purpose': 'one uniform-field sum minus two archived derivatives, same observable'})
    return NativeTensorProgram(program, compiler=CppCompilerAdapter(Path('c++')), cache=kernel_cache,
                               max_bytes=1 << 20, max_work=1000)


def recoverable(published):
    dependencies = {}
    for field, observable in DIAGONAL:
        needed = [(other, observable) for other in FIELD_IDS if other != field]
        if all(pair in published for pair in needed):
            dependencies[(field, observable)] = needed
    return dependencies


def run(model, identity, native, out, policy, events):
    dest = out / model.name / policy
    dest.mkdir(parents=True)
    history_path = dest / 'scalars.json'
    state_path = dest / 'vectors.json'
    start = time.perf_counter()
    journal(events, {'event': 'history_started', 'case': model.name, 'policy': policy})
    state = model.new_cache()
    requested = EDGES if policy == 'eager_table' else HISTORY
    first = model.run_round(requested, FIELD_IDS, (), state)
    good = {(r['field'], r['observable']): r['value'] for r in first['results'] if r['qualified']}
    written = write_scalars(history_path, identity, good)
    vector_bytes = 0
    if policy == 'keep_vectors':
        model.save_cache(state, state_path)
        vector_bytes = state_path.stat().st_size
    first_seconds = time.perf_counter() - start
    journal(events, {'event': 'history_finished', 'case': model.name, 'policy': policy,
                     'counts': first['counts'], 'seconds': first_seconds})
    del state
    journal(events, {'event': 'completion_started', 'case': model.name, 'policy': policy})
    start = time.perf_counter()
    labels, read = read_scalars(history_path, identity)
    if policy == 'remove_history':
        labels = {}
    cache = model.load_cache(state_path) if vector_bytes else model.new_cache()
    required = set(DIAGONAL).difference(labels)
    deps = recoverable(labels) if policy in ('legacy_decode', 'remove_history') else {}
    usable = {key: needed for key, needed in deps.items() if key in required}
    # One combined RHS and one direct RHS per remaining diagonal. A tie calls the ordinary block.
    if 1 + len(required) - len(usable) >= len(required):
        usable = {}
    if policy == 'remove_history' and usable:
        raise AssertionError('missing terms cannot be subtracted')
    counts = Counter()
    combination = None
    calculation = None
    results = []
    for field, obs in sorted(set(DIAGONAL).intersection(labels)):
        results.append({'field': field, 'observable': obs, 'value': labels[(field, obs)],
                        'qualified': True, 'via': 'stored_qualified_scalar'})
    if usable:
        combination = model.combined_field([1, 1, 1], [obs for _, obs in usable])
        counts.update(combination['counts'])
        for (field, obs), known in usable.items():
            first_known, second_known = [labels[e] for e in known]
            combined = combination['values'][obs]
            recovered = float(native.execute({'combined': np.asarray(combined), 'first': np.asarray(first_known),
                                              'second': np.asarray(second_known)})['missing'])
            row = model.assess(field, obs, recovered)
            row.update(via='combined_field_minus_published', subtracted=known,
                       operands=[combined, first_known, second_known],
                       hand_difference=abs(recovered - (combined - first_known - second_known)))
            if row['hand_difference'] > 1e-10:
                raise ValueError('manual scalar recovery and compiled program differ')
            results.append(row)
    remaining = sorted(required - usable.keys())
    if remaining:
        new = sorted({f for f, _ in remaining} - cache['fields'].keys())
        calculation = model.run_round(remaining, new, (), cache)
        counts.update(calculation['counts'])
        results.extend(calculation['results'])
    if {(r['field'], r['observable']) for r in results} != set(DIAGONAL):
        raise AssertionError('a requested target was lost')
    published = {(r['field'], r['observable']): r['value'] for r in results if r['qualified']}
    new_label_bytes = write_scalars(dest / 'new-labels.json', identity, published)
    second_seconds = time.perf_counter() - start
    journal(events, {'event': 'completion_finished', 'case': model.name, 'policy': policy,
                     'counts': dict(counts), 'seconds': second_seconds})
    return {'name': model.name, 'policy': policy, 'identity': identity,
            'historical_requested': len(HISTORY), 'historical_actually_projected': len(requested),
            'history_qualified': len(good), 'history_scalar_bytes': written, 'history_vector_bytes': vector_bytes,
            'second_read_bytes': read + vector_bytes,
            'second_label_bytes': new_label_bytes, 'first_seconds': first_seconds, 'second_seconds': second_seconds,
            'first_counts': first['counts'], 'second_counts': dict(counts),
            'cumulative_jk': first['counts']['jk_calls'] + counts['jk_calls'],
            'completion_results': results, 'first_results': first['results'],
            'combination': combination, 'remaining_block': calculation['block'] if calculation else None,
            'vector_admission': calculation['cache_checks'] if calculation else []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('assets', 'oracles', 'out'):
        parser.add_argument('--' + arg, required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    native = decoder(args.out / 'decoder')
    decoder_seconds = time.perf_counter() - start
    source = json.loads((args.assets / 'index.json').read_text())
    summary = {'project_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'driver_sha256': file_hash(__file__), 'planner_io_sha256': file_hash(ROOT / 'scripts/probe_response_planning.py'),
               'api_sha256': file_hash(ROOT / 'scripts/gqc_dual_response.py'), 'index_sha256': file_hash(args.assets / 'index.json'),
               'threads': {k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
               'decoder_binary_sha256': file_hash(native.library._name), 'decoder_startup_seconds': decoder_seconds,
               'strata': [], 'runs': []}
    for i, case in enumerate(source['rows']):
        info = {k: case.get(k) for k in ('stratum', 'status', 'name', 'error', 'member_sha256')}
        summary['strata'].append(info)
        if case['status'] != 'verified':
            continue
        meta, archive = args.assets / case['metadata_file'], args.assets / case['array_file']
        if (file_hash(meta), file_hash(archive)) != (case['metadata_sha256'], case['array_file_sha256']):
            raise ValueError('upstream asset digest mismatch')
        oracle_path = args.oracles / (case['name'] + '.json')
        model = DualResponseModel(meta, archive, args.out / 'native', oracle_path)
        identity = scalar_identity(model)
        info.update(setup=model.setup, scalar_identity=identity, oracle_sha256=file_hash(oracle_path))
        # Shift the order by source stratum; no sharing of scientific states between strategies.
        order = POLICIES[i % len(POLICIES):] + POLICIES[:i % len(POLICIES)]
        for policy in order:
            summary['runs'].append(run(model, identity, native, args.out, policy, args.out / 'operations.jsonl'))
        witness = args.out / model.name / 'legacy_decode' / 'scalars.json'
        try:
            read_scalars(witness, 'incompatible-reference-identity')
        except ValueError:
            info['foreign_identity_rejected'] = True
        else:
            raise AssertionError('foreign scalar archive accepted')
        write_json(args.out / 'summary.json', summary)
        print(model.name, len(summary['runs']), flush=True)
    summary['wall_seconds_including_journal_and_output'] = time.perf_counter() - start
    write_json(args.out / 'summary.json', summary)


if __name__ == '__main__':
    main()
