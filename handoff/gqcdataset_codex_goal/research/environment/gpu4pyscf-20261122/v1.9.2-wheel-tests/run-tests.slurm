#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
set -euo pipefail
source ~/miniconda3/etc/profile.d/conda.sh
conda activate xtbflow-qc
export OMP_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export OPENBLAS_NUM_THREADS="$SLURM_CPUS_PER_TASK"
export MKL_NUM_THREADS="$SLURM_CPUS_PER_TASK"
cd "$HOME/vibedataset/runs/gpu4pyscf-v1.9.2-build-20261122"
rm -rf tag-tests
mkdir tag-tests
tar -xzf gpu4pyscf-v192-tests.tar.gz -C tag-tests
VENV="$PWD/wheel-venv/bin/python"
$VENV - <<'PY'
import gpu4pyscf, cupy, pyscf, sys
print('gpu4pyscf',gpu4pyscf.__version__)
print('cupy',cupy.__version__)
print('pyscf',pyscf.__version__)
print('python',sys.version)
print('device_count',cupy.cuda.runtime.getDeviceCount())
PY
$VENV -m pytest -q tag-tests/gpu4pyscf/properties/tests/test_polarizability.py tag-tests/gpu4pyscf/scf/tests/test_cphf.py tag-tests/gpu4pyscf/properties/tests/test_ir_intensity.py tag-tests/gpu4pyscf/properties/tests/test_raman_intensity.py --maxfail=1
