#!/usr/bin/env python3
"""Protocol-aware request DAG and shape-bucket planner for Issue #38.

This module deliberately compiles an auditable plan. It does not claim that the
plan itself is a GPU kernel or a new scientific solver. A producer may consume
its nodes, and a failed node is isolated from the rest of a bucket.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from collections import defaultdict
from typing import Iterable

@dataclass(frozen=True)
class PropertyIdentity:
    method:str; basis:str; charge:int; spin:int; ao_representation:str; origin:tuple[float,float,float]; unit:str; geometry_hash:str=''
    def key(self): return (self.method,self.basis,self.charge,self.spin,self.ao_representation,self.origin,self.unit,self.geometry_hash)
    def bucket_key(self, nao:int): return (self.method,self.basis,self.charge,self.spin,self.ao_representation,nao)

@dataclass(frozen=True)
class Request:
    request_id:str; identity:PropertyIdentity; nao:int; properties:tuple[str,...]; source_asset_ids:tuple[str,...]=()

@dataclass
class Node:
    node_id:str; request_id:str; kind:str; depends_on:list[str]; bucket:str; disposition:str='pending'; reason:str=''

class PreparedPropertyBatch:
    def __init__(self,requests:Iterable[Request],max_workspace_bytes:int=0,resident:bool=False):
        self.requests=list(requests);self.max_workspace_bytes=max_workspace_bytes;self.resident=resident
        self.nodes=[];self.buckets=defaultdict(list);self.failures=[];self.workspace_plan={}
    def compile(self):
        for req in self.requests:
            bucket='|'.join(map(str,req.identity.bucket_key(req.nao)))
            self.buckets[bucket].append(req.request_id)
            ref=f'{req.request_id}:reference';self.nodes.append(Node(ref,req.request_id,'reference',[],bucket,'ready'))
            for prop in req.properties:
                node=f'{req.request_id}:{prop}';deps=[ref]
                if prop in ('hessian','ir','raman'):deps.append(f'{req.request_id}:cpks')
                if prop in ('ir','raman') and f'{req.request_id}:cpks' not in [n.node_id for n in self.nodes]:
                    self.nodes.append(Node(f'{req.request_id}:cpks',req.request_id,'cpks',[ref],bucket,'ready'))
                self.nodes.append(Node(node,req.request_id,prop,deps,bucket,'ready'))
        for bucket, request_ids in self.buckets.items():
            nao=next(req.nao for req in self.requests if req.request_id==request_ids[0])
            self.workspace_plan[bucket]={'request_ids':list(request_ids),'workspace_bytes':nao*nao*8,'resident':self.resident}
        if self.resident and self.max_workspace_bytes and self.estimated_workspace_bytes()>self.max_workspace_bytes:
            for node in self.nodes: node.disposition='fallback';node.reason='workspace_budget_exceeded'
        return self
    def estimated_workspace_bytes(self):
        if self.resident and self.workspace_plan:
            return sum(item['workspace_bytes'] for item in self.workspace_plan.values())
        return sum(next(r.nao for r in self.requests if r.request_id==n.request_id)**2*8 for n in self.nodes if n.kind in ('reference','cpks'))
    def execute(self, producer):
        """Run bucket setup once, then isolate request-level producer failures.

        ``producer`` must provide ``prepare_bucket(bucket, request_ids)`` and
        ``run_request(request_id, bucket_state)``. The returned receipt counts
        setup reuse separately from scientific request results.
        """
        if not self.nodes:
            self.compile()
        receipts=[]; setup_count=0
        for bucket, request_ids in self.buckets.items():
            setup_count += 1
            try:
                state=producer.prepare_bucket(bucket, request_ids)
            except Exception as exc:
                for request_id in request_ids:
                    self.isolate_failure(request_id,f'bucket_setup_failed:{type(exc).__name__}')
                    receipts.append({'request_id':request_id,'bucket':bucket,'status':'reject-and-recompute','reason':str(exc)})
                continue
            for request_id in request_ids:
                try:
                    result=producer.run_request(request_id,state)
                    receipts.append({'request_id':request_id,'bucket':bucket,'status':'accepted','result':result})
                except Exception as exc:
                    self.isolate_failure(request_id,f'request_failed:{type(exc).__name__}')
                    receipts.append({'request_id':request_id,'bucket':bucket,'status':'reject-and-recompute','reason':str(exc)})
        return {'setup_count':setup_count,'request_count':len(receipts),'receipts':receipts,'failures':list(self.failures)}
    def isolate_failure(self,request_id,reason):
        for node in self.nodes:
            if node.request_id==request_id:node.disposition='reject-and-recompute';node.reason=reason
        self.failures.append({'request_id':request_id,'reason':reason})
    def to_dict(self):
        return {'schema':'vibedataset.prepared_property_batch.v1','resident':self.resident,'max_workspace_bytes':self.max_workspace_bytes,'estimated_workspace_bytes':self.estimated_workspace_bytes(),'buckets':dict(self.buckets),'workspace_plan':self.workspace_plan,'nodes':[asdict(n) for n in self.nodes],'failures':self.failures}
