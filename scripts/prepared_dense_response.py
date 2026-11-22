"""Small-system dense J/K ablations around the official GPU4PySCF CPHF solver."""

import hashlib
import time

import numpy as np


SOURCE = r"""
extern "C" __global__ void combined_jk(const TYPE* eri,const TYPE* dm,TYPE* out,int n) {
    int cell=blockIdx.x, v=cell%n, u=(cell/n)%n, field=cell/(n*n);
    __shared__ TYPE partial[128];
    TYPE sum=0;
    for (int pair=threadIdx.x; pair<n*n; pair+=128) {
        int k=pair/n, l=pair%n;
        TYPE j=eri[((u*n+v)*n+k)*n+l], exchange=eri[((u*n+k)*n+v)*n+l];
        sum += dm[field*n*n+pair]*(j-(TYPE)0.5*exchange);
    }
    partial[threadIdx.x]=sum;
    __syncthreads();
    for (int s=64;s>0;s/=2) {
        if (threadIdx.x<s) partial[threadIdx.x]+=partial[threadIdx.x+s];
        __syncthreads();
    }
    if (threadIdx.x==0) out[cell]=partial[0];
}
"""


class DenseResponse:
    def __init__(self, cp, mf, mode, max_bytes):
        from gpu4pyscf.scf.int4c2e import get_int4c2e

        self.cp, self.mode = cp, mode
        self.eri64 = self.eri32 = None
        self.fallback = None
        self.n = mf.mol.nao
        self.inner = mode == "mixed"
        self.required_eri_bytes = (12 if self.inner else 8) * self.n**4
        self.kernels = {}
        self.prepare_seconds = 0.0
        start = time.perf_counter()
        if self.required_eri_bytes > max_bytes:
            self.fallback = "dense_eri_budget"
        else:
            try:
                self.eri64 = cp.ascontiguousarray(get_int4c2e(mf.mol), dtype=cp.float64)
                if self.eri64.shape != (self.n,) * 4:
                    raise ValueError("unexpected official GPU AO integral shape")
                if self.inner:
                    self.eri32 = self.eri64.astype(cp.float32)
                if mode != "dense-separated":
                    kinds = ["double", "float"] if self.inner else ["double"]
                    for kind in kinds:
                        kernel = cp.RawKernel(
                            SOURCE.replace("TYPE", kind), "combined_jk"
                        )
                        kernel.compile()
                        self.kernels[kind] = kernel
                cp.cuda.Stream.null.synchronize()
            except cp.cuda.memory.OutOfMemoryError:
                self.eri64 = self.eri32 = None
                self.fallback = "dense_eri_allocator_oom"
        self.prepare_seconds = time.perf_counter() - start

    def apply(self, dm, low=False):
        cp = self.cp
        eri = self.eri32 if low else self.eri64
        if self.mode == "dense-separated":
            j = cp.einsum("uvkl,dkl->duv", eri, dm)
            k = cp.einsum("ukvl,dkl->duv", eri, dm)
            return j - 0.5 * k
        out = cp.empty(dm.shape, dtype=eri.dtype)
        self.kernels["float" if low else "double"](
            (out.size,), (128,), (eri, cp.ascontiguousarray(dm), out, np.int32(self.n))
        )
        return out

    def solve(self, mf, position, fields, tol, max_cycle):
        from gpu4pyscf.properties.polarizability import gen_vind
        from gpu4pyscf.scf import cphf

        cp = self.cp
        mo, occ, energies = mf.mo_coeff, mf.mo_occ, mf.mo_energy
        co, cv = mo[:, occ > 0], mo[:, occ == 0]
        gap = energies[occ == 0, None] - energies[None, occ > 0]
        rhs = (cv.T @ position @ co)[["xyz".index(k) for k in fields]]
        official = gen_vind(mf, mo, occ)
        counts = dict(
            fp32_rows=0,
            fp64_dense_rows=0,
            official_fallback_rows=0,
            calls=0,
            fp64_quality_rows=0,
        )

        def counted(x):
            counts["calls"] += 1
            counts["official_fallback_rows"] += len(x)
            return official(x)

        def make_action(low):
            c, v = (co.astype(cp.float32), cv.astype(cp.float32)) if low else (co, cv)

            def action(x):
                counts["calls"] += 1
                counts["fp32_rows" if low else "fp64_dense_rows"] += len(x)
                trial = x.reshape(-1, v.shape[1], c.shape[1])
                half = 2 * (v @ trial @ c.T)
                dm = half + half.transpose(0, 2, 1)
                return v.T @ self.apply(dm, low) @ c

            return action

        def defect(x):
            counts["fp64_quality_rows"] += len(x)
            return rhs - (gap * x + official(x))

        fallback = self.fallback
        if self.inner and float(gap.min().item()) < 1e-3:
            fallback = "small_orbital_gap"
        history = []
        if fallback is None:
            try:
                if self.inner:
                    x, _ = cphf.solve(
                        make_action(True),
                        energies.astype(cp.float32),
                        occ,
                        -rhs.astype(cp.float32),
                        tol=1e-4,
                        max_cycle=max_cycle,
                        verbose=0,
                    )
                    x = x.astype(cp.float64)
                else:
                    x, _ = cphf.solve(
                        make_action(False),
                        energies,
                        occ,
                        -rhs,
                        tol=tol,
                        max_cycle=max_cycle,
                        verbose=0,
                    )
                for step in range(3):
                    d = defect(x)
                    scale = float(cp.max(cp.abs(d)).item())
                    history.append(scale)
                    if np.isfinite(scale) and scale <= 1e-7:
                        break
                    if step == 2 or not np.isfinite(scale) or not self.inner:
                        if not np.isfinite(scale) or scale > 1e-5:
                            fallback = "failed_FP64_physical_residual"
                        break
                    delta, _ = cphf.solve(
                        make_action(False),
                        energies,
                        occ,
                        -d / scale,
                        tol=1e-11,
                        max_cycle=max_cycle,
                        verbose=0,
                    )
                    x += scale * delta
            except (RuntimeError, ValueError, cp.cuda.memory.OutOfMemoryError) as error:
                fallback = "dense_solver_" + type(error).__name__
        if fallback:
            x, _ = cphf.solve(
                counted, energies, occ, -rhs, tol=tol, max_cycle=max_cycle, verbose=0
            )
            history.append(float(cp.max(cp.abs(defect(x))).item()))
        if not np.isfinite(history[-1]) or history[-1] > 1e-5:
            raise ValueError("official FP64 physical residual gate")
        return dict(
            vectors={f: v for f, v in zip(fields, x)},
            operator_calls=counts["calls"],
            operator_rows=sum(
                counts[k]
                for k in ("fp32_rows", "fp64_dense_rows", "official_fallback_rows")
            ),
            residual_linf=history[-1],
            dense_execution=dict(
                counts=counts,
                physical_residual_history=history,
                fallback=fallback,
                eri_bytes=self.required_eri_bytes,
                setup_seconds=self.prepare_seconds,
                kernel_sha256=hashlib.sha256(SOURCE.encode()).hexdigest()
                if self.kernels
                else None,
            ),
        )
