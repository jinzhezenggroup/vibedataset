#!/usr/bin/env python3
"""Run official SCF/CPHF on its primary stream and stage independent FP64 readouts."""

from __future__ import annotations
import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import platform
import time

import numpy as np

from prepared_property_batch import PreparedPropertyBatch, PropertyIdentity, Request
from run_gpu4pyscf_4arm import build_molecule, load_manifest, solve_fields


RAGGED_SOURCE = r"""
extern "C" __global__ void ragged_readout(const double *dm, const double *rt,
    const int *offsets, double *out) {
    int row = blockIdx.x;
    int di = offsets[3*row], ri = offsets[3*row+1], n = offsets[3*row+2];
    __shared__ double tmp[128];
    double sum = 0.;
    for (int j=threadIdx.x; j<n; j+=blockDim.x) sum += dm[di+j] * rt[ri+j];
    tmp[threadIdx.x] = sum;
    __syncthreads();
    for (int stride=64; stride>0; stride/=2) {
        if (threadIdx.x < stride) tmp[threadIdx.x] += tmp[threadIdx.x+stride];
        __syncthreads();
    }
    if (threadIdx.x == 0) out[row] = tmp[0];
}
"""


def pinned(cp, count, dtype=np.float64):
    return np.frombuffer(
        cp.cuda.alloc_pinned_memory(count * np.dtype(dtype).itemsize),
        dtype=dtype,
        count=count,
    )


class ReadoutSlot:
    """One owning stream and its staging buffers. A completed event releases the slot."""

    def __init__(self, cp, capacity, asynchronous):
        self.cp = cp
        self.stream = (
            cp.cuda.Stream(non_blocking=True) if asynchronous else cp.cuda.Stream.null
        )
        nd, nr, nq = capacity
        self.dm = cp.empty(nd)
        self.rt = cp.empty(nr)
        self.out = cp.empty(nq)
        self.offsets = cp.empty((nq, 3), dtype=cp.int32)
        self.host_offsets = pinned(cp, 3 * nq, np.int32).reshape(-1, 3)
        self.host_dm = pinned(cp, nd)
        self.host_targets = pinned(cp, nq)
        self.live = None

    def submit(self, records, kernel, ready):
        cp = self.cp
        d, r, q = 0, 0, 0
        layout = []
        stream = self.stream
        stream.wait_event(ready)
        first, last = cp.cuda.Event(), cp.cuda.Event()
        with stream:
            first.record(stream)
            for row, dm, position in records:
                width = dm.shape[-1] ** 2
                fields, targets = row["fields_requested"], row["target_mask"]
                self.dm[d : d + dm.size] = dm.ravel()
                self.rt[r : r + position.size] = position.transpose(0, 2, 1).ravel()
                for i, (left, right) in enumerate(targets):
                    a, b = (
                        d + fields.index(left) * width,
                        r + "xyz".index(right) * width,
                    )
                    self.host_offsets[q + i] = (a, b, width)
                    if kernel is None:
                        self.out[q + i] = cp.dot(
                            self.dm[a : a + width], self.rt[b : b + width]
                        )
                layout.append((row, d, width, q))
                d, r, q = d + dm.size, r + position.size, q + len(targets)
            if kernel is not None:
                self.offsets[:q].set(self.host_offsets[:q], stream=stream)
                kernel((q,), (128,), (self.dm, self.rt, self.offsets, self.out))
            self.dm[:d].get(out=self.host_dm[:d], stream=stream, blocking=False)
            self.out[:q].get(out=self.host_targets[:q], stream=stream, blocking=False)
            last.record(stream)
        # Keep producer arrays, readiness event and pinned host buffers alive until D2H ends.
        self.live = (records, ready, layout, first, last, d, q)

    def finish(self, origin):
        records, ready, layout, first, last, d, nq = self.live
        last.synchronize()
        for row, offset, width, out in layout:
            fields, targets = row["fields_requested"], row["target_mask"]
            row["response_densities"] = {
                f: self.host_dm[offset + i * width : offset + (i + 1) * width].tolist()
                for i, f in enumerate(fields)
            }
            row["targets"] = {
                t: float(self.host_targets[out + i]) for i, t in enumerate(targets)
            }
        self.live = None
        return dict(
            requests=[row["request_id"] for row, *_ in layout],
            shapes=[int(dm.shape[-1]) for _, dm, _ in records],
            device_to_host_bytes=int(8 * (d + nq)),
            readout_stream=int(self.stream.ptr),
            gpu_begin_ms=self.cp.cuda.get_elapsed_time(origin, first),
            gpu_end_ms=self.cp.cuda.get_elapsed_time(origin, last),
        )


def options():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--molecules", nargs="+", required=True)
    p.add_argument("--mode", choices=("serial", "async_streams"), required=True)
    p.add_argument(
        "--workers",
        type=int,
        default=2,
        help="maximum simultaneously owned readout slots",
    )
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument(
        "--ragged",
        action="store_true",
        help="one FP64 CUDA readout launch across variable AO lengths",
    )
    p.add_argument("--resident", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--asset-reuse", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--multi-rhs", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument(
        "--workspace-bytes",
        type=int,
        default=0,
        help="GPU readout staging budget; 0 is unbounded",
    )
    p.add_argument(
        "--fault",
        action="append",
        default=[],
        metavar="REQUEST=KIND",
        help="bounded controls: allocator-oom, scf-fail or unsupported",
    )
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if min(args.workers, args.batch_size) < 1 or args.workspace_bytes < 0:
        p.error("invalid staging limits")
    return args


def main():
    begun = time.perf_counter()
    args = options()
    import cupy as cp
    import gpu4pyscf
    from gpu4pyscf import scf
    from gpu4pyscf.scf import cphf
    from pyscf import gto

    manifest = load_manifest(args.manifest)
    protocol = manifest["protocol"]
    by_name = {m["name"]: m for m in manifest["molecules"]}
    if (
        len(set(args.molecules)) != len(args.molecules)
        or not set(args.molecules) <= by_name.keys()
    ):
        raise ValueError("duplicate or unknown molecule")
    primary = cp.cuda.Stream.null
    origin = cp.cuda.Event()
    origin.record(primary)
    origin.synchronize()
    transfer = (
        cp.cuda.Stream(non_blocking=True) if args.mode == "async_streams" else primary
    )
    molecules = {n: build_molecule(gto, by_name[n], protocol) for n in args.molecules}
    trajectories = sorted(manifest["request_trajectories"], key=lambda t: t["order"])
    requests = []
    info = {}
    for traj in trajectories:
        for name, mol in molecules.items():
            item = by_name[name]
            rid = name + ":" + traj["id"]
            identity = PropertyIdentity(
                protocol["method"],
                protocol["basis"],
                item["charge"],
                item["multiplicity"] - 1,
                protocol["basis_representation"],
                tuple(protocol["origin"]),
                protocol["unit"],
                item["member_sha256"],
            )
            requests.append(
                Request(
                    rid,
                    identity,
                    mol.nao,
                    ("response",),
                    nocc=mol.nelectron // 2,
                    grid="none",
                    precision=protocol["precision"],
                    response_operator="RHF-electric-dipole",
                    conditioning_class="unmeasured",
                    request_mask=tuple(traj["targets"]),
                )
            )
            info[rid] = name, traj
    batch = PreparedPropertyBatch(requests, resident=args.resident).compile()
    fault = dict(v.split("=", 1) for v in args.fault)
    if set(fault) - info.keys() or set(fault.values()) - {
        "scf-fail",
        "unsupported",
        "allocator-oom",
    }:
        raise ValueError("unplanned fault")
    ring_size = (
        min(args.workers, math.ceil(len(requests) / args.batch_size))
        if args.mode == "async_streams"
        else 1
    )

    def capacity(group):
        return (
            sum(req.nao**2 * len(info[req.request_id][1]["fields"]) for req in group),
            sum(3 * req.nao**2 for req in group),
            sum(len(info[req.request_id][1]["targets"]) for req in group),
        )

    groups = [
        requests[i : i + args.batch_size]
        for i in range(0, len(requests), args.batch_size)
    ]
    maxima = tuple(map(max, zip(*(capacity(g) for g in groups))))
    required = ring_size * (8 * (sum(maxima)) + 12 * maxima[2])
    budget_fallback = bool(args.workspace_bytes and required > args.workspace_bytes)
    slots = deque()
    busy = deque()
    blocks = []
    rows = []
    timeline = []
    assets = {}
    states = {}
    positions = {}
    allocs = 0
    kernel = None
    compile_seconds = 0.0
    if args.ragged and not budget_fallback:
        start = time.perf_counter()
        kernel = cp.RawKernel(RAGGED_SOURCE, "ragged_readout")
        kernel.compile()
        compile_seconds = time.perf_counter() - start
    if args.resident and not budget_fallback:
        for _ in range(ring_size):
            slots.append(ReadoutSlot(cp, maxima, args.mode == "async_streams"))
            allocs += 1

    def finish_first():
        slot = busy.popleft()
        blocks.append(slot.finish(origin))
        if args.resident:
            slots.append(slot)

    def prefetch(mol):
        with mol.with_common_orig(tuple(protocol["origin"])):
            data = mol.intor("int1e_r", comp=3)
        host = pinned(cp, data.size).reshape(data.shape)
        host[:] = data
        with transfer:
            dev = cp.empty(data.shape, dtype=cp.float64)
            dev.set(host, stream=transfer)
            ready = cp.cuda.Event()
            ready.record(transfer)
        return dev, ready, host

    for name, mol in molecules.items():
        positions[name] = prefetch(mol)
    for group in groups:
        if len(busy) >= ring_size:
            finish_first()
        payload = []
        for req in group:
            rid = req.request_id
            name, traj = info[rid]
            mol = molecules[name]
            fields, targets = traj["fields"], traj["targets"]
            row = dict(
                request_id=rid,
                molecule=name,
                qm9_id=by_name[name]["qm9_id"],
                trajectory=traj["id"],
                input_sha256=manifest["manifest_sha256"],
                protocol=protocol,
                fields_requested=list(fields),
                target_mask=list(targets),
                geometry_sha256=req.identity.geometry_hash,
                bucket=req.bucket(),
            )
            rows.append(row)
            tick = time.perf_counter()
            try:
                if fault.get(rid) == "unsupported":
                    raise NotImplementedError("unsupported_property")
                if fault.get(rid) == "allocator-oom":
                    # A private CuPy pool exercises its real allocation limit without consuming other jobs' memory.
                    bounded = cp.cuda.MemoryPool()
                    bounded.set_limit(size=1024)
                    with cp.cuda.using_allocator(bounded.malloc):
                        cp.empty(4096, dtype=cp.uint8)
                    raise AssertionError("private pool unexpectedly exceeded its limit")
                if name not in states or fault.get(rid) == "scf-fail":
                    mf = scf.RHF(mol)
                    mf.conv_tol = protocol["conv_tol"]
                    mf.max_cycle = (
                        0 if fault.get(rid) == "scf-fail" else protocol["max_cycle"]
                    )
                    mf.kernel()
                    if not mf.converged:
                        raise RuntimeError("scf_nonconvergence")
                    states[name] = mf
                mf = states[name]
                pos, ready, host = positions[name]
                primary.wait_event(ready)
                cache = (
                    assets.setdefault(req.identity.key(), {})
                    if args.asset_reuse
                    else {}
                )
                needed = [f for f in fields if f not in cache]
                calls = work = 0
                residual = None
                first, last = cp.cuda.Event(), cp.cuda.Event()
                first.record(primary)
                batches = (
                    [needed] if args.multi_rhs and needed else [[f] for f in needed]
                )
                for new in batches:
                    solved = solve_fields(
                        cp,
                        cphf,
                        mf,
                        ["xyz".index(f) for f in new],
                        protocol["response_tol"],
                        protocol["response_max_cycle"],
                        None,
                        position=pos,
                        keep_device=True,
                    )
                    cache.update(solved["vectors"])
                    calls += solved["operator_calls"]
                    work += solved["operator_rows"]
                    residual = max(residual or 0, solved["residual_linf"])
                x = cp.stack([cache[f] for f in fields])
                co = mf.mo_coeff[:, mf.mo_occ > 0]
                cv = mf.mo_coeff[:, mf.mo_occ == 0]
                half = 2 * (cv @ x @ co.T)
                dm = half + half.transpose(0, 2, 1)
                last.record(primary)
                row.update(
                    status="accepted",
                    fields_computed=needed,
                    fields_reused=[f for f in fields if f not in needed],
                    operator_calls=calls,
                    operator_rows=work,
                    residual_linf=residual,
                    response_seconds=time.perf_counter() - tick,
                )
                timeline.append((rid, first, last))
                payload.append((row, dm, pos))
            except (RuntimeError, MemoryError, NotImplementedError) as error:
                row.update(
                    status="reject-and-recompute",
                    reason=type(error).__name__ + ": " + str(error),
                )
                batch.isolate_failure(rid, row["reason"])
        if not payload:
            continue
        if budget_fallback:
            for row, device_density, pos in payload:
                dm, rt = cp.asnumpy(device_density), cp.asnumpy(pos)
                row["response_densities"] = {
                    f: d.ravel().tolist() for f, d in zip(row["fields_requested"], dm)
                }
                readout = np.einsum("fuv,kvu->fk", dm, rt)
                row["targets"] = {
                    t: float(
                        readout[row["fields_requested"].index(t[0]), "xyz".index(t[1])]
                    )
                    for t in row["target_mask"]
                }
                row["fallback"] = "host_readout_workspace_budget"
            continue
        ready = cp.cuda.Event()
        ready.record(primary)
        if args.resident:
            slot = slots.popleft()
        else:
            slot = ReadoutSlot(cp, capacity(group), args.mode == "async_streams")
            allocs += 1
        slot.submit(payload, kernel, ready)
        busy.append(slot)
        if args.mode == "serial":
            finish_first()
    while busy:
        finish_first()
    primary.synchronize()
    transfer.synchronize()
    results = []
    for r in rows:
        if r["status"] == "accepted":
            results.append(
                dict(
                    request_id=r["request_id"],
                    bucket=r["bucket"],
                    status="accepted",
                    result=r,
                )
            )
        else:
            results.append(
                dict(
                    request_id=r["request_id"],
                    bucket=r["bucket"],
                    status=r["status"],
                    reason=r["reason"],
                )
            )
    code_hash = hashlib.sha256(Path(cphf.__file__).read_bytes()).hexdigest()
    source = (
        "8536a80c1e03260aab030e108ef1d181a3709057"
        if (gpu4pyscf.__version__, code_hash)
        == ("1.9.2", "1010af1ff5cb62e424223e6c65bad9344e7a6e37bf6882ff574efddb9e2839de")
        else None
    )
    result = dict(
        schema="vibedataset.prepared_gpu4pyscf_streams.v2",
        runtime_mode=args.mode,
        status="partial" if batch.failures else "accepted",
        gpu4pyscf_version=gpu4pyscf.__version__,
        gpu4pyscf_source_commit=source,
        cphf_sha256=code_hash,
        python=platform.python_version(),
        cupy=cp.__version__,
        gpu=cp.cuda.runtime.getDeviceProperties(0)["name"].decode(),
        manifest_sha256=manifest["manifest_sha256"],
        request_count=len(rows),
        bucket_count=len(batch.buckets),
        cuda_context_count=1,
        async_group_count=len(blocks),
        scientific_stream=int(primary.ptr),
        h2d_stream=int(transfer.ptr),
        batch_size=args.batch_size,
        ragged=args.ragged,
        resident=args.resident,
        asset_reuse=args.asset_reuse,
        multi_rhs=args.multi_rhs,
        readout_slot_allocations=allocs,
        readout_gpu_workspace_capacity_bytes=required,
        workspace_budget_fallback=budget_fallback,
        ragged_kernel_sha256=hashlib.sha256(RAGGED_SOURCE.encode()).hexdigest()
        if kernel
        else None,
        compile_seconds=compile_seconds,
        readout_blocks=blocks,
        receipts=results,
        failures=batch.failures,
        compute_event_envelopes=[
            dict(
                request_id=rid,
                gpu_begin_ms=cp.cuda.get_elapsed_time(origin, a),
                gpu_end_ms=cp.cuda.get_elapsed_time(origin, b),
            )
            for rid, a, b in timeline
        ],
        elapsed_seconds=time.perf_counter() - begun,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, allow_nan=False, separators=(",", ":")) + "\n"
    )


if __name__ == "__main__":
    main()
