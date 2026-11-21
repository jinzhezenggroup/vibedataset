"""Fetch the documented public read queries and the immutable record-ID selection into a new directory."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

BASE = 'https://api.qcarchive.molssi.org/api/v1/'
HF = list(range(148574276,148574282))
ESP = [96510994,96510995,96510996]


def main():
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('--out',required=True,type=Path)
    out=args.parse_args().out
    out.mkdir(parents=True,exist_ok=False)
    hf_filter={'method':['hf','rhf','scf'],'basis':['sto-3g'],'status':['complete'],'limit':6}
    queries = [('datasets','datasets',None),('information','information',None),('ds347','datasets/347',None),
               ('hfsto','records/singlepoint/query',hf_filter),
               ('hfprops','records/singlepoint/query',{'driver':['properties'],**hf_filter}),
               ('selected347','records/singlepoint/query',{'dataset_id':[347],'status':['complete'],'limit':3}),
               ('ds-membership','datasets/queryrecords',{'record_id':HF+ESP})]
    for i in HF+ESP:
        route=f'records/singlepoint/{i}'
        queries.extend([(f'record-{i}',route,None),(f'wave-{i}',route+'/wavefunction',None)])
    queries.append(('wfn-96510996','records/singlepoint/96510996/wavefunction/data',None))
    def fetch(item):
        key,route,payload=item
        content='application/msgpack' if key=='wfn-96510996' else 'application/json'
        data=None if payload is None else json.dumps(payload).encode()
        request=Request(BASE+route,data=data,headers={'Content-Type':content,'Accept':content})
        path=out/(key+('.msgpack' if key=='wfn-96510996' else '.json'))
        started=time.perf_counter()
        with urlopen(request,timeout=100) as response:
            raw=response.read()
        path.write_bytes(raw)
        return {'file':path.name,'url':request.full_url,'method':request.get_method(),
                'body':payload,'bytes':len(raw),'seconds':time.perf_counter()-started}
    started=datetime.now(timezone.utc).isoformat()
    with ThreadPoolExecutor(max_workers=3) as pool:
        receipts=list(pool.map(fetch,queries))
        ids=sorted({json.loads((out/f'record-{i}.json').read_bytes())['molecule_id'] for i in HF+ESP})
        receipts.extend(pool.map(fetch,[(f'molecule-{i}',f'molecules/{i}',None) for i in ids]))
    (out/'transfers.json').write_text(json.dumps({'started_utc':started,'requests':receipts},indent=2)+'\n')


if __name__=='__main__':
    main()
