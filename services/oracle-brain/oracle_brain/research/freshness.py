"""Pure observed freshness; no retrieval, scheduler, rights or serving authority."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from .registry import CADENCES


class Freshness(str, Enum):
    NEVER='never'
    FRESH='fresh'
    DUE='due'
    OVERDUE='overdue'


def _identity(value, name):
    if type(value) is not str or not value.strip() or len(value)>200:
        raise ValueError(name+' must be a bounded nonempty string')


def _aware(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware observed timestamps required')


def _attempts(value, name):
    if type(value) is not int or not 0<=value<=10000:
        raise ValueError(name+' must be a bounded nonnegative integer')


def interval_for(cadence: str) -> timedelta:
    if type(cadence) is not str or cadence not in CADENCES:
        raise ValueError('unknown cadence')
    return CADENCES[cadence]


def due_after_success(cadence: str, at: datetime) -> datetime:
    interval=interval_for(cadence);_aware(at)
    return at+interval


def review_due_from(cadence: str, at: datetime) -> datetime:
    return due_after_success(cadence,at)


@dataclass(frozen=True)
class FreshnessStatus:
    source_id: str
    freshness: Freshness
    last_success: datetime | None
    next_due: datetime | None
    review_due: datetime | None
    attempts: int
    cadence: str
    observed_at: datetime | None = None
    required_review_after: datetime | None = None

    def __post_init__(self):
        _identity(self.source_id,'source_id');_attempts(self.attempts,'attempts')
        interval=interval_for(self.cadence);_aware(self.observed_at)
        if type(self.freshness) is not Freshness:raise ValueError('exact freshness status required')
        for value in (self.last_success,self.next_due,self.review_due,self.required_review_after):
            if value is not None:_aware(value)
        if self.required_review_after is not None and self.required_review_after>self.observed_at:
            raise ValueError('future review requirement cannot be satisfied now')
        if self.last_success is None:
            if self.freshness is not Freshness.NEVER:raise ValueError('no success cannot be fresh')
        else:
            if self.last_success>self.observed_at:raise ValueError('future success refused')
            if self.next_due is None or self.review_due is None:raise ValueError('observed success needs bounded due dates')
            if not self.last_success<=self.next_due<=self.last_success+interval:
                raise ValueError('next due cannot extend observed cadence')
            if not self.last_success<=self.review_due<=self.last_success+interval:
                raise ValueError('review due cannot extend observed cadence')
            if self.freshness is Freshness.NEVER:raise ValueError('observed success cannot be never')
            if self.freshness in (Freshness.DUE,Freshness.OVERDUE) and self.next_due>self.observed_at:
                raise ValueError('due status requires an elapsed due fence')
            if self.freshness is Freshness.FRESH and (self.next_due<=self.observed_at
                    or self.review_due<=self.observed_at
                    or (self.required_review_after is not None and self.last_success<self.required_review_after)):
                raise ValueError('stale observation cannot be fresh')


@dataclass(frozen=True)
class RefreshReceipt:
    source_id: str
    run_id: str
    ok: bool
    at: datetime
    attempts_after: int
    next_due: datetime | None
    cadence: str | None = field(default=None,compare=False)

    def __post_init__(self):
        _identity(self.source_id,'source_id');_identity(self.run_id,'run_id');_aware(self.at)
        _attempts(self.attempts_after,'attempts_after')
        if type(self.ok) is not bool:raise ValueError('ok must be a bool')
        if self.cadence is not None:interval_for(self.cadence)
        if self.ok:
            _aware(self.next_due)
            if self.next_due-self.at not in tuple(CADENCES.values()):
                raise ValueError('receipt next due must follow known cadence')
            if self.cadence is not None and self.next_due!=due_after_success(self.cadence,self.at):
                raise ValueError('receipt cadence differs')
        elif self.next_due is not None:raise ValueError('failed retrieval has no next-success due date')


def assess(*,source_id:str,cadence:str,now:datetime,last_success:datetime|None,
           next_due:datetime|None,attempts:int=0,overdue_after:timedelta|None=None,
           review_due:datetime|None=None,required_review_after:datetime|None=None)->FreshnessStatus:
    interval=interval_for(cadence);_aware(now);_identity(source_id,'source_id');_attempts(attempts,'attempts')
    for value in (last_success,next_due,review_due,required_review_after):
        if value is not None:_aware(value)
    if last_success is not None and last_success>now:raise ValueError('future success refused')
    if required_review_after is not None and required_review_after>now:
        raise ValueError('future review requirement cannot be satisfied now')
    if overdue_after is not None and (type(overdue_after) is not timedelta or overdue_after<timedelta(0)):
        raise ValueError('nonnegative finite timedelta grace required')
    if last_success is None:
        freshness=Freshness.NEVER
        fence=review_due if review_due is not None else now+interval
        due=next_due
    else:
        cadence_due=last_success+interval
        if next_due is not None and next_due<last_success:raise ValueError('due precedes success')
        if review_due is not None and review_due<last_success:raise ValueError('review precedes success')
        fence=min(cadence_due,review_due) if review_due is not None else cadence_due
        due=min(cadence_due,fence,next_due) if next_due is not None else min(cadence_due,fence)
        if required_review_after is not None and last_success<required_review_after:
            due=min(due,required_review_after)
        if due>now:freshness=Freshness.FRESH
        else:
            grace=interval if overdue_after is None else overdue_after
            freshness=Freshness.OVERDUE if due+grace<=now else Freshness.DUE
    return FreshnessStatus(source_id,freshness,last_success,due,fence,attempts,cadence,now,required_review_after)


def receipt(*,source_id:str,run_id:str,ok:bool,at:datetime,attempts_after:int,cadence:str)->RefreshReceipt:
    interval_for(cadence)  # failures must validate cadence too
    if type(ok) is not bool:raise ValueError('ok must be a bool')
    return RefreshReceipt(source_id,run_id,ok,at,attempts_after,
        due_after_success(cadence,at) if ok else None,cadence)
