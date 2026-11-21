#!/usr/bin/env python3
"""Verify Issue #36 fixed checkouts and coverage ledger."""
from __future__ import annotations
import argparse,csv,json,subprocess
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--coverage',type=Path,required=True);p.add_argument('--sources-lock',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 lock=json.loads(a.sources_lock.read_text());expected={'gpu4pyscf':'5a717f899cb40d64a5799ef1df7e3626c505c3bd','pyscf_2_14':'c63a953ba603a5ad8c1d65d88da72aaf05ede4d8'}
 rows=list(csv.DictReader(a.coverage.open()))
 errs=[]
 for ident,sha in expected.items():
  item=next((x for x in lock['repositories'] if x['id']==ident),None)
  if not item or item['commit']!=sha:errs.append(f'lock {ident}')
  if item:
   path=Path(item['checkout_path'])
   if not path.exists():errs.append(f'missing {path}')
   else:
    actual=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if actual!=sha:errs.append(f'head {ident}')
 for row in rows:
  if not (Path('_references')/row['source'].lower().replace('pyscf','pyscf')).exists() and row['source'] not in ('GPU4PySCF','PySCF'): pass
  checkout=Path('_references/gpu4pyscf' if row['source']=='GPU4PySCF' else '_references/pyscf_2_14')
  if not (checkout/row['path']).exists(): errs.append(f'path {row["source"]}:{row["path"]}')
 if len(rows)<15:errs.append('coverage rows')
 baseline=json.loads(a.baseline.read_text())
 if baseline['gpu4pyscf_source_commit']!=expected['gpu4pyscf'] or baseline['pyscf_source_commit']!=expected['pyscf_2_14']:errs.append('baseline commits')
 result={'status':'passed' if not errs else 'failed','coverage_rows':len(rows),'executed_rows':sum(r['executed']=='true' for r in rows),'unknowns':baseline['unknowns']}
 if errs:result['errors']=errs
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 if errs:raise SystemExit(1)
if __name__=='__main__':main()
