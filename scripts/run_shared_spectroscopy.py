#!/usr/bin/env python3
"""Schedule exact-state RHF Cartesian responses, Hessians and vibrational readouts."""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from prepared_property_batch import PreparedPropertyBatch, PropertyIdentity, Request


def encoded(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def fingerprint(obj):
    return hashlib.sha256(encoded(obj)).hexdigest()


def build(cp, scf, gto, case, protocol, forced_failure=False, bonding=False):
    shells = {
        s: [[v["angular_momentum"], *v["primitives"]] for v in blocks]
        for s, blocks in protocol["shells"].items()
    }
    mol = gto.M(
        atom=list(zip(case["symbols"], case["xyz"])),
        basis=shells,
        unit="Bohr",
        cart=False,
        charge=protocol["charge"],
        spin=protocol["spin"],
        verbose=0,
    )
    mf = scf.RHF(mol)
    mf.conv_tol = protocol["scf_threshold"]
    mf.conv_tol_cpscf = protocol["response_threshold"]
    if forced_failure:
        mf.max_cycle = 0
    if bonding:
        c = np.ones((mol.nao, 1))
        c /= np.sqrt((c.T @ mol.intor_symmetric("int1e_ovlp") @ c)[0, 0])
        mf.kernel(dm0=cp.asarray(2 * c @ c.T))
    else:
        mf.kernel()
    if not mf.converged:
        raise RuntimeError("scf_nonconvergence")
    return mf


class ResponseState:
    """All mutable caches belong to this one SCF solution and its private driver."""

    def __init__(self, cp, mf, reuse, proof_root=None):
        self.cp, self.mf, self.reuse = cp, mf, reuse
        self.driver = mf.Hessian()
        self.proof_root = proof_root
        self.proof = None
        self.cache = {}
        self.operators = {}
        self.records = []
        self.request = ""
        self.bind()

    def array_id(self, a):
        if a is None:
            return None
        x = np.ascontiguousarray(self.cp.asnumpy(a))
        return (x.dtype.str, x.shape, hashlib.sha256(x.tobytes()).hexdigest())

    def record(self, kind, key, run, logical=0, allow=True):
        begin = time.perf_counter()
        index = (kind, key)
        reused = self.reuse and allow and index in self.cache
        if reused:
            result = self.cache[index]
        else:
            result = run()
            self.cp.cuda.Stream.null.synchronize()
            if self.reuse and allow:
                self.cache[index] = result
        self.records.append(
            dict(
                request_id=self.request,
                kind=kind,
                reused=reused,
                newly_solved_cartesian_rhs=0 if reused else logical,
                seconds=time.perf_counter() - begin,
            )
        )
        return result

    def bind(self):
        drv = self.driver
        original_h1, original_solve = drv.make_h1, drv.solve_mo1
        original_kernel, original_gen = drv.kernel, drv.gen_vind
        atoms = lambda value: tuple(range(self.mf.mol.natm) if value is None else value)

        def h1(coeff, occ, chkfile=None, atmlst=None, verbose=None):
            key = (self.array_id(coeff), self.array_id(occ), atoms(atmlst))
            return self.record(
                "geometric-H1",
                key,
                lambda: original_h1(coeff, occ, chkfile, atmlst, verbose),
                allow=chkfile is None,
            )

        def generate(coeff, occ):
            key = (self.array_id(coeff), self.array_id(occ))
            op = self.record("gen-vind", key, lambda: original_gen(coeff, occ))
            self.operators[id(op)] = (op, key)
            return op

        def solve(
            energy,
            coeff,
            occ,
            h1mo,
            fx=None,
            atmlst=None,
            max_memory=4000,
            verbose=None,
        ):
            op = self.operators.get(id(fx))
            key = (
                self.array_id(energy),
                self.array_id(coeff),
                self.array_id(occ),
                self.array_id(h1mo),
                None if op is None else op[1],
                atoms(atmlst),
                drv.max_cycle,
                drv.level_shift,
                self.mf.conv_tol_cpscf,
            )
            candidate = self.record(
                "geometric-CPHF",
                key,
                lambda: original_solve(
                    energy, coeff, occ, h1mo, fx, atmlst, max_memory, verbose
                ),
                3 * len(atoms(atmlst)),
                allow=op is not None and op[0] is fx,
            )

            if self.proof_root is not None and self.proof is None:
                self.proof_root.mkdir(parents=True, exist_ok=True)
                path = self.proof_root / (self.request + ".npz")
                np.savez_compressed(
                    path,
                    coeff=self.cp.asnumpy(coeff),
                    energy=self.cp.asnumpy(energy),
                    occ=self.cp.asnumpy(occ),
                    h1mo=self.cp.asnumpy(h1mo),
                    mo1=self.cp.asnumpy(candidate[0]),
                    mo_e1=self.cp.asnumpy(candidate[1]),
                )
                self.proof = dict(
                    path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()
                )
            return candidate

        def kernel(*args, **kwargs):
            if args or kwargs:
                return original_kernel(*args, **kwargs)
            return self.record("hessian", (), original_kernel)

        drv.make_h1 = h1
        drv.gen_vind = generate
        drv.solve_mo1 = solve
        drv.kernel = kernel


def readout(cp, state, kind, protocol, case):
    from gpu4pyscf.properties import ir, raman

    mf = state.mf
    driver = state.driver
    if kind == "hessian":
        h = cp.asnumpy(cp.asarray(driver.kernel()))
        return {
            "hessian": h.transpose(0, 2, 1, 3).reshape(3 * mf.mol.natm, -1).tolist()
        }

    def measure():
        mass = [protocol["spectroscopy"]["masses_amu"][s] for s in case["symbols"]]
        np.testing.assert_allclose(
            mf.mol.atom_mass_list(isotope_avg=True), mass, rtol=0, atol=1e-12
        )
        if kind == "ir":
            f, value = ir.eval_ir_freq_intensity(mf, driver)
            return dict(
                ir_frequency_cm1=cp.asnumpy(f).tolist(),
                ir_km_mol=cp.asnumpy(value).tolist(),
            )
        if kind == "raman":
            f, activity, depolar = raman.eval_raman_intensity(
                mf, hessian=driver.kernel()
            )
            freq = cp.asnumpy(f)
            return dict(
                raman_frequency_cm1=(freq.real - freq.imag).tolist(),
                raman_A4_amu=cp.asnumpy(activity).tolist(),
                raman_depolarization=cp.asnumpy(depolar).tolist(),
            )
        raise NotImplementedError("unsupported_property")

    return state.record(
        "readout-" + kind, (protocol["spectroscopy"]["external_frequency_au"],), measure
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--mode", choices=("serial", "shared", "failures"), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--seal-response",
        action="store_true",
        help="save observed H1, gauge and Cartesian MO responses for independent CPU verification",
    )
    a = p.parse_args()
    begun = time.perf_counter()
    import cupy as cp
    import gpu4pyscf
    from gpu4pyscf import scf
    from gpu4pyscf.hessian import rhf
    from pyscf import gto

    spec = json.loads(a.protocol.read_bytes())
    seal = hashlib.sha256(a.protocol.read_bytes()).hexdigest()
    if gpu4pyscf.__version__ != "1.9.2" or cp.cuda.runtime.getDeviceCount() != 1:
        raise ValueError("matched single-GPU wheel required")
    cases = {s["id"]: s for s in spec["cases"]}
    queue = spec["shared_queue"]
    if a.mode == "failures":
        cases["stretched-h2"] = dict(
            id="stretched-h2",
            symbols=["H", "H"],
            xyz=[[0.0, 0.0, 0.0], [0.0, 0.0, 2000.0]],
        )
        queue = [
            dict(
                id=x,
                molecule="stretched-h2"
                if x == "restricted-H2-stretched-gap"
                else "h2o",
                property="invalid" if x == "unsupported-property" else "hessian",
            )
            for x in spec["failure_controls"]
        ]
    reqs = []
    lookup = {}
    states = {}
    events = []
    history = []
    extra = {}
    for q in queue:
        case = cases[q["molecule"]]
        geometry = fingerprint([case["symbols"], case["xyz"]])
        ident = PropertyIdentity(
            spec["method"],
            spec["basis"],
            spec["charge"],
            spec["spin"],
            spec["ao_representation"],
            (0.0, 0.0, 0.0),
            "Bohr",
            geometry,
        )
        # The explicit node also allows previous versions of the generic plan to express Hessian-only requests.
        nao = sum(
            sum(2 * v["angular_momentum"] + 1 for v in spec["shells"][s])
            for s in case["symbols"]
        )
        reqs.append(Request(q["id"], ident, nao, ("cpks", q["property"])))
        lookup[q["id"]] = q
    batch = PreparedPropertyBatch(reqs, resident=a.mode != "serial").compile()
    a.out.mkdir(parents=True, exist_ok=False)
    journal = (a.out / "attempts.jsonl").open("x")

    def log(entry):
        journal.write(encoded(entry).decode() + "\n")
        journal.flush()
        os.fsync(journal.fileno())

    class Producer:
        def prepare_bucket(self, bucket, ids):
            return bucket

        def run_request(self, rid, bucket):
            tick = time.perf_counter()
            q = lookup[rid]
            case = cases[q["molecule"]]
            log(dict(event="started", request_id=rid, unix_time=time.time()))
            state_id = fingerprint(dict(geometry=case, protocol_sha256=seal))
            try:
                if rid == "allocator-oom":
                    pool = cp.cuda.MemoryPool()
                    pool.set_limit(size=1024)
                    with cp.cuda.using_allocator(pool.malloc):
                        cp.empty(4096, dtype=cp.uint8)
                    raise AssertionError("private pool failed to enforce limit")
                if q["property"] not in ("hessian", "ir", "raman"):
                    raise NotImplementedError("unsupported_property")
                state = states.get(state_id) if a.mode != "serial" else None
                if state is None or rid == "single-request-scf-failure":
                    scf_begin = time.perf_counter()
                    history.append(dict(request_id=rid, kind="SCF", status="started"))
                    mf = build(
                        cp,
                        scf,
                        gto,
                        case,
                        spec,
                        forced_failure=rid == "single-request-scf-failure",
                        bonding=rid == "restricted-H2-stretched-gap",
                    )
                    cp.cuda.Stream.null.synchronize()
                    history.append(
                        dict(
                            request_id=rid,
                            kind="SCF",
                            status="finished",
                            seconds=time.perf_counter() - scf_begin,
                        )
                    )
                    gap = float(
                        (
                            cp.min(mf.mo_energy[mf.mo_occ == 0])
                            - cp.max(mf.mo_energy[mf.mo_occ > 0])
                        ).item()
                    )
                    if rid == "restricted-H2-stretched-gap":
                        extra[rid] = dict(
                            gap_hartree=gap,
                            threshold=spec["gap_control"][
                                "orbital_gap_reject_below_hartree"
                            ],
                        )
                        if gap < extra[rid]["threshold"]:
                            raise ValueError("restricted_state_near_degenerate")
                        raise AssertionError(
                            f"stress fixture did not reach the stated gap: {gap}"
                        )
                    state = ResponseState(
                        cp,
                        mf,
                        a.mode != "serial",
                        a.out / "cartesian" if a.seal_response else None,
                    )
                    if a.mode != "serial":
                        states[state_id] = state
                state.request = rid
                before = len(state.records)
                result = readout(cp, state, q["property"], spec, case)
                cp.cuda.Stream.null.synchronize()
                history.extend(state.records[before:])
                return dict(
                    request_id=rid,
                    molecule=case["id"],
                    property=q["property"],
                    scientific_identity=state_id,
                    energy_hartree=float(state.mf.e_tot),
                    cartesian_response=state.proof,
                    result=result,
                )
            finally:
                elapsed = time.perf_counter() - tick
                events.append(dict(request_id=rid, wall_seconds=elapsed))
                log(dict(event="request_exited", request_id=rid, wall_seconds=elapsed))

    try:
        run = batch.execute(Producer())
    finally:
        journal.close()
    report = dict(
        schema="vibedataset.shared_spectroscopy.v1",
        mode=a.mode,
        job=os.environ["SLURM_JOB_ID"],
        protocol_sha256=seal,
        driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        hessian_source_sha256=hashlib.sha256(
            Path(rhf.__file__).read_bytes()
        ).hexdigest(),
        gpu4pyscf=gpu4pyscf.__version__,
        gpu=cp.cuda.runtime.getDeviceProperties(0)["name"].decode(),
        schedule=queue,
        graph=batch.to_dict(),
        requests=run["receipts"],
        events=events,
        history=history,
        controls=extra,
        elapsed_seconds=time.perf_counter() - begun,
    )
    (a.out / "result.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
