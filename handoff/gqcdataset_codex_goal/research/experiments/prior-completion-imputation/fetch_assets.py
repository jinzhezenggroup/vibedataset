"""Obtain the first released checkpoint and a bounded data excerpt from Zenodo 17519032."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import tarfile
from time import perf_counter
from urllib.request import Request, urlopen

RECORD = 'https://zenodo.org/api/records/17519032'
ARCHIVES = {
    'random_drop_prop2prop_checkpoints.tar.gz': (88 * 1024**2, 'random_drop_prop2prop_zenodo/model_random_drop_8_cp_overall.pt'),
    'struct_prop_comparison.tar.gz': (131072, 'zenodo/large_property_combined.csv'),
}


class ReadCounter:
    def __init__(self, response, limit):
        self.response = response
        self.limit = limit
        self.count = 0

    def read(self, n):
        data = self.response.read(min(n, self.limit - self.count))
        self.count += len(data)
        return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='new directory for local research assets')
    output = parser.parse_args().directory
    output.mkdir(parents=True, exist_ok=False)
    started = perf_counter()
    with urlopen(RECORD, timeout=30) as response:
        meta = json.load(response)
    files = {f['key']: f for f in meta['files']}
    reads = []
    for key, (bound, member) in ARCHIVES.items():
        f = files[key]
        request = Request(f['links']['self'], headers={'Range': f'bytes=0-{bound-1}', 'Accept-Encoding': 'identity'})
        with urlopen(request, timeout=60) as response:
            expected = f"bytes 0-{bound-1}/{f['size']}"
            if response.status != 206 or response.headers.get('Content-Range') != expected:
                raise ValueError('server did not confirm the bounded range')
            counter = ReadCounter(response, bound)
            with tarfile.open(fileobj=counter, mode='r|gz') as stream:
                entry = next(e for e in stream if e.isfile())
                if entry.name != member:
                    raise ValueError('unexpected release layout')
                extracted = stream.extractfile(entry)
                if member.endswith('.csv'):
                    data = b''.join(extracted.readline() for _ in range(33))
                    rows = list(csv.reader(io.StringIO(data.decode())))
                    if len(rows) != 33 or any(len(row) != len(rows[0]) for row in rows):
                        raise ValueError('partial CSV row')
                    (output / 'sample.csv').write_bytes(data)
                else:
                    data = extracted.read()
                    if len(data) != entry.size:
                        raise ValueError('incomplete checkpoint')
                    (output / 'model.pt').write_bytes(data)
        reads.append(dict(archive=key, archive_bytes=f['size'], publisher_checksum=f['checksum'],
                          full_archive_verified=False, member=member, response_bytes_read=counter.count,
                          retained_bytes=len(data), retained_sha256=hashlib.sha256(data).hexdigest()))
    (output / 'manifest.json').write_text(json.dumps(dict(
        record=RECORD, doi=meta['doi'], license=meta['metadata']['license']['id'], reads=reads,
        elapsed_seconds=perf_counter() - started), indent=2)+'\n')


if __name__ == '__main__':
    main()
