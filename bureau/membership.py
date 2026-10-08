"""Private local reciprocal-sharing foundation, separate from the open protocol.

No HTTP authentication, billing, legal consent or production membership system.
The local operator supplies the requesting principal, as in the Exchange's
trusted-operator preview. Original signed transaction bodies remain unchanged.
"""
import json
from datetime import datetime, timezone

from .adapters.exchange import authentic, assess, digest, FORMAT

SCHEMA = 'openline.bureau.evidence-sharing.v1'
OBLIGATIONS = ['register_before_work', 'report_all_eligible_attempts',
               'report_all_outcomes_including_failures', 'preserve_original_signed_receipts']
FIELDS = {
    'commission.agreement.v1': ['schema','job_id','buyer','agent','seller','payee','offer_id','service','input_sha256','nonce','deliverable','acceptance','amount','currency','deadline','rules'],
    'commission.offer.v1': ['schema','offer_id','seller','service','deliverable','acceptance','price','currency','note'],
    'commission.result.v1': ['schema','job_id','service','input_sha256','word_count','line_count','nonce'],
    'commission.verdict.v1': ['schema','job_id','verdict','agreement_hash','checks','verified_by','at'],
    'commission.settlement.v1': ['schema','job_id','agreement_hash','verdict_hash','settlement_id','amount','currency','from','to','note','at'],
}


def proposal(x, listing, input_path, agent='agent', readers=None):
    """Freeze scope for one exact future commission before it exists."""
    from pathlib import Path
    import hashlib
    raw = Path(input_path).read_bytes(); nonce = json.loads(raw.splitlines()[0])['nonce']
    buyer, worker, agent_principal = x.principal('owner'), listing['seller_id'], x.principal(agent)
    request_id = x.commission_mod._request_id(agent_principal, listing['offer_id'], nonce)
    return {'schema': SCHEMA, 'version': 1, 'bureau': 'local-allocation-bureau',
            'parties': {'buyer': buyer, 'worker': worker},
            'eligible_job': {'job_id': 'job-' + request_id[4:16], 'agent': agent_principal,
                             'offer_id': listing['offer_id'], 'service': listing['service'],
                             'input_sha256': hashlib.sha256(raw).hexdigest(), 'nonce': nonce},
            'permitted_receipt_fields': {schema: fields[:] for schema, fields in FIELDS.items()},
            'reporting_obligations': OBLIGATIONS[:],
            'sharing': {'visibility': 'private', 'receipt_audience': [buyer, worker],
                        'analysis_audience': readers or [buyer, worker]},
            'boundary': 'local technical agreement, not legal consent; registered commissions only; physical work attempts may be unknown'}


class Sharing:
    """Retains private registrations/reports outside the public receipt table."""
    def __init__(self, store):
        self.store = store
        store.db.executescript('''
        CREATE TABLE IF NOT EXISTS sharing_jobs (
            job_id TEXT PRIMARY KEY, agreement_id TEXT NOT NULL,
            agreement TEXT NOT NULL, signatures TEXT NOT NULL, registered_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sharing_reports (
            job_id TEXT PRIMARY KEY, packet TEXT NOT NULL);
        ''')

    def register(self, x, agreement, signatures):
        if set(agreement) != {'schema','version','bureau','parties','eligible_job','permitted_receipt_fields',
                              'reporting_obligations','sharing','boundary'}:
            raise ValueError('unexpected sharing agreement fields')
        if agreement.get('schema') != SCHEMA or agreement.get('version') != 1:
            raise ValueError('unsupported sharing agreement version')
        if agreement.get('reporting_obligations') != OBLIGATIONS:
            raise ValueError('all eligible attempts and outcomes, including failures, must be reportable')
        parties = agreement['parties']
        if set(parties) != {'buyer', 'worker'} or parties['buyer'] == parties['worker']:
            raise ValueError('distinct buyer and worker parties required')
        if set(signatures) != set(parties.values()) or not all(
                authentic({'record': agreement, 'signature': signatures[p]}, p, SCHEMA)
                for p in parties.values()):
            raise ValueError('each participating party must sign the exact agreement')
        permitted = agreement['permitted_receipt_fields']
        if set(permitted) != set(FIELDS) or any(not set(permitted[s]) <= set(FIELDS[s]) for s in FIELDS):
            raise ValueError('sharing fields must stay within the supported public receipt schemas')
        scope = agreement['sharing']
        if set(scope) != {'visibility','receipt_audience','analysis_audience'}:
            raise ValueError('unexpected sharing scope fields')
        if scope['visibility'] not in ('private', 'public') or any(
                not isinstance(scope.get(k), list) or not scope[k]
                for k in ('receipt_audience','analysis_audience')):
            raise ValueError('explicit receipt and analysis audiences required')
        if scope['visibility'] == 'private' and any('public' in scope[k] for k in ('receipt_audience','analysis_audience')):
            raise ValueError('public audience requires explicit public visibility')
        expected = agreement['eligible_job']
        if set(expected) != {'job_id','agent','offer_id','service','input_sha256','nonce'}:
            raise ValueError('unexpected eligible job fields')
        job_id = expected['job_id']
        calculated = 'job-' + x.commission_mod._request_id(expected['agent'], expected['offer_id'], expected['nonce'])[4:16]
        if job_id != calculated or not any(l['seller_id'] == parties['worker'] and l['offer_id'] == expected['offer_id']
                                           and l['service'] == expected['service'] == 'text_digest'
                                           for l in x.registry.all()):
            raise ValueError('eligible job must name an existing local offer and exact future request')
        if job_id in x.read_json('jobs.json', {}):
            raise ValueError('sharing must be registered before the eligible job begins')
        if parties['buyer'] != x.principal('owner'):
            raise ValueError('sharing buyer does not match the local receiver')
        aid = digest(agreement)
        previous = self.store.db.execute('SELECT agreement_id FROM sharing_jobs WHERE job_id=?', (job_id,)).fetchone()
        if previous:
            if previous[0] != aid: raise ValueError('registered sharing scope is immutable')
            return aid
        self.store.db.execute('INSERT INTO sharing_jobs VALUES (?,?,?,?,?)',
                              (job_id, aid, json.dumps(agreement), json.dumps(signatures), datetime.now(timezone.utc).isoformat()))
        self.store.db.commit()
        return aid

    def _agreement(self, job_id):
        row = self.store.db.execute('SELECT * FROM sharing_jobs WHERE job_id=?', (job_id,)).fetchone()
        if not row: raise ValueError('eligible job was not registered')
        return json.loads(row['agreement'])

    @staticmethod
    def _validate_job(job, agreement):
        if set(job) - {'job_id','agreement','offer','submission','verdict','settlement'}:
            raise ValueError('private input paths or extra data cannot enter sharing evidence')
        a = job['agreement']['record']; expected = agreement['eligible_job']
        if job['job_id'] != expected['job_id'] or a.get('buyer') != agreement['parties']['buyer'] or a.get('seller') != agreement['parties']['worker']:
            raise ValueError('reported transaction has different parties or job')
        if any(a.get(k) != expected[k] for k in ('job_id','agent','offer_id','service','input_sha256','nonce')):
            raise ValueError('reported transaction differs from the registered exact job')
        for phase in ('agreement','offer','submission','verdict','settlement'):
            envelope = job.get(phase)
            if not envelope: continue
            if set(envelope) != {'record','signature'}: raise ValueError('unexpected sharing envelope fields')
            record = envelope['record']; schema = record.get('schema')
            permitted = agreement['permitted_receipt_fields'].get(schema)
            if permitted is None or not set(record) <= set(permitted):
                raise PermissionError('original signed receipt exceeds authorized field scope; do not redact and claim the signature survives')
            signed_body = {k:v for k,v in envelope['signature'].items() if k not in ('signature','payload_hash')}
            if signed_body != record: raise ValueError('original signed evidence has been changed')
            metadata = envelope['signature'].get('signature', {})
            if set(metadata) != {'algorithm','public_key','value'}:
                raise PermissionError('signature metadata contains unauthorized fields')

    def report(self, packet):
        if packet.get('format') != FORMAT or len(packet.get('jobs', [])) != 1:
            raise ValueError('report exactly one selected registered job')
        job = packet['jobs'][0]; agreement = self._agreement(job['job_id'])
        self._validate_job(job, agreement)
        # Advertisements and unrelated metadata are unnecessary here. Preserve
        # the exact original signed bodies and their source-file hash.
        source = packet.get('source') or {}
        if set(source) != {'record_file','sha256'} or source['record_file'] != 'commission/jobs.json':
            raise PermissionError('unexpected source metadata cannot enter sharing evidence')
        selected = {'format': FORMAT, 'source': source, 'jobs': [job]}
        prior = self.store.db.execute('SELECT packet FROM sharing_reports WHERE job_id=?', (job['job_id'],)).fetchone()
        if prior:
            old = json.loads(prior[0])['jobs'][0]
            for phase in ('agreement','offer','submission','verdict','settlement'):
                if old.get(phase) and old.get(phase) != job.get(phase):
                    raise ValueError('report update cannot erase or replace original evidence')
        self.store.db.execute('INSERT OR REPLACE INTO sharing_reports VALUES (?,?)', (job['job_id'], json.dumps(selected)))
        self.store.db.commit()

    @staticmethod
    def _access(agreement, requester, destination, kind):
        scope = agreement['sharing']; audience = scope[kind + '_audience']
        if destination == 'public':
            if scope['visibility'] != 'public' or 'public' not in audience:
                raise PermissionError('public sharing is not authorized')
            if requester not in agreement['parties'].values():
                raise PermissionError('only a participating local party may request publication')
        elif destination == 'private':
            if requester not in audience: raise PermissionError('requester is outside the authorized sharing audience')
        else: raise PermissionError('unsupported sharing destination')

    def export_report(self, job_id, requester, destination='private'):
        agreement = self._agreement(job_id)
        self._access(agreement, requester, destination, 'receipt')
        row = self.store.db.execute('SELECT packet FROM sharing_reports WHERE job_id=?', (job_id,)).fetchone()
        if not row: raise ValueError('report is incomplete: no evidence contributed')
        packet = json.loads(row[0]); self._validate_job(packet['jobs'][0], agreement)
        return packet

    def analysis(self, requester, destination='private'):
        registrations = self.store.db.execute('SELECT * FROM sharing_jobs ORDER BY job_id').fetchall()
        agreements = [json.loads(r['agreement']) for r in registrations]
        if not any(requester in a['parties'].values() for a in agreements):
            raise PermissionError('nonparticipant is not eligible for this Bureau membership analysis')
        visible = []
        for agreement in agreements:
            if destination == 'public': self._access(agreement, requester, destination, 'analysis')
            elif requester not in agreement['sharing']['analysis_audience']: continue
            else: self._access(agreement, requester, destination, 'analysis')
            visible.append(agreement)
        if not visible: raise PermissionError('no shared analysis is authorized for this member')
        workers = {}
        for agreement in visible:
            worker = agreement['parties']['worker']; job_id = agreement['eligible_job']['job_id']
            row = workers.setdefault(worker, {'worker':worker, 'registered_eligible_jobs':0,
                                             'accepted':0, 'rejected':0, 'incomplete_jobs':[], 'job_ids':[]})
            row['registered_eligible_jobs'] += 1; row['job_ids'].append(job_id)
            report = self.store.db.execute('SELECT packet FROM sharing_reports WHERE job_id=?', (job_id,)).fetchone()
            status = assess(json.loads(report[0])['jobs'][0], [agreement['parties']['buyer']]) if report else {}
            complete = bool(status.get('rejected') or status.get('accepted') and status.get('settled'))
            if not complete: row['incomplete_jobs'].append(job_id)
            row['accepted'] += bool(status.get('accepted')); row['rejected'] += bool(status.get('rejected'))
        for row in workers.values():
            row['accepted_fraction'] = None if row['incomplete_jobs'] else row['accepted']/row['registered_eligible_jobs']
            row['reporting_status'] = 'INCOMPLETE' if row['incomplete_jobs'] else 'COMPLETE_FOR_REGISTERED_JOBS'
            row['work_attempt_count'] = None  # original Exchange does not enumerate all physical attempts
        total = sum(r['registered_eligible_jobs'] for r in workers.values())
        missing = [job for r in workers.values() for job in r['incomplete_jobs']]
        return {'participating': True, 'access_eligible': True, 'visibility': destination,
                'registered_eligible_jobs': total, 'incomplete_jobs': missing,
                'accepted_fraction': None if missing else sum(r['accepted'] for r in workers.values())/total,
                'workers': list(workers.values()),
                'boundary': 'private local role policy, not production authentication or legal consent; completeness only for registered eligible commissions'}
