#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();d=json.loads(a.plan.read_text());errs=[]
 if d['oracle_loaded'] or d['scorer_loaded']:errs.append('truth leakage')
 if len(d['rows'])<20:errs.append('denominator')
 for r in d['rows']:
  if r['disposition']=='direct_reuse' and r['source_identity']!=r['target_identity']:errs.append('identity')
  if r.get('quality_certificate') not in ('independent_scorer_required','evidence_unavailable'):errs.append('certificate')
 if errs:raise SystemExit('; '.join(errs))
 out={'status':'passed','rows':len(d['rows']),'direct':sum(x['disposition']=='direct_reuse' for x in d['rows']),'refine':sum(x['disposition']=='refine_required' for x in d['rows']),'reject':sum(x['disposition']=='reject-and-recompute' for x in d['rows'])};a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
