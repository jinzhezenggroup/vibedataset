"""Package the original PLAN-004 files, or verify the retained evidence without a QC installation."""
from collections import defaultdict
import argparse
import csv
import gzip
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import struct
import sys
import tarfile

AXES = ('x', 'y', 'z')
OBS = ('q0', 'r2', 'zz')
POLICIES = ('ordinary','split_xyz','blocked_xyz','blocked_support','keep_history_vectors')
MODES = ('strict','diagnostic')
COUNTS = ('jk_calls','rhs_columns','solver_actions','cache_validation_actions','cache_rejections')
HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pretty(obj):
    return (json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()


def events(path):
    with gzip.open(path,'rt') as f:
        return [json.loads(line) for line in f]


def collect_journals(root):
    return b''.join(f.read_bytes() for f in sorted(root.glob('sources/*/operations.jsonl')))


def pack_assets(work, dest):
    with dest.open('xb') as output, gzip.GzipFile(fileobj=output,mode='wb',mtime=0,filename='') as gz:
        with tarfile.open(fileobj=gz,mode='w|',format=tarfile.USTAR_FORMAT) as tar:
            paths=sorted(work.glob('sources/*/assets/**/*.json'))
            for path in paths:
                data=path.read_bytes()
                info=tarfile.TarInfo(path.relative_to(work/'sources').as_posix())
                info.size=len(data)
                tar.addfile(info,io.BytesIO(data))


def pairs(rows):
    grouped=defaultdict(list)
    for r in rows:
        grouped[r['source']].append(r)
    completed,failed=[],[]
    for name,records in grouped.items():
        require(len(records)%2==0,'orphan event')
        for index,(begin,end) in enumerate(zip(records[::2],records[1::2]),1):
            require(begin['event']=='started' and end['event'] in ('completed','failed'),'invalid journal order')
            require(begin['sequence']==end['sequence']==index,'invalid journal sequence')
            require(all(begin.get(k)==end.get(k) for k in ('phase','mode','policy','mask','source')),'mispaired event')
            (completed if end['event']=='completed' else failed).append(end)
    return completed,failed


def pilot_receipt(root, rows):
    completed,failed=pairs(rows)
    phase={}
    for op in ('setup','history','completion'):
        batch=[r for r in completed if r['phase']==op]
        counts=[r['setup']['counts'] if op=='setup' else r['counts'] for r in batch]
        phase[op]={'completed':len(batch),'observed_jk':sum(c['jk_calls'] for c in counts),
                   'observed_rhs':sum(c.get('rhs_columns',0) for c in counts),'operation_seconds':sum(r['seconds'] for r in batch)}
    return {'source_metadata':json.loads((root/'protocol.json').read_bytes()),'phase_counts':phase,
            'failed_calls':failed,'total_observed_completed_jk':sum(x['observed_jk'] for x in phase.values()),
            'total_observed_completed_rhs':sum(x['observed_rhs'] for x in phase.values()),
            'reason':'The isolated first checkout had the old run_round signature. The first attempt to bind the mixed-column keyword failed before entering that physical call.',
            'final_cohort_use':False}


def scalar_key(row):
    return row['field'],row['observable']


def costs(row,history):
    outputs=row['results']
    residuals=[v for b in row['blocks'] for v in b['stats']['residuals'].values()]
    residuals.extend(c['true_residual'] for b in row['blocks'] for c in b['cache_checks'] if c['true_residual'] is not None)
    support=row['relation'].get('support')
    if support is None:
        support=list(AXES) if row['relation'].get('used') else []
    return {'source':row['source'],'mask':row['mask'],'mode':row['mode'],'policy':row['policy'],
        'history_qualified_or_admitted':row['available_old_scalars'],'targets':len(outputs),
        'public_qualified':sum(r['qualified'] is True for r in outputs),
        'independent_passed':sum(r['qualified'] is True for r in (row['independent_checks_of_diagnostics'] or outputs)),
        'mixed_support':''.join(support),'physical_blocks':sum(b['counts']['rhs_columns']>0 for b in row['blocks']),
        'new_rhs':row['counts']['rhs_columns'],'new_jk':row['counts']['jk_calls'],
        'new_solver_actions':row['counts']['solver_actions'],'new_vector_check_actions':row['counts']['cache_validation_actions'],
        'history_rhs':row['history_rhs'],'history_jk':row['history_jk'],'setup_jk':row['source_setup_jk'],
        'cumulative_rhs':row['cumulative_rhs'],'cumulative_jk':row['cumulative_jk'],
        'cumulative_jk_with_setup':row['cumulative_jk_including_setup'],
        'history_scalar_bytes':row['history_scalar_bytes'],'history_vector_bytes':row['history_vector_bytes'],
        'completion_input_bytes':row['asset_read_bytes'],'completion_output_bytes':row['second_asset']['bytes'],
        'worst_true_residual':max(residuals,default=0.),'maximum_difference_from_ordinary':row['max_difference_from_ordinary'],
        'history_seconds_for_policy':row['history_cost_seconds'],'completion_seconds':row['seconds'],
        'completion_solve_seconds':row['solve_seconds'],'completion_read_seconds':row['read_seconds'],
        'completion_write_seconds':row['second_asset']['write_seconds'],'history_solve_seconds':history['solve_seconds']}


def render_table(group):
    keys=('targets','public_qualified','independent_passed','new_rhs','new_jk','new_solver_actions','new_vector_check_actions',
          'history_rhs','history_jk','cumulative_jk','cumulative_rhs','completion_input_bytes','completion_output_bytes',
          'history_scalar_bytes','history_vector_bytes','completion_solve_seconds','completion_seconds','history_seconds_for_policy')
    return dict(runs=len(group),mixed_runs=sum(bool(x['mixed_support']) for x in group),
        max_difference_from_ordinary=max(r['maximum_difference_from_ordinary'] for r in group),
        max_true_residual=max(r['worst_true_residual'] for r in group),
        **{key:sum(r[key] for r in group) for key in keys})


def derive(protocol,rows):
    completed,failed=pairs(rows)
    require(not failed,'final cohort has failures')
    history={(r['source'],r['mask']):r for r in completed if r['phase']=='history'}
    setups={r['source']:r for r in completed if r['phase']=='setup'}
    rounds=[r for r in completed if r['phase']=='completion']
    costs_rows=[costs(r,history[r['source'],r['mask']]) for r in rounds]
    by_mode,by_mask={},{}
    for mode in MODES:
        by_mode[mode]={policy:render_table([r for r in costs_rows if r['mode']==mode and r['policy']==policy]) for policy in POLICIES}
        by_mask[mode]={m[0]:{p:render_table([r for r in costs_rows if (r['mode'],r['mask'],r['policy'])==(mode,m[0],p)])
                             for p in POLICIES} for m in protocol['masks']}
    lookup={(r['source'],r['mask'],r['mode'],r['policy']):r for r in costs_rows}
    counter=[]
    for a in [r for r in costs_rows if r['policy']=='blocked_support']:
        b=lookup[a['source'],a['mask'],a['mode'],'ordinary']
        if a['new_rhs']<b['new_rhs'] and a['new_jk']>b['new_jk']:
            counter.append({'source':a['source'],'mask':a['mask'],'mode':a['mode'],'ordinary_rhs_jk':[b['new_rhs'],b['new_jk']],
                            'blocked_support_rhs_jk':[a['new_rhs'],a['new_jk']]})
    qualified={(r['source'],t['field'],t['observable']) for r in rounds if r['mode']=='strict' and r['policy']=='ordinary'
               for t in r['results'] if t['qualified']}
    requested={tuple(p) for _,_,targets in protocol['masks'] for p in targets}
    no_state=[name for name,r in protocol['source_candidates'].items() if r['status']!='verified']
    summary={'source_candidates':len(protocol['source_candidates']),'sources_with_state':len(setups),'missing_state_ids':no_state,
       'distinct_requested_targets_per_source':len(requested),'unique_target_denominator':len(protocol['source_candidates'])*len(requested),
       'unique_with_scientific_state':len(setups)*len(requested),'distinct_independent_qualified_among_requested':len(qualified),
       'missing_state_unique_targets':len(no_state)*len(requested),'histories_executed':len(history),'policy_runs_executed':len(rounds),
       'actual_shared_setup_jk':sum(r['setup']['counts']['jk_calls'] for r in setups.values()),
       'actual_history_jk_once_per_mask_source':sum(r['counts']['jk_calls'] for r in history.values()),
       'actual_history_rhs_once_per_mask_source':sum(r['counts']['rhs_columns'] for r in history.values()),
       'actual_followup_jk_all_measured_methods':sum(r['new_jk'] for r in costs_rows),
       'actual_followup_rhs_all_measured_methods':sum(r['new_rhs'] for r in costs_rows),
       'per_mode':by_mode,'fewer_rhs_more_jk':counter,'per_mask':by_mask}
    return summary,costs_rows


def table(rows):
    buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=list(rows[0]),lineterminator='\n')
    writer.writeheader()
    writer.writerows(sorted(rows,key=lambda r:(r['source'],r['mask'],r['mode'],r['policy'])))
    return buffer.getvalue().encode()


def pack(work, failed, dest):
    dest.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((work/'protocol.json').read_bytes())
    packed=collect_journals(work)
    rows=[json.loads(l) for l in packed.splitlines()]
    previous=collect_journals(failed)
    pilot=pilot_receipt(failed,[json.loads(l) for l in previous.splitlines()])
    summary,rows_csv=derive(metadata,rows)
    require(len(rows_csv)==1200,'incomplete final cohort')
    raw={'operations.jsonl.gz':gzip.compress(packed,mtime=0),'pilot-operations.jsonl.gz':gzip.compress(previous,mtime=0),
         'pilot.json':pretty(pilot),'protocol.json':pretty(metadata),'timing.json':pretty(json.loads((work/'run.json').read_bytes())),
         'summary.json':pretty(summary),'costs.csv.gz':gzip.compress(table(rows_csv),mtime=0)}
    for name,data in raw.items():
        with (dest/name).open('xb') as f:
            f.write(data)
    pack_assets(work,dest/'assets.tar.gz')
    raw_names=sorted([*raw,'assets.tar.gz'])
    (dest/'manifest.json').write_bytes(pretty({name:{'sha256':sha((dest/name).read_bytes()),'bytes':(dest/name).stat().st_size}
                                                for name in raw_names}))


def oracle_for(setup):
    prov=setup['provenance']
    paths=[EXP/folder/prov['oracle_file'] for folder in ('qm9_extension','gqc_dual_response')]
    candidates=[p.read_bytes() for p in paths if p.is_file()]
    matches=[data for data in candidates if sha(data)==prov['oracle_sha256']]
    require(len(matches)==1,'exactly one pinned independent oracle per source')
    payload=matches[0]
    require(sha(payload)==prov['oracle_sha256'],'oracle mismatch')
    obj=json.loads(payload)
    require(obj['problem_identity']==prov['problem_identity'] and obj['reference_identity']==prov['reference_identity'],'oracle identities')
    reference=prov['reference_files']
    for tag in ('metadata','array'):
        name=reference[tag+'_file']
        candidates=[base/name for base in (EXP/'qm9_response_assets', EXP/'qm9_extension/assets')]
        matches=[c for c in candidates if c.is_file() and sha(c.read_bytes())==reference[tag+'_sha256']]
        require(len(matches)==1,'pinned '+tag+' input')
    return obj


def check_grade(row, ref, mode):
    raw=row['raw_value']
    require(math.isfinite(raw),'nonfinite raw response')
    if mode=='diagnostic':
        require(row['qualified'] is None and row['value'] is None and row['status']=='residual_verified','diagnostic published')
        return
    errors={key:abs(raw-val) for key,val in [('direct',ref['direct']),('adjoint',ref['adjoint']),('cphf',ref['cphf']),
                    *ref['finite_fields'].items()] if isinstance(val,(int,float)) and math.isfinite(val)}
    bad=set(ref['reasons'])
    for key,delta in errors.items():
        if delta>(1e-4 if key in ref['finite_fields'] else 1e-8):
            bad.add(key)
    require(len(errors)==5,'incomplete independent references')
    require(row['qualified']==(not bad) and set(row['reasons'])==bad,'wrong independent qualification')
    require(row['value']==(raw if not bad else None),'wrong public scalar')
    require(all(abs(row['errors'][key]-value)<=1e-14 for key,value in errors.items()),'wrong independent deviation')


def read_assets(path):
    data={}
    with tarfile.open(path,'r:gz') as archive:
        for member in archive:
            require(member.isfile() and member.name not in data and '..' not in Path(member.name).parts,'asset path')
            data[member.name]=archive.extractfile(member).read()
    return data


def artifact(data,path,rec):
    raw=data[path]
    require(len(raw)==rec['bytes'] and sha(raw)==rec['sha256'],'asset digest')
    return json.loads(raw)


def verify(dest):
    manifest=json.loads((dest/'manifest.json').read_bytes())
    for name,r in manifest.items():
        require(len((dest/name).read_bytes())==r['bytes'] and sha((dest/name).read_bytes())==r['sha256'],'manifest '+name)
    metadata=json.loads((dest/'protocol.json').read_bytes())
    rows=events(dest/'operations.jsonl.gz')
    prem=events(dest/'pilot-operations.jsonl.gz')
    complete,failed=pairs(rows)
    require(not failed and len(complete)==1332,'complete final event set')
    finished,rejected=pairs(prem)
    pilot=json.loads((dest/'pilot.json').read_bytes())
    require(len(rejected)==len(pilot['failed_calls'])==11,'pilot failures')
    require(sum((r['setup']['counts'] if r['phase']=='setup' else r['counts'])['jk_calls'] for r in finished)==pilot['total_observed_completed_jk'],'pilot JK')
    summary,cost_rows=derive(metadata,rows)
    require(summary==json.loads((dest/'summary.json').read_bytes()),'summary differs')
    require(gzip.decompress((dest/'costs.csv.gz').read_bytes())==table(cost_rows),'costs table differs')
    assets=read_assets(dest/'assets.tar.gz')
    require(len(assets)==1560,'persisted assets missing')
    setups={r['source']:r for r in complete if r['phase']=='setup'}
    oracles={name:oracle_for(event) for name,event in setups.items()}
    masks={n:([tuple(x) for x in history],[tuple(x) for x in missing]) for n,history,missing in metadata['masks']}
    history={}
    values={}
    # Load the planner in the checkout being verified. Numerical evidence stays
    # bound to the older source digest in the original run protocol.
    scripts=HERE.parents[5]/'scripts'
    sys.path.insert(0,str(scripts))
    from response_field_plan import SUPPORTS, plan_field_block
    replans={'blocked_xyz':0,'blocked_support':0}
    for r in complete:
        name,phase=r['source'],r['phase']
        if phase=='setup':
            continue
        mask=r['mask']
        src=name+'/assets/'+mask+'/'
        for blk in r['blocks']:
            require(blk['counts']['jk_calls']==blk['counts']['operator_actions']==blk['counts']['solver_actions']+blk['counts']['cache_validation_actions'],'block actions')
            require(all(v<=1e-10 for v in blk['stats']['residuals'].values()),'physical solve residual')
            require(all(v['decision']=='accepted' and v['true_residual']<=1e-10 for v in blk['cache_checks']),'physical read residual')
        for key in COUNTS:
            require(r['counts'].get(key,0)==sum(b['counts'].get(key,0) for b in r['blocks']),'double counted block '+key)
        if phase=='history':
            old=set(masks[mask][0])
            require(set(map(scalar_key,r['projected']))==old,'history content')
            fields=set(r['fields']); obs=set(r['observables'])
            require(all(f in fields or o in obs for f,o in old),'uncovered observed history')
            minimum=min(len(chosen) for n in range(7) for chosen in itertools.combinations((*AXES,*OBS),n)
                        if all(f in chosen or o in chosen for f,o in old))
            require(len(fields)+len(obs)==minimum==r['counts']['rhs_columns'],'history failed min-cover bound')
            vect=artifact(assets,src+'vectors.json',r['vector_asset'])
            for side,keys in [('fields',fields),('observables',obs)]:
                require(set(vect[side])==keys,'historical endpoint mismatch')
                for key,vector in vect[side].items():
                    content=b''.join(struct.pack('<d',q) for q in vector['solution'])
                    require(sha(content)==vector['solution_sha256'] and vector['solver_true_residual']<=1e-10,'historical vector')
            for mode in MODES:
                body=artifact(assets,src+mode+'.json',r['scalar_assets'][mode])
                require(body['scope']==r['identity'] and body['operator']==setups[name]['provenance']['operator_contract'] and
                        body['problem']==setups[name]['provenance']['problem_identity'] and body['producer']==r['producer'],'source identity')
                admitted={scalar_key(z):z for z in body['records']}
                for z in r['projected']:
                    edge=scalar_key(z); check_grade(z,None,'diagnostic')
                    if mode=='strict':
                        ref=oracles[name]['targets'][edge[0]][edge[1]]
                        if edge not in admitted:
                            require(bool(ref['reasons']) or any(abs(z['raw_value']-ref[tag])>1e-8 for tag in ('cphf','direct','adjoint')) or
                                    any(abs(z['raw_value']-v)>1e-4 for v in ref['finite_fields'].values()),'qualified history was lost')
                            continue
                        check_grade(admitted[edge],ref,mode)
                    require(z['raw_value']==admitted[edge]['raw_value'] and z['target_identity']==admitted[edge]['target_identity'],'operand copied from different source')
                history[name,mask,mode]=(r,admitted)
            continue
        mode,policy=r['mode'],r['policy']
        old,known=history[name,mask,mode]
        require(r['history_rhs']==old['counts']['rhs_columns'] and r['history_jk']==old['counts']['jk_calls'],'history charge')
        require(r['cumulative_jk']==r['history_jk']+r['counts']['jk_calls'] and r['cumulative_rhs']==r['history_rhs']+r['counts']['rhs_columns'],'two-round work')
        require(r['history_vector_bytes']==(old['vector_asset']['bytes'] if policy=='keep_history_vectors' else 0),'storage policy')
        require(set(map(scalar_key,r['results']))==set(masks[mask][1]),'target coverage')
        if policy in replans:
            supports=(AXES,) if policy=='blocked_xyz' else SUPPORTS
            plan=plan_field_block(masks[mask][1],known,supports=supports)
            first=r['blocks'][0]
            coefficients=tuple(int(axis in plan.support) for axis in AXES) if plan.support else None
            observed=tuple(first['support']) if first['support'] is not None else None
            require(tuple(first['fields'])==plan.fields and tuple(first['observables'])==plan.observables,
                    'updated planner changed first-block unit endpoints')
            require(observed==coefficients and tuple(r['relation']['support'])==plan.support,
                    'updated planner changed mixed field')
            require(set(map(tuple,first['requests']))==set(plan.ordinary_requests),'updated ordinary request set')
            receipts={(z['field'],z['observable']):tuple(tuple(x['pair']) for x in z['operands'])
                      for z in r['relation'].get('reconstructions',[])}
            require(receipts==plan.operands,'updated decoder inputs changed')
            if coefficients:
                require(set(first['combined']['observable_identities'])=={o for _,o in plan.operands},
                        'updated mixed-field contractions changed')
            replans[policy]+=1
        out=artifact(assets,src+'out/'+mode+'-'+policy+'.json',r['second_asset'])
        require(out['records']==[z for z in r['results'] if mode=='diagnostic' or z['qualified']],'persisted completion')
        for z in r['results']:
            f,o=scalar_key(z)
            ref=oracles[name]['targets'][f][o]
            check_grade(z,ref,mode)
            if mode=='diagnostic':
                post=next(q for q in r['independent_checks_of_diagnostics'] if scalar_key(q)==(f,o))
                raw=z['raw_value']
                errors={tag:abs(raw-val) for tag,val in [('direct',ref['direct']),('adjoint',ref['adjoint']),
                        ('cphf',ref['cphf']),*ref['finite_fields'].items()]}
                check_grade(dict(post,raw_value=raw,value=raw if post['qualified'] else None,errors=errors),ref,'strict')
            key=(name,mask,mode,f,o)
            if policy=='ordinary':
                values[key]=z['raw_value']
            require(abs(values[key]-z['raw_value'])<=1e-8,'ordinary numerical control')
        for recons in r['relation'].get('reconstructions',[]):
            o=recons['observable']; val=r['relation']['combined']['values'][o]
            for operand in recons['operands']:
                edge=tuple(operand['pair'])
                require(edge[1]==o and edge in known and operand['target_identity']==known[edge]['target_identity']
                        and operand['value']==known[edge]['raw_value'] and operand['source_attempt']==old['producer'],'decoder operand')
                val-=operand['value']
            require(abs(val-recons['candidate']['raw_value'])<=1e-10,'scalar reconstruction')
    require(replans=={'blocked_xyz':240,'blocked_support':240},'new planner replay denominator')
    report=dict(source_candidates=summary['source_candidates'],histories=len(history)//2,
                measured_strategies=len(cost_rows),persisted_assets=len(assets),excluded_pilot_failures=len(rejected),
                replayed_first_blocks=replans,replanned_fields_observables_coefficients_operands_equal=True,
                measured_planner_sha256=metadata['source_files']['response_field_plan.py'],
                replay_planner_sha256=sha((scripts/'response_field_plan.py').read_bytes()),
                replay_cover_sha256=sha((scripts/'response_cover.py').read_bytes()),
                measured_project_commit=metadata['source_commit'])
    print(json.dumps(report,separators=(',',':')))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',nargs=2,type=Path,metavar=('WORK','PILOT'))
    parser.add_argument('--directory',type=Path,default=HERE)
    parser.add_argument('--receipt',type=Path,help='write an optional fresh verification receipt')
    args=parser.parse_args()
    if args.package:
        pack(*args.package,args.directory)
    verified=verify(args.directory)
    if args.receipt:
        args.receipt.write_bytes(pretty(verified))
