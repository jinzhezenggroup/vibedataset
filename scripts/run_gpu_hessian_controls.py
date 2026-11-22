#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time,sys
import numpy as np

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
 from pyscf import gto
 from gpu4pyscf import scf,dft
 rows=[]
 cases=[('h2o-rhf','O 0 0 0; H 0 1.4 0; H 1.3 0 0','RHF',None),('nh3-rhf','N 0 0 0; H 0 1.8 0; H 1.56 -0.9 0; H -1.56 -0.9 0','RHF',None),('h2o-rks','O 0 0 0; H 0 1.4 0; H 1.3 0 0','RKS','b3lyp')]
 for name,atom,kind,xc in cases:
  mol=gto.M(atom=atom,unit='Bohr',basis='sto-3g',verbose=0);mf=scf.RHF(mol) if kind=='RHF' else dft.RKS(mol)
  if xc:mf.xc=xc
  mf.conv_tol=1e-10;mf.max_cycle=100;started=time.perf_counter();mf.kernel();row={'name':name,'method':kind,'xc':xc,'scf_converged':bool(mf.converged),'energy_hartree':float(mf.e_tot),'scf_hessian_status':'pending'}
  try:
   h=mf.Hessian().kernel();row.update(scf_hessian_status='accepted',hessian_shape=list(h.shape),hessian_max=float(np.max(np.abs(h))),hessian_sha256=hashlib.sha256(np.asarray(h,dtype=np.float64).tobytes()).hexdigest(),hessian_values=np.asarray(h,dtype=np.float64).tolist(),seconds=time.perf_counter()-started)
  except Exception as exc:row.update(scf_hessian_status='reject-and-recompute',reason=f'{type(exc).__name__}: {exc}',seconds=time.perf_counter()-started)
  rows.append(row)
 result={'schema':'vibedataset.gpu_hessian_controls.v1','python':sys.version,'gpu4pyscf_source_commit':'5a717f899cb40d64a5799ef1df7e3626c505c3bd','rows':rows,'limitations':['no IR/Raman','no VeloxChem cross-check','no finite-difference GPU Hessian']}
 open(a.out,'w').write(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
