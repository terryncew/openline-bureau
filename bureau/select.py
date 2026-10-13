"""Bureau's task-specific public beta shortlist, mirrored by static Exchange.

The cheapest matching offered price is the ordinary selection baseline.
Reproduced outcomes remain contextual evidence, not a universal score or an
authorization. The original allocation experiment/selector is unchanged.
"""
import argparse
import json
import math


def evaluations_for(catalog, capability, task):
    return [e for e in catalog.get('evaluations', [])
            if e.get('capability_id') == capability['id']
            and e.get('capability_version') == capability['version']
            and e.get('worker_id') is None
            and e.get('task') == task]


def select_candidates(catalog, criteria):
    """Read the reviewed compiler artifact; never run work or issue a grant."""
    if catalog.get('format') != 'openline.catalog.v1':
        raise ValueError('unsupported catalog version')
    minimum = criteria.get('minEvaluations', 1)
    try:
        minimum = int(minimum)
        if minimum < 0:
            raise ValueError
        value = criteria.get('budget')
        budget = None if value in ('', None) else float(value)
        if budget is not None and (not math.isfinite(budget) or budget < 0):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError('budget and minimum evaluations must be nonnegative finite numbers') from None

    def result(baseline, eligible, explanation):
        return {'baseline': baseline, 'eligible': eligible, 'recommendation': None,
                'abstention': explanation}

    task = criteria.get('task')
    if not task:
        return result(None, [], 'Choose one documented task. Select does not generalize evidence to other tasks.')
    if not criteria.get('basis'):
        return result(None, [], 'Choose one pricing unit so offered prices can be compared fairly.')
    offered = []
    for c in catalog.get('capabilities', []):
        p = c.get('price')
        if task not in c['tasks'] or not p or p['currency'] != criteria.get('currency') or p['basis'] != criteria['basis']:
            continue
        price = float(p['amount'])
        if math.isfinite(price) and price >= 0 and (budget is None or price <= budget):
            offered.append(c)
    offered.sort(key=lambda c: (float(c['price']['amount']), c['id'], c['version']))
    baseline = offered[0] if offered else None
    eligible = [c for c in offered if sum(
        e.get('independence') == 'SEPARATE_REVIEWED_CONTRIBUTOR'
        for e in evaluations_for(catalog, c, task)) >= minimum]
    if baseline is None:
        return result(baseline, eligible, 'No offered price matches this task, currency, pricing unit and budget. Unpriced capabilities can still be explored in the catalog.')
    if not eligible:
        return result(baseline, eligible, 'No candidate meets the independent evaluation requirement for this exact task. The cheapest offer alone is not an evidence recommendation.')
    reproduced = [[e for e in evaluations_for(catalog, c, task)
                   if e.get('independence') == 'SEPARATE_REVIEWED_CONTRIBUTOR'
                   and e.get('outcome_verification') == 'MAINTAINER_REPRODUCED'] for c in eligible]
    if catalog.get('synthetic'):
        return result(baseline, eligible, 'These are synthetic examples. No real outcome or economic benefit has been demonstrated.')
    if any(not rows for rows in reproduced):
        return result(baseline, eligible, 'Abstaining: each shortlisted candidate needs maintainer-reproduced evidence for this exact task before an evidence recommendation is supportable.')
    conditions = {json.dumps([e['task'], e['method'], e['environment'],
                             e.get('sample', {}).get('total'),
                             e.get('sample', {}).get('dataset'),
                             e.get('sample', {}).get('selection')], sort_keys=True)
                  for rows in reproduced for e in rows}
    if len(conditions) != 1:
        return result(baseline, eligible, 'Abstaining: evaluation methods, environments, datasets, sampling or sample sizes differ. Inspect the evidence without combining incompatible results.')
    return result(baseline, eligible, 'Comparable reproduced evidence is available for human review. Select does not infer future outcomes or automatically authorize a purchase.')


def main(argv=None):
    from .catalog import load_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', required=True, help='local reviewed compiled catalog JSON; no URL fetching')
    parser.add_argument('--task', required=True)
    parser.add_argument('--budget', type=float)
    parser.add_argument('--currency', default='USD')
    parser.add_argument('--basis', required=True)
    parser.add_argument('--minimum-evaluations', type=int, default=1)
    args = parser.parse_args(argv)
    result = select_candidates(load_json(args.catalog), {
        'task': args.task, 'budget': args.budget, 'currency': args.currency,
        'basis': args.basis, 'minEvaluations': args.minimum_evaluations})
    result['authorization'] = 'NONE: manual inquiry, owner review and receiver authorization remain separate.'
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
