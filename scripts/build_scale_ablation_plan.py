#!/usr/bin/env python3
"""Summarize completed strata and freeze the remaining scale/ablation gates."""
from __future__ import annotations
import argparse,json,gzip
from collections import Counter,defaultdict
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();e=a.experiment;c=json.loads(a.contract.read_text());manifest=json.loads((e/'manifest.json').read_text());rows=[json.loads(x) for x in (e/'raw/raw-C.jsonl').read_text().splitlines() if x.strip()]
 by=defaultdict(list)
 for row,m in zip(rows,[next(x for x in manifest['molecules'] if x['name']==r['molecule']) for r in rows]):by[len([z for z in m['atomic_numbers'] if z>1])].append(row)
 strata=[]
 for n,items in sorted(by.items()):strata.append({'n_heavy':n,'request_rows':len(items),'status':'measured','gqc_response_seconds':sum((r.get('response_metrics') or {}).get('seconds',0) for r in items),'molecule_seconds':sum(r['molecule_seconds'] for r in items)})
 ablations=[{'name':name,'status':'not_run','reason':reason} for name,reason in [('shape_bucket','requires #37 phase profile'),('gpu_residency','requires new GPU runtime implementation'),('async_streams','requires CUPTI event ledger'),('fused_jk','requires physical-equivalence patch and independent scorer'),('multi_rhs','official baseline already present in #31'),('adjoint','not part of current GPU4PySCF A-D contract'),('asset_planner','measured in #31/#33'),('compile_cache','patch cache negative result measured in #31'),('mixed_precision','FP64 contract has priority'),('batch_size','only 17-geometry cohort available')]]
 scale_manifest=Path(__file__).resolve().parents[1]/c.get('scale_geometry_manifest','')
 scale_count=0
 if scale_manifest.exists():
  with gzip.open(scale_manifest,'rt') as handle: scale_count=json.load(handle)['count']
 result={'schema':'vibedataset.scale_ablation_plan.v1','contract_sha256':c['manifest_sha256'],'completed_scale':{'molecules':17,'request_rows':len(rows),'geometry_manifest_rows':scale_count,'target_scale':1000,'status':'partial-falsified-response-labels-blocked'},'strata':strata,'devices':{'n2':'NVIDIA RTX PRO 6000 Blackwell, measured','n5':'NVIDIA RTX 5090, energy assets measured in prior handoff','A100_H100':'not_available'},'ablations':ablations,'claim_gate':{'ten_x':'not_supported','reason':'C vs A endpoint geometric mean speedup about 1.09x and CI crosses 1','next_required':'generate protocol-consistent response labels and independent quality references for the 1000-row geometry manifest before broad claim'}}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'partial-falsified','molecules':17,'request_rows':len(rows),'ablations':len(ablations)},indent=2))
if __name__=='__main__':main()
