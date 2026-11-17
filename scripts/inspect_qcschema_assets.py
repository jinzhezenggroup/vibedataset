#!/usr/bin/env python3
"""Inventory all single-point inputs/results in the QCFractal QCSchema v1 fixtures."""
import argparse
import hashlib
import json
import lzma
import math
from pathlib import Path
import subprocess

PIN = '4ec1ed623f82536076c069dd65a4eb132969d9ed'
DIRECTORY = Path('qcarchivetesting/qcarchivetesting/qcschema_v1_data')


def digest_json(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def summarize(repo, path):
    raw = path.read_bytes()
    data = json.loads(lzma.decompress(raw))
    task, result = data['input'], data['result']
    molecule = task['molecule']
    geometry = {k: molecule[k] for k in ('symbols', 'geometry', 'molecular_charge', 'molecular_multiplicity')}
    wavefunction = result.get('wavefunction') or {}
    basis = wavefunction.get('basis')
    props = result.get('properties', {})
    geometry_in_result = result.get('molecule')
    error = result.get('error') or {}
    message = error.get('error_message', '')
    reason = None
    if error:
        if 'Unable to find a basis set' in message:
            reason = 'basis_not_found'
        elif 'Could not converge SCF iterations' in message:
            reason = 'scf_nonconvergence'
        else:
            reason = 'unclassified_failure'
    # Array names alone do not establish their conventions or that a target SCF converged.
    arrays = {key: {'stored_length': len(value), 'sha256_json': digest_json(value),
                    'all_finite': all(math.isfinite(x) for x in value)}
              for key, value in wavefunction.items() if isinstance(value, list)}
    producer = result.get('provenance', {})
    return {
        'path': str(path.relative_to(repo)), 'compressed_bytes': len(raw),
        'compressed_sha256': hashlib.sha256(raw).hexdigest(),
        'molecule': molecule.get('name'), 'input_geometry': geometry,
        'input_geometry_sha256': digest_json(geometry),
        'output_geometry_matches_input': (
            all(geometry_in_result[k] == v for k, v in geometry.items()) if geometry_in_result else None),
        'driver': task['driver'], 'model': task['model'], 'keywords': task['keywords'],
        'requested_protocols': task['protocols'], 'success': result['success'],
        'error_type': error.get('error_type'), 'failure_evidence': reason,
        'program': {k: producer.get(k) for k in ('creator', 'version', 'qcengine_version')},
        'populated_properties': sorted(k for k, v in props.items() if v is not None),
        'counts': {k: v for k, v in props.items() if k.startswith('calcinfo_')},
        'basis_sha256_json': digest_json(basis) if basis else None,
        'has_explicit_centers': bool(basis and basis.get('center_data') and basis.get('atom_map')),
        'restricted': wavefunction.get('restricted'),
        'wavefunction_aliases': {k: v for k, v in wavefunction.items() if isinstance(v, str)},
        'wavefunction_arrays': arrays,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('_references/qcfractal'))
    repo = parser.parse_args().repo
    commit = subprocess.check_output(['git', '-C', repo, 'rev-parse', 'HEAD'], text=True).strip()
    if commit != PIN or subprocess.check_output(['git', '-C', repo, 'status', '--porcelain']):
        raise ValueError('expected clean pinned QCFractal checkout')
    directory = repo / DIRECTORY
    records = [summarize(repo, path) for path in sorted(directory.glob('*.json.xz'))
               if path.name.startswith(('sp_', 'error_'))]
    print(json.dumps({'source_commit': commit, 'selection': 'All sp_* and error_* single-point fixtures in ' + str(DIRECTORY),
                      'record_count': len(records), 'records': records}, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
