"""Inspect pinned local sources, the whole official QM9 member archive, and saved QCArchive responses."""
import argparse
import ast
from collections import Counter
import gzip
from hashlib import sha256
import json
import lzma
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
from inspect_qcschema_assets import DIRECTORY, PIN, summarize

WATER_PIN = 'c7e355fd22eb0b66c2135f21601c5ea0709ac6c2'
PSI_PIN = 'f2492db10de56b30b188239bdc6b4cfbc4a23bd5'
DATA_SERVER = 'https://api.qcarchive.molssi.org/api/v1/'


def read(path):
    return json.loads(path.read_bytes())


def digest(data):
    return sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pinned(repo, commit):
    def git(*args):
        return subprocess.check_output(['git', '-C', repo, *args], text=True).strip()
    require(git('rev-parse','HEAD') == commit and not git('status','--porcelain'), f'unexpected source tree {repo}')
    return {'commit': commit, 'tree':git('rev-parse','HEAD^{tree}')}


def qm9(path):
    seed, extra = (read(EXP / name / 'cohort.json') for name in ('qm9_response_assets','qm9_extension'))
    expected = {r['selected']['qm9_id']:r['selected'] for cohort in (seed,extra)
                for r in cohort['strata'] if r['selected']}
    require(len(expected) == 17, 'unexpected QM9 candidate set')
    release = {r['name']:r for r in seed['source']['verified_members']}
    archive = path / 'dsgdb9nsd.xyz.tar.bz2'
    for p in (archive, path / 'readme.txt'):
        require(digest(p.read_bytes()) == release[p.name]['sha256'], f'QM9 checksum {p.name}')
    header, atoms, tail = Counter(),Counter(),Counter()
    matched, samples, seen = {}, {}, set()
    byte_count = 0
    with tarfile.open(archive, 'r|bz2') as tar:
        for member in tar:
            require(member.isfile() and re.fullmatch(r'dsgdb9nsd_[0-9]{6}\.xyz', member.name),
                    f'unexpected QM9 member {member.name}')
            data = tar.extractfile(member).read()
            lines = data.decode('ascii').splitlines()
            natom = int(lines[0]); props = lines[1].split(); idx = int(props[1])
            require(member.name == f'dsgdb9nsd_{idx:06d}.xyz' and idx not in seen and props[0] == 'gdb', member.name)
            seen.add(idx)
            byte_count += len(data)
            header[len(props)] += 1
            tail[len(lines) - natom - 2] += 1
            rows = [line.split() for line in lines[2:2+natom]]
            atoms.update(map(len, rows))
            if idx in expected:
                e = expected[idx]
                samples[member.name] = data.decode('ascii')
                xyz = [[float(x.replace('*^','e')) for x in row[1:4]] for row in rows]
                require(digest(data) == e['member_sha256'] and [r[0] for r in rows] == e['symbols']
                        and xyz == e['coordinates_angstrom'], 'QM9 cohort identity')
                matched[e['name']] = {'member': member.name, 'sha256':digest(data),
                    'first_atom':rows[0][0], 'net_Mulliken_charge_e':rows[0][4],
                    'isotropic_polarizability_bohr3':props[6], 'electronic_extent_bohr2':props[10]}
    require(len(seen)==133885 and len(matched)==17, 'QM9 source denominator')
    return {'readme_ascii':(path/'readme.txt').read_text(), 'members_ascii_for_geometry_matches':samples, 'release':{n:{k:release[n][k] for k in ('metadata_url','download_url','sha256','verified_publisher_md5','license','observed_size')}
                       for n in (archive.name,'readme.txt')},
            'members':len(seen), 'member_payload_bytes':byte_count, 'header_widths':dict(header),
            'atom_row_widths':dict(atoms), 'footer_line_counts':dict(tail), 'matched_targets_geometry_only':matched}


def fixture_records(repo):
    info = pinned(repo, PIN)
    records = []
    for p in sorted((repo/DIRECTORY).glob('*.json.xz')):
        if not p.name.startswith(('sp_', 'error_')):
            continue
        row = summarize(repo, p)
        raw = read_xz(p)['result']
        extras = raw.get('extras') or {}
        records.append({k:row[k] for k in ('path','compressed_bytes','compressed_sha256','input_geometry_sha256',
                'molecule','driver','model','requested_protocols','success','failure_evidence','populated_properties')} |
                       {'wavefunction_arrays':sorted(row['wavefunction_arrays']), 'extra_keys':sorted(extras),
                        'extra_qcvars':sorted((extras.get('qcvars') or {}).keys())})
    require(len(records)==13, 'QCFractal snapshot denominator')
    return dict(**info, records=records)


def read_xz(path):
    return json.loads(lzma.decompress(path.read_bytes()))


def psi4(repo):
    info = pinned(repo, PSI_PIN)
    files={}
    for folder in ('scf-response1','scf-response2','scf-response3'):
        base = repo/'tests'/folder
        for p in sorted(base.iterdir()):
            if p.name not in ('input.dat','output.ref'):
                continue
            raw = p.read_bytes()
            data = raw.decode()
            blocks = {}
            if p.name == 'output.ref':
                lines = data.splitlines()
                for i,line in enumerate(lines):
                    match = re.fullmatch(r'\s*=>\s*((?:Traceless )?(?:Dipole|Quadrupole) Polarizabilities)\s*<=\s*',line,re.I)
                    if match:
                        axes = lines[i+2].split()
                        k = len(axes)
                        matrix = [r.split() for r in lines[i+4:i+4+k]]
                        require([r[0] for r in matrix] == axes and all(len(r)==1+k for r in matrix), 'Psi4 response block')
                        blocks[match[1].lower()]={'readout_and_perturbation_axes':axes, 'first_diagonal':matrix[0][1]}
            files[str(p.relative_to(repo))]={'bytes':len(raw),'sha256':digest(raw),'response_blocks':blocks}
    impl = Path('psi4/driver/procrouting/response/scf_response.py')
    raw = (repo/impl).read_bytes()
    files[str(impl)]={'bytes':len(raw),'sha256':digest(raw),'symbols':['cpscf_linear_response','_print_matrix']}
    return dict(**info, files=files)


def water_tables(repo):
    info=pinned(repo,WATER_PIN)
    entries = subprocess.check_output(['git','-C',repo,'ls-tree','--full-tree','-r','-z','HEAD']).split(b'\0')
    files,types,shapes = [],Counter(),Counter()
    total_values, nonfinite, mixed = 0,0,[]
    for entry in entries:
        if not entry:
            continue
        git, name = entry.split(b'\t'); name=name.decode()
        mode,kind,oid=git.decode().split()
        require(kind=='blob','unexpected submodule')
        raw=(repo/name).read_bytes()
        require(not raw.startswith(b'version https://git-lfs.github.com/spec'), 'unhydrated LFS artifact')
        files.append((name,oid,len(raw),digest(raw),mode))
        if not name.endswith('.npy'):
            continue
        require(raw[:8]==b'\x93NUMPY\x01\x00', 'unrecognized array header')
        n = struct.unpack('<H',raw[8:10])[0]
        sky=ast.literal_eval(raw[10:10+n].decode('ascii'))
        require(sky['descr']=='<f8' and not sky['fortran_order'] and len(raw)==10+n+8*math.prod(sky['shape']),
                'unexpected surface data layout')
        shape=sky['shape']; shapes[str(shape)]+=1
        values=[x for x, in struct.iter_unpack('<d',raw[10+n:])]
        total_values+=len(values); nonfinite+=sum(not math.isfinite(v) for v in values)
        basename=Path(name).stem.split('_',1)[1]
        method=Path(name).parent.name
        if basename.startswith('p'):
            a,b=basename[1:].split('_'); family=a[0]+'-'+b[0]
            if family=='1-2' and name.endswith('/O_p10_20.npy'):
                # Grid angle=105 degrees, mean OH=0.96 angstrom and bond-length difference=0.
                mixed.append({'path':name,'grid_indices':[9,3,0], 'surface_value':values[(9*shape[1]+3)*shape[2]]})
        else:
            family='static'
        types[method+'/'+family]+=1
    require(len(files)==218 and len(mixed)==2, 'water surface tree or mixed readout changed')
    return dict(**info, files=len(files), paths_blob_bytes_sha256_mode=files, units_documented_by_consumer={
        'internal_angle':'degree','mean_and_difference_OH':'angstrom','polarizability_output':'native rank/component labels; no explicit scalar unit in get_dp'},
        shapes=dict(shapes), scalar_entries=total_values, nonfinite_entries=nonfinite, files_by_method_and_rank=dict(types),
        mixed_grid_example=mixed, source_license_files=[r[0] for r in files if 'license' in r[0].lower()])


def qcarchive(directory):
    members=read(directory/'ds-membership.json')
    catalogue=read(directory/'datasets.json')
    stamp=read(directory/'information.json')
    records=[]
    for path in sorted(directory.glob('record-*.json')):
        record=read(path); ident=record['id']; molecule=read(directory/f'molecule-{record["molecule_id"]}.json')
        props=record['properties']
        records.append({'record_id':ident,'record_url':DATA_SERVER+'records/singlepoint/'+str(ident),
            'dataset_memberships':[r['dataset_id'] for r in members if r['record_id']==ident],
            'specification':record['specification'],'state':record['status'],
            'created_on':record['created_on'],'modified_on':record['modified_on'],
            'archive_property_keys':sorted(props),'result_extra_keys':sorted(record['extras']),
            'example_zero_field_properties': {k:props[k][:3] for k in ('scf dipole','mulliken charges') if k in props},
            'molecule_id':molecule['id'], 'ordered_geometry_sha256':digest(canonical([molecule['symbols'],molecule['geometry']])),
            'natoms':len(molecule['symbols']),'elements':sorted(set(molecule['symbols'])),
            'charge':molecule['molecular_charge'],'multiplicity':molecule['molecular_multiplicity'],
            'wavefunction_metadata':read(directory/f'wave-{ident}.json')})
    qmeta=read(directory/'ds347.json')
    require(len(records)==9 and sorted(r['record_id'] for r in records)==sorted(
        read(directory/'hfsto.json')+read(directory/'selected347.json')), 'QCArchive selection')
    stored = {p.name:{'bytes':p.stat().st_size,'sha256':digest(p.read_bytes())} for p in sorted(directory.iterdir())
              if p.suffix in ('.json','.msgpack') and (p.name in ('ds-membership.json','information.json','datasets.json',
                'ds347.json','hfprops.json','hfsto.json','selected347.json','wfn-96510996.msgpack')
                or p.name.startswith(('molecule-','wave-','record-')))}
    return {'server':stamp['name'],'version':stamp['version'],'dataset_catalogue_size':len(catalogue),
            'dataset_types':Counter(r['dataset_type'] for r in catalogue),'global_hf_sto3g_properties_query':read(directory/'hfprops.json'),
            'dataset_347':{k:qmeta[k] for k in ('id','name','tagline')},'dataset_347_metadata_keys':sorted(qmeta['metadata']),
            'snapshot_files':stored,'snapshot_bytes':sum(v['bytes'] for v in stored.values()), 'records':records}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for tag in ('qm9','references','water','qca','out'):
        parser.add_argument('--'+tag,type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    results, clocks = {}, {}
    for tag, fn, path in [('qm9',qm9,args.qm9),('qcfractal_fixtures',fixture_records,args.references/'qcfractal'),
                          ('psi4',psi4,args.references/'psi4_1_10'),('water',water_tables,args.water),('qcarchive',qcarchive,args.qca)]:
        start=time.perf_counter()
        results[tag]=fn(path)
        clocks[tag]=time.perf_counter()-start
    output=canonical(results)
    (args.out/'assets.json.gz').write_bytes(gzip.compress(output,mtime=0))
    (args.out/'inspection.json').write_text(json.dumps({'report_uncompressed_sha256':digest(output),
        'report_uncompressed_bytes':len(output),'seconds_by_source':clocks,'argv':sys.argv, 'python':sys.version},
        sort_keys=True,indent=2)+'\n')
    previous=HERE/'assets.json.gz'
    if previous.exists():
        require(gzip.decompress(previous.read_bytes()) == output,'source content differs from committed inspection')
    print(json.dumps(clocks,sort_keys=True))


if __name__=='__main__':
    main()
