"""$0 simulated COVERAGE-001 experiment; no provider API or public ingestion."""
import argparse
import copy
import json
from pathlib import Path
import sys

from .coverage import Coverage, ReceiverBoundary, agreement, envelope
from .store import Store


def prepare(wallet_repo, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(Path(wallet_repo).resolve() / 'demo/agent-exchange-001'))
    from exchange.kernel import Exchange
    from openline_wallet.crypto import sign_record
    x = Exchange(out / 'exchange')
    x.bootstrap(budget=1000)
    listing = x.registry.all()[0]
    buyer, worker = x.principal('owner'), listing['seller_id']
    key = x.commission_mod._load_key(x.chome, 'owner')
    store = Store(str(out / 'bureau-private.db'))
    coverage = Coverage(store, [buyer])
    # Fixed UTC epoch seconds exercise ordering without trusting imported times.
    body = agreement(buyer, worker, 1800000000, 1800000100)
    signatures = {buyer: sign_record(body, key), worker: sign_record(
        body, x.commission_mod._load_key(x.chome, listing['identity']))}
    cid = coverage.enroll(body, signatures)
    receiver = ReceiverBoundary(x, coverage, cid, out / 'receiver-private.db')
    events = []
    for i in range(8):
        p = out / f'input-{i}.txt'
        p.write_text(json.dumps({'nonce': f'coverage-{i}'}) + '\nsynthetic private customer fixture\n')
        events.append(receiver.admit(listing, p, at=1800000001 + i))
    return x, listing, store, coverage, receiver, cid, events


def outcomes(x, listing, events):
    from exchange.evidence import export_selected
    packets = []
    for i, e in enumerate(events):
        job = e['record']['job_id']
        x.deliver(job, listing['identity'], wrong_input=i >= 2)
        x.adjudicate(job)
        packets.append(export_selected(x, [job]))
    return packets


def run(wallet_repo, out):
    x, listing, store, c, receiver, cid, events = prepare(wallet_repo, out)
    buyer = x.principal('owner')
    before = x.read_json('jobs.json')
    assert all(not j.get('submission') and not j.get('verdict') and not j.get('settlement') for j in before.values())
    cp = receiver.checkpoint()
    c.anchor(cid, cp, now=1800000100)
    packets = outcomes(x, listing, events)
    source = (x.chome / 'jobs.json').read_bytes()
    for packet in packets[:2]:
        c.report(cid, packet)
    selective = c.analysis(cid, buyer, now=1800000110)
    assert selective['eligible_jobs'] == 8 and len(selective['missing_outcomes']) == 6
    assert selective['reporting_coverage'] == .25 and selective['observed_completion_rate'] is None
    for packet in packets[2:]:
        c.report(cid, packet)
    complete = c.analysis(cid, buyer, now=1800000110)
    assert complete['reporting_coverage'] == 1 and complete['observed_completion_rate'] == .25
    assert (x.chome / 'jobs.json').read_bytes() == source

    # C: genuine receipts alone do not supply a trustworthy denominator.
    unanchored_store = Store(':memory:')
    unanchored = Coverage(unanchored_store, [buyer])
    agreement_row = store.db.execute('SELECT * FROM coverage_agreements').fetchone()
    unanchored.enroll(json.loads(agreement_row['body']), json.loads(agreement_row['signatures']))
    for i in range(2):
        member = store.db.execute('SELECT * FROM sharing_jobs WHERE job_id=?', (events[i]['record']['job_id'],)).fetchone()
        unanchored_store.db.execute('INSERT INTO sharing_jobs VALUES (?,?,?,?,?)', tuple(member))
        unanchored_store.db.commit()
        unanchored.receive_admission(cid, events[i])
        unanchored.sharing.report(packets[i])
    uncertifiable = unanchored.analysis(cid, buyer, now=1800000110)
    assert uncertifiable['observed_completion_rate'] is None
    try:
        unanchored.anchor(cid, cp, now=1800000110)
    except ValueError:
        pass
    else:
        raise AssertionError('retrospective checkpoint certified disclosed outcomes')

    # Critical falsifier: an independently retained but dishonest receiver
    # declaration has only two admissions. The six unseen jobs cannot be found.
    # Use a separate fresh execution so the truncated commitment really is
    # retained before outcomes, rather than backdating an already known result.
    hx, hl, hs, honest_log, hr, hcid, hevents = prepare(wallet_repo, Path(out) / 'suppression')
    hbuyer = hx.principal('owner')
    dishonest_store = Store(':memory:')
    dishonest = Coverage(dishonest_store, [hbuyer])
    hrow = hs.db.execute('SELECT * FROM coverage_agreements').fetchone()
    dishonest.enroll(json.loads(hrow['body']), json.loads(hrow['signatures']))
    for i in range(2):
        member = hs.db.execute('SELECT * FROM sharing_jobs WHERE job_id=?', (hevents[i]['record']['job_id'],)).fetchone()
        dishonest_store.db.execute('INSERT INTO sharing_jobs VALUES (?,?,?,?,?)', tuple(member))
        dishonest_store.db.commit()
        dishonest.receive_admission(hcid, hevents[i])
    body = copy.deepcopy(hr.checkpoint()['record'])
    body['through_sequence'] = 2
    body['admission_hashes'] = body['admission_hashes'][:2]
    dishonest.anchor(hcid, envelope(body, hr.key), now=1800000100)
    hpackets = outcomes(hx, hl, hevents)
    for packet in hpackets[:2]:
        dishonest.report(hcid, packet)
    hidden = dishonest.analysis(hcid, hbuyer, now=1800000110)
    assert hidden['observed_completion_rate'] == 1 and hidden['global_completeness'] == 'NOT ESTABLISHED'
    nonmember = x.registry.all()[2]
    job = x.commission(nonmember, text='synthetic nonmember transaction')
    x.deliver(job, nonmember['identity'])
    verdict = x.adjudicate(job)
    assert verdict['verdict'] == 'accepted'
    try:
        c.analysis(cid, nonmember['seller_id'], now=1800000110)
    except PermissionError:
        denied = True
    else:
        raise AssertionError('nonmember received private analysis')
    assert store.count() == 0
    result = {'finding': 'PASS', 'complete': complete, 'selective': selective,
              'uncertifiable': uncertifiable, 'suppression_counterexample': {
                  'actual_eligible_jobs': 8, 'hidden_failures': 6, 'assessment': hidden,
                  'finding': 'GLOBAL_COMPLETENESS_NOT_ESTABLISHED'},
              'nonmember': {'transaction': verdict['verdict'], 'analysis_denied': denied},
              'public_receipt_count': store.count(), 'external_paid_api_spend_usd': 0}
    Path(out, 'coverage-report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    receiver.close()
    hr.close()
    for s in (store, unanchored_store, dishonest_store, hs):
        s.close()
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--wallet-repo', required=True)
    ap.add_argument('--out', required=True, help='new private scratch directory')
    args = ap.parse_args(argv)
    result = run(args.wallet_repo, args.out)
    print(json.dumps({k: result[k] for k in ('finding', 'complete', 'selective', 'uncertifiable', 'suppression_counterexample', 'nonmember')}, indent=2))


if __name__ == '__main__':
    main()
