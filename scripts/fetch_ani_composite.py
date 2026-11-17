#!/usr/bin/env python3
"""Package the three published ANI v1 group slices used by CBS-001 for offline replay."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.request import urlopen

import fsspec
import h5py
import numpy as np

from inspect_ani_release import FILE_ID, RECORD

ASSETS = Path('handoff/gqcdataset_codex_goal/research/assets')
# Distinguish total HF energies from correlation increments at each basis/PNO setting.
COLUMNS = {
    'hf_t': 'hf_tz.energy', 'hf_q': 'hf_qz.energy', 'mp2_t': 'mp2_tz.corr_energy',
    'mp2_q': 'mp2_qz.corr_energy', 'normal_t': 'npno_ccsd(t)_tz.corr_energy',
    'tight_d': 'tpno_ccsd(t)_dz.corr_energy', 'normal_d': 'npno_ccsd(t)_dz.corr_energy',
    'published': 'ccsd(t)_cbs.energy',
}


def main(outdir):
    start = time.perf_counter()
    sample = json.loads((ASSETS / 'ani-v1-slice.json').read_text())
    with urlopen(RECORD, timeout=30) as response:
        record = json.load(response)
    file = next(entry for entry in record['files'] if entry['id'] == FILE_ID)
    if (record['doi'], file['computed_md5'], file['size']) != (sample['doi'], sample['publisher_md5'], sample['size']):
        raise ValueError('release identity mismatch')
    fs = fsspec.filesystem('http', client_kwargs={'trust_env': True}, timeout=30)
    arrays, groups = {}, []
    with fs.open(file['download_url'], 'rb', size=file['size'], block_size=256 * 1024,
                 cache_type='blockcache') as remote:
        with h5py.File(remote, 'r') as hdf:
            for i, group_info in enumerate(sample['groups']):
                group = hdf[group_info['group']]
                lo, hi = group_info['row_interval']
                coords = group['coordinates'][lo:hi]
                nuclei = group['atomic_numbers'][()]
                coord_hash = hashlib.sha256(coords.tobytes()).hexdigest()
                if nuclei.tolist() != group_info['atomic_numbers'] or coord_hash != group_info['fields']['coordinates']['slice_sha256_c_order']:
                    raise ValueError('geometry/order no longer matches the selected release')
                groups.append({'group': group.name, 'rows': [lo, hi], 'coordinate_slice_sha256': coord_hash})
                for alias, key in COLUMNS.items():
                    values = group[key][lo:hi]
                    if values.dtype.str != '<f8' or values.shape != (hi - lo,):
                        raise ValueError(f'unexpected dtype or shape for {group.name}/{key}')
                    if alias == 'published' and hashlib.sha256(values.tobytes()).hexdigest() != group_info['fields'][key]['slice_sha256_c_order']:
                        raise ValueError('published label slice changed')
                    arrays[f'g{i}_{alias}'] = values
        bytes_requested = remote.cache.total_requested_bytes
        misses = remote.cache.miss_count
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / 'components.npz'
    np.savez_compressed(path, **arrays)
    report = {'doi': record['doi'], 'record_url': RECORD, 'file_id': FILE_ID, 'publisher_md5': file['computed_md5'],
              'license': record['license'], 'groups': groups, 'columns': COLUMNS,
              'components_npz_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'components_npz_bytes': path.stat().st_size, 'raw_numeric_bytes': sum(a.nbytes for a in arrays.values()),
              'array_sha256_c_order': {k: hashlib.sha256(a.tobytes()).hexdigest() for k, a in arrays.items()},
              'block_cache_requested_bytes': bytes_requested, 'block_cache_misses': misses,
              'elapsed_seconds': time.perf_counter() - start}
    (outdir / 'fetch.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outdir', type=Path)
    main(parser.parse_args().outdir)
