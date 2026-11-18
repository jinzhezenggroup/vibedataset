"""Measure only the additional dense first round; the sealed dense follow-up reads zero history bytes."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path

from run import (Decoders, HISTORIES, HERE, ROOT, Q_COMMIT, Q_SHA, clock, evaluate, file_hash, git, journal, json_hash,
                 json, ordinary, plan_cover, quality_code, record, save, setup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cpu', type=int, default=0)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.sched_setaffinity(0, {args.cpu})
    if not all(os.environ.get(k) == '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('single-thread environment required')
    quality = quality_code(out)
    save(out / 'protocol.json', dict(project=git(ROOT,'rev-parse','HEAD'), q14_commit=Q_COMMIT, q14_sha256=Q_SHA,
         driver_sha256=file_hash(__file__), cpu=list(os.sched_getaffinity(0)), utc=datetime.now(timezone.utc).isoformat()))
    start = clock()
    actual = 0
    for catalog in (HERE.parent/'qm9_response_assets', HERE.parent/'qm9_extension/assets'):
        for row in sorted(json.loads((catalog/'index.json').read_bytes())['rows'], key=lambda r:r.get('name') or ''):
            name = row['name']
            if not name:
                continue
            if row['status'] != 'verified':
                journal(out, dict(phase='reference_unavailable', source=name, reason=row['error']))
                continue
            directory = out/name
            directory.mkdir()
            meta, array = (catalog/row[k] for k in ('metadata_file','array_file'))
            if (file_hash(meta),file_hash(array)) != (row['metadata_sha256'],row['array_file_sha256']):
                raise ValueError('source hash mismatch')
            cold = setup(out,meta,array,directory/'native','first',name)
            model = setup(out,meta,array,directory/'native','reopen',name)
            stability = quality.StabilityEvidence.from_model(model)
            if stability.report['status'] != 'available':
                raise ValueError('missing stability evidence')
            scope = json_hash({'problem':model.problem.identity,'source':model.source,'contract':model.contract_identity,
                               'units':{'q0':'e / au_field','r2':'bohr^2 / au_field','zz':'bohr^2 / au_field'},
                               'quality_sha256':Q_SHA,'matrix':stability.report['matrix_sha256']})
            journal(out, dict(phase='quality_setup', source=name, report=stability.report))
            for rep in range(4):
                where = directory/('rep'+str(rep))
                where.mkdir()
                for key, edges in sorted(HISTORIES.items(),reverse=bool(rep%2)):
                    def produce(trace):
                        at = clock()
                        fs, _ = plan_cover(edges)
                        plan = ordinary(edges,'cover',fs)
                        rows, _ = evaluate(model,quality,stability,plan,{}, {},trace,Decoders(directory/'decoders'),dense=True)
                        trace['production_seconds_before_writes'] = clock()-at
                        trace['scalars'] = save(where/(key+'.json'), dict(identity=scope,rows={f+'/'+o:v for (f,o),v in rows.items()}))
                    record(out,model,dict(source=name,repetition=rep,phase='history',kind=key),produce)
            actual += cold.counts['jk_calls'] + model.counts['jk_calls']
    save(out/'finished.json',dict(seconds=clock()-start,jk=actual,journal_sha256=file_hash(out/'events.jsonl')))


if __name__ == '__main__':
    main()
