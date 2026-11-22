#!/bin/bash
#SBATCH --partition=main
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00
set -eu
out="$PWD/final-$SLURM_JOB_ID"
mkdir "$out"
python3 report_gpu4pyscf_upstream.py --root "$PWD" --inputs test-inputs.json.gz --out "$out/files.json.gz" > "$out/counts.json"
find suite-* retry-* collect-* properties-* -type d -name tree -prune -o -type f -print0 |
  tar -czf "$out/upstream-output.tar.gz" --null -T -
(cd "$out" && sha256sum files.json.gz counts.json upstream-output.tar.gz > checksums.sha256)
