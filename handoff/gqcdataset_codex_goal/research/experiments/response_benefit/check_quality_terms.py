"""Apply #14's hardened operand schema to every measured scalar subtraction."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from verify import HERE, sha, verify

PIN = 'd158cfd94a8c7e8d5749d2f9d18ac830671865e7'
DIGEST = '0c596864ea7f2ff9acf788c20b12a269ada32aa06a7a4555bbdaf151d0914dec'
ROOT = HERE.parents[4]


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='exact file from the pinned quality commit')
    args = parser.parse_args()
    raw = args.source.read_bytes() if args.source else subprocess.check_output(
        ['git','show',PIN + ':scripts/target_response_quality.py'], cwd=ROOT)
    if sha(raw) != DIGEST:
        raise ValueError('quality evidence source digest')
    sys.path.insert(0, str(ROOT/'scripts'))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/'quality.py'
        path.write_bytes(raw)
        spec = importlib.util.spec_from_file_location('reviewed_quality_evidence', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        counts = Counter()
        def check(terms):
            counts['combinations'] += 1
            counts['terms'] += len(terms)
            return module.linear_combination(terms)
        verify(HERE/'evidence', calibrator=check)
        print(json.dumps(dict(quality_commit=PIN, sha256=DIGEST, **counts),sort_keys=True))


if __name__ == '__main__':
    main()
