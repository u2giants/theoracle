from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator, field_validator

class PydanticEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    event_id: str = Field(min_length=1); row_index: int = Field(strict=True, ge=1)
    case_id: str = Field(min_length=1); activity_id: str = Field(min_length=1)
    timestamp: AwareDatetime; original_timestamp: str; original_zone: str
    lifecycle: Literal['start','complete','point']; tie_order: int | None = Field(default=None, strict=True, ge=0)
    status: Literal['ongoing','completed','cancelled','unknown']; resource: str | None = None
    cost: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False); source_import_id: UUID

    @field_validator('timestamp')
    @classmethod
    def utc(cls, value): return value.astimezone(timezone.utc)

class LogReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    workspace_id: UUID; import_id: UUID
    input_hash: str = Field(pattern=r'^[0-9a-f]{64}$'); mapping_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    window_start: AwareDatetime; window_end: AwareDatetime
    events: tuple[PydanticEvent, ...]; quarantined_rows: tuple[int, ...] = ()
    quality_notes: tuple[str, ...] = (); case_censoring: dict[str, str] = {}

    @model_validator(mode='after')
    def valid(self):
        if self.window_end <= self.window_start: raise ValueError('window must be strictly increasing')
        if len({e.event_id for e in self.events}) != len(self.events): raise ValueError('duplicate event_id')
        if any(e.source_import_id != self.import_id for e in self.events): raise ValueError('event import mismatch')
        if any(e.timestamp < self.window_start or e.timestamp > self.window_end for e in self.events): raise ValueError('event outside source window')
        return self
