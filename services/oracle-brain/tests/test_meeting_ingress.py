from oracle_brain.ingest.consent import Invitation, authorize_capture, authorize_learning, evaluate_intake
from oracle_brain.ingest.meeting import Transcript, Turn
from oracle_brain.ingest.speakers import Speaker


def invitation(**overrides):
    fields = dict(
        tenant_id='tenant',
        meeting_id='meeting',
        explicitly_invited=True,
        capture_permission=True,
        transcript_permission=True,
        consent_current=True,
    )
    fields.update(overrides)
    return Invitation(**fields)


def final_transcript(tenant='tenant', meeting='meeting', *, final=True):
    turn = Turn('turn', 1, Speaker('p', 'Name'), 'reported instruction')
    return Transcript(tenant, meeting, 1, (turn,), final)


def test_public_or_uninvited_meeting_is_never_joined():
    decision = authorize_capture(invitation(explicitly_invited=False))
    assert not decision.admitted
    assert 'explicit invitation' in decision.reason
    assert authorize_learning(
        invitation(explicitly_invited=False), final_transcript()).stage == 'learning'


def test_missing_capture_or_stale_consent_refuses_before_bot_creation():
    for overrides, fragment in (
        ({'capture_permission': False}, 'missing capture permission'),
        ({'consent_current': False}, 'not current'),
    ):
        decision = authorize_capture(invitation(**overrides))
        assert not decision.admitted
        assert fragment in decision.reason


def test_missing_transcript_permission_is_visible_failure_not_success():
    decision = authorize_learning(
        invitation(transcript_permission=False), final_transcript())
    assert not decision.admitted
    assert decision.stage == 'learning'
    assert 'missing transcript permission' in decision.reason


def test_live_or_cross_meeting_transcript_cannot_be_learned_from():
    live = authorize_learning(invitation(), final_transcript(final=False))
    assert not live.admitted and 'final' in live.reason
    cross = authorize_learning(invitation(), final_transcript(meeting='other'))
    assert not cross.admitted and 'cross-meeting' in cross.reason
    assert not authorize_learning(invitation(), None).admitted


def test_rejected_lobby_and_transcription_failure_stay_visible():
    refused_lobby = evaluate_intake(
        invitation(), lobby_admitted=False, transcription_succeeded=True)
    assert not refused_lobby.admitted and 'lobby' in refused_lobby.reason
    refused_transcription = evaluate_intake(
        invitation(), lobby_admitted=True, transcription_succeeded=False)
    assert not refused_transcription.admitted and 'transcription' in refused_transcription.reason


def test_explicit_invitation_current_consent_and_final_transcript_admit():
    assert authorize_capture(invitation()).admitted
    assert evaluate_intake(
        invitation(), lobby_admitted=True, transcription_succeeded=True).admitted
    assert authorize_learning(invitation(), final_transcript()).admitted
