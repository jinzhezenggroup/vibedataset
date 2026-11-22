#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math
from pathlib import Path

def main():
 p=argparse.ArgumentParser(); p.add_argument('--result',type=Path,required=True); p.add_argument('--raw-c',type=Path,required=True); p.add_argument('--score',type=Path,required=True); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
 result=json.loads(a.result.read_text()); raw={}
 for line in a.raw_c.read_text().splitlines():
  if line.strip():
   row=json.loads(line); raw[(row['molecule'],row['trajectory'])]=row
 score=json.loads(a.score.read_text()); scored={(r['molecule'],r['trajectory']):r for r in score['rows'] if r['arm']=='C'}
 errors=[]; checked=0; max_target=0.; max_residual=0.
 if result.get('status')!='accepted': errors.append('runtime status')
 if result.get('bucket_count')!=1 or result.get('resident_bucket_setup_count')!=1: errors.append('bucket accounting')
 for receipt in result.get('receipts',[]):
  if receipt.get('status')!='accepted': errors.append(f"receipt {receipt.get('request_id')}"); continue
  value=receipt.get('result',{}); key=(value.get('molecule'),value.get('trajectory')); base=raw.get(key); independent=scored.get(key)
  if base is None or independent is None: errors.append(f'missing baseline {key}'); continue
  if independent.get('status')!='accepted': errors.append(f'independent scorer {key}')
  for name,observed in value.get('targets',{}).items():
   diff=abs(float(observed)-float(base['targets'][name])); max_target=max(max_target,diff); checked+=1
   if diff>1e-5: errors.append(f'target {key} {name}: {diff}')
  residual=value.get('residual_linf')
  if residual is not None: max_residual=max(max_residual,float(residual));
 result_out={'schema':'vibedataset.prepared_gpu4pyscf_control_verification.v1','status':'passed' if not errors else 'failed','request_count':len(result.get('receipts',[])),'target_components_checked':checked,'max_target_diff_vs_archived_C':max_target,'max_runtime_residual_linf':max_residual,'independent_archived_C_rows':sum(v.get('status')=='accepted' for v in scored.values()),'errors':errors,'scope':'archived C raw receipt comparison plus independent scorer acceptance coverage; no new scorer process'}
 a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(result_out,indent=2)+'\n'); print(json.dumps(result_out,indent=2));
 if errors: raise SystemExit(1)
if __name__=='__main__': main()
