#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,time,sys
import numpy as np

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();from pyscf import gto;from gpu4pyscf import scf;from gpu4pyscf.properties import ir,raman
 def serial(array):
  values=np.asarray(array)
  return {'real':values.real.tolist(),'imag':values.imag.tolist()} if np.iscomplexobj(values) else values.tolist()
 mol=gto.M(atom='O 0 0 0; H 0 1.4 0; H 1.3 0 0',unit='Bohr',basis='sto-3g',verbose=0);mf=scf.RHF(mol).set(conv_tol=1e-10);started=time.perf_counter();mf.kernel();hess=mf.Hessian();freq,intensity=ir.eval_ir_freq_intensity(mf,hess);rf,activity,depolar=raman.eval_raman_intensity(mf,hessian=hess.kernel());result={'schema':'vibedataset.gpu_spectroscopy_controls.v1','gpu4pyscf_source_commit':'5a717f899cb40d64a5799ef1df7e3626c505c3bd','protocol':{'method':'RHF','basis':'sto-3g','precision':'FP64'},'scf_converged':bool(mf.converged),'ir_frequency_cm1':serial(freq.get()),'ir_intensity_km_mol':serial(intensity.get()),'raman_frequency_cm1':serial(rf),'raman_activity':serial(activity),'raman_depolarization':serial(depolar),'seconds':time.perf_counter()-started,'limitations':['single H2O control','no VeloxChem/Psi4 cross-check','no batch sharing']};open(a.out,'w').write(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
