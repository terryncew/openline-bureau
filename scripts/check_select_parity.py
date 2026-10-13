#!/usr/bin/env python3
"""Verify the static Exchange and Bureau use the same task shortlist rule.

Run against an explicitly reviewed Exchange checkout, never a contribution.
Uses test-only in-memory catalogs; no evidence or real inquiry is published.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bureau.select import select_candidates
from tests.test_select import fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exchange', type=Path, required=True)
    args = parser.parse_args()
    model = (args.exchange / 'docs/beta/model.mjs').resolve().as_uri()
    script = '''
const {selectCandidates} = await import(process.argv[1]);
let data = ''; for await (const chunk of process.stdin) data += chunk;
const cases = JSON.parse(data);
process.stdout.write(JSON.stringify(cases.map(c => selectCandidates(c.catalog,c.criteria))));
'''
    criteria = {'task': 'digest', 'budget': 25, 'currency': 'USD', 'basis': 'task', 'minEvaluations': 1}
    cases = [{'catalog': fixture(), 'criteria': criteria}]
    for key, value in [('task', 'missing'), ('basis', ''), ('currency', 'EUR'), ('budget', 5), ('minEvaluations', 2)]:
        cases.append({'catalog': fixture(), 'criteria': {**criteria, key: value}})
    synthetic = fixture()
    synthetic['synthetic'] = True
    cases.append({'catalog': synthetic, 'criteria': criteria})
    for verification in ('EVALUATOR_REPORTED', 'MAINTAINER_REPRODUCED'):
        data = fixture()
        data['evaluations'][0]['outcome_verification'] = verification
        data['evaluations'][0]['sample']['total'] = 5
        cases.append({'catalog': data, 'criteria': criteria})
    differing_data = fixture()
    differing_data['evaluations'][0]['sample']['dataset'] = 'Dataset A'
    differing_data['evaluations'][1]['sample']['dataset'] = 'Dataset B'
    cases.append({'catalog': differing_data, 'criteria': criteria})
    punctuation = fixture()
    punctuation['capabilities'][0]['id'] = 'alpha_a'
    punctuation['capabilities'][1]['id'] = 'alpha-a'
    punctuation['capabilities'][0]['price']['amount'] = '10.00'
    punctuation['evaluations'] = []
    cases.append({'catalog': punctuation, 'criteria': {**criteria, 'minEvaluations': 0}})
    result = subprocess.run(['node', '--input-type=module', '-e', script, model],
        input=json.dumps(cases), text=True, stdout=subprocess.PIPE, check=True)
    expected = [select_candidates(c['catalog'], c['criteria']) for c in cases]
    if json.loads(result.stdout) != expected:
        raise SystemExit('Bureau and Exchange shortlist rules disagree')
    print(f'PASS: {len(cases)} Bureau / static Exchange policy conformance cases')


if __name__ == '__main__':
    main()
