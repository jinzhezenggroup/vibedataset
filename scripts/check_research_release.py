#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--release',type=Path,required=True);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();d=json.loads((a.release/'release_manifest.json').read_text());errs=[]
 for x in d['artifacts']:
  f=a.root/x['path']
  if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest()!=x['sha256']:errs.append(x['path'])
 claims=(a.release/'claims.csv').read_text().splitlines()
 if len(claims)<10:errs.append('claims')
 out={'status':'passed' if not errs else 'failed','artifacts':len(d['artifacts']),'claims':len(claims)-1,'unknowns':len(d['unknowns'])}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
 if errs:raise SystemExit('; '.join(errs))
if __name__=='__main__':main()
