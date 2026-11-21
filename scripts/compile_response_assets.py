#!/usr/bin/env python3
"""Compile protocol-bound response asset dispositions without loading oracle truth."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def identity(protocol,molecule):return hashlib.sha256(canonical({'protocol':protocol,'molecule':molecule})).hexdigest()
def classify(source,target):
 keys=('method','basis','charge','multiplicity','basis_representation','origin','unit','precision')
 mism=[k for k in keys if source.get(k)!=target.get(k)]
 if not mism:return 'direct_reuse','exact_protocol_identity'
 if set(mism)<= {'basis','method'} and source.get('charge')==target.get('charge') and source.get('multiplicity')==target.get('multiplicity'):return 'refine_required','protocol_model_changed'
 return 'reject-and-recompute','state_or_operator_identity_mismatch'
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();m=json.loads(a.manifest.read_text());base={**m['protocol'],'method':m['protocol']['method'],'basis':m['protocol']['basis'],'charge':0,'multiplicity':1,'unit':m['protocol']['unit'],'precision':m['protocol']['precision']}
 rows=[]
 for item in m['molecules']:
  target={**base,'charge':item['charge'],'multiplicity':item['multiplicity'],'basis_representation':item['basis_representation']}
  status,reason=classify(target,target);rows.append({'asset_id':item['name']+':response','geometry_hash':item['member_sha256'],'source_identity':identity(target,item['name']),'target_identity':identity(target,item['name']),'disposition':status,'reason':reason,'quality_certificate':'independent_scorer_required','oracle_loaded':False})
 for label,change,expected in [('wrong-basis',{'basis':'6-31g*'},'refine_required'),('wrong-method',{'method':'B3LYP'},'refine_required'),('open-shell',{'multiplicity':2},'reject-and-recompute')]:
  source=dict(base);target={**base,**change};rows.append({'asset_id':'qm9-000003:'+label,'source_identity':identity(source,'qm9-000003'),'target_identity':identity(target,'qm9-000003'),'disposition':classify(source,target)[0],'expected':expected,'reason':classify(source,target)[1],'quality_certificate':'evidence_unavailable','oracle_loaded':False})
 result={'schema':'vibedataset.response_asset_compiler.v1','manifest_sha256':m['manifest_sha256'],'rows':rows,'oracle_loaded':False,'scorer_loaded':False,'certificate_policy':{'physical_residual':'required','conditioning':'only_if_covered','independent_reference':'required','evidence_unavailable':'retain_in_denominator'}}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'built','rows':len(rows),'direct':sum(x['disposition']=='direct_reuse' for x in rows),'refine':sum(x['disposition']=='refine_required' for x in rows),'reject':sum(x['disposition']=='reject-and-recompute' for x in rows)},indent=2))
if __name__=='__main__':main()
