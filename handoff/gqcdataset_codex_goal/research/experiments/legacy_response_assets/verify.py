"""Offline checks for audited legacy files, complete denominators, and their exclusion evidence."""
from collections import Counter
import gzip
from hashlib import sha1, sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


def load(path):
    return json.loads(path.read_bytes())


def tree_oid(files):
    # Reconstruct the source's Git tree from all published regular blob IDs.
    tree = {}
    for name, blob, _, _, mode in files:
        parent = tree
        parts = name.split('/')
        for part in parts[:-1]:
            parent = parent.setdefault(part, {})
        assert parts[-1] not in parent
        parent[parts[-1]] = (mode.encode(), bytes.fromhex(blob))
    def encode(items):
        entries = []
        for name, entry in items.items():
            directory = isinstance(entry,dict)
            mode = b'40000' if directory else entry[0]
            rawname = name.encode()
            order = rawname + (b'/' if directory else b'')
            entries.append((order, mode + b' ' + rawname + b'\0' + (encode(entry) if directory else entry[1])))
        content = b''.join(value for _,value in sorted(entries))
        return sha1(b'tree ' + str(len(content)).encode() + b'\0' + content).digest()
    return encode(tree).hex()


def main():
    if not __debug__:
        raise RuntimeError('run the evidence checks without Python optimization')
    raw=gzip.decompress((HERE/'assets.json.gz').read_bytes())
    assert sha256(raw).hexdigest()==load(HERE/'inspection.json')['report_uncompressed_sha256']
    data=json.loads(raw)
    qm=data['qm9']
    release=load(EXP/'qm9_response_assets/cohort.json')['source']['verified_members']
    assert all(any(r['sha256']==source['sha256'] and r['observed_size']==source['observed_size']
                   for r in release) for source in qm['release'].values())
    assert qm['members']==133885 and qm['header_widths']=={'17':133885} and qm['atom_row_widths']=={'5':2407753}
    assert qm['footer_line_counts']=={'3':133885}
    raw_readme=qm['readme_ascii'].encode('ascii')
    assert sha256(raw_readme).hexdigest()==qm['release']['readme.txt']['sha256']
    assert all(s in raw_readme for s in (b'Mulliken partial charge (e)', b'Electronic spatial extent',
                                         b'Isotropic polarizability', b'DFT/B3LYP/6-31G(2df,p)'))
    samples=qm['matched_targets_geometry_only']
    chosen={t['selected']['name']:t['selected'] for batch in ('qm9_extension','qm9_response_assets')
            for t in load(EXP/batch/'cohort.json')['strata'] if t['selected']}
    assert len(samples)==len(chosen)==len(qm['members_ascii_for_geometry_matches'])==17
    for name,expected in chosen.items():
        sample=samples[name]
        member=qm['members_ascii_for_geometry_matches'][sample['member']]
        assert sha256(member.encode('ascii')).hexdigest()==sample['sha256']==expected['member_sha256']
        lines=member.splitlines()
        n=int(lines[0]); params=lines[1].split()
        assert len(params)==17 and len(lines)==n+5 and params[:2]==['gdb',str(expected['qm9_id'])]
        atoms=[l.split() for l in lines[2:2+n]]
        assert [a[0] for a in atoms]==expected['symbols']
        assert [[float(x.replace('*^','e')) for x in a[1:4]] for a in atoms]==expected['coordinates_angstrom']
        assert (atoms[0][4],params[6],params[10])==(sample['net_Mulliken_charge_e'],sample['isotropic_polarizability_bohr3'],
                                                   sample['electronic_extent_bohr2'])
    fixtures=data['qcfractal_fixtures']['records']
    prior=load(EXP.parent/'assets/qcfractal-singlepoints.json')
    assert len(fixtures)==len(prior['records'])==13
    for f, ref in zip(fixtures,prior['records'],strict=True):
        assert all(f[k]==ref[k] for k in ('path','compressed_sha256','model','populated_properties','failure_evidence'))
        assert f['wavefunction_arrays']==sorted(ref['wavefunction_arrays'])
    assert sum(f['success'] for f in fixtures)==11 and sum(bool(f['wavefunction_arrays']) for f in fixtures)==3
    block=data['psi4']['files']['tests/scf-response1/output.ref']['response_blocks']
    assert block['dipole polarizabilities']['readout_and_perturbation_axes']==list('XYZ')
    for name in ('quadrupole polarizabilities','traceless quadrupole polarizabilities'):
        assert block[name]['readout_and_perturbation_axes']==['XX','XY','XZ','YY','YZ','ZZ']
    water=data['water']
    assert tree_oid(water['paths_blob_bytes_sha256_mode'])==water['tree']=='7591714551d82c8eb29153c0fe14ce8e0d79c3fa'
    assert water['files']==218 and water['scalar_entries']==384912 and water['nonfinite_entries']==0
    assert water['files_by_method_and_rank']['hf_avtz/1-2']==water['files_by_method_and_rank']['dft_avtz/1-2']==24
    run=load(HERE/'consumers.json')
    for r in run['water_consumer']:
        grid=next(v for v in water['mixed_grid_example'] if v['path']==f"H2O/{r['method']}/O_p10_20.npy")
        assert r['raw_O_p10_20']==grid['surface_value'] and r['formatted_O_p10_20']==round(grid['surface_value'],5)
        assert r['absolute_rounding_difference']==abs(r['raw_O_p10_20']-r['formatted_O_p10_20'])>1e-8
        assert r['opened_npy_files']==63 and r['logical_input_bytes']==906192
    qc=data['qcarchive']; status=Counter()
    assert qc['dataset_catalogue_size']==214 and qc['dataset_types']['singlepoint']==41
    assert qc['global_hf_sto3g_properties_query']==[]
    for r in qc['records']:
        spec=r['specification']; keys=r['archive_property_keys']
        if spec['basis']=='sto-3g':
            assert spec['method']=='hf' and spec['keywords']['reference']=='rohf' and spec['driver']=='gradient'
            assert 'mulliken charges' in keys and r['natoms']==121 and r['wavefunction_metadata'] is None
            status['HF_STO3G_gradient']+=1
        else:
            assert r['dataset_memberships']==[347] and spec['basis']=='6-31g*' and spec['driver']=='energy'
            assert r['wavefunction_metadata']=={'compression_type':'zstd'}
            status['OpenFF_347_energy']+=1
    assert status=={'HF_STO3G_gradient':6,'OpenFF_347_energy':3}
    wf=run['qcarchive_ground_state']
    assert wf['sha256']==qc['snapshot_files']['wfn-96510996.msgpack']['sha256']
    assert wf['restricted'] and wf['alpha_coefficients']==wf['alpha_eigenvalues']**2==159**2
    print(json.dumps({'official_QM9_members':qm['members'],'matched_QM9_geometries':len(samples),
          'singlepoint_fixtures':len(fixtures),'production_records':status,'water_surface_tree':water['tree'],
          'matched_v2_operands':0,'consumer_request_streams_for_v2':0},sort_keys=True))


if __name__=='__main__':
    main()
