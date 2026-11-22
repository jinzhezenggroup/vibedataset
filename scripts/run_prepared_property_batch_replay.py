#!/usr/bin/env python3
"""Replay archived request receipts through PreparedPropertyBatch.

This is a planner/producer replay. It counts bucket setup reuse and request
isolation from already archived A-D records. It does not recompute scientific
labels and never presents the accounting as a GPU speedup.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from prepared_property_batch import PreparedPropertyBatch,PropertyIdentity,Request

def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--raw',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();m=json.loads(a.manifest.read_text());raw=[json.loads(x) for x in a.raw.read_text().splitlines() if x.strip()]
 by_name={x['name']:x for x in m['molecules']};requests=[];receipt_by_id={}
 for i,row in enumerate(raw):
  molecule=by_name[row['molecule']];req_id=f"{row['molecule']}:{row['trajectory']}";identity=PropertyIdentity(m['protocol']['method'],m['protocol']['basis'],molecule['charge'],molecule['multiplicity']-1,molecule['basis_representation'],tuple(m['protocol']['origin']),m['protocol']['unit'],molecule['member_sha256']);nao=len(molecule['atomic_numbers'])+4;requests.append(Request(req_id,identity,nao,tuple(row['fields_requested'])));receipt_by_id[req_id]=row
 class Producer:
  def prepare_bucket(self,bucket,request_ids):return {'bucket':bucket,'request_ids':request_ids}
  def run_request(self,request_id,state):
   row=receipt_by_id[request_id];metric=row.get('response_metrics') or {};return {'archived_response_seconds':metric.get('seconds'),'archived_operator_rows':metric.get('operator_rows'),'scientific_label_source':'archived_raw_receipt'}
 batch=PreparedPropertyBatch(requests,resident=True,max_workspace_bytes=0).compile();runtime=batch.execute(Producer());result={'schema':'vibedataset.prepared_property_batch.replay.v1','manifest_sha256':m['manifest_sha256'],'request_count':len(requests),'bucket_count':len(batch.buckets),'serial_setup_count':len(requests),'resident_bucket_setup_count':runtime['setup_count'],'setup_reduction_ratio':runtime['setup_count']/len(requests),'accepted_receipts':sum(x['status']=='accepted' for x in runtime['receipts']),'failures':runtime['failures'],'scientific_producer':'archived raw receipt replay','oracle_loaded':False,'planner_loaded':False,'plan':batch.to_dict()}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('request_count','bucket_count','serial_setup_count','resident_bucket_setup_count','setup_reduction_ratio','accepted_receipts')},indent=2))
if __name__=='__main__':main()
