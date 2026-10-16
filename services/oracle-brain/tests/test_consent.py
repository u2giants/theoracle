"""Consent DTOs and checks. Synthetic subjects only; no employee data."""
from oracle_brain.interviews.consent import ConsentRecord, current_consent, is_consent_current

AT = '2026-10-16T12:00:00Z'


def _consent(**kw) -> ConsentRecord:
    base = dict(consent_id='c1', subject_id='p1', purpose='interview_learning',
                granted_at='2026-10-01T00:00:00Z')
    base.update(kw)
    return ConsentRecord(**base)


def test_granted_consent_is_current_for_its_purpose():
    c = _consent()
    assert is_consent_current(c, purpose='interview_learning', at=AT) is True
    assert is_consent_current(c, purpose='chat_learning', at=AT) is False


def test_not_yet_granted_expired_or_revoked_is_not_current():
    assert is_consent_current(_consent(granted_at='2026-11-01T00:00:00Z'),
                              purpose='interview_learning', at=AT) is False
    assert is_consent_current(_consent(expires_at='2026-10-15T00:00:00Z'),
                              purpose='interview_learning', at=AT) is False
    assert is_consent_current(_consent(revoked_at='2026-10-10T00:00:00Z'),
                              purpose='interview_learning', at=AT) is False
    # revocation at the same instant counts as revoked
    assert is_consent_current(_consent(revoked_at=AT),
                              purpose='interview_learning', at=AT) is False


def test_current_consent_requires_exactly_one_match():
    one = _consent()
    assert current_consent([one], subject_id='p1', purpose='interview_learning', at=AT) is one
    assert current_consent([], subject_id='p1', purpose='interview_learning', at=AT) is None
    two = _consent(consent_id='c2')
    assert current_consent([one, two], subject_id='p1',
                           purpose='interview_learning', at=AT) is None
