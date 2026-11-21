"""Read one archived orbital record and run the pinned author's water interpolation routine."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

import msgpack
import numpy
import scipy

from inspect_assets import WATER_PIN, pinned


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--water',type=Path,required=True)
    parser.add_argument('--wavefunction',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    src=args.water.resolve()
    source=pinned(src, WATER_PIN)
    sys.path.insert(0,str(src))
    import interpolate_dp_dm as author
    receipts = []
    for method in ('hf_avtz','dft_avtz'):
        paths = []
        original_open = open
        def observe(path, *args, **kw):
            paths.append(Path(path))
            return original_open(path,*args,**kw)
        start=time.perf_counter()
        with patch('builtins.open',observe):
            output=author.get_dp(105,0.96,0,'w1',str(src/'H2O'/method))
        elapsed=time.perf_counter()-start
        grid=numpy.load(src/'H2O'/method/'O_p10_20.npy')[9,3,0].item()
        printed=float(output[0].strip().splitlines()[1].split()[3])
        assert len(paths)==len(set(paths))==63 and len(output)==3 and abs(printed-grid) <= 5.1e-6
        receipts.append(dict(method=method,angle_degree=105,mean_OH_angstrom=.96,difference_OH_angstrom=0.,
                             opened_npy_files=len(paths),logical_input_bytes=sum(p.stat().st_size for p in paths),
                             returned_text_bytes=sum(len(row.encode()) for row in output),seconds=elapsed,
                             output_sha256=sha256('\n'.join(output).encode()).hexdigest(),raw_O_p10_20=grid,
                             formatted_O_p10_20=printed,absolute_rounding_difference=abs(grid-printed)))
    start=time.perf_counter()
    raw=args.wavefunction.read_bytes()
    encoded,compression=msgpack.unpackb(raw,raw=False)
    assert compression=='zstd'
    payload=subprocess.run(['zstd','-q','-d','-c'],input=encoded,stdout=subprocess.PIPE,check=True).stdout
    wf=msgpack.unpackb(payload,raw=False)
    eig=wf[wf['eigenvalues_a']];coef=wf[wf['orbitals_a']]
    assert wf['restricted'] and len(eig)**2==len(coef)
    record=dict(record_id=96510996,message_bytes=len(raw),sha256=sha256(raw).hexdigest(),
                decompressed_bytes=len(payload),decompressed_sha256=sha256(payload).hexdigest(),
                keys=sorted(wf),basis=wf['basis']['name'],basis_keys=sorted(wf['basis']),
                alpha_eigenvalues=len(eig),alpha_coefficients=len(coef),restricted=wf['restricted'],
                seconds=time.perf_counter()-start)
    result=dict(source=source,python=sys.version,numpy=numpy.__version__,scipy=scipy.__version__,msgpack=msgpack.__version__,
                zstd=subprocess.check_output(['zstd','--version'],text=True).strip(),
                water_consumer=receipts,qcarchive_ground_state=record)
    with args.out.open('x') as f:
        json.dump(result,f,indent=2,sort_keys=True,allow_nan=False)
        f.write('\n')


if __name__=='__main__':
    main()
