#!/usr/bin/env python3
"""Verify official QM9 members and select the predeclared lowest-ID strata."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import time
from urllib.request import urlopen

API = 'https://api.figshare.com/v2'
ARCHIVE = 'dsgdb9nsd.xyz.tar.bz2'
MEMBERS = [(1057646, 2, 3195389, ARCHIVE, 'ad1ebd51ee7f5b3a6e32e974e5d54012'),
           (1057641, 1, 3195392, 'readme.txt', 'c6581a03f673746528c57acfc6b79679'),
           (1057644, 1, 3195404, 'uncharacterized.txt', 'a361887bacb427b8a0ce7903d92a53b4')]
BOHR_ANGSTROM = 0.529177210903
STRATA = [f'{size}/{element}' for size in ('1-2', '3') for element in ('F', 'O', 'N', 'CH')]


def cached(folder, name, url):
    dst = folder / name
    if not dst.exists():
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                with urlopen(url, timeout=90) as response:
                    shutil.copyfileobj(response, tmp, 1 << 20)
            except Exception:
                tmp_path.unlink()
                raise
        tmp_path.replace(dst)
    return dst


def load_metadata(path):
    return json.loads(path.read_bytes())


def source_receipt(cache):
    collection = load_metadata(cached(cache, 'collection-v5.json', API + '/collections/978904/versions/5'))
    members = load_metadata(cached(cache, 'collection-members.json', API + '/collections/978904/articles'))
    notices = []
    ids = {item['id'] for item in members}
    for article, version, file_id, name, md5 in MEMBERS:
        url = f'{API}/articles/{article}/versions/{version}'
        meta = load_metadata(cached(cache, f'article-{article}-v{version}.json', url))
        file = next(f for f in meta['files'] if f['id'] == file_id)
        if (article not in ids or meta['id'] != article or meta['version'] != version or file['name'] != name
                or file['computed_md5'] != md5 or meta['license']['name'] != 'CC0'):
            raise ValueError(f'metadata mismatch for {name}')
        data = cached(cache, name, file['download_url']).read_bytes()
        if len(data) != file['size'] or hashlib.md5(data).hexdigest() != md5:
            raise ValueError(f'size/digest mismatch for {name}')
        notices.append({'article_id': article, 'article_version': version, 'title': meta['title'], 'doi': meta['doi'],
                        'license': meta['license'], 'metadata_url': url, 'file_id': file_id, 'published': meta['published_date'],
                        'name': name, 'download_url': file['download_url'], 'observed_size': len(data),
                        'verified_publisher_md5': md5, 'sha256': hashlib.sha256(data).hexdigest()})
    return {'collection_id': collection['id'], 'collection_version': collection['version'],
            'collection_doi': collection['doi'], 'membership_observed_url': API + '/collections/978904/articles',
            'verified_members': notices}


def scan(cache):
    flags = {int(m.group(1)) for m in re.finditer(r'^\s*(\d+)\s+\S+', (cache/'uncharacterized.txt').read_text(), re.M)}
    if len(flags) != 3054:
        raise ValueError('unexpected count of publisher geometry flags')
    selected, eligible, failed, skipped = {}, {s: [] for s in STRATA}, [], Counter()
    seen = set()
    with tarfile.open(cache / ARCHIVE, 'r|bz2') as archive:
        for member in archive:
            if not member.isfile():
                continue
            try:
                match = re.fullmatch(r'dsgdb9nsd_(\d{6})\.xyz', member.name)
                if not match:
                    raise ValueError('unexpected archive member')
                number = int(match.group(1))
                if number in seen:
                    raise ValueError('duplicate gdb id')
                seen.add(number)
                raw = archive.extractfile(member).read()
                lines = raw.decode('ascii').splitlines()
                count = int(lines[0])
                if lines[1].split()[:2] != ['gdb', str(number)] or len(lines) < count + 2:
                    raise ValueError('header/member mismatch')
                atom_rows = [s.split() for s in lines[2:2+count]]
                symbols = [a[0] for a in atom_rows]
                if not symbols or not set(symbols) <= {'C', 'H', 'O', 'N', 'F'}:
                    raise ValueError('unknown element or empty molecule')
                heavy = sum(s != 'H' for s in symbols)
                if heavy not in (1, 2, 3):
                    skipped[str(heavy)] += 1
                    continue
                cls = next((s for s in ('F', 'O', 'N') if s in symbols), 'CH')
                key = ('3' if heavy == 3 else '1-2') + '/' + cls
                eligible[key].append(number)
                coords = [[float(tok.replace('*^', 'e')) for tok in a[1:4]] for a in atom_rows]
                if any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in coords):
                    raise ValueError('nonfinite or incomplete coordinates')
                if key not in selected or number < selected[key]['qm9_id']:
                    selected[key] = {'qm9_id': number, 'name': f'qm9-{number:06d}',
                                     'member': member.name, 'member_sha256': hashlib.sha256(raw).hexdigest(),
                                     'member_bytes': len(raw), 'symbols': symbols,
                                     'coordinates_angstrom': coords, 'coordinates_bohr': [
                                     [x / BOHR_ANGSTROM for x in v] for v in coords],
                                     'source_geometry_disagreement_flag': number in flags, 'n_heavy': heavy}
            except (ValueError, UnicodeError, IndexError) as exc:
                failed.append({'member': member.name, 'error': str(exc)})
    if len(seen) != 133885 or seen != set(range(1,133886)):
        raise ValueError('archive IDs do not cover the published 133885 members')
    rows = []
    for key in STRATA:
        ids = sorted(eligible[key])
        if ids and (key not in selected or selected[key]['qm9_id'] != ids[0]):
            raise ValueError('lowest-ID eligible input is invalid; do not substitute')
        rows.append({'stratum': key, 'eligible_ids': ids,
                     'eligible_flagged_ids': sorted(flags.intersection(ids)), 'selected': selected.get(key)})
    return {'family_count':len(seen), 'ineligible_counts_by_nheavy':dict(skipped),
            'parse_failures':failed, 'bohr_angstrom':BOHR_ANGSTROM, 'strata':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    t = time.perf_counter()
    args.cache.mkdir(exist_ok=True, parents=True)
    receipt = source_receipt(args.cache)
    t_scan = time.perf_counter()
    report = scan(args.cache)
    report.update(source=receipt, checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  cached_source_validation_seconds=t_scan - t, decompression_and_selection_seconds=time.perf_counter()-t_scan)
    args.out.parent.mkdir(exist_ok=True, parents=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
