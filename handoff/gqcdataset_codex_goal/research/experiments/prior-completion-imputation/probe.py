"""Test information loss in the authors' published property-only imputer."""
import argparse
import csv
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import platform
import subprocess
from time import perf_counter
import zipfile

import torch

PIN = '386217f233f5607a6c69e09c8bd9375fbde06444'
WEIGHT_SHA = '5c87f90555fca68a0d485b9befaf71e41647a67b0637e85579d28d6540ededfb'
SAMPLE_SHA = '37d591e2a33dbeea64369b9336d1d8a3f7f33a1b7f1b258fee7686eb5650ebb6'
REPO = Path('_references/mol_prop_imputation')
MODEL = REPO / 'random_drop_prop2prop/model_random_drop.py'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('assets', type=Path)
    args = ap.parse_args()
    if subprocess.check_output(['git', '-C', REPO, 'rev-parse', 'HEAD'], text=True).strip() != PIN:
        raise ValueError('model source differs')
    if subprocess.check_output(['git', '-C', REPO, 'status', '--porcelain']):
        raise ValueError('model checkout changed')
    weight = args.assets / 'model.pt'
    sample = args.assets / 'sample.csv'
    if hashlib.sha256(weight.read_bytes()).hexdigest() != WEIGHT_SHA or not zipfile.is_zipfile(weight):
        raise ValueError('unexpected checkpoint')
    if hashlib.sha256(sample.read_bytes()).hexdigest() != SAMPLE_SHA:
        raise ValueError('unexpected data slice')

    spec = spec_from_file_location('author_imputer', MODEL)
    source = module_from_spec(spec)
    spec.loader.exec_module(source)
    torch.set_num_threads(1)
    torch.manual_seed(0)
    start = perf_counter()
    model = source.Model(include_quad=False)
    model.load_state_dict(torch.load(weight, map_location='cpu', weights_only=True), strict=True)
    model.eval()
    load_seconds = perf_counter() - start

    with sample.open() as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames[2:24]
        rows = list(reader)
    column = 'homo_lumo_gap'
    index = fields.index(column)
    raw = [float(row[column]) for row in rows]
    missing = torch.full((len(rows), len(fields)), -100., dtype=torch.float32)
    partial = missing.clone()
    # Change one normalized input only. This fixture has no assigned physical units.
    partial[:, 0] = 50.
    invalid = missing.clone()
    invalid[:, 0] = float('nan')
    start = perf_counter()
    with torch.inference_mode():
        predicted = model(missing)
        alternative = model(partial)
        unconverted_nan = model(invalid)
    forward_seconds = perf_counter() - start
    if not torch.isfinite(predicted).all() or not torch.equal(predicted[:1].expand_as(predicted), predicted):
        raise AssertionError('all-missing forward behavior changed')
    if not torch.isfinite(alternative).all() or torch.equal(predicted[:, index], alternative[:, index]):
        raise AssertionError('chosen observed slot did not alter the masked output')
    if not max(raw) > min(raw):
        raise AssertionError('distinct raw targets required for the ambiguity witness')

    print(json.dumps({
        'source_commit': PIN, 'checkpoint_sha256': WEIGHT_SHA, 'sample_sha256': SAMPLE_SHA,
        'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'model_source_sha256': hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        'paper_checkpoint_member': 'random_drop_prop2prop_zenodo/model_random_drop_8_cp_overall.pt',
        'record': '10.5281/zenodo.17519032', 'backend': 'cpu', 'torch': torch.__version__,
        'python': platform.python_version(), 'torch_threads': torch.get_num_threads(), 'seed': 0,
        'selection': 'first 32 data rows of first CSV member in the release. All 22 input slots masked.',
        'frame_shape': list(predicted.shape), 'data_splits': {s: sum(r['split'] == s for r in rows)
                          for s in sorted({r['split'] for r in rows})},
        'observed_target': column, 'raw_min': min(raw), 'raw_max': max(raw),
        'raw_column_units_lower_bound_on_max_absolute_error_of_any_common_prediction': (max(raw) - min(raw)) / 2,
        'all_missing_prediction_normalized_units': float(predicted[0, index]),
        'one_observed_normalized_slot_prediction': float(alternative[0, index]),
        'nonfinite_outputs_when_passing_raw_nan': int((~torch.isfinite(unconverted_nan)).sum()),
        'unique_predictions_all_missing': len(torch.unique(predicted[:, index])), 'scf_calls': 0,
        'parameters': sum(p.numel() for p in model.parameters()),
        'model_initialization_and_parameter_load_seconds': load_seconds,
        'three_forward_batch_seconds': forward_seconds,
        'scope': 'No training or validation-set score. Raw gap range gives a mathematical lower bound for identical inputs under a common inverse scale. No original split scaler needed for this argument.'
    }, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
