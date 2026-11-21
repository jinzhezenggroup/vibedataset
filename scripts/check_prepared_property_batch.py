#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from prepared_property_batch import PreparedPropertyBatch,PropertyIdentity,Request

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 same=PropertyIdentity('RHF','sto-3g',0,0,'real_spherical',(0.,0.,0.),'Bohr');wrong=PropertyIdentity('RHF','6-31g*',0,0,'real_spherical',(0.,0.,0.),'Bohr')
 batch=PreparedPropertyBatch([Request('h2o-a',same,7,('energy','forces','hessian','ir')),Request('h2o-b',same,7,('energy','forces')),Request('wrong-basis',wrong,12,('energy','hessian'))],max_workspace_bytes=0,resident=True).compile();batch.isolate_failure('wrong-basis','protocol_identity_not_reusable')
 budget=PreparedPropertyBatch([Request('large',same,100,('hessian',))],max_workspace_bytes=1000,resident=True).compile()
 result={'status':'passed','positive_bucket_count':len(batch.buckets),'positive_node_count':len(batch.nodes),'isolated_failure':batch.failures,'budget_fallback':sum(n.disposition=='fallback' for n in budget.nodes),'plan':batch.to_dict()}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('status','positive_bucket_count','positive_node_count','budget_fallback')},indent=2))
if __name__=='__main__':main()
