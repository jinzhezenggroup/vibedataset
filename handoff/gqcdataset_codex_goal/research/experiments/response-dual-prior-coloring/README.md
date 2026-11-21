# 源码参照的复现命令

该目录保存 4 个探针。OpenMDAO 和 CppAD 处理结构已知、请求缺失、已知交叉项三种不同输入；PySCF 提供实际分子量化对照，pyMOR 提供带已知稳定性下界的降阶算例。运行证据包括首次失败和补充验证。[数值与科学范围](../../audits/response-dual-prior-adjoint.md) · [方向数与可辨识性](../../audits/response-dual-prior-coloring.md)

从项目根目录运行，按源码计划取得 5 份相关 checkout。`pkg-config`、C++17 编译器及 Python 3.13 可用时无需系统变更。原机缺少 pkg-config，通过 `apt-get download pkg-config=0.29.2-1ubuntu3` 和 `dpkg-deb -x` 解到实验私有目录，加入该目录的 bin。首个 CMake 配置只运行到依赖检查，原机使用的二进制和编译时间均有回执。

```bash
set -euo pipefail
root="$PWD"
wrk="$root/.work/response-dual-prior-replay"
exp="$root/handoff/gqcdataset_codex_goal/research/experiments/response-dual-prior-coloring"
mkdir -p "$wrk"
uv venv --python 3.13 "$wrk/env"
uv pip install --python "$wrk/env/bin/python" numpy==2.5.5 scipy==1.18.1 openmdao==3.45.2 \
  pyscf==2.14.0 pymor==2026.1.1 pytest==9.2.0 cmake==4.4.5 ninja==1.13.2
export PATH="$wrk/env/bin:$PATH"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENMDAO_REPORTS=0 PYTHONDONTWRITEBYTECODE=1
PYTHONPATH="$root/_references/openmdao_3_45_2" python "$exp/openmdao_probe.py" > "$wrk/openmdao.json"
(
  cd "$wrk"
  PYTHONPATH="$root/_references/openmdao_3_45_2" python -m pytest -q --import-mode=importlib -p no:cacheprovider \
    "$root/_references/openmdao_3_45_2/openmdao/core/tests/test_coloring.py::BidirectionalTestCase::test_bidir_3colorblock"
)
PYTHONPATH="$root/_references/pymor_2026_1/src" python "$exp/pymor_probe.py" > "$wrk/pymor.json"
PYTHONPATH="$root/_references/gqc/python:$root/_references/gqc" python -m pytest -q -p no:cacheprovider \
  "$root/_references/gqc/tests/python/test_response_krylov.py" \
  -k 'multi_rhs_strategies_and_rank_deficient_rhs or stale_recycle_space_fails_closed_and_explicit_transport_works or failed_solve_does_not_poison_recycle_space'
```

CppAD 的 CMake 在源码目录生成配置头，所以在干净归档的副本中构建。可执行文件直接链接到同一源码树的两个上游数值用例，并继续执行针对部分 Jacobian 的对照。

```bash
mkdir -p "$wrk/cppad-src"
git -C "$root/_references/cppad_2026" archive 5d51b2aa6d6874c8d561da298a90b3721550d45d | tar -x -C "$wrk/cppad-src"
cmake -S "$wrk/cppad-src" -B "$wrk/cppad-build" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$wrk/cppad-build" --target cppad_lib --parallel 3
cpp_lib="$wrk/cppad-build/cppad_lib"
c++ -std=c++17 -O2 -I"$wrk/cppad-src/include" "$exp/cppad_probe.cpp" \
  "$wrk/cppad-src/example/sparse/sparse_jac_for.cpp" "$wrk/cppad-src/example/sparse/sparse_jac_rev.cpp" \
  -L"$cpp_lib" -Wl,-rpath,"$cpp_lib" -lcppad_lib -o "$wrk/cppad-probe"
"$wrk/cppad-probe" > "$wrk/cppad.json"
```

MP2 默认运行的残差超限，程序会在写出 JSON 后返回 1。第二次沿用同一几何、误差门槛和能量有限差分，仅通过公开配置收紧 Krylov 基相关性阈值。两次均按完整分母保留。

```bash
printf '%s\n' 'lib_linalg_helper_dsolve_lindep = 1e-13' > "$wrk/default.py"
printf '%s\n' 'lib_linalg_helper_dsolve_lindep = 1e-24' > "$wrk/tighter.py"
default_status=0
PYSCF_CONFIG_FILE="$wrk/default.py" python "$exp/mp2_adjoint_probe.py" > "$wrk/mp2-default.json" || default_status=$?
test "$default_status" -eq 1
PYSCF_CONFIG_FILE="$wrk/tighter.py" python "$exp/mp2_adjoint_probe.py" > "$wrk/mp2-tightened.json"
```

代数算例确定性构造，不使用训练、随机掩码或额外量化调用。分子实验的输入坐标、固定方向、每个 SCF 周期数、电子数所对应的分子协议、投影梯度和独立残差随结果发布。GQC 3 个上游用例使用已有测试数据；首次漏配仓库根目录导致测试收集失败，补上后通过。OpenMDAO 的已通过用例产生一条未指定约束上下界的上游测试警告。[版本、启动故障和测试记录](verification.json) · [OpenMDAO](openmdao.json) · [CppAD](cppad.json) · [pyMOR](pymor.json) · [PySCF 默认](mp2-default.json) · [PySCF 补充](mp2-tightened.json)
