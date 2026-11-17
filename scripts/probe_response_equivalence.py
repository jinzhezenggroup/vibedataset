#!/usr/bin/env python3
"""Measure same-operator scalar recovery without producing any publishable cached labels."""
import argparse
import json
from pathlib import Path
import subprocess
import time

import numpy as np

from gqc_dual_response import ANALYTIC_TOL, DualResponseModel, FIELD_IDS, OBSERVABLE_IDS
from probe_gqc_residual import file_hash, json_hash, write_json
from probe_response_planning import ROOT, journal, scalar_identity
from probe_scalar_response import DIAGONAL, HISTORY, decoder


def measured_round(model, edges):
    result = model.run_round(edges, FIELD_IDS, (), model.new_cache())
    if any(row['status'] != 'residual_verified' or row['value'] is not None for row in result['results']):
        raise ValueError('same-operator experiment requires residual-verified raw observations')
    return result


def run_case(row, assets, oracle_path, out, native, log):
    name = row['name']
    meta, arrays = assets / row['metadata_file'], assets / row['array_file']
    if (file_hash(meta), file_hash(arrays)) != (row['metadata_sha256'], row['array_file_sha256']):
        raise ValueError('reference file digest mismatch')
    model = DualResponseModel(meta, arrays, out / 'native')
    log.update(setup=model.setup, oracle_sha256=file_hash(oracle_path))
    t = time.perf_counter()
    history = measured_round(model, HISTORY)
    log['history'] = history
    identity = json_hash({'purpose':'same-operator diagnostic only', 'physical_identity':scalar_identity(model)})
    payload = {'identity':identity, 'readouts':history['results']}
    file = out / (name + '-diagnostic-operands.json')
    write_json(file, {'sha256':json_hash(payload), 'payload':payload})
    log.update(history_seconds_with_write=time.perf_counter()-t, operand_bytes=file.stat().st_size)
    t = time.perf_counter()
    check = json.loads(file.read_bytes())
    saved = check['payload']
    if saved['identity'] != identity or json_hash(saved) != check['sha256']:
        raise ValueError('wrong diagnostic operands')
    operands = {(v['field'], v['observable']):v['raw_value'] for v in saved['readouts']}
    if operands.keys() != set(HISTORY):
        raise ValueError('incomplete measured history')
    combined = model.combined_field([1, 1, 1], OBSERVABLE_IDS)
    log['combined'] = combined
    decoded = {}
    for field, obs in DIAGONAL:
        first, second = [operands[f, obs] for f in FIELD_IDS if f != field]
        total = combined['values'][obs]
        value = float(native.execute({'combined':np.asarray(total), 'first':np.asarray(first),
                                      'second':np.asarray(second)})['missing'])
        decoded[field, obs] = (value, abs(value - (total-first-second)))
    log['recovery_seconds_with_read'] = time.perf_counter() - t
    t = time.perf_counter()
    direct = measured_round(model, DIAGONAL)
    log.update(direct=direct, direct_seconds=time.perf_counter()-t)
    # Independent values enter only after both same-operator paths have finished.
    model.attach_oracle(oracle_path)
    comparisons = []
    for r in direct['results']:
        f, o = r['field'], r['observable']
        value, hand_error = decoded[f, o]
        delta = abs(value-r['raw_value'])
        comparisons.append({'field':f, 'observable':o, 'recovered_diagnostic':value, 'direct_diagnostic':r['raw_value'],
                            'absolute_difference':delta, 'hand_difference':hand_error,
                            'passes_same_operator_tolerance':delta <= ANALYTIC_TOL and hand_error <= 1e-10,
                            'independent_reference_qualified':model.oracle['targets'][f][o]['qualified'],
                            'independent_assessment_of_diagnostic': model.assess(f, o, value)['reasons']})
    log['comparisons'] = comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('assets','oracles','out'):
        parser.add_argument('--'+flag,type=Path,required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    started = time.perf_counter()
    native = decoder(args.out/'decoder')
    report = {'purpose':'diagnostic only; no release labels written', 'index_sha256':file_hash(args.assets/'index.json'),
              'driver_sha256':file_hash(__file__), 'api_sha256':file_hash(ROOT/'scripts/gqc_dual_response.py'),
              'scalar_driver_sha256':file_hash(ROOT/'scripts/probe_scalar_response.py'),
              'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'compiled_decoder_sha256':file_hash(native.library._name),'decoder_seconds':time.perf_counter()-started,
              'records':[]}
    for row in json.loads((args.assets/'index.json').read_text())['rows']:
        record = {key:row.get(key) for key in ('name','qm9_id','status','error','stratum','member_sha256')}
        report['records'].append(record)
        if row['status'] != 'verified':
            continue
        name = row['name']
        journal(args.out/'events.jsonl',{'molecule':name,'event':'started'})
        start = time.perf_counter()
        try:
            run_case(row,args.assets,args.oracles/(name+'.json'),args.out,native,record)
            record['status'] = 'completed'
        except Exception as error:
            record.update(status='diagnostic_failed',error=f'{type(error).__name__}: {error}')
        record['seconds'] = time.perf_counter()-start
        journal(args.out/'events.jsonl',{'molecule':name,'event':record['status'],'seconds':record['seconds']})
        write_json(args.out/'summary.json',report)
        print(name,record['status'],flush=True)
    report['total_seconds'] = time.perf_counter()-started
    write_json(args.out/'summary.json',report)
    return int(any(r['status']=='diagnostic_failed' for r in report['records']))


if __name__ == '__main__':
    raise SystemExit(main())
