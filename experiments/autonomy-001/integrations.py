"""Thin bindings to pinned Receipt Gate and Airlock; no agent reasoning here."""
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from olp_gate.adapters import TrustStore
from olp_gate.crypto import (generate_private_key_file, load_private_key,
    public_key_hex, sign_olp_body, verify_olp_signature, sha256_hex,
    olp_canonical_json, jcs_integer_canonical_json)
from olp_gate.demo import _agent_receipt, _source_hash
from olp_gate.evidence import issue_outcome_receipt
from olp_gate.gateway import evaluate_request
from olp_gate.policy import PolicySpec
from olp_gate.session import SessionLedger
from olp_gate.verified_commit import VerifiedCommitLedger, issue_one_use_code, settings_hash
from airlock.providers.registry import resolve_provider
from airlock_submit.worker import _docker_result

IMAGE = 'python@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce'
LIMITS = {'pids_limit': 64, 'memory': '256m', 'cpus': 1}


def durable_write(path, obj):
    """Atomic file replacement plus data and directory durability."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(obj, f, sort_keys=True, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def signing_key(state_dir, name='receiver'):
    import fcntl
    root = Path(state_dir)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'keys.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / 'keys' / (name + '.key')
        if not path.exists():
            generate_private_key_file(path)
            with path.open('rb') as f:
                os.fsync(f.fileno())
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return load_private_key(path)


def isolated_run(workspace, argv, timeout=120):
    """Use Airlock's credential-free Docker executor, with no host fallback.

    Workspace must be an exported tree without Git pointers to host metadata.
    Image is digest pinned, pulls disabled, network disabled, limits enforced.
    """
    if (Path(workspace) / '.git').exists():
        raise ValueError('sandbox workspace must not contain Git metadata')
    # Trusted in-container supervisor limits output and kills the container's
    # workload by exiting even if the host Docker client/controller is killed.
    supervisor = (
        "import subprocess,sys,tempfile,resource; "
        "resource.setrlimit(resource.RLIMIT_FSIZE,(2097152,2097152)); "
        "out=tempfile.TemporaryFile(); err=tempfile.TemporaryFile(); "
        "\ntry:\n p=subprocess.run(sys.argv[2:],stdout=out,stderr=err,timeout=int(sys.argv[1]))"
        "\nexcept subprocess.TimeoutExpired:\n sys.exit(124)"
        "\nfor f,dst in [(out,sys.stdout.buffer),(err,sys.stderr.buffer)]:"
        "\n f.seek(0,2); n=f.tell(); f.seek(max(0,n-2000)); dst.write(f.read())"
        "\nsys.exit(p.returncode)"
    )
    return _docker_result(Path(workspace), IMAGE,
        ['python', '-I', '-c', supervisor, str(timeout), *argv], LIMITS, timeout + 15)


def issue_permission(state_dir, action_core, evidence, policy_binding):
    """Receipt Gate evaluates local receiver evidence and exact action binding.

    The source and witness are separate keys under ONE operator, not external
    independent attestation. No claim of model identity or software improvement.
    """
    root = Path(state_dir) / 'gate' / evidence['task_id']
    root.mkdir(parents=True, exist_ok=True)
    durable_write(root / 'evidence.json', evidence)
    artifact_hash = sha256_hex((root / 'evidence.json').read_bytes())
    run = evidence['operation_id']
    source_key = signing_key(state_dir, 'source')
    witness_key = signing_key(state_dir, 'witness')
    gate_key = signing_key(state_dir)
    method = 'did:example:autonomy-local-evaluator#key-1'
    now = datetime.now(timezone.utc)
    source = _agent_receipt(key=source_key, method=method, chain_id=run,
        session_id=run, action_id=run, action_type='tool_call',
        response_hash=artifact_hash, timestamp=now.isoformat())
    # Reidentify and resign the existing Receipt Gate wire builder's output.
    source.pop('proof')
    source['issuer']['id'] = 'did:example:autonomy-local-evaluator'
    source['credentialSubject']['principal']['id'] = 'owner:Terrynce White'
    sig = source_key.sign(jcs_integer_canonical_json(source))
    source['proof'] = {'type': 'Ed25519Signature2020', 'created': now.isoformat(),
        'verificationMethod': method, 'proofPurpose': 'assertionMethod',
        'proofValue': 'u' + base64.urlsafe_b64encode(sig).decode().rstrip('=')}
    sessions = SessionLedger(root / 'sessions.json')
    binding = sessions.issue_challenge(run_id=run, session_id=run,
        expected_source_hash=_source_hash(source))
    action = {**action_core, 'run_id': run, 'capsule_hash': policy_binding,
              'evidence_hashes': [artifact_hash]}
    policy = PolicySpec.from_mapping({'policy_id': 'autonomy-001.local-receiver',
        'version': '1.5', 'require_declared_coverage': True,
        'require_outcome_witness': True, 'required_evidence_ids': ['result'],
        'evidence_assertions': [{'evidence_id': 'result', 'path': 'eligible',
                                 'op': 'equals', 'value': True}],
        'metadata': {'verified_commit': {'required': True,
            'tool': action['tool'], 'target': action['target'],
            'settings_hash': settings_hash(action['settings']), 'run_id': run,
            'capsule_hash': policy_binding, 'evidence_hashes': [artifact_hash],
            'max_ttl_seconds': 120}}})
    action['policy_hash'] = policy.policy_hash
    code = issue_one_use_code()
    store = TrustStore.from_mapping({'keys': {
        method: {'public_key': public_key_hex(source_key), 'roles': ['source'],
                 'independence': 'operator', 'controller': 'local-source'},
        public_key_hex(witness_key): {'public_key': public_key_hex(witness_key),
            'roles': ['outcome'], 'independence': 'receiver', 'controller': 'local-receiver'}}})
    request = {'schema': 'openline.proof_to_policy.request.v0.2',
        'request_id': run, 'action_type': 'tool_call',
        'claim': 'Exact isolated branch update authorized by existing policy',
        'source_receipts': [source], 'binding': binding,
        'evidence': [{'id': 'result', 'artifact_path': 'evidence.json',
            'content_hash': artifact_hash,
            'source_commitment_path': 'credentialSubject.outcome.response_hash'}],
        'outcome_receipt': issue_outcome_receipt(source_receipt_hash=_source_hash(source),
            outcome_status='pass', harmful=False, evidence_hash=artifact_hash,
            witness_id='local-receiver', rollback_supported=True, key=witness_key),
        'commit_request': {**action, 'expires_at': (now + timedelta(seconds=90)).isoformat(),
                           'one_use_code': code}}
    durable_write(root / 'proof-inputs.json', {
        'source_receipts': request['source_receipts'],
        'outcome_receipt': request['outcome_receipt'], 'policy': policy.as_dict(),
        'binding': binding, 'action': action})
    receipt = evaluate_request(request, policy=policy, trust_store=store,
        signing_key=gate_key, issuer_id='autonomy-001-local-receiver',
        decision_path=root / 'decisions.jsonl', session_ledger=sessions,
        base_dir=root, now=now)
    durable_write(root / 'permission.json', receipt)
    if receipt['decision'] != 'COMMIT':
        raise RuntimeError('Receipt Gate refused: ' + repr(receipt['reason_codes']))
    return receipt, action, code
