"""Consent records for interview and ordinary chat learning. Pure DTOs and checks."""
from dataclasses import dataclass
from typing import Iterable, Optional

PURPOSES = frozenset({'interview_learning', 'chat_learning'})


@dataclass(frozen=True)
class ConsentRecord:
    consent_id: str
    subject_id: str
    purpose: str
    granted_at: str
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None
    scope: tuple = ()


def _valid_purpose(purpose: str) -> bool:
    return purpose in PURPOSES


def is_consent_current(consent: ConsentRecord, *, purpose: str, at: str) -> bool:
    """True only for an unrevoked, unexpired consent covering this purpose at `at`."""
    if not _valid_purpose(purpose) or consent.purpose != purpose:
        return False
    if not consent.consent_id or not consent.subject_id or not consent.granted_at:
        return False
    if consent.granted_at > at:
        return False
    if consent.expires_at is not None and consent.expires_at <= at:
        return False
    if consent.revoked_at is not None and consent.revoked_at <= at:
        return False
    return True


def current_consent(consents: Iterable[ConsentRecord], *, subject_id: str,
                    purpose: str, at: str) -> Optional[ConsentRecord]:
    """Return the current consent for this subject/purpose, or None.

    Ambiguous duplicates (two current consents) are refused: no silent pick.
    """
    matches = [c for c in consents
               if c.subject_id == subject_id and is_consent_current(c, purpose=purpose, at=at)]
    if len(matches) != 1:
        return None
    return matches[0]
