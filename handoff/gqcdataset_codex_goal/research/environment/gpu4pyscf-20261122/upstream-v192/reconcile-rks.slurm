#!/bin/bash
#SBATCH --partition=main
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:08:00
set -eu
python3 merge_upstream_pytest_cases.py --root . --out "retry-$SLURM_JOB_ID" --nodes rks-nodeids.txt --array "$1"
