#!/usr/bin/env python3
"""Build a phase cost ledger from the completed four-arm request receipts."""
from __future__ import annotations
import argparse,json
from pathlib import Path

def rows(path):return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
def main():
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();e=a.experiment
 summary=json.loads((e/'summary.json').read_text());arms={}
 for arm in 'ABCD':
  rs=rows(e/'raw'/f'raw-{arm}.jsonl')
  totals=summary['arms'][arm]['totals']
  timing={
   'prepare':None,'environment_startup':None,'data_read':None,'compile_jit':None,'warmup':None,
   'h2d_observed_bytes':totals['host_to_device_bytes'],'d2h_observed_bytes':totals['device_to_host_bytes'],
   'scf_fock_proxy_cycles':totals['scf_cycles'],'cp_hf_gmres_response_seconds':totals['response_seconds'],
   'physical_residual_seconds':None,'property_readout_seconds':None,'independent_scorer':None,
   'serialization':None,'retry':None,'fallback':None,'end_to_end_molecule_seconds':totals['molecule_seconds'],
   'kernel_launches':None,'occupancy':None,'flops':None,'peak_device_memory_bytes':None,'peak_host_memory_bytes':None,'energy_joules':None}
  arms[arm]={'rows':len(rs),'timing':timing,'cost_totals':totals,'cold_warm_split':'not separately recorded in this run','unknown_fields':[k for k,v in timing.items() if v is None]}
 out={'schema':'vibedataset.attribution_profile.v1','manifest_sha256':json.loads((e/'manifest.json').read_text())['manifest_sha256'],'arms':arms,'paired_effects':summary['paired_effects'],'claim_gate':{'ten_x_hypothesis':'not supported by this run','official_vs_gqc_speedup_geometric_mean':1.0/summary['paired_effects']['gqc_minus_native_official']['molecule_seconds']['geometric_mean_ratio'],'quality_gate':'all 204 scored rows accepted','ci_lower_bound_gt_one':False,'reason':'GQC planner reduced operator rows but did not establish 10x end-to-end speedup'},'unknowns':sorted({u for arm in arms.values() for u in arm['unknown_fields']})}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':'built','arms':4,'unknown_fields':len(out['unknowns'])},indent=2))
if __name__=='__main__':main()
