"""Synthetic independent meeting host, never imported by application code."""
from dataclasses import replace
import time
from oracle_brain.meetings.participation import (
    CurrentSettingsProof, CURRENT_PROOF_PURPOSE, current_settings_payload,
)
from seal_testkit import sign_seal

SETTINGS_EXPIRY = time.time() + 240


def host_current(meeting_id, challenge, *, generation=1, enabled=True):
    proof = CurrentSettingsProof(meeting_id, generation, enabled, challenge,
                                 time.time() + 30, '')
    return replace(proof, mac=sign_seal(CURRENT_PROOF_PURPOSE, current_settings_payload(proof)))


def host_audience(meeting_id, channel, generation, body_hash, challenge, *,
                  recipients=frozenset({'p-1'}), authorized=frozenset({'p-1'}), complete=True):
    from oracle_brain.workflows.meeting_turn import CurrentAudienceProof, AUDIENCE_PURPOSE, audience_payload
    proof = CurrentAudienceProof(meeting_id, channel, generation, body_hash,
                                 recipients, authorized, complete, challenge, time.time() + 30, '')
    return replace(proof, mac=sign_seal(AUDIENCE_PURPOSE, audience_payload(proof)))
