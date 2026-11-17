#!/usr/bin/env python3
"""Repackage the measured n2 GQC installation for n5, retaining its RECORD integrity."""
import argparse
import base64
import csv
import hashlib
import importlib.metadata as metadata
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

SOURCE = '2bf3fd98da9c6cfba46ca83345e63e1d934e4780'
LIB_SHA = '67bc98a4549fe8854ed6ae65791c824024bd77a9e8e498c6891dea3b8de670c4'
INFO = 'generativeqc-0.1.0.dist-info'
WHEEL = 'generativeqc-0.1.0-py3-none-linux_x86_64.whl'


def wheel_path(installed):
    path = str(installed)
    if path == '../../../bin/generativeqc':
        return 'generativeqc-0.1.0.data/scripts/generativeqc'
    if path == '../../../bin/generativeqc-tune' or path.endswith('.pyc'):
        return None
    if path in {f'{INFO}/{key}' for key in ('INSTALLER', 'REQUESTED', 'direct_url.json', 'RECORD')}:
        return None
    if installed.parts[0] not in ('generativeqc', 'generativeqc_compiler', INFO) or '..' in installed.parts:
        raise ValueError(f'unexpected installation path {path}')
    return path


def zip_member(path, executable=False):
    info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    info.compress_type = ZIP_DEFLATED
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    started = time.monotonic()
    if os.environ.get('GQC_SOURCE_SHA') != SOURCE:
        raise ValueError('n2 runtime source declaration differs')
    dist = metadata.distribution('generativeqc')
    if dist.version != '0.1.0' or 'Tag: py3-none-linux_x86_64' not in dist.read_text('WHEEL'):
        raise ValueError('unexpected GQC distribution')
    args.destination.mkdir(exist_ok=True, parents=True)
    target = args.destination / WHEEL
    if target.exists():
        raise FileExistsError(target)
    rows = []
    with tempfile.TemporaryDirectory(dir=args.destination) as temporary:
        stage = Path(temporary) / WHEEL
        with ZipFile(stage, 'x', allowZip64=True) as package:
            for installed in sorted(dist.files, key=str):
                name = wheel_path(installed)
                if name is None:
                    continue
                if installed.hash is None or installed.hash.mode != 'sha256':
                    raise ValueError(f'missing RECORD sha256 for {name}')
                path = Path(dist.locate_file(installed))
                is_executable = bool(path.stat().st_mode & 0o111)
                md = hashlib.sha256()
                size = 0
                with path.open('rb') as source, package.open(zip_member(name, is_executable), 'w') as dest:
                    while block := source.read(4 << 20):
                        md.update(block)
                        size += len(block)
                        dest.write(block)
                encoded = base64.urlsafe_b64encode(md.digest()).rstrip(b'=').decode()
                if encoded != installed.hash.value or size != installed.size:
                    raise ValueError(f'{name}: installed bytes differ from RECORD')
                if name == 'generativeqc/lib/libgenerativeqc.so' and md.hexdigest() != LIB_SHA:
                    raise ValueError('native binary differs from CP-001')
                rows.append((name, 'sha256=' + encoded, size))
            if 'generativeqc/lib/libgenerativeqc.so' not in {r[0] for r in rows}:
                raise ValueError('missing native library')
            record = io.StringIO(newline='')
            writer = csv.writer(record, lineterminator='\n')
            writer.writerows([*rows, (f'{INFO}/RECORD', '', '')])
            package.writestr(zip_member(f'{INFO}/RECORD'), record.getvalue())
        # Create the public path exactly once, including if two operators race.
        os.link(stage, target)
    with target.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    print(json.dumps({'filename': WHEEL, 'sha256': digest, 'compressed_bytes': target.stat().st_size,
                      'record_verified_files': len(rows), 'payload_bytes': sum(row[2] for row in rows),
                      'gqc_source_declaration': SOURCE, 'libgenerativeqc_sha256': LIB_SHA,
                      'slurm_job_id': os.environ.get('SLURM_JOB_ID'),
                      'elapsed_seconds': time.monotonic() - started}, indent=2))


if __name__ == '__main__':
    main()
