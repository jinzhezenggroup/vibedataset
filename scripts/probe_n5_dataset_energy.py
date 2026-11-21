#!/usr/bin/env python3
"""N5-DS-001: add a separate cold RHF energy to each pinned QCFractal input."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import itertools
import json
import lzma
import math
import os
from pathlib import Path
import platform
import time

import generativeqc
from generativeqc import Atom, Calculator, _native
from generativeqc.checkpoint import _controls
from pyscf import gto, scf

from probe_gqc_checkpoint import Journal


def read(path):
    return json.loads(path.read_bytes())


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def fingerprint(obj):
    return digest(json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def load_inputs(directory, manifest):
    rows = []
    for record in manifest:
        path = directory / record['path']
        raw = path.read_bytes()
        if len(raw) != record['bytes'] or digest(raw) != record['sha256']:
            raise ValueError(f'input differs from pinned bytes: {path.name}')
        data = json.loads(lzma.decompress(raw))
        task, result = data['input'], data['result']
        m = task['molecule']
        if (len(m['geometry']) != 3 * len(m['symbols']) or not all(m.get('real', [True]))
                or m['molecular_charge'] != 0 or m['molecular_multiplicity'] != 1
                or not all(math.isfinite(x) for x in m['geometry'])):
            raise ValueError(f'geometry outside this protocol: {path.name}')
        atoms = [Atom.from_value((s, m['geometry'][3*i:3*i+3])) for i, s in enumerate(m['symbols'])]
        error = result.get('error') or {}
        msg = error.get('error_message', '')
        if 'Unable to find a basis set' in msg:
            cause = 'upstream_basis_not_found'
        elif 'Could not converge SCF iterations' in msg:
            cause = 'upstream_scf_nonconvergence'
        else:
            cause = error.get('error_type')
        rows.append({'id': path.name, 'source_sha256': record['sha256'], 'molecule': m.get('name'),
                     'source_model': task['model'], 'source_driver': task['driver'], 'source_keywords': task['keywords'],
                     'source_protocols': task['protocols'], 'source_success': result['success'],
                     'source_error': cause, 'atoms': atoms, 'charge': int(m['molecular_charge']),
                     'multiplicity': m['molecular_multiplicity']})
    return rows


def assign_keys(rows, calc, protocol):
    identities = {}
    for row in rows:
        atoms = row['atoms']
        scientific = calc.resolved_model(atoms, charge=row['charge'], multiplicity=row['multiplicity']).to_dict()
        basis = calc.basis_metadata(atoms, charge=row['charge'], multiplicity=row['multiplicity'])
        identity = {'protocol_sha256': fingerprint(protocol), 'ordered_atomic_numbers': [a.atomic_number for a in atoms],
                    'coordinates_bohr_hex': [[(x if x else 0.).hex() for x in a.position] for a in atoms],
                    'charge': row['charge'], 'multiplicity': row['multiplicity'],
                    'resolved_model': scientific, 'basis_metadata': basis}
        key = fingerprint(identity)
        row['target_key'] = key
        identities.setdefault(key, identity)
        if identities[key] != identity:
            raise ValueError('nonidentical scientific identities share a digest')
    return identities


def snapshot(item):
    good = item.succeeded and item.converged and item.executed_backend == 'cuda' and math.isfinite(item.energy)
    good = good and not item.warm_start_used and not item.warm_start_fallback and item.restart_origin == 'cold'
    return {'stage_status': 'valid' if good else 'failed', 'status_code': int(item.status),
            'status_message': item.status_message, 'iterations': int(item.iterations),
            'fock_builds': item.fock_builds, 'converged': bool(item.converged),
            'executed_backend': item.executed_backend, 'warm_start_used': bool(item.warm_start_used),
            'warm_start_fallback': bool(item.warm_start_fallback), 'restart_origin': item.restart_origin,
            'basis_identity': item.basis_metadata['orbital']['basis_identity'],
            'energy_hartree': float(item.energy) if math.isfinite(item.energy) else None}


def calculate_batch(label, rows, options, journal):
    try:
        def prepare():
            return Calculator(**options).prepare_batch(
                [r['atoms'] for r in rows], charges=[r['charge'] for r in rows],
                multiplicities=[r['multiplicity'] for r in rows], warm_start=False)
        with journal.call(label, 'gqc_prepare', prepare) as batch:
            items = journal.call(label, 'gqc_execute', lambda: batch.execute(strict=False, properties=('energy',)))
            if len(items.items) != len(rows) or any(item.index != i for i, item in enumerate(items.items)):
                raise ValueError('GQC batch slot or cardinality mismatch')
            return [snapshot(item) for item in items.items]
    except Exception as exc:
        return [{'stage_status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)} for row in rows]


def pyscf_reference(row, shells, comparison, journal):
    def solve():
        atoms = row['atoms']
        basis = {}
        for atom in atoms:
            symbol = gto.mole._symbol(atom.atomic_number)
            if symbol not in basis:
                basis[symbol] = [
                    [shell['angular_momentum'], *[(float(e), float(c)) for e, c in
                     zip(shell['exponents'], shell['coefficients'], strict=True)]]
                    for shell in shells[str(atom.atomic_number)]]
        mol = gto.M(atom=[(gto.mole._symbol(a.atomic_number), a.position) for a in atoms],
                    basis=basis, charge=row['charge'], spin=row['multiplicity'] - 1,
                    unit='Bohr', cart=False, verbose=0)
        mf = scf.RHF(mol)
        mf.chkfile = None
        mf.init_guess = 'minao'
        mf.conv_tol = comparison['pyscf_conv_tol']
        mf.conv_tol_grad = comparison['pyscf_conv_tol_grad']
        mf.direct_scf_tol = 1e-14
        mf.max_cycle = comparison['max_cycle']
        energy = float(mf.kernel())
        valid = mf.converged and math.isfinite(energy)
        return {'stage_status': 'valid' if valid else 'failed', 'n_ao': mol.nao_nr(),
                'electrons': mol.nelectron, 'cycles': int(mf.cycles), 'converged': bool(mf.converged),
                'energy_hartree': energy if math.isfinite(energy) else None}
    try:
        return journal.call(row['target_key'], 'pyscf_scf', solve, summary=lambda x: x)
    except Exception as exc:
        return {'stage_status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)}


def counts(results, calls):
    def total(field):
        values = [r.get(field) for r in results]
        return sum(values) if all(x is not None for x in values) else None
    return {'execute_calls_started': calls, 'requested_physical_systems': len(results),
            'systems_with_valid_result': sum(r['stage_status'] == 'valid' for r in results),
            'iterations': total('iterations'), 'fock_builds': total('fock_builds')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    start = time.perf_counter()
    args.out.mkdir(exist_ok=False, parents=True)
    study = read(args.study)
    ref = study['comparison']
    config_path = Path(study['calculator_config_path'])
    config = read(config_path)
    if file_sha(config_path) != study['calculator_config_sha256'] or not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('expected predeclared Slurm configuration')
    n = len(study['input_manifest'])
    journal = Journal(args.out, {'gqc_execute': 2*n+1, 'pyscf_scf': n})
    t = time.perf_counter()
    rows = load_inputs(args.inputs, study['input_manifest'])
    times = {'input_read_decode_seconds': time.perf_counter() - t}
    t = time.perf_counter()
    native = journal.call('loaded_cdll', 'native_library_load', lambda: _native.load_library(device='cuda'))
    sha = file_sha(native._name)
    if sha != config['native_library_sha256'] or not Path(native._name).samefile(os.environ['GQC_NATIVE_LIBRARY']):
        raise ValueError('wrong loaded CDLL')
    basis_file = Path(generativeqc.__file__).parent / 'data/basis_pack.json'
    basis_sha = file_sha(basis_file)
    if basis_sha != '1bbb5611e5580d033e56eea7e24cf17ef85e58d0d6d67aa25e3732690822d6fe':
        raise ValueError('basis pack differs from pinned GQC source')
    options = config['calculator']
    elements = read(basis_file)['bases'][options['basis']]['elements']
    calc = Calculator(**options)
    protocol = {'column': 'gqc_rhf_sto3g_direct_fp64_total_energy_hartree', 'property': 'total_electronic_plus_nuclear_energy',
                'environment': 'isolated gas phase, all-electron nonrelativistic Coulomb',
                'state_branch': 'closed-shell RHF cold start with default SCF branch selection',
                'energy_unit': 'hartree', 'coordinate_unit': 'bohr', 'options': options,
                'controls': _controls(calc), 'warm_start': False, 'gqc_source_declaration': os.environ['GQC_SOURCE_SHA'],
                'native_library_sha256': sha, 'native_source_identity': native.generativeqc_get_source_identity().decode(),
                'basis_pack_sha256': basis_sha}
    identities = assign_keys(rows, calc, protocol)
    times['identity_and_runtime_attestation_seconds'] = time.perf_counter() - t
    t = time.perf_counter()
    singles = []
    call_count = journal.counts['gqc_execute']
    for row in rows:
        singles.extend(calculate_batch('row/' + row['id'], [row], options, journal))
    stages = {'per_row_cold': counts(singles, journal.counts['gqc_execute'] - call_count)}
    times['per_row_cold_seconds'] = time.perf_counter() - t
    t = time.perf_counter()
    cache = {}
    call_count = journal.counts['gqc_execute']
    for row in rows:
        key = row['target_key']
        if key not in cache:
            cache[key] = calculate_batch('dictionary/' + key, [row], options, journal)[0]
    stages['dictionary'] = counts(list(cache.values()), journal.counts['gqc_execute'] - call_count)
    times['dictionary_seconds'] = time.perf_counter() - t
    t = time.perf_counter()
    representatives = {}
    for row in rows:
        representatives.setdefault(row['target_key'], row)
    call_count = journal.counts['gqc_execute']
    slots = calculate_batch('unique_batch', list(representatives.values()), options, journal)
    batched = dict(zip(representatives, slots, strict=True))
    stages['unique_batch'] = counts(slots, journal.counts['gqc_execute'] - call_count)
    times['unique_batch_seconds'] = time.perf_counter() - t
    t = time.perf_counter()
    references = {k: pyscf_reference(row, elements, ref, journal) for k, row in representatives.items()}
    times['pyscf_reference_seconds'] = time.perf_counter() - t
    labels = []
    for row, single in zip(rows, singles, strict=True):
        key = row['target_key']
        gqc = [single, cache[key], batched[key]]
        reference = references[key]
        failed = [k for k,v in zip(('per_row_cold','dictionary','unique_batch','pyscf'), [*gqc,reference], strict=True)
                  if v['stage_status'] != 'valid']
        checks = {}
        if not failed:
            basis_id = identities[key]['basis_metadata']['orbital']['basis_identity']
            if any(x['basis_identity'] != basis_id for x in gqc):
                failed.append('basis_identity')
            es = [x['energy_hartree'] for x in gqc]
            checks['max_pairwise_gqc_difference_eh'] = max(abs(a-b) for a,b in itertools.combinations(es,2))
            checks['max_independent_difference_eh'] = max(abs(a-reference['energy_hartree']) for a in es)
            if checks['max_pairwise_gqc_difference_eh'] > ref['same_protocol_hartree']:
                failed.append('same_protocol_energy')
            if checks['max_independent_difference_eh'] > ref['independent_reference_hartree']:
                failed.append('independent_reference_energy')
        labels.append({**{k:v for k,v in row.items() if k!='atoms'}, 'representative_row': representatives[key]['id'],
                       'energy_hartree': None if failed else batched[key]['energy_hartree'],
                       'status':'failed' if failed else 'verified','failed_checks':failed, **checks,
                       'per_row_cold':single})
    save(args.out/'labels.json', {'protocol':protocol, 'source_commit':study['source_commit'],
                                 'scientific_identities':identities, 'rows':labels})
    times['total_seconds_through_label_write'] = time.perf_counter() - start
    result = {'source_manifest_sha256':file_sha(args.study), 'driver_sha256': file_sha(__file__),
              'project_commit':os.environ['VIBEDATASET_CODE_SHA'], 'job':os.environ['SLURM_JOB_ID'],
              'python':platform.python_version(), 'packages':{p:importlib.metadata.version(p)
              for p in ('generativeqc','pyscf','numpy','scipy','scipy-openblas32')},
              'n_rows':n,'n_unique':len(identities), 'label_status':dict(Counter(r['status'] for r in labels)),
              'source_failures':sum(not r['source_success'] for r in labels),'stages':stages,
              'dictionary':cache,'unique_batch':batched,'references':references, 'comparison':ref,
              'attempts':dict(journal.counts),'times':times,
              'labels_sha256':file_sha(args.out/'labels.json'),'source_compressed_bytes':sum(r['bytes'] for r in study['input_manifest']),
              'scope':'Fixed ordered inputs. Wall clocks are single-run measurements; solver work is counted per physical item.'}
    save(args.out/'result.json', result)
    print(json.dumps({k:result[k] for k in ('job','n_rows','n_unique','label_status','stages','times')},indent=2))
    return int(any(row['status'] != 'verified' for row in labels))


if __name__ == '__main__':
    raise SystemExit(main())
