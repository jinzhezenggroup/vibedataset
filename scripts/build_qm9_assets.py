#!/usr/bin/env python3
"""Generate n5 all-electron RHF reference assets for the prespecified QM9 cohort."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np
import pyscf
from pyscf import scf
from pyscf.scf import stability
import generativeqc
from generativeqc import Atom, Calculator, _native
from generativeqc.profiles import canonical_hash

from probe_gqc_checkpoint import Journal

GQC_HELPER_COMMIT = '2791504cc238fe83d328fc1718080642b288222a'
PACK_HASH = '1bbb5611e5580d033e56eea7e24cf17ef85e58d0d6d67aa25e3732690822d6fe'


def file_hash(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def peak(x):
    return float(np.max(np.abs(x)))


def gqc_batch(rows, options, journal):
    def prepare():
        systems = [list(zip(r['symbols'], r['coordinates_bohr'], strict=True)) for r in rows]
        return Calculator(**options).prepare_batch(systems, charges=[0]*len(systems),
                                                  multiplicities=[1]*len(systems), warm_start=False)
    try:
        with journal.call('all_selected', 'gqc_prepare', prepare) as plan:
            batch = journal.call('all_selected', 'gqc_execute',
                                 lambda:plan.execute(strict=False, properties=('energy',)))
            recorded = {}
            for i, (row, item) in enumerate(zip(rows, batch.items, strict=True)):
                if i != item.index:
                    raise ValueError('unexpected GQC output slot')
                okay = (item.succeeded and item.converged and item.executed_backend == 'cuda'
                        and np.isfinite(item.energy) and item.restart_origin == 'cold' and not item.warm_start_used)
                recorded[row['name']] = {'valid':bool(okay), 'energy_hartree':float(item.energy) if np.isfinite(item.energy) else None,
                                         'status':int(item.status), 'message':item.status_message,'iterations':int(item.iterations),
                                         'fock_builds':item.fock_builds, 'backend':item.executed_backend,
                                         'basis_metadata':item.basis_metadata,'restart_origin':item.restart_origin}
            return recorded
    except Exception as error:
        return {r['name']:{'valid':False,'error_type':type(error).__name__,'error':str(error)} for r in rows}


def make_reference(row, gqc, elements, path, journal, helpers, diagnostics):
    pyscf_molecule, fixture_snapshot = helpers
    atoms = [Atom.from_value(p) for p in zip(row['symbols'],row['coordinates_bohr'],strict=True)]
    shells = []
    for i, atom in enumerate(atoms):
        for shell in elements[str(atom.atomic_number)]:
            shells.append({'atom_index':i,'angular_momentum':shell['angular_momentum'],
                           'primitives':[[float(a),float(c)] for a,c in zip(shell['exponents'], shell['coefficients'], strict=True)]})
    settings = {'energy_tolerance':1e-13, 'gradient_tolerance':1e-11, 'direct_scf_tol':1e-14,'max_iterations':100}
    inputs = {'name':row['name'],'method':'rhf','atomic_numbers':[a.atomic_number for a in atoms],
              'coordinates':row['coordinates_bohr'],'charge':0,'multiplicity':1,'basis_representation':'real_spherical',
              'shells':shells,'scf_settings':settings,'cc_settings':None}
    name = row['name']
    mol, scale, _ = journal.call(name,'reference_molecule',lambda:pyscf_molecule(inputs))
    if mol.nelectron <= 0 or mol.nelectron % 2:
        raise ValueError('neutral closed-shell incompatible electron count')
    ref = scf.RHF(mol)
    ref.chkfile = None
    ref.conv_tol = settings['energy_tolerance']
    ref.conv_tol_grad = settings['gradient_tolerance']
    ref.direct_scf_tol = settings['direct_scf_tol']
    ref.max_cycle = settings['max_iterations']
    ref.init_guess = 'minao'
    energy = float(journal.call(name,'reference_scf',ref.kernel,summary=float))
    diagnostics.update(scf_cycles=int(ref.cycles), pyscf_energy_hartree=energy, n_ao=mol.nao_nr(),
                       scf_converged=bool(ref.converged), electron_count=mol.nelectron)
    if not ref.converged or not np.isfinite(energy):
        raise ValueError('PySCF reference SCF failed')
    def check_stability():
        _, _, internal, external = stability.rhf_stability(ref,internal=True,external=True,return_status=True,
                                                           nroots=3,tol=1e-7,verbose=0)
        return {'internal':bool(internal),'external':bool(external)}
    stability_flags = journal.call(name,'orbital_stability',check_stability,summary=dict)
    diagnostics['pyscf_local_stability'] = stability_flags
    def integrals_and_state():
        s = mol.intor_symmetric('int1e_ovlp')
        raw_dm = ref.make_rdm1()
        f = ref.get_fock(dm=raw_dm)
        c = np.asarray(ref.mo_coeff) / scale[:,None]
        c[:,c[np.argmax(np.abs(c),axis=0),np.arange(c.shape[1])] < 0] *= -1
        two = scale[:,None]*scale[None,:]
        return {'conventional_S':s*two, 'conventional_h':ref.get_hcore()*two, 'conventional_F':f*two,
                'conventional_C':c, 'conventional_eps':ref.mo_energy.copy(),'conventional_occ':ref.mo_occ.copy(),
                'ao':np.einsum('pqrs,p,q,r,s->pqrs',mol.intor('int2e',aosym='s1'),scale,scale,scale,scale,optimize=True)}
    arrays = journal.call(name,'integrals_and_state',integrals_and_state)
    c,h,s,f = (arrays['conventional_'+k] for k in ('C','h','S','F'))
    eps, occ = (arrays['conventional_'+k] for k in ('eps','occ'))
    density = (c * occ) @ c.T
    eri = arrays['ao']
    physical = h + np.einsum('pqrs,rs->pq',eri,density) - 0.5*np.einsum('prsq,rs->pq',eri,density)
    nocc = mol.nelectron//2
    diagnostics.update(ortho=peak(c.T@s@c-np.eye(len(c))), trace_error=abs(float(np.trace(density@s)-mol.nelectron)),
                       scf_residual=peak(f@density@s-s@density@f), physical_fock_error=peak(physical-f),
                       gap_hartree=float(eps[nocc]-eps[nocc-1]), min_overlap_eigenvalue=float(np.linalg.eigvalsh(s)[0]),
                       independent_energy_error=abs(energy-gqc['energy_hartree']) if gqc['valid'] else None)
    gates = {'internal_stability':stability_flags['internal'],'external_stability':stability_flags['external'],
             'metric':diagnostics['ortho']<=1e-9,'trace':diagnostics['trace_error']<=1e-8,
             'residual':diagnostics['scf_residual']<=1e-8,'physical_fock':diagnostics['physical_fock_error']<=1e-10,
             'gap':diagnostics['gap_hartree']>1e-6,'independent_energy':gqc['valid'] and diagnostics['independent_energy_error']<=2e-8}
    diagnostics['gates'] = gates
    if not all(gates.values()):
        raise ValueError('failed gates: '+', '.join(k for k,v in gates.items() if not v))
    md = {'schema':'vibedataset.qm9_rhf_reference','version':1, 'inputs':inputs,'auxiliary_shells':[],
          'records':{'conventional':{'hf_energy':energy,'electron_count':mol.nelectron,'scf_residual':diagnostics['scf_residual']}},
          'array_hash':canonical_hash({k:hashlib.sha256(np.ascontiguousarray(v,dtype='<f8').tobytes()).hexdigest()
                                       for k,v in arrays.items()}), 'source_qm9':row,
          'versions':{'pyscf':pyscf.__version__,'numpy':np.__version__,'gqc_fixture_helper_commit':GQC_HELPER_COMMIT},
          'state_producer':'CPU PySCF RHF with explicit GQC STO-3G parameters; unit-overlap AO convention',
          'ao_basis_convention':'real spherical; libcint p=x,y,z; unit self-overlap; chemist-order AO ERIs in float64',
          'units':{'coordinates':'Bohr','orbital_energies':'Hartree','hf_energy':'Hartree','ao_eri':'Hartree'},
          'ao_labels':mol.ao_labels(), 'libcint_to_unit_ao':scale.tolist(),'diagnostics':diagnostics}
    snapshot = journal.call(name,'snapshot_validation',lambda:fixture_snapshot(md,arrays))
    md['reference_identity'] = snapshot.identity
    md['reference_diagnostics'] = dict(snapshot.diagnostics)
    def persist():
        array_path = path/(name+'.npz')
        np.savez_compressed(array_path,**arrays)
        metadata_path = path/(name+'.json')
        write(metadata_path,md)
        return {'metadata_file':metadata_path.name,'array_file':array_path.name,'reference_identity':snapshot.identity,
                'metadata_sha256':file_hash(metadata_path),'array_file_sha256':file_hash(array_path),
                'metadata_bytes':metadata_path.stat().st_size,'array_file_bytes':array_path.stat().st_size,
                'uncompressed_array_bytes':sum(array.nbytes for array in arrays.values())}
    return journal.call(name,'persist_reference',persist,summary=dict)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--helpers',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if not os.environ.get('SLURM_JOB_ID') or pyscf.__version__!='2.14.0':
        raise RuntimeError('expected n5 Slurm runtime and PySCF 2.14.0')
    sys.path.insert(0,str(args.helpers.resolve()))
    from tools.generate_validation_references import pyscf_molecule
    from tools.generativeqc_posthf.fixtures import fixture_snapshot
    start=time.perf_counter()
    args.out.mkdir(exist_ok=False,parents=True)
    cohort=json.loads(args.cohort.read_text())
    members=[s['selected'] for s in cohort['strata'] if s['selected']]
    journal=Journal(args.out,{'gqc_prepare':1,'gqc_execute':1,'reference_scf':len(members),'orbital_stability':len(members)})
    config=json.loads(args.config.read_text())
    native=journal.call('actual_n5_cdll','load_library',lambda:_native.load_library(device='cuda'))
    pack=Path(generativeqc.__file__).parent/'data/basis_pack.json'
    sha=file_hash(native._name)
    if sha!=config['native_library_sha256'] or not Path(native._name).samefile(os.environ['GQC_NATIVE_LIBRARY']) or file_hash(pack)!=PACK_HASH:
        raise ValueError('n5 GQC identity mismatch')
    elements=json.loads(pack.read_text())['bases']['sto-3g']['elements']
    gt=time.perf_counter()
    gpu=gqc_batch(members,config['calculator'],journal)
    gqc_seconds=time.perf_counter()-gt
    rows=[]
    for s in cohort['strata']:
        item={'stratum':s['stratum'],'eligible_count':len(s['eligible_ids'])}
        row=s['selected']
        if row is None:
            rows.append({**item,'name':None,'status':'empty_stratum'})
            continue
        name=row['name']
        diag={}
        item.update(name=name,qm9_id=row['qm9_id'],member_sha256=row['member_sha256'], gqc=gpu[name],pyscf=diag)
        t=time.perf_counter()
        try:
            asset=make_reference(row,gpu[name],elements,args.out,journal,(pyscf_molecule,fixture_snapshot),diag)
            item.update(status='verified',**asset)
        except Exception as error:
            item.update(status='failed',error_type=type(error).__name__,error=str(error))
        item['reference_and_storage_seconds']=time.perf_counter()-t
        rows.append(item)
        write(args.out/'partial.json',rows)
    imports=[args.helpers/rel for rel in ('tools/generate_validation_references.py','tools/generativeqc_validation/fixtures.py',
                                          'tools/generativeqc_posthf/reference.py','tools/generativeqc_posthf/fixtures.py')]
    summary={'job':os.environ['SLURM_JOB_ID'],'project_commit':os.environ['VIBEDATASET_CODE_SHA'],
             'finished_at_utc':datetime.now(timezone.utc).isoformat(),'driver_sha256':file_hash(__file__),
             'cohort_sha256':file_hash(args.cohort),'config_sha256':file_hash(args.config),'n5_native_library_sha256':sha,
             'gqc_runtime_source_declaration':os.environ['GQC_SOURCE_SHA'],'native_source_identity':native.generativeqc_get_source_identity().decode(),
             'basis_pack_sha256':PACK_HASH,'gqc_protocol':config['calculator'],'helper_commit':GQC_HELPER_COMMIT,
             'helper_hashes':{str(p.relative_to(args.helpers)):file_hash(p) for p in imports},
             'python':platform.python_version(),'packages':{p:importlib.metadata.version(p) for p in ('generativeqc','pyscf','numpy','scipy')},
             'pyscf_libcgto_sha256':file_hash(pyscf.gto.moleintor.libcgto._name),
             'pyscf_libcint_sha256':file_hash(Path(pyscf.__file__).parent/'lib/deps/lib/libcint.so'),
             'threads':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')},
             'n_selected':len(members),'outcomes':dict(Counter(r['status'] for r in rows)), 'rows':rows,
             'operation_attempts':dict(journal.counts),'gqc_batch_seconds':gqc_seconds,
             'total_production_seconds_through_assets':time.perf_counter()-start}
    write(args.out/'index.json',summary)
    print(json.dumps({k:summary[k] for k in ('job','outcomes','operation_attempts','gqc_batch_seconds','total_production_seconds_through_assets')},indent=2))
    return int(any(r['status']=='failed' for r in rows))


if __name__=='__main__':
    raise SystemExit(main())
