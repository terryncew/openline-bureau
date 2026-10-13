"""Publish the bounded results of the existing frozen allocation trial.

This is an economic-validation exhibit, never live marketplace performance.
Only the three recorded, hash-checked public experiment reports are exported.
Private Wallet homes, input files and signing keys are never traversed.
"""
import argparse
import hashlib
import json
from pathlib import Path

from .allocation_demo import PROTOCOL, seal, trial_result

RECORDED = Path(__file__).resolve().parents[1] / 'demo/bureau-allocation-001/recorded'


def exhibit(root=RECORDED):
    root = Path(root)
    hashes = json.loads((root / 'SHA256.json').read_text())
    cases = []
    for name in ('mixed', 'reversal', 'sparse'):
        loaded = {}
        for filename in ('protocol.json', 'selections.json', 'experiment.json'):
            relative = name + '/' + filename
            raw = (root / relative).read_bytes()
            if hashlib.sha256(raw).hexdigest() != hashes[relative]:
                raise ValueError('frozen public trial hash mismatch: ' + relative)
            loaded[filename] = json.loads(raw)
        protocol, selections, result = (loaded[k] for k in (
            'protocol.json', 'selections.json', 'experiment.json'))
        if protocol != PROTOCOL or selections['protocol_sha256'] != seal(protocol):
            raise ValueError('trial protocol or selection binding mismatch')
        recomputed = trial_result(result['rows'], sparse=name == 'sparse')
        if recomputed != result:
            raise ValueError('trial result does not recompute')
        pairs = {}
        for row in result['rows']:
            pairs.setdefault(row['task'], []).append(row)
            if row['worker'] != selections['choices'][row['condition']]:
                raise ValueError('result worker differs from frozen selection')
        if set(pairs) != set(selections['task_ids']) or any(
            len(rows) != 2 or {r['condition'] for r in rows} != {'bureau', 'control'}
            or len({r['task_content_sha256'] for r in rows}) != 1
            for rows in pairs.values()
        ):
            raise ValueError('held-out paired tasks do not match')
        cases.append({
            'scenario': name, 'synthetic': True, **result,
            'source': 'demo/bureau-allocation-001/recorded/' + name,
            'original_sha256': hashes[name + '/experiment.json'],
            'selection_sha256': hashes[name + '/selections.json'],
            'future_outcomes_available_at_selection': False,
            'measured_cost': 'signed simulated settlement only',
            'unmeasured_costs': ['labor', 'compute', 'opportunity cost'],
            'duration': None, 'real_payment': False,
        })
    return {
        'format': 'openline.bureau.economic-validation.v1',
        'synthetic': True, 'protocol': PROTOCOL, 'scenarios': cases,
        'conclusion': ('No demonstrated commercial advantage. Mixed improves completion '
                       'but loses accepted-work efficiency per settled simulated dollar; '
                       'reversal loses all four pairs; sparse is inconclusive.'),
        'trust_boundary': ('Locally controlled buyer and workers. Recorded SHA-256 checks '
                           'preserve published artifacts, not independent commercial attestation.'),
        'authorization': 'Recommendation does not authorize work. Wallet owner review and receiver enforcement remain required.',
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, help='new public JSON exhibit output')
    args = ap.parse_args(argv)
    data = exhibit()
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    print('Validated three frozen synthetic scenarios; exported no private Wallet state.')


if __name__ == '__main__':
    main()
