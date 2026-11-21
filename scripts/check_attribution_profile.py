#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();d=json.loads(a.profile.read_text());errs=[]
 if set(d['arms'])!=set('ABCD'):errs.append('arms')
 if d['claim_gate']['ten_x_hypothesis']!='not supported by this run':errs.append('10x gate')
 if d['claim_gate']['ci_lower_bound_gt_one'] is not False:errs.append('ci gate')
 for arm in 'ABCD':
  if d['arms'][arm]['rows']!=51:errs.append(f'rows {arm}')
  if not d['arms'][arm]['unknown_fields']:errs.append(f'unknowns {arm}')
 if errs:raise SystemExit('; '.join(errs))
 out={'status':'passed','arms':4,'rows_per_arm':51,'ten_x_gate':d['claim_gate']}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
