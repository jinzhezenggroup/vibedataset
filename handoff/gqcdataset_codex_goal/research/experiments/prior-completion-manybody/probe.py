"""MB-001. Compare QCManyBody assembly and persistent reuse with a direct reference."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from math import fsum
import os
from pathlib import Path
import platform
import subprocess
from time import perf_counter

import numpy as np
from pyscf import gto, lib, scf
from qcelemental.models.v2 import Molecule
import qcmanybody

QCMB_PIN = '90273ab21e4f824b286d55411666394c80cf2472'
TOL = 1e-10
SYMBOLS = ['He', 'H', 'H', 'O', 'H', 'H']
COORDS = [[0., 0., 0.], [5.20, 0., 0.], [5.20, 0., 1.4],
          [0., 5.8, 0.], [0., 7.23, 1.09], [0., 4.38, 1.08]]
FRAGMENTS = [[0], [1, 2], [3, 4, 5]]


def encoded(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read_identity():
    root = Path('_references/qcmanybody').resolve()
    if Path(qcmanybody.__file__).resolve().parent != root / 'qcmanybody':
        raise ValueError('use PYTHONPATH pointing to the pinned QCManyBody tree')
    if subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip() != QCMB_PIN:
        raise ValueError('QCManyBody pin differs')
    if subprocess.check_output(['git', '-C', root, 'status', '--porcelain']):
        raise ValueError('QCManyBody checkout is dirty')
    if metadata.version('pyscf') != '2.14.0':
        raise ValueError('use the predeclared PySCF release')
    return {
        'python': platform.python_version(), 'system': platform.platform(),
        'qcmanybody_pin': QCMB_PIN, 'qcmanybody': metadata.version('qcmanybody'),
        'qcelemental': metadata.version('qcelemental'), 'pyscf': metadata.version('pyscf'),
        'numpy': np.__version__, 'scipy': metadata.version('scipy'), 'method': 'RHF',
        'driver': 'ground state total energy', 'unit': 'hartree', 'coordinate_unit': 'bohr',
        'basis': {s: gto.basis.load('sto-3g', s) for s in sorted(set(SYMBOLS))},
        'spherical': True, 'density_fitting': False, 'conv_tol': 1.e-13, 'conv_tol_grad': 1.e-9,
        'max_cycle': 120, 'init_guess': 'minao', 'threads': lib.num_threads(),
        'libcgto_sha256': sha(Path(gto.moleintor.libcgto._name).read_bytes()),
        'libcvhf_sha256': sha(Path(scf._vhf.libcvhf._name).read_bytes()),
    }


def parent(geometry):
    return Molecule(symbols=SYMBOLS, geometry=geometry, fragments=FRAGMENTS,
                    fragment_charges=[0, 0, 0], fragment_multiplicities=[1, 1, 1],
                    molecular_charge=0, molecular_multiplicity=1, fix_com=True, fix_orientation=True)


def make_core(mol, treatments, final_only):
    return qcmanybody.ManyBodyCore(mol, treatments, {n: 'RHF/STO-3G' for n in (1, 2, 3)},
                                   return_total_data=False, supersystem_ie_only=final_only,
                                   embedding_charges=None)


def description(symbols, geometry, real, charge, multiplicity):
    entries = [{'element': str(symbol), 'xyz': [float(x) for x in xyz], 'real': bool(active)}
               for symbol, xyz, active in zip(symbols, geometry, real, strict=True)]
    return {'atoms': entries, 'charge': float(charge), 'multiplicity': int(multiplicity)}


def component(mol):
    return description(mol.symbols, mol.geometry, mol.real, mol.molecular_charge, mol.molecular_multiplicity)


class Runner:
    def __init__(self, out, identity):
        self.out = out
        self.identity_hash = sha(encoded(identity))
        self.identity = identity
        self.counts = Counter()
        self.events = out / 'scf.jsonl'
        self.store = out / 'components'
        self.store.mkdir()

    def key(self, record):
        return sha(encoded([self.identity_hash, record]))

    def emit(self, event):
        with self.events.open('a') as f:
            f.write(json.dumps(event, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())

    def solve(self, stage, label, record):
        start = perf_counter()
        key = self.key(record)
        self.counts[stage] += 1
        event = {'stage': stage, 'label': label, 'call': self.counts[stage], 'key': key}
        self.emit(dict(event, status='started', at=datetime.now(timezone.utc).isoformat()))
        try:
            atoms = [(a['element'] if a['real'] else 'ghost-' + a['element'], a['xyz']) for a in record['atoms']]
            mol = gto.M(atom=atoms, unit='Bohr', charge=int(record['charge']), spin=record['multiplicity'] - 1,
                        basis=self.identity['basis'], cart=False, verbose=0)
            mf = scf.RHF(mol)
            mf.chkfile = None
            mf.conv_tol = self.identity['conv_tol']
            mf.conv_tol_grad = self.identity['conv_tol_grad']
            mf.max_cycle = self.identity['max_cycle']
            mf.init_guess = self.identity['init_guess']
            energy = float(mf.kernel())
            if not mf.converged or not np.isfinite(energy):
                raise ArithmeticError(f'failed target SCF at {label}')
            self.emit(dict(event, status='converged', elapsed_seconds=perf_counter() - start,
                           energy=energy, nbf=mol.nao_nr(), electrons=mol.nelectron, cycles=mf.cycles))
            return energy
        except Exception as error:
            self.emit(dict(event, status='failed', elapsed_seconds=perf_counter() - start, error=str(error)))
            raise

    def evaluate(self, mol, treatments, final_only, stage, archive=False):
        start = perf_counter()
        core = make_core(mol, treatments, final_only)
        jobs = sorted(core.iterate_molecules(), key=lambda item: item[1])
        values, hits, lookup_seconds, write_seconds = {}, 0, 0., 0.
        for _, label, job in jobs:
            record = component(job)
            t = perf_counter()
            path = self.store / (self.key(record) + '.json')
            if archive and path.exists():
                entry = json.loads(path.read_text())
                if entry['protocol'] != self.identity_hash or entry['input'] != record:
                    raise ValueError('foreign stored record')
                energy = entry['energy']
                hits += 1
                lookup_seconds += perf_counter() - t
            else:
                lookup_seconds += perf_counter() - t
                energy = self.solve(stage, label, record)
                if archive:
                    t = perf_counter()
                    with path.open('xb') as f:
                        f.write(encoded({'protocol': self.identity_hash, 'input': record, 'energy': energy}))
                    write_seconds += perf_counter() - t
            values[label] = {'energy': energy}
        t = perf_counter()
        results = core.analyze(values)['results']
        top = {name: results[f'{name}_corrected_interaction_energy'] for name in treatments}
        stats = {'stage': stage, 'requested': treatments, 'supersystem_ie_only': final_only, 'entries': len(values),
                 'new_solves': self.counts[stage], 'archive_hits': hits, 'energies': top,
                 'assembly_seconds': perf_counter() - t, 'lookup_seconds': lookup_seconds, 'write_seconds': write_seconds,
                 'elapsed_seconds': perf_counter() - start, 'stored_bytes_after': sum(p.stat().st_size for p in self.store.iterdir())}
        return stats, values


def direct_reference(runner):
    """Independent atom/ghost layout, bypassing all QCManyBody fragment generation and assembly."""
    whole = runner.solve('direct_formula', 'super', description(SYMBOLS, COORDS, [True] * len(SYMBOLS), 0, 1))
    energy = {}
    for name in ('cp', 'nocp'):
        monomers = []
        for i, frag in enumerate(FRAGMENTS):
            indices = list(range(len(SYMBOLS))) if name == 'cp' else frag
            record = description([SYMBOLS[j] for j in indices], [COORDS[j] for j in indices],
                                 [j in frag for j in indices], 0, 1)
            monomers.append(runner.solve('direct_formula', f'{name} monomer {i+1}', record))
        energy[name] = whole - fsum(monomers)
    return energy


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('out', type=Path, help='new output directory')
    out = ap.parse_args().out
    out.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    lib.num_threads(1)
    identity = read_identity()
    runner = Runner(out, identity)
    ref = direct_reference(runner)
    mol = parent(COORDS)
    stages = []
    for name, treatments, final_only, use_archive in [
            ('all_orders_cold', ['cp', 'nocp'], False, False), ('joint_cold', ['cp', 'nocp'], True, False),
            ('round1', ['nocp'], True, True), ('round2', ['cp'], True, True),
            ('round3', ['cp', 'nocp'], True, True)]:
        stage, values = runner.evaluate(mol, treatments, final_only, name, use_archive)
        stage['max_reference_error'] = max(abs(value - ref[k]) for k, value in stage['energies'].items())
        if stage['max_reference_error'] > TOL:
            raise AssertionError(f'{name} exceeded {TOL:g} hartree')
        stages.append(stage)

    # Try using bare energies as CP monomer energies. Correct scalar shape and
    # correct cluster labels alone do not check the origin of externally supplied values.
    core = make_core(mol, ['cp'], True)
    cp_values = {label: values[label] for _, label, _ in core.iterate_molecules()}
    bad = cp_values.copy()
    monomer_labels = []
    for label in cp_values:
        mc, fragments, basis = qcmanybody.delabeler(label)
        if len(fragments) == 1:
            monomer_labels.append(label)
            bad[label] = values[qcmanybody.labeler(mc, fragments, fragments)]
    wrong = core.analyze(bad)['results']['cp_corrected_interaction_energy']
    missing = cp_values.copy()
    omitted = min(monomer_labels)
    del missing[omitted]
    try:
        core.analyze(missing)
    except KeyError as error:
        missing_reason = str(error)
    else:
        raise AssertionError('missing necessary component escaped detection')

    changed_xyz = np.array(COORDS)
    changed_xyz[-1, 1] += 0.2
    changed_core = make_core(parent(changed_xyz), ['cp'], True)
    before = {label: runner.key(component(job)) for _, label, job in core.iterate_molecules()}
    after = {label: runner.key(component(job)) for _, label, job in changed_core.iterate_molecules()}
    if before.keys() != after.keys() or any(after[k] == before[k] for k in before):
        raise AssertionError('geometry/ghost coordinates failed the scope check')
    counts = [stage['new_solves'] for stage in stages]
    if counts != [13, 7, 4, 3, 0]:
        raise AssertionError(f'unexpected solve counts {counts}')
    if abs(wrong - ref['cp']) <= TOL:
        raise AssertionError('ghost substitution was not distinguishable in this experiment')

    result = dict(identity=identity, geometry=COORDS, fragments=FRAGMENTS,
                  input_symbols=SYMBOLS, fixed_target_tolerance_hartree=TOL,
                  direct_target_reference=ref, direct_reference_solves=runner.counts['direct_formula'],
                  stages=stages, total_scf_calls=sum(runner.counts.values()), expected_rejections={
                      'omitted_required_cp_component': omitted, 'missing_exception': missing_reason,
                      'mislabeled_bare_as_cp_value': wrong, 'absolute_error_hartree': abs(wrong - ref['cp']),
                      'same_cp_local_labels_after_displacement': len(before), 'matching_physical_keys': 0},
                  archive_file_count=len(list(runner.store.iterdir())),
                  journal_sha256=sha(runner.events.read_bytes()), driver_sha256=sha(Path(__file__).read_bytes()),
                  elapsed_seconds_after_imports=perf_counter() - started)
    (out / 'result.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
