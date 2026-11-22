#!/usr/bin/env python3
"""Extract a compact, licensed QM9 geometry manifest without copying the archive."""
from __future__ import annotations
import argparse,hashlib,json,tarfile
from pathlib import Path

def parse_xyz(data):
 lines=data.decode(errors='replace').splitlines();n=int(lines[0].strip());atoms=[]
 for line in lines[2:2+n]:
  p=line.split();atoms.append({'symbol':p[0],'xyz_angstrom':[float(p[1]),float(p[2]),float(p[3])]})
 return atoms

def main():
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--limit',type=int,default=1000);a=p.parse_args();rows=[]
 with tarfile.open(a.archive,'r:bz2') as tar:
  for member in sorted((m for m in tar.getmembers() if m.name.endswith('.xyz')),key=lambda m:m.name):
   if len(rows)>=a.limit:break
   fh=tar.extractfile(member)
   if fh is None:continue
   data=fh.read()
   try:atoms=parse_xyz(data)
   except Exception:continue
   rows.append({'request_id':f'qm9-scale-{len(rows)+1:06d}','qm9_member':member.name,'member_sha256':hashlib.sha256(data).hexdigest(),'atoms':atoms,'charge':0,'spin':0,'method':'RHF','basis':'sto-3g','unit':'Angstrom','source_kind':'public-qm9-geometry','status':'not_run','target_properties':['response_x','response_y','response_z'],'missingness_mask':{'all_targets_missing':True}})
 out={'schema':'vibedataset.qm9_scale_manifest.v1','source':{'archive_name':'dsgdb9nsd.xyz.tar.bz2','sha256':hashlib.sha256(a.archive.read_bytes()).hexdigest(),'license':'CC0','selection':'first 1000 lexicographic valid XYZ members'},'count':len(rows),'response_labels_generated':False,'rows':rows};a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':'built','count':len(rows),'archive_sha256':out['source']['sha256']},indent=2))
if __name__=='__main__':main()
