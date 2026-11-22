#!/usr/bin/env python3
"""Instrument the four-arm producer with NVTX, CUDA events and NVML energy."""
import argparse
import ctypes as ct
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path


class MemoryInfo(ct.Structure):
    _fields_ = [(name, ct.c_ulonglong) for name in ("total", "free", "used")]


class Board:
    def __init__(self, pci):
        self.lib = ct.CDLL("libnvidia-ml.so.1")
        handle = ct.c_void_p
        signatures = {"nvmlInit_v2": [], "nvmlDeviceGetHandleByPciBusId_v2": [ct.c_char_p, ct.POINTER(handle)],
                      "nvmlDeviceGetMemoryInfo": [handle, ct.POINTER(MemoryInfo)],
                      "nvmlDeviceGetTotalEnergyConsumption": [handle, ct.POINTER(ct.c_ulonglong)]}
        for name, args in signatures.items():
            fn = getattr(self.lib, name)
            fn.argtypes, fn.restype = args, ct.c_int
        self.handle = handle()
        if self.lib.nvmlInit_v2() or self.lib.nvmlDeviceGetHandleByPciBusId_v2(pci.encode(), ct.byref(self.handle)):
            raise RuntimeError("cannot identify the Slurm-allocated PCI device through NVML")

    def energy(self):
        value = ct.c_ulonglong()
        status = self.lib.nvmlDeviceGetTotalEnergyConsumption(self.handle, ct.byref(value))
        return {"millijoules": None if status else value.value, "nvml_status": status}

    def sample(self):
        memory = MemoryInfo()
        rc = self.lib.nvmlDeviceGetMemoryInfo(self.handle, ct.byref(memory))
        return time.perf_counter_ns(), None if rc else memory.used


class Observer:
    def __init__(self, cupy, out, board):
        self.cp, self.out, self.board = cupy, out, board
        self.samples = []
        self.stop = threading.Event()

    def sample(self):
        while not self.stop.wait(0.01):
            self.samples.append(self.board.sample())

    @contextmanager
    def measure(self, name):
        cp = self.cp
        cp.cuda.runtime.deviceSynchronize()
        start, end = cp.cuda.Event(), cp.cuda.Event()
        self.out.write(json.dumps(dict(name=name, status="started")) + "\n")
        self.out.flush()
        os.fsync(self.out.fileno())
        baseline = self.board.sample()
        first = self.board.energy()
        begin = time.perf_counter_ns()
        cp.cuda.nvtx.RangePush(name)
        start.record()
        state = "interrupted"
        try:
            yield
            cp.cuda.runtime.deviceSynchronize()
            end.record()
            end.synchronize()
            state = "finished"
        finally:
            cp.cuda.nvtx.RangePop()
            elapsed = (time.perf_counter_ns()-begin) / 1e9
            last = self.board.energy()
            finish = self.board.sample()
            samples = [baseline, *[s for s in self.samples if begin <= s[0] <= finish[0]], finish]
            used = [n for _,n in samples if n is not None]
            energy = None
            if first["nvml_status"] == last["nvml_status"] == 0:
                energy = (last["millijoules"] - first["millijoules"]) / 1000
            self.out.write(json.dumps(dict(name=name, status=state, wall_seconds=elapsed,
                cuda_event_seconds=cp.cuda.get_elapsed_time(start, end)/1000 if state == "finished" else None,
                energy_start=first, energy_end=last, board_joules=energy, valid_memory_samples=len(used),
                sampled_board_memory_peak_bytes=max(used) if used else None))+"\n")
            self.out.flush()

    def store_rows(self, out, records):
        ledger = []
        with (out / "raw.jsonl").open("xb") as handle:
            for row in records:
                tick = time.perf_counter_ns()
                body = (json.dumps(row, sort_keys=True) + "\n").encode()
                serialized = time.perf_counter_ns()
                handle.write(body)
                handle.flush()
                end = time.perf_counter_ns()
                ledger.append(dict(molecule=row["molecule"], trajectory=row["trajectory"], bytes=len(body),
                                   serialize_ns=serialized-tick, write_flush_ns=end-serialized))
            tick = time.perf_counter_ns()
            os.fsync(handle.fileno())
            durable_ns = time.perf_counter_ns() - tick
        (out / "storage.json").write_text(json.dumps(dict(rows=ledger, queue_fsync_ns=durable_ns))+"\n")

    def requests(self, molecule, requests):
        for row in requests:
            with self.measure(f"request/{molecule}/{row['id']}"):
                yield row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--arm", choices=list("ABCD"), required=True)
    p.add_argument("--patch", type=Path)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--telemetry", action="store_true", help="store the full timing schema and write/fsync costs")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    import cupy
    import gpu4pyscf
    from gpu4pyscf.scf import cphf
    from run_gpu4pyscf_4arm import run_arm, sha256_file

    patched = args.arm in "BD"
    digest = sha256_file(Path(cphf.__file__))
    expected = ("e945d59c4b19a5b183af2e4651caf2bb9276dc807079b8c060bb6490854a4d6a" if patched else
                "1010af1ff5cb62e424223e6c65bad9344e7a6e37bf6882ff574efddb9e2839de")
    if digest != expected or gpu4pyscf.__version__ != "1.9.2" or patched != bool(args.patch):
        raise ValueError("loaded backend identity does not match arm")
    if patched:
        from gpu4pyscf.lib import response_cache
        if sha256_file(args.patch) != "dad0f28af59dc9dca2fc3c0c78f73920ae4f5593bc2d50408fc02153293679d5" or sha256_file(Path(response_cache.__file__)) != "62afccc84479183487d4a9e5fe442926bca87e772fe50bb1f59f5de876d1d359":
            raise ValueError("unexpected B/D cache implementation")
    args.gpu4pyscf_source_commit = "8536a80c1e03260aab030e108ef1d181a3709057"
    pci = cupy.cuda.Device().pci_bus_id
    board = Board(pci)
    with (args.out/"phases.jsonl").open("x") as journal:
        observer = Observer(cupy, journal, board)
        args.observer = observer
        sampler = threading.Thread(target=observer.sample, daemon=True)
        sampler.start()
        try:
            if args.telemetry:
                from run_gpu4pyscf_4arm_telemetry import run
                run(args)
            else:
                run_arm(args)
        finally:
            observer.stop.set()
            sampler.join()
    (args.out/"trace-identity.json").write_text(json.dumps(dict(version=gpu4pyscf.__version__, cphf_sha256=digest,
        arm=args.arm, pci=pci, gpu=cupy.cuda.runtime.getDeviceProperties(0)["name"].decode(),
        observer_sha256=sha256_file(Path(__file__)), sample_wait_ms=10, python=sys.version),indent=2)+"\n")


if __name__ == "__main__":
    main()
