#!/usr/bin/env python3
"""Plan property dependencies and bound resident scratch separately from physical state."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import time
from typing import Iterable


@dataclass(frozen=True)
class PropertyIdentity:
    method: str
    basis: str
    charge: int
    spin: int
    ao_representation: str
    origin: tuple[float, float, float]
    unit: str
    geometry_hash: str = ""

    def key(self):
        return (
            self.method,
            self.basis,
            self.charge,
            self.spin,
            self.ao_representation,
            self.origin,
            self.unit,
            self.geometry_hash,
        )

    def bucket_key(self, nao):
        return (
            self.method,
            self.basis,
            self.charge,
            self.spin,
            self.ao_representation,
            nao,
        )


@dataclass(frozen=True)
class Request:
    request_id: str
    identity: PropertyIdentity
    nao: int
    properties: tuple[str, ...]
    source_asset_ids: tuple[str, ...] = ()
    nocc: int | None = None
    grid: str | None = None
    response_operator: str | None = None
    precision: str | None = None
    conditioning_class: str | None = None
    request_mask: tuple[str, ...] = ()

    def bucket(self):
        key = self.identity.bucket_key(self.nao)
        # Historical requests specify only the six original shape fields.
        if (
            any(
                v is not None
                for v in (
                    self.nocc,
                    self.grid,
                    self.response_operator,
                    self.precision,
                    self.conditioning_class,
                )
            )
            or self.request_mask
        ):
            key += (
                self.nocc,
                self.grid,
                self.response_operator,
                self.precision,
                self.conditioning_class,
                ",".join(self.request_mask),
            )
        return "|".join(map(str, key))


@dataclass
class Node:
    node_id: str
    request_id: str
    kind: str
    depends_on: list[str]
    bucket: str
    disposition: str = "ready"
    reason: str = ""


class PreparedPropertyBatch:
    def __init__(
        self,
        requests: Iterable[Request],
        max_workspace_bytes: int = 0,
        resident: bool = False,
    ):
        self.requests = list(requests)
        self.max_workspace_bytes = max_workspace_bytes
        self.resident = resident
        self.nodes = []
        self.buckets = defaultdict(list)
        self.failures = []
        self.workspace_plan = {}
        self._request = {r.request_id: r for r in self.requests}
        if len(self._request) != len(self.requests) or max_workspace_bytes < 0:
            raise ValueError("duplicate request identity or negative workspace budget")
        self._compiled = False
        self._over_budget = False

    def compile(self):
        if self._compiled:
            return self
        for req in self.requests:
            bucket = req.bucket()
            self.buckets[bucket].append(req.request_id)
            root = f"{req.request_id}:reference"
            response = f"{req.request_id}:cpks"
            self.nodes.append(Node(root, req.request_id, "reference", [], bucket))
            properties = dict.fromkeys(req.properties)
            if any(p in properties for p in ("cpks", "hessian", "ir", "raman")):
                self.nodes.append(
                    Node(response, req.request_id, "cpks", [root], bucket)
                )
            for prop in properties:
                if prop in ("reference", "cpks"):
                    continue
                deps = (
                    [root, response] if prop in ("hessian", "ir", "raman") else [root]
                )
                self.nodes.append(
                    Node(f"{req.request_id}:{prop}", req.request_id, prop, deps, bucket)
                )
        for bucket, ids in self.buckets.items():
            self.workspace_plan[bucket] = dict(
                request_ids=list(ids),
                workspace_bytes=self._request[ids[0]].nao ** 2 * 8,
                resident=self.resident,
            )
        self._over_budget = bool(
            self.resident
            and self.max_workspace_bytes
            and self.estimated_workspace_bytes() > self.max_workspace_bytes
        )
        if self._over_budget:
            for node in self.nodes:
                node.disposition, node.reason = "fallback", "workspace_budget_exceeded"
        self._compiled = True
        return self

    def estimated_workspace_bytes(self):
        if self.resident:
            return sum(item["workspace_bytes"] for item in self.workspace_plan.values())
        return sum(
            self._request[node.request_id].nao ** 2 * 8
            for node in self.nodes
            if node.kind in ("reference", "cpks")
        )

    def isolate_failure(self, request_id, reason):
        for node in self.nodes:
            if node.request_id == request_id:
                node.disposition, node.reason = "reject-and-recompute", reason
        if not any(row["request_id"] == request_id for row in self.failures):
            self.failures.append({"request_id": request_id, "reason": reason})

    def _execute(self, producer, group_key, max_workers):
        self.compile()
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        receipts = {}
        started = time.perf_counter()
        setup_count, group_count = 0, 0
        previously_failed = {r["request_id"]: r["reason"] for r in self.failures}

        def failed(request_id, bucket, reason, detail=None):
            return dict(
                request_id=request_id,
                bucket=bucket,
                status="reject-and-recompute",
                reason=reason,
                detail=detail,
            )

        for bucket, ids in self.buckets.items():
            active = []
            for rid in ids:
                if self._over_budget or rid in previously_failed:
                    reason = previously_failed.get(rid, "workspace_budget_exceeded")
                    receipts[rid] = failed(rid, bucket, reason)
                else:
                    active.append(rid)
            if not active:
                continue
            setup_count += 1
            try:
                state = producer.prepare_bucket(bucket, active)
            except Exception as exc:
                for rid in active:
                    receipts[rid] = failed(
                        rid,
                        bucket,
                        f"bucket_setup_failed:{type(exc).__name__}",
                        str(exc),
                    )
                continue

            def run_chain(chain):
                output = []
                for rid in chain:
                    tick = time.perf_counter()
                    try:
                        row = dict(
                            request_id=rid,
                            bucket=bucket,
                            status="accepted",
                            result=producer.run_request(rid, state),
                        )
                    except Exception as exc:
                        row = failed(
                            rid,
                            bucket,
                            f"request_failed:{type(exc).__name__}",
                            str(exc),
                        )
                    if group_key is not None:
                        row["scheduler_seconds"] = time.perf_counter() - tick
                    output.append(row)
                return output

            if group_key is None:
                rows = run_chain(active)
            else:
                groups = defaultdict(list)
                for rid in active:
                    groups[group_key(rid)].append(rid)
                group_count += len(groups)
                with ThreadPoolExecutor(
                    max_workers=min(max_workers, len(groups))
                ) as pool:
                    rows = [
                        r
                        for chain in pool.map(run_chain, groups.values())
                        for r in chain
                    ]
            receipts.update({r["request_id"]: r for r in rows})
        ordered = [receipts[r.request_id] for r in self.requests]
        for row in ordered:
            if row["status"] != "accepted":
                self.isolate_failure(row["request_id"], row["reason"])
        result = dict(
            setup_count=setup_count,
            request_count=len(ordered),
            receipts=ordered,
            failures=list(self.failures),
        )
        if group_key is not None:
            result.update(
                execution_mode="async-chains",
                max_workers=max_workers,
                group_count=group_count,
                scheduler_seconds=time.perf_counter() - started,
            )
        return result

    def execute(self, producer):
        return self._execute(producer, None, 1)

    def execute_async(self, producer, group_key, max_workers=2):
        """Run host-side chains for producers that support independent concurrent calls."""
        return self._execute(producer, group_key, max_workers)

    def to_dict(self):
        return dict(
            schema="vibedataset.prepared_property_batch.v1",
            resident=self.resident,
            max_workspace_bytes=self.max_workspace_bytes,
            estimated_workspace_bytes=self.estimated_workspace_bytes(),
            buckets=dict(self.buckets),
            workspace_plan=self.workspace_plan,
            nodes=[asdict(n) for n in self.nodes],
            failures=self.failures,
        )
