"""Private receiver-relative coverage, not proof of unobserved activity.

The local operator pins receiver keys and supplies trusted UTC epoch seconds.
Keep this store independent of the reporting participant. No HTTP entry point.
"""
import json
import sqlite3

from .adapters.exchange import authentic, assess, digest
from .membership import Sharing

AGREEMENT = 'openline.bureau.coverage-agreement.v1'
ADMISSION = 'openline.bureau.coverage-admission.v1'
CHECKPOINT = 'openline.bureau.coverage-checkpoint.v1'
OBLIGATIONS = ['register_before_outcome', 'commit_all_eligible_admissions',
               'report_all_outcomes_including_failures', 'preserve_original_signed_receipts']
ADMISSION_FIELDS = ['schema', 'coverage_id', 'sequence', 'job_id', 'category',
                    'sharing_agreement_hash', 'admitted_at']
CHECKPOINT_FIELDS = ['schema', 'coverage_id', 'through_sequence', 'admission_hashes',
                     'closed_at']
PERMITTED = {'admission': ADMISSION_FIELDS, 'checkpoint': CHECKPOINT_FIELDS,
             'outcome': ['authorized_original_exchange_receipts']}


def agreement(receiver, worker, start, end, max_age=300):
    return {'schema': AGREEMENT, 'receiver': receiver, 'worker': worker,
            'categories': ['text_digest'], 'period': {'start': start, 'end': end},
            'checkpoint_max_age': max_age, 'reporting_requirements': OBLIGATIONS[:],
            'permitted_evidence': {k: v[:] for k, v in PERMITTED.items()},
            'sharing': {'visibility': 'private', 'receipt_audience': [receiver, worker],
                        'analysis_audience': [receiver, worker]}}


def envelope(body, key):
    from openline_wallet.crypto import sign_record
    return {'record': body, 'signature': sign_record(body, key)}


def _signed(value, receiver, schema, fields):
    if not isinstance(value, dict) or set(value) != {'record', 'signature'}:
        raise ValueError('unexpected signed envelope fields')
    if set(value['record']) != set(fields) or not authentic(value, receiver, schema):
        raise ValueError('invalid signature, signer, schema or evidence fields')
    signed = value['signature']
    if set(signed) != set(fields) | {'payload_hash', 'signature'} or set(
            signed['signature']) != {'algorithm', 'public_key', 'value'}:
        raise ValueError('unexpected signature metadata')
    return value['record']


def _integer(value):
    return type(value) is int


class Coverage:
    def __init__(self, store, trusted_receivers=()):
        self.store = store
        self.sharing = Sharing(store)
        self.trusted_receivers = frozenset(trusted_receivers)
        store.db.executescript('''
        CREATE TABLE IF NOT EXISTS coverage_agreements (
            coverage_id TEXT PRIMARY KEY, body TEXT NOT NULL, signatures TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS coverage_admissions (
            coverage_id TEXT NOT NULL, sequence INTEGER NOT NULL, job_id TEXT NOT NULL,
            hash TEXT NOT NULL, envelope TEXT NOT NULL,
            PRIMARY KEY (coverage_id, sequence), UNIQUE (coverage_id, job_id));
        CREATE TABLE IF NOT EXISTS coverage_checkpoints (
            coverage_id TEXT PRIMARY KEY, envelope TEXT NOT NULL, retained_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS coverage_conflicts (
            coverage_id TEXT NOT NULL, kind TEXT NOT NULL, evidence TEXT NOT NULL,
            UNIQUE (coverage_id, kind, evidence));
        ''')

    def enroll(self, body, signatures):
        expected = set(agreement('', '', 0, 1))
        if set(body) != expected or body.get('schema') != AGREEMENT:
            raise ValueError('unsupported coverage agreement fields/version')
        receiver, worker = body['receiver'], body['worker']
        if receiver not in self.trusted_receivers or receiver == worker:
            raise ValueError('independently trusted, distinct receiver required')
        if set(signatures) != {receiver, worker}:
            raise ValueError('receiver and worker must sign the exact coverage agreement')
        for p in (receiver, worker):
            _signed({'record': body, 'signature': signatures[p]}, p, AGREEMENT, expected)
        if body['categories'] != ['text_digest'] or body['reporting_requirements'] != OBLIGATIONS:
            raise ValueError('unsupported eligibility or reporting obligations')
        if body['permitted_evidence'] != PERMITTED:
            raise ValueError('unsupported or private evidence fields')
        period = body['period']
        if (set(period) != {'start', 'end'} or not all(_integer(v) for v in period.values())
                or not 0 <= period['start'] < period['end'] or not _integer(body['checkpoint_max_age'])
                or body['checkpoint_max_age'] <= 0):
            raise ValueError('finite period and positive freshness bound required')
        if body['sharing'] != {'visibility': 'private', 'receipt_audience': [receiver, worker],
                               'analysis_audience': [receiver, worker]}:
            raise ValueError('private participating-party audiences required')
        cid = digest(body)
        self.store.db.execute('INSERT OR IGNORE INTO coverage_agreements VALUES (?,?,?)',
                              (cid, json.dumps(body), json.dumps(signatures)))
        self.store.db.commit()
        return cid

    def _body(self, cid):
        row = self.store.db.execute('SELECT body FROM coverage_agreements WHERE coverage_id=?', (cid,)).fetchone()
        if not row:
            raise ValueError('coverage agreement not enrolled')
        body = json.loads(row[0])
        if body['receiver'] not in self.trusted_receivers:
            raise PermissionError('receiver is no longer trusted by this operator')
        return body

    def _conflict(self, cid, kind, value):
        # Retain authenticated equivocation. Refusing a packet must not let an
        # earlier apparently clean assessment survive conflicting evidence.
        self.store.db.execute('INSERT OR IGNORE INTO coverage_conflicts VALUES (?,?,?)',
                              (cid, kind, json.dumps(value, sort_keys=True)))
        self.store.db.commit()
        raise ValueError('conflicting ' + kind)

    def receive_admission(self, cid, value):
        body = self._body(cid)
        event = _signed(value, body['receiver'], ADMISSION, ADMISSION_FIELDS)
        period = body['period']
        if (event['coverage_id'] != cid or not _integer(event['sequence']) or event['sequence'] < 1
                or not _integer(event['admitted_at']) or not period['start'] <= event['admitted_at'] < period['end']
                or event['category'] not in body['categories']):
            raise ValueError('admission is outside the exact eligibility scope')
        member = self.sharing._agreement(event['job_id'])
        if (member['parties'] != {'buyer': body['receiver'], 'worker': body['worker']}
                or member['eligible_job']['service'] != event['category']
                or digest(member) != event['sharing_agreement_hash']
                or member['sharing'] != body['sharing']):
            raise ValueError('admission must bind the authorized private membership registration')
        h = digest(event)
        previous = self.store.db.execute(
            'SELECT hash FROM coverage_admissions WHERE coverage_id=? AND (sequence=? OR job_id=?)',
            (cid, event['sequence'], event['job_id'])).fetchall()
        if previous:
            if len(previous) != 1 or previous[0][0] != h:
                self._conflict(cid, 'admission', value)
            return h
        checkpoint = self.store.db.execute('SELECT envelope FROM coverage_checkpoints WHERE coverage_id=?', (cid,)).fetchone()
        if checkpoint:
            committed = json.loads(checkpoint[0])['record']['admission_hashes']
            if event['sequence'] > len(committed) or committed[event['sequence'] - 1] != h:
                self._conflict(cid, 'admission_after_commitment', value)
            if self.store.db.execute('SELECT 1 FROM sharing_reports WHERE job_id=?', (event['job_id'],)).fetchone():
                self._conflict(cid, 'outcome_disclosed_before_registration_delivery', value)
        self.store.db.execute('INSERT INTO coverage_admissions VALUES (?,?,?,?,?)',
                              (cid, event['sequence'], event['job_id'], h, json.dumps(value)))
        self.store.db.commit()
        return h

    def anchor(self, cid, value, *, now):
        """Independent Bureau retention, never a participant-provided receipt time."""
        body = self._body(cid)
        checkpoint = _signed(value, body['receiver'], CHECKPOINT, CHECKPOINT_FIELDS)
        hashes = checkpoint['admission_hashes']
        if (checkpoint['coverage_id'] != cid or not _integer(now)
                or not _integer(checkpoint['closed_at'])
                or checkpoint['closed_at'] != body['period']['end']
                or now < checkpoint['closed_at']
                or not _integer(checkpoint['through_sequence']) or checkpoint['through_sequence'] < 0
                or not isinstance(hashes, list) or checkpoint['through_sequence'] != len(hashes)
                or len(set(hashes)) != len(hashes)
                or any(not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h) for h in hashes)):
            raise ValueError('invalid closing coverage commitment')
        previous = self.store.db.execute('SELECT envelope FROM coverage_checkpoints WHERE coverage_id=?', (cid,)).fetchone()
        if previous:
            if json.loads(previous[0])['record'] != checkpoint:
                self._conflict(cid, 'checkpoint', value)
            return  # Replay does not refresh retention/freshness.
        existing = self.store.db.execute('SELECT a.job_id FROM coverage_admissions a JOIN sharing_reports r ON a.job_id=r.job_id WHERE coverage_id=?', (cid,)).fetchall()
        if existing:
            raise ValueError('checkpoint received after outcomes were disclosed')
        self.store.db.execute('INSERT INTO coverage_checkpoints VALUES (?,?,?)', (cid, json.dumps(value), now))
        self.store.db.commit()

    def report(self, cid, packet):
        body = self._body(cid)
        if not self.store.db.execute('SELECT 1 FROM coverage_checkpoints WHERE coverage_id=?', (cid,)).fetchone():
            raise ValueError('independent pre-outcome checkpoint required')
        jobs = packet.get('jobs', [])
        if len(jobs) != 1:
            raise ValueError('report one authorized original transaction')
        job = jobs[0]
        if not self.store.db.execute('SELECT 1 FROM coverage_admissions WHERE coverage_id=? AND job_id=?', (cid, job['job_id'])).fetchone():
            raise ValueError('missing receiver registration')
        member = self.sharing._agreement(job['job_id'])
        self.sharing._validate_job(job, member)
        a = job['agreement']['record']
        signers = {'agreement': a['agent'], 'offer': body['worker'], 'submission': body['worker'],
                   'verdict': body['receiver'], 'settlement': body['receiver']}
        for phase, p in signers.items():
            e = job.get(phase)
            if e and not authentic(e, p, e['record'].get('schema')):
                raise ValueError('forged or untrusted ' + phase)
        # Existing Sharing enforces authorized fields and append-only phase updates.
        self.sharing.report(packet)

    def analysis(self, cid, requester, *, now):
        body = self._body(cid)
        Sharing._access({'sharing': body['sharing'], 'parties': {'buyer': body['receiver'], 'worker': body['worker']}},
                        requester, 'private', 'analysis')
        if not _integer(now):
            raise ValueError('operator time must be UTC epoch seconds')
        rows = self.store.db.execute('SELECT * FROM coverage_admissions WHERE coverage_id=? ORDER BY sequence', (cid,)).fetchall()
        anchor = self.store.db.execute('SELECT * FROM coverage_checkpoints WHERE coverage_id=?', (cid,)).fetchone()
        issues = []
        missing_sequences = []
        if not anchor:
            issues.append('NO_INDEPENDENT_CHECKPOINT')
            denominator = None
        else:
            cp = json.loads(anchor['envelope'])['record']
            denominator = cp['through_sequence']
            known = {r['sequence']: r['hash'] for r in rows}
            missing_sequences = [i for i in range(1, denominator + 1) if i not in known]
            if missing_sequences:
                issues.append('MISSING_REGISTRATIONS_OR_SEQUENCE_GAPS')
            if any(i > denominator or cp['admission_hashes'][i - 1] != h for i, h in known.items()):
                issues.append('REGISTRATION_COMMITMENT_MISMATCH')
            if now < anchor['retained_at'] or now - cp['closed_at'] > body['checkpoint_max_age']:
                issues.append('STALE_OR_FUTURE_CHECKPOINT')
        if self.store.db.execute('SELECT 1 FROM coverage_conflicts WHERE coverage_id=?', (cid,)).fetchone():
            issues.append('CONFLICTING_SIGNED_EVIDENCE')
        incomplete, missing, missing_settlements = [], [], []
        verified, settled, successes, failures, reported, executed = 0, 0, 0, 0, 0, 0
        for row in rows:
            report = self.store.db.execute('SELECT packet FROM sharing_reports WHERE job_id=?', (row['job_id'],)).fetchone()
            job = json.loads(report[0])['jobs'][0] if report else None
            status = assess(job, [body['receiver']]) if job else {}
            reported += bool(report)
            executed += bool(job and authentic(job.get('submission'), body['worker'], 'commission.result.v1'))
            verified += bool(status.get('accepted') or status.get('rejected'))
            settled += bool(status.get('settled'))
            success = bool(status.get('accepted') and status.get('settled'))
            failure = bool(status.get('rejected'))
            successes += bool(status.get('accepted'))
            failures += failure
            if not (status.get('accepted') or failure):
                missing.append(row['job_id'])
            if status.get('accepted') and not success:
                missing_settlements.append(row['job_id'])
            if not (success or failure):
                incomplete.append(row['job_id'])
        complete = not issues and not incomplete and denominator is not None and denominator > 0
        return {'coverage_id': cid, 'status': 'COMPLETE_FOR_COMMITTED_BOUNDARY' if complete else 'NOT_ESTABLISHED' if issues else 'INCOMPLETE',
                'eligible_jobs': denominator, 'admissions_received': len(rows),
                'missing_registration_sequences': missing_sequences, 'missing_outcomes': missing,
                'missing_settlements': missing_settlements, 'incomplete_jobs': incomplete,
                'reports_received': reported, 'execution_receipts': executed,
                'verified_outcomes': verified, 'settled_successes': settled,
                'verified_successes': successes, 'verified_failures': failures,
                'reporting_coverage': verified / denominator if not issues and denominator else None,
                'observed_completion_rate': successes / denominator if complete else None,
                'issues': issues, 'global_completeness': 'NOT ESTABLISHED',
                'boundary': 'only eligible admissions at the specified honest receiver boundary covered by the independently retained commitment; hidden, off-platform and uninstrumented activity is unknown'}


class ReceiverBoundary:
    """Enrolled local admission wrapper; the Exchange engine remains unchanged.

    The receiver journal is distinct from Bureau's independently retained store.
    A durable registration precedes commissioning, execution and verification.
    Bypassing this wrapper is precisely the uninstrumented-activity trust limit.
    """
    def __init__(self, x, coverage, cid, journal):
        self.x, self.coverage, self.cid = x, coverage, cid
        self.key = x.commission_mod._load_key(x.chome, 'owner')
        self.db = sqlite3.connect(str(journal))
        self.db.execute('CREATE TABLE IF NOT EXISTS admissions (coverage_id TEXT, sequence INTEGER, job_id TEXT, envelope TEXT, PRIMARY KEY(coverage_id,sequence), UNIQUE(coverage_id,job_id))')
        self.db.commit()

    def admit(self, listing, input_path, *, at):
        from .membership import proposal
        from openline_wallet.crypto import sign_record
        member = proposal(self.x, listing, input_path)
        job_id = member['eligible_job']['job_id']
        previous = self.db.execute('SELECT envelope FROM admissions WHERE coverage_id=? AND job_id=?', (self.cid, job_id)).fetchone()
        if previous:
            value = json.loads(previous[0])
        else:
            signatures = {
                member['parties']['buyer']: sign_record(member, self.key),
                member['parties']['worker']: sign_record(member, self.x.commission_mod._load_key(self.x.chome, listing['identity']))}
            self.coverage.sharing.register(self.x, member, signatures)
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                seq = self.db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM admissions WHERE coverage_id=?', (self.cid,)).fetchone()[0]
                value = envelope({'schema': ADMISSION, 'coverage_id': self.cid, 'sequence': seq,
                                  'job_id': job_id, 'category': listing['service'],
                                  'sharing_agreement_hash': digest(member), 'admitted_at': at}, self.key)
                # Validate against the enrolled scope before committing the receiver log.
                self.coverage.receive_admission(self.cid, value)
                self.db.execute('INSERT INTO admissions VALUES (?,?,?,?)', (self.cid, seq, job_id, json.dumps(value)))
        self.coverage.receive_admission(self.cid, value)
        actual = self.x.commission(listing, input_path=str(input_path))
        if actual != job_id:
            raise ValueError('receiver admission differs from commissioned job')
        return value

    def checkpoint(self):
        body = self.coverage._body(self.cid)
        rows = self.db.execute('SELECT envelope FROM admissions WHERE coverage_id=? ORDER BY sequence', (self.cid,)).fetchall()
        return envelope({'schema': CHECKPOINT, 'coverage_id': self.cid,
                         'through_sequence': len(rows),
                         'admission_hashes': [digest(json.loads(r[0])['record']) for r in rows],
                         'closed_at': body['period']['end']}, self.key)

    def close(self):
        self.db.close()
