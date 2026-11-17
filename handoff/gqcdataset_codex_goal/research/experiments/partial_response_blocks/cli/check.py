#!/usr/bin/env python3
"""Exercise subset-field recovery and real solver fallback via the normal dataset client."""
from argparse import ArgumentParser
from dataclasses import replace
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[6]
sys.path.insert(0,str(ROOT/'scripts'))
import complete_response_dataset as client
import gqc_dual_response as molecular

URL = 'https://api.figshare.com/v2/articles/1057646/versions/2'
DIAGONAL = [('x','q0'),('y','r2'),('z','zz')]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    work = parser.parse_args().work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    batches = {}

    def run(name, requested, *, history=None, mode=None, previous=None, short_first_solve=False):
        input_path = work/(name+'.jsonl')
        output = work/(name+'.json')
        db = work/((previous or name) + '.sqlite')
        input_path.write_text(''.join(json.dumps({'source':URL, 'record_id':3, 'field':f, 'observable':o})+'\n'
                                      for f,o in requested))
        args = [str(ROOT/'scripts/complete_response_dataset.py'), '--requests', str(input_path),
                '--out', str(output), '--cache-db', str(db), '--kernel-cache', str(work/'kernels')]
        if history:
            source = work/(history+'.json')
            args.extend(['--history',sha256(source.read_bytes()).hexdigest(),str(source)])
        if mode:
            args.extend(['--scalar-plan',mode])
        if short_first_solve:
            solve = molecular.solve_many
            called = []
            def limited(operator, rhs, **kw):
                called.append(rhs.shape[1])
                if len(called) == 1:
                    kw['options'] = replace(kw['options'],max_iterations=1)
                return solve(operator,rhs,**kw)
            with patch.object(molecular,'solve_many',limited), patch.object(sys,'argv',args):
                assert client.main() == 0
            assert called == [2,3], called
        else:
            subprocess.run([sys.executable,*args],check=True)
        raw=output.read_bytes()
        measured=json.loads(raw)
        assert [r['status'] for r in measured['records']] == ['qualified']*len(requested)
        with sqlite3.connect(db) as c:
            assert c.execute('pragma integrity_check').fetchone()==('ok',)
        batches[name]=measured
        return measured['work'][0]

    two = [('y','q0'),('x','r2')]
    run('cross-two',two)
    run('cross-four',two+[('z','q0'),('z','r2')])
    plain=run('plain',DIAGONAL)
    two_new=run('from-two',DIAGONAL,history='cross-two')
    two_old=run('from-two-split',DIAGONAL,history='cross-two',mode='split-xyz')
    four_new=run('from-four',DIAGONAL,history='cross-four')
    four_old=run('from-four-split',DIAGONAL,history='cross-four',mode='split-xyz')
    repeated=run('reopen',DIAGONAL,previous='from-two')
    for record in [two_new,four_new]:
        assert record['rhs']==2 and record['relation']['support']==['x','y']
        assert record['block']['column_order']==['combined_field','fields/z']
        assert all(len(r['operands'])==1 for r in record['relation']['reconstructions'])
    assert plain['rhs']==two_old['rhs']==3 and four_old['rhs']==2
    assert repeated['round_jk']==0 and not repeated['model_started']
    shifted=[('x','r2'),('y','zz'),('z','q0')]
    run('non-diagonal-history',[('y','r2'),('x','zz')])
    nonsym=run('non-diagonal',shifted,history='non-diagonal-history')
    assert nonsym['rhs']==2 and nonsym['relation']['support']==['x','y']
    fallback=run('solver-fallback',DIAGONAL,history='cross-two',short_first_solve=True)
    failed=fallback['relation']['failed_block']
    assert failed['submitted_blocks']==1 and failed['counts']['jk_calls']>0
    assert fallback['rhs']==2+plain['rhs'] and fallback['round_jk']==plain['round_jk']+failed['counts']['jk_calls']
    baseline={ (r['request']['field'],r['request']['observable']):r['value'] for r in batches['plain']['records']}
    deltas={k:max(abs(r['value']-baseline[(r['request']['field'],r['request']['observable'])])
                  for r in batches[k]['records']) for k in ('from-two','from-four','from-four-split','solver-fallback','reopen')}
    assert max(deltas.values()) <= 1e-8
    summary={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'cli_sha256':sha256((ROOT/'scripts/complete_response_dataset.py').read_bytes()).hexdigest(),
             'model_sha256':sha256((ROOT/'scripts/gqc_dual_response.py').read_bytes()).hexdigest(),
             'max_delta_from_plain_by_client':deltas,'short_first_solve':'max_iterations=1 on the first actual two-column GQC solve',
             'clients':{k:{'setup_jk':b['work'][0]['setup_jk'],'solver_and_check_jk':b['work'][0]['round_jk'],
                           'new_rhs':b['work'][0]['rhs'],'seconds':b['seconds'],'counts_by_status':b['counts_by_status'],
                           'file_sha256':sha256((work/(k+'.json')).read_bytes()).hexdigest()} for k,b in batches.items()}}
    (work/'verification.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    (work/'batches.json.gz').write_bytes(gzip.compress(json.dumps(batches,sort_keys=True,allow_nan=False).encode(),mtime=0))
    print(json.dumps({k:v['solver_and_check_jk'] for k,v in summary['clients'].items()}))


if __name__=='__main__':
    main()
