#!/usr/bin/env python3
"""Inspect an unfiltered, deterministic slice of the ANI-1x/1ccx v1 release."""
import hashlib
import json
import time
from urllib.request import urlopen

import fsspec
import h5py
import numpy as np

RECORD = 'https://api.figshare.com/v2/articles/10047041/versions/1'
FILE_ID = 18112775
FIELDS = ('coordinates', 'wb97x_dz.energy', 'wb97x_dz.forces', 'ccsd(t)_cbs.energy')


def inspect_group(group):
    size = group['coordinates'].shape[0]
    stop = min(256, size)
    field_stats = {}
    masks = []
    for name in FIELDS:
        dataset = group[name]
        values = dataset[:stop]
        finite = np.isfinite(values).reshape(stop, -1).all(axis=1)
        masks.append(finite)
        field_stats[name] = {
            'shape_on_disk': dataset.shape, 'dtype': dataset.dtype.str,
            'slice_sha256_c_order': hashlib.sha256(values.tobytes()).hexdigest(),
            'finite_rows': int(finite.sum()), 'all_nan_rows': int(
                np.isnan(values).reshape(stop, -1).all(axis=1).sum()),
        }
    pattern, counts = np.unique(np.stack(masks, axis=1), axis=0, return_counts=True)
    return {
        'group': group.name, 'row_interval': [0, stop], 'rows_in_group': size,
        'atomic_numbers': group['atomic_numbers'][()].tolist(),
        'keys_on_disk': sorted(group.keys()), 'fields': field_stats,
        'finite_patterns_in_field_order': [
            {'present': bits.tolist(), 'rows': int(count)}
            for bits, count in zip(pattern, counts, strict=True)
        ],
    }


def main():
    start = time.perf_counter()
    with urlopen(RECORD, timeout=30) as response:
        metadata = json.load(response)
    file = next(f for f in metadata['files'] if f['id'] == FILE_ID)
    fs = fsspec.filesystem('http', client_kwargs={'trust_env': True}, timeout=30)
    with fs.open(file['download_url'], 'rb', size=file['size'], block_size=256 * 1024,
                 cache_type='blockcache') as remote:
        with h5py.File(remote, 'r') as hdf:
            n = len(hdf)
            # Choose by HDF5 root member index before looking at label availability.
            indices = [0, n // 2, n - 1]
            groups = [inspect_group(hdf[hdf.id.get_objname_by_idx(i)]) for i in indices]
        requested = remote.cache.total_requested_bytes
        misses = remote.cache.miss_count
    print(json.dumps({
        'record': RECORD, 'doi': metadata['doi'], 'release_file': file['name'],
        'file_id': FILE_ID, 'license': metadata['license'], 'size': file['size'],
        'publisher_md5': file['computed_md5'], 'full_file_digest_verified': False,
        'root_group_count': n, 'group_indices': indices, 'fields_in_order': FIELDS,
        'groups': groups, 'block_cache_requested_bytes': requested,
        'block_cache_misses': misses, 'elapsed_seconds': time.perf_counter() - start,
        'versions': {'fsspec': fsspec.__version__, 'h5py': h5py.__version__, 'numpy': np.__version__},
    }, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
