"""Closed control selectors. Never participant bytes, observation or send body."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, TypeAdapter
from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes


class ParticipationStatusV1(StrictRecord):
    operation: Literal['status']
    caller_deadline: AwareDatetime


class ParticipationControlV1(StrictRecord):
    operation: Literal['control']
    expected_head: int = Field(strict=True,ge=0,le=16383)
    command_id: UUID
    enabled: bool = Field(strict=True)
    proactive_enabled: bool = Field(default=False,strict=True)
    cooldown_seconds: int = Field(default=120,strict=True,ge=120,le=86400)
    max_proactive: int = Field(default=3,strict=True,ge=0,le=3)
    caller_deadline: AwareDatetime


_REQUEST = TypeAdapter(Annotated[ParticipationStatusV1 | ParticipationControlV1,Field(discriminator='operation')])


def parse_participation_control_v1(raw):
    # Shared strict parser rejects duplicates/nonfinite/noncanonical bytes. A
    # validated roundtrip additionally refuses omitted/default/replayed fields.
    from oracle_brain.operating_model.protected_inputs_v1 import parse_canonical_object_v1
    parse_canonical_object_v1(raw)
    value = _REQUEST.validate_json(raw)
    if canonical_bytes(value.model_dump(mode='json')) != raw:
        raise ValueError('exact canonical participation control required')
    if isinstance(value,ParticipationControlV1) and not value.enabled and (
            value.proactive_enabled or value.cooldown_seconds != 120 or value.max_proactive != 3):
        raise ValueError('disable cannot carry enabling controls')
    return value
