"""Conservative speaker identity for chat/interview turns. Shared names never merge."""
from oracle_brain.interviews.speaker import SpeakerCandidate, resolve_speaker

ROSTER = [
    SpeakerCandidate('p-alice', 'Alice', 'alice@pop.example'),
    SpeakerCandidate('p-alex', 'Alex', 'alex@pop.example'),
    SpeakerCandidate('p-bob', 'Bob', 'bob@pop.example'),
]


def test_exact_stable_id_wins_even_when_name_is_shared():
    r = resolve_speaker(ROSTER, speaker_id='p-alice', display_name='Sam')
    assert r.speaker_id == 'p-alice' and r.resolution == 'exact_id'


def test_exact_email_unique_match():
    r = resolve_speaker(ROSTER, email='alex@pop.example')
    assert r.speaker_id == 'p-alex' and r.resolution == 'exact_email'


def test_ambiguous_identity_abstains():
    # no candidate has display_name 'Sam' shared, so add one and collide
    roster = ROSTER + [SpeakerCandidate('p-sam1', 'Sam'), SpeakerCandidate('p-sam2', 'Sam')]
    assert resolve_speaker(roster, display_name='Sam') is None
    assert resolve_speaker(roster, email=None) is None
    assert resolve_speaker(roster, speaker_id='p-missing') is None
    assert resolve_speaker(roster, email='shared@pop.example') is None


def test_unique_display_name_resolves_but_is_weakest_resolution():
    r = resolve_speaker(ROSTER, display_name='Bob')
    assert r.speaker_id == 'p-bob' and r.resolution == 'unique_name'
