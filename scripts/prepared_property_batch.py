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
    method:str; basis:str; charge:int; spin:int; ao_representation:str; origin:tuple[float,float,float]; unit:str
    def key(self): return (self.method,self.basis,self.charge,self.spin,self.ao_representation,self.origin,self.unit)

@dataclass(frozen=True)
class Request:
    request_id:str; identity:PropertyIdentity; nao:int; properties:tuple[str,...]; source_asset_ids:tuple[str,...]=()

@dataclass
class Node:
    node_id:str; request_id:str; kind:str; depends_on:list[str]; bucket:str; disposition:str='pending'; reason:str=''

class PreparedPropertyBatch:
    def __init__(self,requests:Iterable[Request],max_workspace_bytes:int=0,resident:bool=False):
        self.requests=list(requests);self.max_workspace_bytes=max_workspace_bytes;self.resident=resident
        self.nodes=[];self.buckets=defaultdict(list);self.failures=[]
    def compile(self):
        for req in self.requests:
            bucket=f'{req.identity.method}|{req.identity.basis}|{req.identity.charge}|{req.identity.spin}|{req.identity.ao_representation}|nao={req.nao}'
            self.buckets[bucket].append(req.request_id)
            ref=f'{req.request_id}:reference';self.nodes.append(Node(ref,req.request_id,'reference',[],bucket,'ready'))
            for prop in req.properties:
                node=f'{req.request_id}:{prop}';deps=[ref]
                if prop in ('hessian','ir','raman'):deps.append(f'{req.request_id}:cpks')
                if prop in ('ir','raman') and f'{req.request_id}:cpks' not in [n.node_id for n in self.nodes]:
                    self.nodes.append(Node(f'{req.request_id}:cpks',req.request_id,'cpks',[ref],bucket,'ready'))
                self.nodes.append(Node(node,req.request_id,prop,deps,bucket,'ready'))
        if self.resident and self.max_workspace_bytes and self.estimated_workspace_bytes()>self.max_workspace_bytes:
            for node in self.nodes: node.disposition='fallback';node.reason='workspace_budget_exceeded'
        return self
    def estimated_workspace_bytes(self):
        return sum(next(r.nao for r in self.requests if r.request_id==n.request_id)**2*8 for n in self.nodes if n.kind in ('reference','cpks'))
    def isolate_failure(self,request_id,reason):
        for node in self.nodes:
            if node.request_id==request_id:node.disposition='reject-and-recompute';node.reason=reason
        self.failures.append({'request_id':request_id,'reason':reason})
    def to_dict(self):
        return {'schema':'vibedataset.prepared_property_batch.v1','resident':self.resident,'max_workspace_bytes':self.max_workspace_bytes,'estimated_workspace_bytes':self.estimated_workspace_bytes(),'buckets':dict(self.buckets),'nodes':[asdict(n) for n in self.nodes],'failures':self.failures}
