"""Exact original-language preservation; translations never replace evidence.

These descriptive records grant no reading qualification, permission or truth.
"""
from __future__ import annotations

import hashlib
from uuid import UUID
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..operating_model.contracts import StrictRecord, digest

MAX_TEXT_CHARS = 32768
LANGUAGE = r'^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8}){0,3}$'
HEX = r'^[0-9a-f]{64}$'


def utf8_digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8', errors='strict')).hexdigest()


class OriginalLanguage(StrictRecord):
    workspace_id: UUID
    actor_id: UUID
    thread_id: UUID
    turn_id: UUID
    revision: int = Field(ge=1)
    language: str = Field(pattern=LANGUAGE, max_length=40)
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    original_sha256: str = Field(pattern=HEX)

    @field_validator('text')
    @classmethod
    def exact_nonempty_utf8(cls, value):
        if not value.strip():raise ValueError('original response must not be blank')
        value.encode('utf-8', errors='strict')
        return value

    @model_validator(mode='after')
    def verify_original(self):
        if utf8_digest(self.text) != self.original_sha256:
            raise ValueError('original UTF8 hash differs')
        return self

    def identity_digest(self) -> str:
        return digest(self.model_dump(mode='json'))


class UnreviewedTranslation(StrictRecord):
    original_identity_digest: str = Field(pattern=HEX)
    original_sha256: str = Field(pattern=HEX)
    target_language: str = Field(pattern=LANGUAGE, max_length=40)
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    review_state: Literal['unreviewed'] = 'unreviewed'
    replaces_original: Literal[False] = False

    @field_validator('text')
    @classmethod
    def nonempty_utf8(cls, value):
        return OriginalLanguage.exact_nonempty_utf8(value)

    @model_validator(mode='after')
    def never_replaces(self):
        if self.replaces_original is not False:
            raise ValueError('translation cannot replace original evidence')
        return self


def preserve_original(*, workspace_id: UUID, actor_id: UUID, thread_id: UUID,
                      turn_id: UUID, revision: int, language: str, text: str,
                      expected_sha256: str | None = None) -> OriginalLanguage:
    if type(text) is not str:raise TypeError('exact original text required')
    return OriginalLanguage(workspace_id=workspace_id, actor_id=actor_id,
        thread_id=thread_id, turn_id=turn_id, revision=revision, language=language,
        text=text, original_sha256=expected_sha256 if expected_sha256 is not None else utf8_digest(text))


def bind_translation(original: OriginalLanguage, translation: UnreviewedTranslation) -> None:
    if type(original) is not OriginalLanguage or type(translation) is not UnreviewedTranslation:
        raise TypeError('exact original and unreviewed translation records required')
    checked=OriginalLanguage.model_validate(original.model_dump(mode='python'))
    supplied=UnreviewedTranslation.model_validate(translation.model_dump(mode='python'))
    if (supplied.original_identity_digest != checked.identity_digest()
            or supplied.original_sha256 != checked.original_sha256):
        raise ValueError('translation does not bind this exact original identity')
