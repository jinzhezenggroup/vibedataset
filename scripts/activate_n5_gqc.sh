# Source this file in bash. The deployed environment lives entirely under this project.
gqc_env=${VIBEDATASET_N5_ENV:-"$HOME/vibedataset/envs/gqc-2bf3fd98-cp313"}
export GQC_PYTHON="$gqc_env/bin/python"
test -x "$GQC_PYTHON" || return 1
gqc_site=$("$GQC_PYTHON" -c 'import sysconfig; print(sysconfig.get_path("purelib"))') || return 1
export GQC_NATIVE_LIBRARY="$gqc_site/generativeqc/lib/libgenerativeqc.so"
test -f "$GQC_NATIVE_LIBRARY" || return 1
export GENERATIVEQC_LIBRARY="$GQC_NATIVE_LIBRARY"
export GENERATIVEQC_PROFILE=off
export GQC_SOURCE_SHA=2bf3fd98da9c6cfba46ca83345e63e1d934e4780
export CUDA_HOME=${VIBEDATASET_CUDA_HOME:-/group/software/cuda-12.9.1}
export PATH="$gqc_env/bin:$CUDA_HOME/bin:$PATH"
gqc_base=$("$GQC_PYTHON" -c 'import sys; print(sys.base_prefix)') || return 1
gqc_ld="$gqc_site/scipy_openblas32/lib"
for gqc_provider in cuda_runtime cublas cusolver cusparse nvjitlink cuda_nvrtc; do
    gqc_ld="$gqc_ld:$gqc_site/nvidia/$gqc_provider/lib"
done
export LD_LIBRARY_PATH="$gqc_ld:$gqc_base/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONNOUSERSITE=1
unset gqc_env gqc_site gqc_base gqc_ld gqc_provider
