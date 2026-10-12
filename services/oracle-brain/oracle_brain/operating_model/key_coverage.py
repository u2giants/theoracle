"""Externally admitted coverage of every consumer of the owner-budgeted key.

This is a receipt verifier, not a caller-discovery or deployment mechanism.
An issuer must independently establish the census and live central reservation
path; passing caller-supplied booleans cannot authorize private dispatch.
"""
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from .contracts import StrictRecord, digest


class KeyConsumer(StrictRecord):
    consumer_id: str = Field(min_length=1)
    runtime_revision_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    mode: Literal['central-reservation', 'read-only-catalog', 'inactive-preserved']
    proof_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class KeyCoverageAdmission(StrictRecord):
    domain: Literal['existing-owner-authorized-oracle-key']
    key_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    provider_key_record_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    consumers: tuple[KeyConsumer, ...]
    census_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    ledger_identity_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    external_liability_receipt_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    issuer_actor: UUID
    reviewer_actor: UUID
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    census_complete: Literal[True]
    unreserved_paid_callers: Literal[0]
    unreserved_outstanding_liabilities: Literal[0]

    @field_validator('unreserved_paid_callers', 'unreserved_outstanding_liabilities', mode='before')
    @classmethod
    def literal_counts(cls, value):
        if type(value) is not int or value != 0:
            raise ValueError('a strict zero unreserved population is required')
        return value

    @field_validator('census_complete', mode='before')
    @classmethod
    def literal_complete(cls, value):
        if value is not True:
            raise ValueError('complete census requires literal true')
        return value


class VerifiedKeyCoverage(StrictRecord):
    admission_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    key_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    ledger_identity_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    observed_at: AwareDatetime
    expires_at: AwareDatetime


def verify_key_coverage(admission: KeyCoverageAdmission, *, trusted_admission_hash: str,
                        key_fingerprint: str, current_census_hash: str,
                        current_ledger_identity_hash: str,
                        current_external_liability_receipt_hash: str,
                        current_observed_at: datetime,
                        now: datetime) -> VerifiedKeyCoverage:
    """Inputs named current are trusted coordinator readbacks, not model output.

    The admission hash is supplied out of band by the independent review issuer.
    A zero-liability receipt must cover old local readers, queued cloud calls and
    delayed/batch charges as well as live callers; an absent census cannot pass.
    """
    admission_hash = digest(admission.model_dump(mode='json'))
    if admission_hash != trusted_admission_hash or admission.issuer_actor == admission.reviewer_actor:
        raise PermissionError('independent externally trusted key coverage required')
    if (now.tzinfo is None or current_observed_at.tzinfo is None
            or not timedelta(0) <= now-current_observed_at <= timedelta(seconds=15)
            or admission.observed_at > current_observed_at
            or now >= admission.expires_at or admission.expires_at <= admission.observed_at):
        raise PermissionError('current live key coverage required')
    if (admission.key_fingerprint != key_fingerprint or admission.census_hash != current_census_hash
            or admission.ledger_identity_hash != current_ledger_identity_hash
            or admission.external_liability_receipt_hash != current_external_liability_receipt_hash):
        raise PermissionError('key consumer census or central reservation path changed')
    consumers = admission.consumers
    if not consumers or len({c.consumer_id for c in consumers}) != len(consumers):
        raise PermissionError('unique complete key consumer population required')
    if not any(c.mode == 'central-reservation' for c in consumers):
        raise PermissionError('live central reservation consumer required')
    return VerifiedKeyCoverage(admission_hash=admission_hash, key_fingerprint=key_fingerprint,
                               ledger_identity_hash=current_ledger_identity_hash,
                               observed_at=current_observed_at, expires_at=admission.expires_at)
