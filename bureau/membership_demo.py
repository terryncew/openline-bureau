"""Small subordinate example; does not alter the allocation trial."""
import argparse
import json
import sys
from pathlib import Path

from .membership import Sharing, proposal
from .store import Store


def run(wallet_repo, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(Path(wallet_repo).resolve()/'demo/agent-exchange-001'))
    from exchange.kernel import Exchange
    from exchange.evidence import export_selected
    from openline_wallet.crypto import sign_record
    x = Exchange(out/'exchange'); x.bootstrap(budget=300)
    store = Store(str(out/'membership-private.db')); sharing = Sharing(store)
    listings = x.registry.all(); buyer = x.principal('owner')
    readers = [buyer, listings[0]['seller_id'], listings[1]['seller_id']]
    registrations = []
    # Both versioned agreements are durably registered before either job begins.
    for i, listing in enumerate(listings[:2]):
        path = out/f'participating-{i}.txt'
        path.write_text(json.dumps({'nonce':f'membership-{i}'})+'\npublic membership fixture\n')
        body = proposal(x, listing, path, readers=readers)
        signatures = {buyer:sign_record(body,x.commission_mod._load_key(x.chome,'owner')),
                      listing['seller_id']:sign_record(body,x.commission_mod._load_key(x.chome,listing['identity']))}
        aid = sharing.register(x,body,signatures)
        registrations.append((listing,path,body,aid))
    jobs = []
    for i, (listing,path,body,aid) in enumerate(registrations):
        job = x.commission(listing,input_path=str(path)); assert job == body['eligible_job']['job_id']
        x.deliver(job,listing['identity'],wrong_input=i==1); x.adjudicate(job);jobs.append(job)
        if i==0: sharing.report(export_selected(x,[job]))
    omitted = sharing.analysis(buyer)
    assert omitted['registered_eligible_jobs']==2 and omitted['accepted_fraction'] is None
    assert jobs[1] in omitted['incomplete_jobs']
    sharing.report(export_selected(x,[jobs[1]]))
    complete = sharing.analysis(buyer)
    assert complete['accepted_fraction']==.5
    # The open transaction protocol remains available to a nonmember.
    nonmember = listings[2]
    job = x.commission(nonmember,text='public nonmember transaction')
    x.deliver(job,nonmember['identity']); verdict=x.adjudicate(job)
    assert verdict['verdict']=='accepted'
    try:sharing.analysis(nonmember['seller_id'])
    except PermissionError: access='DENIED_NOT_PARTICIPATING'
    else:raise AssertionError('nonmember received private shared analysis')
    try:sharing.export_report(jobs[0],buyer,destination='public')
    except PermissionError: publication='DENIED_PRIVATE_SCOPE'
    else:raise AssertionError('private evidence published')
    report={'label':'LOCAL SYNTHETIC RECIPROCAL-SHARING FOUNDATION',
            'registered_before_commission':[{'agreement_id':aid,'job_id':body['eligible_job']['job_id']} for _,_,body,aid in registrations],
            'omitted_failure':omitted, 'completed_reporting':complete,
            'nonparticipant':{'protocol_transaction':verdict['verdict'],'shared_analysis':access},
            'public_export':publication, 'default_visibility':'private',
            'public_receipt_table_count':store.count(),
            'boundary':'local operator role policy; no production authentication, legal consent or selective disclosure claim'}
    (out/'membership-report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    # Agreements, reports and keys stay in the private database/home. This
    # standalone demonstration summary uses only explicitly public fixture facts.
    store.close();return report


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--wallet-repo',required=True);ap.add_argument('--out',required=True)
    args=ap.parse_args(argv);report=run(args.wallet_repo,args.out)
    print(json.dumps({'registered_jobs':2,'missing_report_rate':None,
                      'reported_rate':report['completed_reporting']['accepted_fraction'],
                      'nonparticipant':report['nonparticipant'],'publication':report['public_export']},indent=2))


if __name__=='__main__':main()
