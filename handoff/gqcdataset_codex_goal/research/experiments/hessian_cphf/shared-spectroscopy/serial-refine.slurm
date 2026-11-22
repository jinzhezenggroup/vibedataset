#!/bin/bash
#SBATCH --partition=main
#SBATCH --gres=gpu:pro6000:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
set -eu
unset PYTHONPATH
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
out="$PWD/refined-$SLURM_JOB_ID"
mkdir "$out"
for plan in serial-refine-*.json; do
    name=${plan#serial-refine-}; name=${name%.json}
    "$GPU4PYSCF_ENV/bin/python" refine_raman_modes.py --protocol protocol.json --plan "$plan" \
       --shared-result "$SHARED_RESULT" --out "$out/$name" > "$out/$name.log" 2>&1
done
date -u +%FT%TZ > "$out/finished"
