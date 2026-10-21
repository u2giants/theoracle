"""Pure, reported/unconfirmed chat proposals; no authenticated durable workflow.

The caller must supply server-established scope and turn origin. Source text,
quotes, recaps, hashes and serialized histories cannot confer actor identity,
permission, original-reading qualification or policy confirmation.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from ..operating_model.contracts import StrictRecord, digest
from ..interviews.language import (OriginalLanguage, UnreviewedTranslation,
    MAX_TEXT_CHARS, LANGUAGE, preserve_original, bind_translation)

MAX_HISTORY = 256
HEX = r'^[0-9a-f]{64}$'


class ChatScope(StrictRecord):
    workspace_id: UUID
    actor_id: UUID
    thread_id: UUID


class ChatTurn(StrictRecord):
    workspace_id: UUID
    actor_id: UUID
    thread_id: UUID
    turn_id: UUID
    revision: int = Field(ge=1)
    role: Literal['employee', 'assistant', 'system', 'tool']
    language: str = Field(pattern=LANGUAGE, max_length=40)
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    response_kind: Literal['statement', 'unknown', 'refused'] = 'statement'
    corrects_turn_id: UUID | None = None
    corrects_revision: int | None = Field(default=None, ge=1)
    corrects_original_sha256: str | None = Field(default=None, pattern=HEX)

    @model_validator(mode='after')
    def validate_original_and_correction(self):
        preserve_original(workspace_id=self.workspace_id, actor_id=self.actor_id,
            thread_id=self.thread_id, turn_id=self.turn_id, revision=self.revision,
            language=self.language, text=self.text)
        refs=(self.corrects_turn_id,self.corrects_revision,self.corrects_original_sha256)
        if any(value is not None for value in refs) and not all(value is not None for value in refs):
            raise ValueError('correction needs exact prior turn/revision/original hash')
        if self.corrects_turn_id == self.turn_id:
            raise ValueError('correction must use a new turn identity')
        if self.role != 'employee' and self.corrects_turn_id is not None:
            raise ValueError('display-only turn cannot correct employee evidence')
        return self


class ReportedProposal(StrictRecord):
    original_identity_digest: str = Field(pattern=HEX)
    proposed_text: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT_CHARS)
    missing_reason: Literal['unknown', 'refused'] | None = None
    reported: Literal[True] = True
    confirmed: Literal[False] = False
    policy_authority: Literal[False] = False
    source_qualified: Literal[False] = False
    permission_granted: Literal[False] = False


class TurnRecord(StrictRecord):
    turn: ChatTurn
    original: OriginalLanguage
    translation: UnreviewedTranslation | None = None
    proposal: ReportedProposal | None
    visible_recap: str = Field(min_length=1, max_length=MAX_TEXT_CHARS + 512)
    correction_path: str = Field(min_length=1, max_length=512)
    payload_digest: str = Field(pattern=HEX)


class ProposalResult(StrictRecord):
    record: TurnRecord
    history: tuple[TurnRecord, ...] = Field(max_length=MAX_HISTORY)
    created: bool
    durable_authenticated_workflow: Literal[False] = False


def _scope(scope, turn):
    if (turn.workspace_id,turn.actor_id,turn.thread_id) != (scope.workspace_id,scope.actor_id,scope.thread_id):
        raise PermissionError('turn does not match server-established chat scope')


def _record(turn, translation):
    original=preserve_original(workspace_id=turn.workspace_id, actor_id=turn.actor_id,
        thread_id=turn.thread_id, turn_id=turn.turn_id, revision=turn.revision,
        language=turn.language, text=turn.text)
    if translation is not None:bind_translation(original,translation)
    correction='Submit a new employee turn referencing this exact turn ID, revision and original hash; both originals are retained.'
    proposal=None
    if turn.role != 'employee':
        recap='Display only; assistant, system and tool wording is excluded from learned evidence.'
    elif turn.response_kind == 'statement':
        proposal=ReportedProposal(original_identity_digest=original.identity_digest(),proposed_text=original.text)
        recap='Reported and unconfirmed; no policy approval.\nOriginal response:\n'+original.text
    else:
        proposal=ReportedProposal(original_identity_digest=original.identity_digest(),missing_reason=turn.response_kind)
        recap='Information remains missing ('+turn.response_kind+'). No fact was supplied.\nOriginal response:\n'+original.text
    if translation is not None:
        recap+='\nTranslation supplied separately: unreviewed; the original remains evidence.'
    payload={'turn':turn.model_dump(mode='json'),
        'translation':translation.model_dump(mode='json') if translation is not None else None}
    return TurnRecord(turn=turn,original=original,translation=translation,proposal=proposal,
        visible_recap=recap,correction_path=correction,payload_digest=digest(payload))


def _correction(turn, records, corrected):
    if turn.corrects_turn_id is None:return
    previous=records.get(turn.corrects_turn_id)
    if previous is None or previous.turn.role != 'employee':
        raise PermissionError('correction requires an existing employee original')
    if turn.corrects_turn_id in corrected:
        raise PermissionError('correction target is stale')
    if (turn.corrects_revision != previous.original.revision
            or turn.corrects_original_sha256 != previous.original.original_sha256):
        raise PermissionError('correction target revision/original hash differs')


def propose_update(scope: ChatScope, turn: ChatTurn, *, history: tuple[TurnRecord, ...] = (),
                   translation: UnreviewedTranslation | None = None) -> ProposalResult:
    """Return immutable descriptive history and visible, nonconfirming proposal.

    No repository/database/provider/worker operation occurs. Reusing supplied
    history is in-process idempotency, not durable storage or authentication.
    """
    if type(scope) is not ChatScope or type(turn) is not ChatTurn:
        raise TypeError('exact server scope and turn required')
    ChatScope.model_validate(scope.model_dump(mode='python'))
    ChatTurn.model_validate(turn.model_dump(mode='python'))
    _scope(scope,turn)
    if type(history) is not tuple or len(history) > MAX_HISTORY:
        raise ValueError('bounded immutable proposal history required')
    records={};corrected=set()
    for prior in history:
        if type(prior) is not TurnRecord:raise TypeError('exact prior turn record required')
        TurnRecord.model_validate(prior.model_dump(mode='python'))
        _scope(scope,prior.turn)
        if prior.turn.turn_id in records:
            raise ValueError('duplicate turn in supplied history')
        if _record(prior.turn,prior.translation) != prior:
            raise ValueError('prior proposal/original payload changed')
        _correction(prior.turn,records,corrected)
        records[prior.turn.turn_id]=prior
        if prior.turn.corrects_turn_id is not None:corrected.add(prior.turn.corrects_turn_id)
    record=_record(turn,translation)
    previous=records.get(turn.turn_id)
    if previous is not None:
        if previous != record:raise ValueError('same turn identity has conflicting exact payload')
        return ProposalResult(record=previous,history=history,created=False)
    if len(history) >= MAX_HISTORY:raise ValueError('proposal history bound exceeded')
    _correction(turn,records,corrected)
    return ProposalResult(record=record,history=history+(record,),created=True)
