#!/usr/bin/env python3
"""Freeze one represented-matrix decision per source, using only zero-field data and an archived x vector."""
from argparse import ArgumentParser
from collections import Counter
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
from time import perf_counter
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from bound import exact_bound

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
from gqc_dual_response import DualResponseModel
from probe_gqc_residual import check, file_hash, write_json
from target_response_quality import StabilityEvidence


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out.resolve()
    out.mkdir(parents=True, exist_ok=False)

    # These inputs are not needed by the producer, including for asset/coverage queries.
    def keep_blind(event, args):
        if event == 'open' and isinstance(args[0], (str, os.PathLike)):
            parts = Path(args[0]).resolve().parts
            if ('oracles' in parts or 'cphf_v2' in parts or 'response-labels.jsonl' in parts or
                    'oracle-index.json' in parts):
                raise PermissionError('independent labels are sealed during the matrix experiment')
    sys.addaudithook(keep_blind)
    start = perf_counter()
    assets = EXP / 'partial_response_blocks/cohort'
    tar_path = assets / 'assets.tar.gz'
    check(file_hash(tar_path) == json.loads((assets/'manifest.json').read_bytes())[tar_path.name]['sha256'],
          'historical vector archive digest')
    raw = tar_path.read_bytes()
    indices = [EXP/'qm9_response_assets/index.json', EXP/'qm9_extension/assets/index.json']
    cases = []
    matrices = out / 'systems.zip'
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tar, ZipFile(matrices, 'x', ZIP_DEFLATED) as z:
        for index in indices:
            for row in json.loads(index.read_bytes())['rows']:
                name = row.get('name')
                if not name:
                    continue
                rec = {'name': name, 'source_index_sha256': file_hash(index), 'member_sha256': row['member_sha256']}
                cases.append(rec)
                if row['status'] != 'verified':
                    rec.update(status='reference_unavailable', reason=row['error'])
                    continue
                meta, arrays = [index.parent / row[key] for key in ('metadata_file', 'array_file')]
                check((file_hash(meta), file_hash(arrays)) == (row['metadata_sha256'], row['array_file_sha256']),
                      'zero-field source digest')
                model = DualResponseModel(meta, arrays, out/'kernels')
                check(model.ref.identity == row['reference_identity'], 'ground-state identity')
                rec.update(setup=model.setup, input_bytes=meta.stat().st_size + arrays.stat().st_size)
                t = perf_counter()
                member = tar.getmember(name + '/assets/six/vectors.json')
                check(member.isfile(), 'expected a regular historical vector file')
                envelope = json.load(tar.extractfile(member))
                vec = envelope['fields']['x']
                narrow = {'problem_identity': envelope['problem_identity'], 'fields': {'x': vec}, 'observables': {}}
                before = model.counts.copy()
                x, validation = model._cached('fields', 'x', narrow)
                rec.update(vector_member=member.name, vector_envelope_bytes=member.size, vector_sha256=vec['solution_sha256'],
                           vector_checks=validation, vector_seconds=perf_counter() - t,
                           validation_counts=dict(model.counts - before))
                if validation['decision'] != 'accepted':
                    rec.update(status='reject', reason=validation['decision'])
                    continue
                evidence = StabilityEvidence.from_model(model)
                rec['assembly'] = evidence.report
                if evidence.matrix is None:
                    rec.update(status='evidence_unavailable', reason=evidence.report.get('reason'))
                    continue
                b, w = model.rhs_values['fields']['x'], model.rhs_values['observables']['q0']
                q = float(w @ x)
                pieces = (evidence.matrix.ravel(), b, w, x, [q])
                data = np.concatenate(pieces).astype('<f8', copy=False).tobytes()
                t = perf_counter()
                bound = exact_bound(data)
                rec.update(status=bound['status'], bound=bound, bound_seconds=perf_counter()-t, raw_readout=q,
                           field_identity=model.endpoint_identity['fields']['x'],
                           readout_identity=model.endpoint_identity['observables']['q0'], system_bytes=len(data))
                z.writestr(name + '.f64', data)
    check(len(cases) == 17 and len({r['name'] for r in cases}) == len(cases), 'input denominator')
    report = dict(decisions=cases, scope='Exact reals defined by stored FP64 A, b, w, x, q only',
                  coordinate_reference='GQC archived ia rotations, static RHF/STO-3G',
                  python=platform.python_version(), numpy=np.__version__, project_commit=subprocess.check_output(
                      ['git','-C',ROOT,'rev-parse','HEAD'],text=True).strip(), archive_sha256=file_hash(tar_path),
                  archive_bytes=len(raw), systems_sha256=file_hash(matrices), systems_bytes=matrices.stat().st_size,
                  source_hashes={p.name:file_hash(p) for p in (Path(__file__), HERE/'bound.py',
                                ROOT/'scripts/target_response_quality.py', ROOT/'scripts/gqc_dual_response.py')},
                  statuses=dict(Counter(r['status'] for r in cases)), runtime_seconds=perf_counter()-start)
    write_json(out/'decisions.json', report)


if __name__ == '__main__':
    main()
