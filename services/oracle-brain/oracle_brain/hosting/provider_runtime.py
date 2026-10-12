"""Fixed native broker startup; external observer and admissions are never issued here.

Preparation only: no deployed external coverage observer, signed current witness,
least-privilege TLS roles, independent job/key/ledger admissions or private
provider deployment is established by this module. Their absence denies startup.
Only source-extraction responses have a fixed validator; embeddings, census,
audit and semantic-assessment dispatch remain unavailable in this profile.
"""
from datetime import datetime, timezone
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

import psycopg
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import AwareDatetime, Field

from oracle_brain.knowledge.authority import _has_authority_conn
from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes, digest
from oracle_brain.operating_model.extraction import validate_response
from oracle_brain.operating_model.key_coverage import KeyCoverageAdmission, verify_key_coverage
from oracle_brain.operating_model.native_factory import LedgerRegistry, NativeBrokerEgress, NativeDispatchJob
from oracle_brain.operating_model.source_receipts import SourceReceipt
from .egress import EgressServer
from .gateway import server_tls, unique_object
from .runtime import protected_file

HASH = r'^[a-f0-9]{64}$'


class CoverageWitness(StrictRecord):
    census_hash: str = Field(pattern=HASH)
    provider_key_record_hash: str = Field(pattern=HASH)
    ledger_identity_hash: str = Field(pattern=HASH)
    external_liability_receipt_hash: str = Field(pattern=HASH)
    observed_at: AwareDatetime


class JobContext(StrictRecord):
    job: NativeDispatchJob
    actor_id: UUID
    job_hash: str = Field(pattern=HASH)
    permission_hash: str = Field(pattern=HASH)
    receipt: SourceReceipt
    inventories: dict[str, dict]


class JobRegistry(StrictRecord):
    issuer_actor: UUID
    reviewer_actor: UUID
    runtime_hash: str = Field(pattern=HASH)
    expires_at: AwareDatetime
    contexts: tuple[JobContext, ...] = Field(min_length=1)


def read_json(path):
    return json.loads(protected_file(path), object_pairs_hook=unique_object,
                      parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def pinned(path, seal):
    raw = protected_file(path)
    if hashlib.sha256(raw).hexdigest() != seal:
        raise PermissionError('external file seal mismatch')
    return raw


def signed_coverage(path, *, public_key, admission, admission_hash, key_fingerprint, now):
    value = read_json(path)
    if not isinstance(value, dict) or set(value) != {'witness', 'signature'}:
        raise PermissionError('complete signed observer witness required')
    witness = CoverageWitness.model_validate_json(json.dumps(value['witness']))
    # Sign the exact supplied JSON representation; verification cannot rewrite timestamps.
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
        base64.b64decode(value['signature'], validate=True), canonical_bytes(value['witness']))
    return verify_key_coverage(admission, trusted_admission_hash=admission_hash,
        key_fingerprint=key_fingerprint, current_census_hash=witness.census_hash,
        current_provider_key_record_hash=witness.provider_key_record_hash,
        current_ledger_identity_hash=witness.ledger_identity_hash,
        current_external_liability_receipt_hash=witness.external_liability_receipt_hash,
        current_observed_at=witness.observed_at, now=now)


def tls_url(path):
    url = protected_file(path, limit=8192).decode().strip()
    parts = psycopg.conninfo.conninfo_to_dict(url)
    if parts.get('sslmode') != 'verify-full' or not parts.get('sslrootcert'):
        raise PermissionError('authenticated database TLS required')
    protected_file(parts['sslrootcert'])
    return url


def load_settings(path, seal):
    raw = pinned(path, seal)
    config = json.loads(raw, object_pairs_hook=unique_object)
    fields = {'profile', 'runtime_hash', 'ledger_url_file', 'metadata_url_file', 'provider_key_file',
              'ledger_registry_file', 'ledger_registry_hash', 'coverage_admission_file', 'coverage_admission_hash',
              'observer_public_key', 'coverage_witness_file', 'job_registry_file', 'job_registry_hash',
              'private_receipts', 'server_cert', 'server_key', 'client_ca', 'executor_uri', 'bind_host', 'bind_port'}
    if not isinstance(config, dict) or set(config) != fields or config['profile'] != 'provider':
        raise PermissionError('exact sealed provider settings required')
    import re
    for field in ('runtime_hash', 'ledger_registry_hash', 'coverage_admission_hash', 'job_registry_hash', 'observer_public_key'):
        if not isinstance(config[field], str) or not re.fullmatch(HASH, config[field]):
            raise PermissionError('external digest/public key pin required')
    if type(config['bind_port']) is not int or not 1 <= config['bind_port'] <= 65535:
        raise PermissionError('bounded internal port required')
    if config['bind_host'] not in {'0.0.0.0', '127.0.0.1'} or not config['executor_uri'].startswith('spiffe://oracle/'):
        raise PermissionError('fixed internal executor identity required')
    config['_ledger_url'] = tls_url(config['ledger_url_file'])
    config['_metadata_url'] = tls_url(config['metadata_url_file'])
    billing = psycopg.conninfo.conninfo_to_dict(config['_ledger_url'])
    metadata = psycopg.conninfo.conninfo_to_dict(config['_metadata_url'])
    if (billing.get('user') == metadata.get('user') or
            any(billing.get(k) != metadata.get(k) for k in ('host', 'port', 'dbname'))):
        raise PermissionError('separate metadata role on same ledger required')
    return config


class CurrentJobs:
    def __init__(self, config):
        self.config = config

    def registry(self):
        c = self.config
        raw = pinned(c['job_registry_file'], c['job_registry_hash'])
        registry = JobRegistry.model_validate_json(raw)
        if (registry.issuer_actor == registry.reviewer_actor or registry.runtime_hash != c['runtime_hash']
                or registry.expires_at <= datetime.now(timezone.utc)
                or len({ctx.job.dispatch_id for ctx in registry.contexts}) != len(registry.contexts)):
            raise PermissionError('independent current immutable job registry required')
        for ctx in registry.contexts:
            job = ctx.job
            if (job.purpose != 'source-extraction'
                    or job.request.get('model') not in {'openai/gpt-6.1-sol', 'openai/gpt-6-astra'}
                    or 'input' in job.request
                    or digest(job.model_dump(mode='json')) != ctx.job_hash
                    or job.permission_hash != ctx.permission_hash or job.workspace_id != ctx.receipt.ref.workspace_id):
                raise PermissionError('exact source extraction context required')
        return registry

    def context(self, job):
        matches = [ctx for ctx in self.registry().contexts if ctx.job.dispatch_id == job.dispatch_id]
        if len(matches) != 1 or matches[0].job != job:
            raise PermissionError('immutable current job mismatch')
        return matches[0]

    def resolve(self, identity):
        matches = [ctx.job for ctx in self.registry().contexts if ctx.job.dispatch_id == identity]
        if len(matches) != 1:
            raise PermissionError('unique admitted job required')
        return matches[0]

    def authorize(self, job):
        ctx = self.context(job)
        ref = ctx.receipt.ref
        with psycopg.connect(self.config['_metadata_url'], connect_timeout=5) as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            if not conn.info.ssl_in_use:
                raise PermissionError('metadata TLS unavailable')
            powerful = conn.execute("SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
            if not powerful or powerful[0]:
                raise PermissionError('least-privilege metadata role required')
            if conn.execute("SELECT has_table_privilege(current_user,'oracle2.operating_dispatch_reservations','INSERT')").fetchone()[0]:
                raise PermissionError('metadata role cannot reserve billing')
            if not _has_authority_conn(conn, ref.workspace_id, ctx.actor_id, 'source-read:' + str(ref.source_id)):
                raise PermissionError('current source appointment denied')
            rows = conn.execute('''SELECT s.revision,s.status,d.status FROM oracle2.sources s
                JOIN oracle2.drafts d ON d.workspace_id=s.workspace_id AND d.source_id=s.source_id
                WHERE s.workspace_id=%s AND s.source_id=%s''', (ref.workspace_id, ref.source_id)).fetchall()
            receipt = conn.execute('''SELECT original_hash,reading_hash,parser_id
                FROM oracle2.operating_model_source_receipts WHERE workspace_id=%s AND source_id=%s AND revision=%s''',
                (ref.workspace_id, ref.source_id, ref.revision)).fetchone()
            if (len(rows) != 1 or rows[0][0] != ref.revision or rows[0][1] not in {'draft', 'confirmed'}
                    or rows[0][2] != 'confirmed' or receipt != (ref.original_sha256, ref.reading_sha256, ref.parser_id)):
                raise PermissionError('current original/reading/parser metadata changed')
        if self.context(job) != ctx:
            raise PermissionError('registry changed during metadata read')
        return True

    def validate(self, job, response):
        self.authorize(job)
        ctx = self.context(job)
        validate_response(ctx.receipt, response, inventories=ctx.inventories)
        self.authorize(job)


def build_broker(config):
    registry = LedgerRegistry.model_validate_json(pinned(config['ledger_registry_file'], config['ledger_registry_hash']))
    admission = KeyCoverageAdmission.model_validate_json(pinned(config['coverage_admission_file'], config['coverage_admission_hash']))
    # Files are pinned as serialized bytes; native factories independently pin canonical typed records.
    registry_hash = digest(registry.model_dump(mode='json'))
    admission_hash = digest(admission.model_dump(mode='json'))
    if registry.transport != 'verify-full-tls':
        raise PermissionError('production profile has no synthetic provider mode')
    jobs = CurrentJobs(config)
    jobs.registry()
    key = protected_file(config['provider_key_file'], limit=8192).decode().strip()
    fingerprint = hashlib.sha256(key.encode()).hexdigest()
    def coverage():
        # Native transport checks coverage before every catalog/key read and POST.
        for context in jobs.registry().contexts:
            jobs.authorize(context.job)
        return signed_coverage(config['coverage_witness_file'], public_key=config['observer_public_key'],
            admission=admission, admission_hash=admission_hash, key_fingerprint=fingerprint,
            now=datetime.now(timezone.utc))
    coverage()
    return NativeBrokerEgress(api_key=key, ledger_url=config['_ledger_url'], registry=registry,
        trusted_registry_hash=registry_hash, coverage_receipt=coverage, trusted_coverage_hash=admission_hash,
        resolve_job=jobs.resolve, authorize_current_job=jobs.authorize, validate_response=jobs.validate,
        private_receipts=Path(config['private_receipts']))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('profile', choices=('validate', 'provider'))
    args = parser.parse_args(argv)
    if args.profile == 'validate':
        print(json.dumps({'profile': 'provider', 'admitted': False, 'company_questions': 'paused', 'grading': 'paused'}))
        return
    config = load_settings(os.environ.get('ORACLE_PROVIDER_SETTINGS', '/run/oracle-auth/provider.json'),
                           os.environ.get('ORACLE_PROVIDER_SETTINGS_SHA256', ''))
    broker = build_broker(config)
    for field in ('server_cert', 'server_key', 'client_ca'):
        protected_file(config[field])
    tls = server_tls(certfile=config['server_cert'], keyfile=config['server_key'], cafile=config['client_ca'])
    EgressServer((config['bind_host'], config['bind_port']), tls=tls, executor_uri=config['executor_uri'], egress=broker).serve_forever()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('provider profile denied or stopped', file=__import__('sys').stderr)
        raise SystemExit(1)
