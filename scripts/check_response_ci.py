#!/usr/bin/env python3
"""Run the archived response checks or the pinned molecular CPU regressions in a fresh directory."""
import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from importlib import metadata
import gzip
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / 'handoff/gqcdataset_codex_goal'
EXP = HANDOFF / 'research/experiments'
SCRIPTS = ROOT / 'scripts'
REQUIREMENTS = ROOT / 'configs/response-science-requirements.txt'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class Run:
    def __init__(self, tier, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=False)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONOPTIMIZE='0')
        self.receipt = {
            'tier': tier, 'started_utc': datetime.now(timezone.utc).isoformat(), 'checks': [],
            'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
        }
        self.receipt['tracked_changes'] = subprocess.check_output(
            ['git', 'status', '--short', '--untracked-files=no'], cwd=ROOT, text=True).splitlines()

    def command(self, name, args, *, codes=(0,)):
        command = list(map(str, args))
        log = self.out / (name + '.log')
        start = time.perf_counter()
        print(name, flush=True)
        with log.open('x') as stream:
            result = subprocess.run(command, cwd=ROOT, env=self.env, stdout=stream, stderr=subprocess.STDOUT)
        self.receipt['checks'].append({'check': name, 'argv': command, 'exit': result.returncode,
                                       'seconds': time.perf_counter() - start, 'log': log.name})
        if result.returncode not in codes:
            raise RuntimeError(f'{name} exited {result.returncode}\n{log.read_text()[-3500:]}')
        return result.returncode

    def python(self, name, script, *args, **kw):
        return self.command(name, [sys.executable, script, *args], **kw)


def archive(run):
    files = sorted(SCRIPTS.glob('*.py'))
    for path in files:
        ast.parse(path.read_bytes(), filename=str(path))
    run.receipt['python_sources_parsed'] = len(files)
    for name, expected in [('cover', {'combinations_checked': 32768}),
                           ('field_plan', {'disjoint_known_requested_masks': 19683, 'cached_control_combinations': 768})]:
        run.python(name, SCRIPTS / ('check_response_' + name + '.py'))
        report = read(run.out / (name + '.log'))
        require(all(report[k] == n for k, n in expected.items()), name + ' audit denominator')
    labels = {}
    for family, count in [('response_planning', 54), ('qm9_extension', 153)]:
        out = run.out / family
        run.python(family, SCRIPTS / ('summarize_' + family + '.py'), '--out', out)
        path = out / 'response-labels.jsonl'
        require(path.read_bytes() == (EXP / family / path.name).read_bytes(), family + ' labels differ from release')
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        require(len({(r['qm9_id'], r['field'], r['observable']) for r in rows}) == len(rows) == count,
                family + ' target denominator')
        labels[family] = {'sha256': digest(path), 'status': Counter(r['status'] for r in rows)}
    run.receipt['v1_labels'] = labels
    run.python('partial-cohort', EXP / 'partial_response_blocks/cohort/evidence.py',
               '--receipt', run.out / 'cohort.json')
    migration = run.out / 'cphf_v2'
    run.python('cphf-migration', SCRIPTS / 'summarize_cphf_migration.py', '--out', migration)
    migrations = {}
    for name in ('response-labels.jsonl', 'migration.csv', 'qualification-costs.json'):
        measured = migration / name
        require(measured.read_bytes() == (EXP / 'cphf_v2' / name).read_bytes(), 'v2 archive differs: ' + name)
        migrations[name] = digest(measured)
    run.receipt['v2_migration_sha256'] = migrations
    for batch in ('cohort', 'planning'):
        run.python('cphf-v2-' + batch, EXP / 'cphf_v2' / batch / 'verify.py')
    for experiment in ('response_quality_prior', 'represented_matrix_bound', 'legacy_response_assets', 'response_benefit'):
        run.python('check-' + experiment, EXP / experiment / 'verify.py')
    run.python('dense-history-baseline', EXP / 'response_benefit/verify_dense.py')
    for split in ('seed', 'holdout'):
        published = EXP / 'target_quality' / split
        score = run.out / (split + '-quality.json')
        costs = score.with_suffix('.csv')
        run.python('sealed-quality-' + split, SCRIPTS / 'score_target_quality.py',
                   '--sealed', published, '--out', score, '--costs', costs, '--check-controls')
        require(score.read_bytes() == (published / 'score.json').read_bytes() and
                costs.read_bytes() == (published / 'costs.csv').read_bytes(), split + ' blind decisions or costs differ')
    # Exercise the same archived-summary entry point against a private damaged copy.
    raw = EXP / 'response_planning/raw'
    with tempfile.TemporaryDirectory(dir=run.out) as directory:
        evidence = Path(directory)
        manifest = read(raw / 'manifest.json')
        first = manifest[min(manifest)]['summary.json']['file']
        for path in raw.iterdir():
            if path.name == first:
                (evidence / first).write_bytes(path.read_bytes() + b'!')
            else:
                (evidence / path.name).symlink_to(path)
        run.python('corrupt-archive-control', SCRIPTS / 'summarize_response_planning.py',
                   '--evidence', evidence, '--out', evidence / 'replay', codes=(1,))
        require(first + ': compressed digest' in (run.out / 'corrupt-archive-control.log').read_text(),
                'corrupt archive did not fail its own checksum')


def prepare_science(run):
    require(sys.version_info[:2] == (3, 13), 'science regression requires Python 3.13')
    packages = dict(line.split('==') for line in REQUIREMENTS.read_text().splitlines())
    installed = {name: metadata.version(name) for name in packages}
    require(installed == packages, f'install {REQUIREMENTS} in this interpreter; found {installed}')
    run.receipt['packages'] = installed
    threads = dict.fromkeys(('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'), '1')
    run.env.update(threads)
    run.env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + run.env['PATH']
    # Local imports and subprocesses must run the same single-thread protocol.
    os.environ.update(threads)
    run.receipt['threads'] = threads
    run.command('cxx', ['c++', '--version'])
    run.command('sccache', ['sccache', '--version'])
    run.command('sccache-start', ['sccache', '--start-server'])
    plan = read(HANDOFF / 'research/acquisition_plan.json')
    selected = [s for s in plan['repositories'] if s['id'] in ('gqc', 'pyscf_2_14')]
    require({s['id'] for s in selected} == {'gqc', 'pyscf_2_14'}, 'missing scientific source lock')
    missing = [s for s in selected if not (ROOT / s['checkout_path']).exists()]
    if missing:
        inputs = run.out / 'acquisition-plan.json'
        write(inputs, {'repositories': missing, 'receipt_directory': str(run.out / 'acquisition'),
                       'inventory_directory': str(run.out / 'inventories')})
        run.python('pinned-source-fetch', HANDOFF / 'tools/acquire_sources.py', '--plan', inputs)
    run.receipt['source_commits'] = {}
    for source in selected:
        path = ROOT / source['checkout_path']
        actual = subprocess.check_output(['git', '-C', path, 'rev-parse', 'HEAD'], text=True).strip()
        clean = subprocess.check_output(['git', '-C', path, 'status', '--porcelain'], text=True)
        require(actual == source['commit'] and not clean, source['id'] + ' source checkout differs from lock')
        run.receipt['source_commits'][source['id']] = actual


def check_molecular_report(expected_index, generated_index, code):
    expected, actual = read(expected_index), read(generated_index)
    require(expected['index_sha256'] == actual['index_sha256'], 'molecular input index differs from release')
    totals = Counter()
    max_differences = {}
    for original, replay in zip(expected['strata'], actual['strata'], strict=True):
        for key in ('name', 'stratum', 'input_status', 'status'):
            require(original[key] == replay[key], f'{key} differs for {original["stratum"]}')
        status = replay['status']
        require(status in ('not_run', 'completed'), f'incomplete molecular regression: {replay}')
        if status == 'not_run':
            totals['skipped_input_strata'] += 1
            continue
        published, measured = expected_index.parent / original['oracle'], generated_index.parent / replay['oracle']
        require(digest(published) == original['sha256'] and digest(measured) == replay['sha256'],
                'molecular oracle checksum')
        targets, fresh = read(published)['targets'], read(measured)['targets']
        decisions = Counter()
        for f in ('x', 'y', 'z'):
            for o in ('q0', 'r2', 'zz'):
                ref, cell = targets[f][o], fresh[f][o]
                require(cell['status'] == ref['status'] and cell['qualified'] is ref['qualified']
                        and set(cell['reasons']) == set(ref['reasons']),
                        f'qualification changed for {replay["name"]}/{f}/{o}')
                require(cell['value'] == (cell['direct'] if cell['qualified'] else None),
                        'published value disagrees with the qualified direct response')
                methods = [(method, ref[method], cell[method], 1e-8) for method in ('direct', 'adjoint', 'cphf')]
                methods.extend((step, ref['finite_fields'][step], cell['finite_fields'][step], 1e-4)
                               for step in ('0.0005', '0.0002'))
                for method, old, new, tolerance in methods:
                    if old is None:
                        require(new is None, f'previously missing {method} changed for {replay["name"]}/{f}/{o}')
                    else:
                        delta = abs(old - new)
                        require(math.isfinite(delta) and delta <= tolerance,
                                f'{method} differs by {delta} for {replay["name"]}/{f}/{o}')
                        max_differences[method] = max(delta, max_differences.get(method, 0.0))
                decisions[cell['status']] += 1
        n = decisions['qualified']
        require(n == replay['qualified'] == original['qualified'] and replay['targets'] == original['targets'] == 9,
                'molecular denominator disagrees with target records')
        totals.update(molecules=1, qualified=n, response_rejected=decisions['response_rejected'],
                      oracle_unqualified=decisions['oracle_unqualified'])
    require(totals['molecules'] == 4 and totals['skipped_input_strata'] == 4, 'initial cohort denominator')
    require(code == int(totals['qualified'] < 9 * totals['molecules']), 'scientific exit code disagrees with complete report')
    return {**totals, 'maximum_absolute_difference_from_release': max_differences}


def science(run):
    prepare_science(run)
    raw_root = HANDOFF / "research/environment/gpu4pyscf-20261122/a-d-telemetry/raw"
    cartesian = EXP / "hessian_cphf/shared-spectroscopy"
    verified_cartesian = run.out / "physical-cartesian-cphf.json"
    run.command("physical-cartesian-cphf", [sys.executable, SCRIPTS / "score_cartesian_cphf.py",
                "--root", cartesian / "cartesian-certificate", "--protocol", cartesian / "protocol.json",
                "--out", verified_cartesian])
    cartesian_result=json.loads(verified_cartesian.read_text())
    if not cartesian_result["all_accepted"] or len(cartesian_result["request_links"])!=12:
        raise ValueError("unqualified Cartesian CPHF response")
    new_ao_score = run.out / "independent-ao-score.json.gz"
    run.command("cpu-ao-response", [sys.executable, SCRIPTS / "score_ao_density_response.py",
                "--manifest", EXP / "attribution_4arm/manifest.json", "--raw-root", raw_root, "--out", new_ao_score])
    physical = json.loads(gzip.decompress(new_ao_score.read_bytes()))
    reference = json.loads(gzip.decompress((EXP / "response_asset_compiler/scorer-v192-ao.json.gz").read_bytes()))
    require(physical["input_files"] == reference["input_files"] and physical["counts"] == {"accepted": 204},
            "independent candidate AO response residual or denominator")
    require(all(v["status"] == "reject-and-recompute" for v in physical["negative_controls"].values()),
            "independent negative control accepted")

    from complete_response_dataset import DEFAULT_CATALOGS

    source_index, expected_index = DEFAULT_CATALOGS[0]
    dual = run.out / 'dual'
    code = run.python('independent-dual', SCRIPTS / 'probe_gqc_dual_response.py',
                      '--index', source_index, '--out', dual, codes=(0, 1))
    run.receipt['molecular_status'] = check_molecular_report(expected_index, dual / 'summary.json', code)
    run.python('dual-controls', SCRIPTS / 'check_gqc_dual_response.py', '--out', run.out / 'dual-controls')
    run.python('joint-block', SCRIPTS / 'check_gqc_joint_response.py', '--out', run.out / 'joint-block')
    cli = EXP / 'response_dataset_cli'
    for label, script in [('cli', cli / 'verify.py'), ('history', cli / 'verify_history.py'),
                          ('catalogs', cli / 'verify_catalogs.py'),
                          ('solver-fallback', EXP / 'partial_response_blocks/cli/check.py'),
                          ('failure-costs', SCRIPTS / 'check_response_failure_receipts.py')]:
        run.python(label, script, '--work', run.out / label)
    run.python('cphf-controls', SCRIPTS / 'check_cphf_reference.py', '--out', run.out / 'cphf-controls')
    run.python('output-quality-controls', SCRIPTS / 'check_target_quality_controls.py',
               '--out', run.out / 'numerical-controls.json')
    run.python('quality-inputs', SCRIPTS / 'check_target_quality_inputs.py', '--work', run.out / 'quality-inputs')
    for label, filename in (('two-field-identities', 'check_algebra.py'), ('measured-operand-errors', 'check_quality_terms.py')):
        run.python(label, EXP / 'response_benefit' / filename)
    blind = run.out / 'blind-production'
    run.python('blind-production', SCRIPTS / 'run_blind_target_quality.py', '--split', 'seed', '--smoke', '--out', blind)
    run.python('independent-output-score', SCRIPTS / 'score_target_quality.py', '--sealed', blind / 'sealed',
               '--out', run.out / 'blind-score.json', '--check-controls')
    # Independent follow-up research checks. These read only sealed source assets
    # and fixed evidence, then write reports under the CI output directory.
    issue25 = EXP / 'information_sufficiency' / 'analyze_issue25.py'
    issue25_result = run.out / 'issue25-result.json'
    run.python('issue25-independent-hand-and-multi4', issue25, '--result', issue25_result)
    require(issue25_result.read_bytes() ==
            (EXP / 'information_sufficiency' / 'issue25' / 'issue25_result.json').read_bytes(),
            'issue25 deterministic replay differs from the sealed result')
    operator = EXP / 'error_certificates' / 'operator_probe.py'
    run.python('issue26-operator-probe', operator, 'score',
               '--sealed', EXP / 'error_certificates' / 'operator_probe' / 'sealed.json',
               '--out', run.out / 'operator-probe')
    run.python('issue27-response-migration', EXP / 'cross_protocol' / 'response_migration' / 'verify.py')
    run.python('cross-protocol-psi4-pyscf', EXP / 'cross_protocol' / 'verify.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tier', choices=('archive', 'science'))
    parser.add_argument('--out', type=Path, required=True, help='new directory for all raw reports and the run receipt')
    args = parser.parse_args()
    run = Run(args.tier, args.out.resolve())
    try:
        {'archive': archive, 'science': science}[args.tier](run)
    except Exception as error:
        run.receipt.update(passed=False, error=str(error))
        raise
    else:
        run.receipt['passed'] = True
    finally:
        run.receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write(run.out / 'checks.json', run.receipt)


if __name__ == '__main__':
    main()
