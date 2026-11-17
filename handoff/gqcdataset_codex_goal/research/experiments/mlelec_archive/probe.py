"""Exercise the authors' released reference program and discriminate its response definition."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import platform
import subprocess
from time import perf_counter
from unittest.mock import patch

import ase
from ase.io import read
import h5py
import numpy as np
import pyscf
from pyscf import dft, lib
from pyscf.scf import cphf
from pyscf.scf import _response_functions  # registers gen_response on RKS
from scipy import linalg
import scipy

PIN = '9c34bd9e1351770d3ac5b0887ecf0a98da317417'
AUTHOR_SHA = '279e3be8d4cb240f0c75ce3cd39ac622a01614dfd8b068bbec7f98d956e69649'
STEPS = [0.0005, 0.0002]
TOL = {'author_vs_sum_over_states': 1e-5, 'relaxed_step_agreement': 2e-3,
       'cpks_vs_relaxed_fd': 2e-3, 'distinct_response': 1e-2}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def peak(a):
    return float(np.max(np.abs(a)))


def encode_scalar(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f'Unsupported JSON field {type(value).__name__}')


class Journal:
    def __init__(self, path):
        self.path = path
        self.sequence = 0

    def write(self, d):
        with self.path.open('a') as f:
            f.write(json.dumps(d, allow_nan=False) + '\n')
            f.flush()
            os.fsync(f.fileno())

    @contextmanager
    def operation(self, label):
        self.sequence += 1
        fields = {'sequence': self.sequence, 'label':label}
        self.write(dict(fields, status='started',utc=datetime.now(timezone.utc).isoformat()))
        start = perf_counter()
        try:
            yield fields
        except Exception as error:
            self.write(dict(fields,status='failed',elapsed_seconds=perf_counter()-start,error=str(error)))
            raise
        self.write(dict(fields,status='completed',elapsed_seconds=perf_counter()-start))


def run_case(name, xyz_file, outdir, author, journal):
    structure = read(xyz_file, index=0)
    numbers,positions = structure.numbers,structure.positions
    saved = {}
    original_output = author.get_output
    def capture(mf):
        saved['mf'] = mf
        calls = []
        original_eig = mf.eig
        original_veff = mf.get_veff
        def count_eig(*args, **kwargs):
            calls.append('eig')
            return original_eig(*args, **kwargs)
        def count_veff(*args, **kwargs):
            calls.append('veff')
            return original_veff(*args, **kwargs)
        with patch.object(mf, 'eig', count_eig), patch.object(mf, 'get_veff', count_veff):
            data = original_output(mf)
        saved.update(source_calls=calls, values=data)
        return data

    # The unmodified entry writes a PySCF log and small first-party NPZ relative to cwd.
    root = Path.cwd()
    directory = outdir / name
    (directory/'sto-3g').mkdir(parents=True)
    try:
        os.chdir(directory)
        with journal.operation(name+'/author_single_point') as event, patch.object(author,'get_output',capture):
            author.single_point(positions, numbers, 0)
            event['source_converged'] = bool(saved['values']['converged'])
            event['source_eigen_and_veff_order'] = saved['source_calls']
    finally:
        os.chdir(root)
    ref = saved['values']
    mf = saved['mf']
    mol = mf.mol
    if not ref['converged'] or not np.isfinite(ref['energy_tot']):
        raise ArithmeticError('source RKS did not converge')
    # The reference routine leaves mf.mo_* at its last +z field; derive the
    # zero-field frame explicitly from the recorded zero-field Fock and S.
    fock,overlap = ref['fock'],ref['ovlp']
    eps,coeff = linalg.eigh(fock,overlap)
    occ = mf.get_occ(eps,coeff)
    co,cv = coeff[:,occ>0],coeff[:,occ==0]
    ao_r = mol.intor('int1e_r',comp=3)
    dip_vo = np.einsum('pa,xpq,qi->xai',cv,ao_r,co)
    gaps = eps[occ==0,None] - eps[occ>0]
    if np.any(occ[occ>0] != 2) or np.min(gaps) <= 0:
        raise ArithmeticError('restricted ground-state sum-over-states scope')
    independent = 4*np.einsum('xai,yai,ai->xy',dip_vo,dip_vo,1/gaps)
    first_eig = saved['source_calls'].index('eig')
    if saved['source_calls'][first_eig:].count('veff') != 0 or saved['source_calls'].count('eig')!=4:
        raise AssertionError('changed reference property path')

    # Compute actual induced J/K/XC response on precisely the stored basis/grid.
    # For an occupied-virtual amplitude X, dD = 2(Cv X Co.T + transpose).
    vresp = mf.gen_response(mo_coeff=coeff,mo_occ=occ,singlet=None,hermi=1)
    induced_calls=0
    def induced(x):
        nonlocal induced_calls
        induced_calls += 1
        xx = np.asarray(x).reshape(-1,cv.shape[1],co.shape[1])
        trans = np.einsum('pa,xai,qi->xpq',cv,xx,co)
        d_dens = 2*(trans+trans.transpose(0,2,1))
        potential = np.asarray(vresp(d_dens)).reshape(d_dens.shape)
        return np.einsum('pa,xpq,qi->xai',cv,potential,co)

    with journal.operation(name+'/coupled_RKS_linear_response') as event:
        dx = cphf.solve(induced,eps,occ,dip_vo,max_cycle=80,tol=1e-11)[0]
        actions = induced_calls
        residual = peak(gaps*dx + induced(dx) + dip_vo)
        coupled = -4*np.einsum('xai,yai->xy',dip_vo,dx)
        event.update(solver_induced_actions=actions, extra_residual_actions=1, true_max_residual=residual,
                     rhs=len(dx))
    if not np.isfinite(coupled).all():
        raise ArithmeticError('nonfinite analytic CPKS result')

    h0 = mf.get_hcore()
    fd={}
    for h in STEPS:
        tensor=np.zeros((3,3))
        for axis in range(3):
            dipoles=[]
            for sign in [-1,1]:
                with journal.operation(f'{name}/selfconsistent_{h}_{axis}_{sign}') as event:
                    field_mf = dft.RKS(mol)
                    field_mf.xc = mf.xc
                    field_mf.conv_tol = mf.conv_tol
                    field_mf.grids = mf.grids
                    field_mf.chkfile = None
                    field_mf.verbose = 0
                    field_mf.get_hcore = lambda *args: h0 + sign*h*ao_r[axis]
                    cycles=[]
                    field_mf.callback=lambda env: cycles.append(env['cycle'])
                    energy=field_mf.kernel()
                    if not field_mf.converged or not np.isfinite(energy):
                        raise ArithmeticError('field SCF did not converge')
                    mu=field_mf.dip_moment(unit='AU',verbose=0)
                    dipoles.append(mu)
                    event.update(energy_hartree_with_electronic_field=float(energy),dipole_au=mu.tolist(),scf_cycles=len(cycles))
            tensor[:,axis]=(dipoles[1]-dipoles[0])/(2*h)
        fd[str(h)]=tensor
    a=ref['polarisability']
    checks=dict(author_vs_sum_over_states=peak(a-independent),relaxed_step_agreement=peak(fd[str(STEPS[0])]-fd[str(STEPS[1])]),
                cpks_vs_relaxed_fd=max(peak(t-coupled) for t in fd.values()),
                distinct_response=min(peak(t-a) for t in fd.values()))
    passed=all(np.isfinite(q) and (q>TOL[k] if k=='distinct_response' else q<=TOL[k]) for k,q in checks.items())
    return dict(case=name,index=0,xyz_file_sha256=sha(xyz_file),symbols=structure.get_chemical_symbols(),
                geometry_angstrom_author_text=author.get_geom(positions,numbers),actual_coords_bohr=mol.atom_coords().tolist(),
                ao_dimension=mol.nao_nr(),ao_labels=mol.ao_labels(),charge=mol.charge,multiplicity=mol.spin+1,
                electron_count=mol.nelectron,mo_occ=occ.tolist(),gap_hartree=float(np.min(gaps)),
                resolved_basis_sha256=hashlib.sha256(json.dumps(mol._basis,sort_keys=True).encode()).hexdigest(),
                source_grid_points=len(mf.grids.coords),source_xc=mf.xc,source_threshold=mf.conv_tol,
                source_energy_hartree=float(ref['energy_tot']),source_dipole_au=ref['dip_moment'].tolist(),
                final_mf_density_change_from_archived_density=peak(mf.make_rdm1()-ref['dm']),
                source_eig_calls=saved['source_calls'].count('eig'),source_veff_calls_after_first_eig=saved['source_calls'][first_eig:].count('veff'),
                author_one_sided_1e_minus_8=a.tolist(),fock_frozen_analytic=independent.tolist(),
                coupled_cpks=coupled.tolist(),cpks_true_max_residual=residual,selfconsistent_centered_fd={k:v.tolist() for k,v in fd.items()},
                checks=checks,passed=passed)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verified',type=Path,required=True,help='directory made by inspect_release.py')
    ap.add_argument('--output',type=Path,required=True,help='fresh output directory')
    args=ap.parse_args()
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    members=args.verified.resolve()/'members'
    root=Path('_references/mlelec_qm7')
    if subprocess.check_output(['git','-C',root,'rev-parse','HEAD'],text=True).strip()!=PIN:
        raise ValueError('wrong geometry source pin')
    if subprocess.check_output(['git','-C',root,'status','--porcelain']):
        raise ValueError('geometry source dirty')
    src=members/'dataset/scripts/pyscf_ref_calc.py'
    if sha(src)!=AUTHOR_SHA or pyscf.__version__!='2.3.0' or ase.__version__!='3.22.1':
        raise ValueError('wrong generator or runtime')
    spec=spec_from_file_location('release_ref_calc',src)
    author=module_from_spec(spec)
    spec.loader.exec_module(author)
    lib.num_threads(1)
    journal=Journal(out/'operations.jsonl')
    geometry_files={'water':root/'examples/data/water_1000/water_1000.xyz',
                    'qm7':members/'dataset/data/qm7/qm7.xyz'}
    started=perf_counter()
    cases=[]
    for name, path in geometry_files.items():
        case=run_case(name,path,out,author,journal)
        (out/name/'case.json').write_text(json.dumps(case,indent=2,default=encode_scalar,allow_nan=False)+'\n')
        cases.append(case)
    hdf_status=[]
    for path in sorted((members/'dataset/data/qm7/reference/sto-3g').glob('*.hickle')):
        with h5py.File(path,'r') as hdf:
            if not isinstance(hdf.get('data',getlink=True),h5py.HardLink):
                raise ValueError('unexpected link')
            dataset=hdf['data']
            if isinstance(dataset,h5py.Group):
                if not isinstance(dataset.get('data0',getlink=True),h5py.HardLink): raise ValueError('unexpected link')
                dataset=dataset['data0']
            hdf_status.append(dict(file=path.name,path=dataset.name,dtype=dataset.dtype.str,shape=dataset.shape,
                                    first_two_raw_bytes_hex=bytes(dataset[:2]).hex() if dataset.dtype==np.uint8 else None))
    version_info={'python':platform.python_version(),'platform':platform.platform(),'pyscf':pyscf.__version__,
                  'libxc':dft.libxc.libxc_version(),'b3lypg_libxc_ids_and_coefficients':dft.libxc.parse_xc('b3lypg'),
                  'b3lypg_hybrid_coeff':dft.libxc.hybrid_coeff('b3lypg'),'ase':ase.__version__,'scipy':scipy.__version__,
                  'numpy':np.__version__,'h5py':h5py.__version__,'threads':lib.num_threads(),
                  'loaded_libcgto_sha256':sha(Path(gto_lib_path()))}
    result=dict(release_doi='10.24435/materialscloud:mg-8f',qm7_branch_commit=PIN,author_driver_sha256=AUTHOR_SHA,
                probe_sha256=sha(Path(__file__).resolve()),environment=version_info,thresholds=TOL,cases=cases,
                hdf_metadata_only=hdf_status,archive_labels_deserialized=False,source_rks_scf_calls=len(cases),
                perturbed_rks_scf_calls=len(cases)*len(STEPS)*3*2,physical_cpks_multi_rhs_calls=len(cases),
                training_steps=0,elapsed_seconds_after_setup=perf_counter()-started,
                journal_sha256=sha(out/'operations.jsonl'))
    (out/'result.json').write_text(json.dumps(result,indent=2,default=encode_scalar,allow_nan=False)+'\n')
    return int(not all(c['passed'] for c in cases))


def gto_lib_path():
    from pyscf.gto import moleintor
    return moleintor.libcgto._name


if __name__=='__main__':
    raise SystemExit(main())
