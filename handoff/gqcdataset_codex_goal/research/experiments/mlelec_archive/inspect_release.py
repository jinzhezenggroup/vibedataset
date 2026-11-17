"""Verify the v1 deposit, stream an all-member index and extract only the small audit inputs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
from time import perf_counter
from urllib.request import urlopen

API = 'https://archive.materialscloud.org/api/records/4vezc-jtt98'
DOI = '10.24435/materialscloud:mg-8f'
TAR_SHA = 'df6c0894e0063a9c99ad5f94c5989f982dc7186b5476a092b32a780ad9640dfb'
BRANCH = Path('_references/mlelec_qm7')
PIN = '9c34bd9e1351770d3ac5b0887ecf0a98da317417'
KEEP = {f'dataset/scripts/{name}' for name in ('environment.yml','model_train.py','pyscf_ref_calc.py')}
KEEP |= {'dataset/data/qm7/qm7.xyz'}
KEEP |= {f'dataset/data/qm7/reference/sto-3g/{name}.hickle' for name in ('pol','dip','fock','overlap')}


def git_blobs():
    tree = subprocess.check_output(['git','-C',BRANCH,'ls-tree','-rz','--full-tree',PIN])
    by_blob = {}
    for item in tree.split(b'\0'):
        if item:
            info, path = item.split(b'\t', 1)
            _, kind, oid = info.split()
            if kind == b'blob':
                by_blob.setdefault(oid.decode(), []).append(path.decode())
    return by_blob


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--record',type=Path,help='use a local copy of the official metadata')
    ap.add_argument('--archive',type=Path,required=True,help='existing tar.xz, or new download destination')
    ap.add_argument('--output',type=Path,required=True,help='fresh directory')
    ap.add_argument('--download',action='store_true',help='fetch the official archive when absent')
    args = ap.parse_args()
    start = perf_counter()
    if args.record:
        metadata = json.loads(args.record.read_bytes())
    else:
        with urlopen(API,timeout=40) as response:
            metadata = json.load(response)
    assert metadata['pids']['doi']['identifier'] == DOI
    assert metadata['versions']['index'] == 1
    entry = metadata['files']['entries']['dataset.tar.xz']
    if not args.archive.exists() and args.download:
        args.archive.parent.mkdir(parents=True,exist_ok=True)
        with urlopen(entry['links']['content'],timeout=60) as response, args.archive.open('xb') as dest:
            shutil.copyfileobj(response,dest,length=4*1024**2)
    if args.archive.stat().st_size != entry['size']:
        raise ValueError('incomplete v1 archive')
    sha,md5=hashlib.sha256(),hashlib.md5()
    with args.archive.open('rb') as handle:
        for data in iter(lambda:handle.read(4*1024**2),b''):
            sha.update(data)
            md5.update(data)
    if sha.hexdigest()!=TAR_SHA or 'md5:'+md5.hexdigest()!=entry['checksum']:
        raise ValueError('archive checksum does not match v1')
    blobs=git_blobs()
    args.output.mkdir(parents=True,exist_ok=False)
    members=[]
    source_rows=[]
    with tarfile.open(args.archive,'r|xz') as archive:
        seen=set()
        for member in archive:
            name=PurePosixPath(member.name)
            if str(name) in seen or name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()):
                raise ValueError('unexpected v1 tar element')
            seen.add(str(name))
            row={'name':str(name),'bytes':member.size,'type':member.type.decode()}
            if member.isfile():
                digest=hashlib.sha256()
                blob=hashlib.sha1(f'blob {member.size}\0'.encode())
                keep=str(name) in KEEP
                sink=None
                if keep:
                    target=args.output/'members'/name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    sink=target.open('xb')
                try:
                    with archive.extractfile(member) as stream:
                        for data in iter(lambda:stream.read(2*1024**2),b''):
                            digest.update(data)
                            blob.update(data)
                            if sink:
                                sink.write(data)
                finally:
                    if sink:
                        sink.close()
                row['sha256']=digest.hexdigest()
                if ('scripts' in name.parts or name.suffix in {'.py','.ipynb','.yml','.yaml','.sh','.md','.toml'}
                        or 'license' in name.name.lower()):
                    source_rows.append(dict(row,git_blob=blob.hexdigest(),identical_in_qm7=blobs.get(blob.hexdigest(),[])))
            members.append(row)
    missing=KEEP-seen
    if missing:
        raise ValueError(f'missing expected v1 input files: {sorted(missing)}')
    raw=(json.dumps(members,separators=(',',':'))+'\n').encode()
    packed=gzip.compress(raw,mtime=0)
    (args.output/'members.json.gz').write_bytes(packed)
    summary=dict(doi=DOI,version=1,archive_url=entry['links']['content'],
                 publication_date=metadata['metadata']['publication_date'],
                 rights=metadata['metadata']['rights'],related_identifiers=metadata['metadata']['related_identifiers'],
                 creators=[author['person_or_org']['name'] for author in metadata['metadata']['creators']],
                 archive_bytes=entry['size'],md5=md5.hexdigest(),sha256=sha.hexdigest(),
                 paper_branch_commit=PIN,paper_branch_tree=subprocess.check_output(['git','-C',BRANCH,'rev-parse',PIN+'^{tree}'],text=True).strip(),
                 regular_files=sum(row['type']=='0' for row in members),directories=sum(row['type']=='5' for row in members),
                 total_file_bytes=sum(row['bytes'] for row in members),member_index_uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
                 member_index_gzip_sha256=hashlib.sha256(packed).hexdigest(),source_members=source_rows,
                 elapsed_seconds=perf_counter()-start)
    (args.output/'release.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')


if __name__=='__main__':
    main()
