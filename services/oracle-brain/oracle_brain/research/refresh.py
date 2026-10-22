"""Nondurable, single-instance scheduler with explicit uncertain outcomes.

The instance lock only coordinates threads sharing this object. Supplied
completion observations are not authenticated receipts, source rights or
cross-process persistence. No fetch/provider/platform operation occurs here.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock
from typing import Callable
import uuid

from .registry import Source

RETRY_BACKOFF = (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=6))
LEASE = timedelta(hours=1)
MAX_ATTEMPTS = 1 + len(RETRY_BACKOFF)
MAX_SOURCES = 256
MAX_ISSUED_RUNS = 100000


def _identity(value, name):
    if type(value) is not str or not 0<len(value)<=200 or any(not 33<=ord(c)<=126 for c in value):
        raise ValueError(name+' must be a bounded nonempty identifier')


def _aware(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware observed clock required')


def _after(now, delta):
    try:return now+delta
    except OverflowError as exc:raise ValueError('observed timestamp exceeds scheduling bounds') from exc


@dataclass
class SourceState:
    next_due: datetime | None = None
    last_success: datetime | None = None
    attempts: int = 0
    exhausted: bool = False
    in_flight: str | None = None
    lease_until: datetime | None = None
    uncertain: bool = False
    last_completed_run: str | None = None
    last_completed_ok: bool | None = None

    def __post_init__(self):
        self.validate()

    def validate(self, now=None):
        if type(self.attempts) is not int or not 0<=self.attempts<=MAX_ATTEMPTS:
            raise ValueError('attempts outside existing retry budget')
        if type(self.exhausted) is not bool or type(self.uncertain) is not bool:
            raise ValueError('actual boolean source state required')
        for stamp in (self.next_due,self.last_success,self.lease_until):
            if stamp is not None:_aware(stamp)
        if now is not None and self.last_success is not None and self.last_success>now:
            raise ValueError('future successful observation refused')
        if self.next_due is not None and self.last_success is not None and self.next_due<self.last_success:
            raise ValueError('next due precedes observed success')
        if (self.in_flight is None)!=(self.lease_until is None):
            raise ValueError('in-flight identity and lease must be paired')
        if self.in_flight is not None:
            _identity(self.in_flight,'run_id')
            if self.attempts<1 or self.exhausted:raise ValueError('invalid in-flight retry state')
        if self.uncertain and self.in_flight is None:raise ValueError('UNKNOWN must retain original run')
        if self.exhausted and (self.attempts!=MAX_ATTEMPTS or self.next_due is None):
            raise ValueError('exhaustion requires spent known-failure budget and next cadence')
        if (self.last_completed_run is None)!=(self.last_completed_ok is None):
            raise ValueError('terminal run and observation must be paired')
        if self.last_completed_run is not None:
            _identity(self.last_completed_run,'completed_run_id')
            if type(self.last_completed_ok) is not bool:raise ValueError('actual terminal bool required')
            if self.last_completed_run==self.in_flight:raise ValueError('completed run cannot be in flight')


@dataclass
class Scheduler:
    sources: tuple[Source, ...]
    clock: Callable[[], datetime]
    new_run_id: Callable[[], str] = field(default=lambda: uuid.uuid4().hex)
    state: dict[str, SourceState] = field(default_factory=dict)
    _lock: object = field(default_factory=RLock,init=False,repr=False,compare=False)
    _last_observed_at: datetime | None = field(default=None,init=False,repr=False)
    # Collision protection only for this in-memory lifetime, not a second ledger.
    _issued_run_ids: set[str] = field(default_factory=set,init=False,repr=False)

    def __post_init__(self):
        self._validate()
        for state in self.state.values():
            for run_id in (state.in_flight,state.last_completed_run):
                if run_id is not None:
                    if run_id in self._issued_run_ids:raise ValueError('duplicate retained run identity')
                    self._issued_run_ids.add(run_id)

    def _validate(self, now=None):
        if type(self.sources) is not tuple or len(self.sources)>MAX_SOURCES:
            raise ValueError('bounded immutable source register required')
        if not callable(self.clock) or not callable(self.new_run_id):raise TypeError('clock and run factory required')
        ids=set()
        for source in self.sources:
            if type(source) is not Source:raise TypeError('exact registered source required')
            Source(**vars(source))
            _identity(source.source_id,'source_id')
            if type(source.enabled) is not bool or type(source.rights_confirmed) is not bool:
                raise ValueError('source access flags must be actual booleans')
            if source.source_id in ids:raise ValueError('duplicate source identity')
            ids.add(source.source_id)
        if type(self.state) is not dict or set(self.state)-ids:raise ValueError('state contains unregistered source')
        retained=set()
        for state in self.state.values():
            if type(state) is not SourceState:raise TypeError('exact source state required')
            state.validate(now)
            for run_id in (state.in_flight,state.last_completed_run):
                if run_id is not None:
                    if run_id in retained:raise ValueError('duplicate retained run identity')
                    retained.add(run_id)

    def _observe(self):
        self._validate()
        now=self.clock()  # exactly one clock sample for the whole transition
        _aware(now)
        if self._last_observed_at is not None and now<self._last_observed_at:
            raise ValueError('observed clock moved backwards')
        self._validate(now)
        self._last_observed_at=now
        # Observed expiry remains UNKNOWN even if a later operation is denied
        # by changed rights; losing access never turns uncertainty into failure.
        for state in self.state.values():
            if state.in_flight is not None and state.lease_until<=now:
                state.uncertain=True
        return now

    def _source(self, source_id):
        _identity(source_id,'source_id')
        for source in self.sources:
            if source.source_id==source_id:return source
        raise ValueError('unregistered source identity')

    def _state(self, source_id):
        return self.state.setdefault(source_id,SourceState())

    def _due(self, now):
        out=[]
        for source in self.sources:
            st=self.state.get(source.source_id)
            if st is not None and st.in_flight is not None:
                if st.lease_until<=now:st.uncertain=True
                continue  # live or UNKNOWN original attempt always owns this slot
            if not source.authorized:continue
            if st is None or st.next_due is None or st.next_due<=now:out.append(source)
        return out

    def due(self) -> list[Source]:
        with self._lock:
            return self._due(self._observe())

    def dispatch(self) -> list[tuple[str,str]]:
        """Claim once on this instance; lease expiry never mints a replacement."""
        with self._lock:
            now=self._observe();sources=self._due(now)
            if len(self._issued_run_ids)+len(sources)>MAX_ISSUED_RUNS:
                raise ValueError('in-process run identity history bound reached; no reset authority')
            lease_until=_after(now,LEASE) if sources else None
            planned=[];seen=set(self._issued_run_ids)
            for retained in self.state.values():
                seen.update(run_id for run_id in (retained.in_flight,retained.last_completed_run) if run_id is not None)
            for source in sources:
                run_id=self.new_run_id();_identity(run_id,'run_id')
                if run_id in seen:raise ValueError('run identity collision')
                seen.add(run_id);planned.append((source,run_id))
            # Every generated identity is valid before any claim/budget mutation.
            for source,run_id in planned:
                st=self._state(source.source_id)
                if st.exhausted:st.attempts,st.exhausted=0,False
                st.attempts+=1
                st.in_flight,st.lease_until=run_id,lease_until
                self._issued_run_ids.add(run_id)
            return [(source.source_id,run_id) for source,run_id in planned]

    def complete(self, source_id:str, run_id:str, ok:bool) -> str:
        """Classify exact supplied terminal observation; never infer one from expiry.

        Only the latest retained completion is compared for conflicting duplicates.
        Older unretained IDs return explicit 'stale', never a success claim.
        Durable authenticated receipt retention remains separate integration.
        """
        if type(ok) is not bool:raise ValueError('ok must be an actual bool')
        _identity(run_id,'run_id')
        with self._lock:
            source=self._source(source_id);now=self._observe()
            if not source.authorized:raise PermissionError('current source rights unavailable')
            st=self.state.get(source_id)
            if st is None:return 'stale'
            if st.last_completed_run==run_id:
                if st.last_completed_ok is not ok:raise ValueError('conflicting retained completion observation')
                return 'duplicate'
            if st.in_flight!=run_id:return 'stale'
            # Compute bounded dates before changing attempt/receipt state.
            delay=source.interval if ok or st.attempts>=MAX_ATTEMPTS else RETRY_BACKOFF[st.attempts-1]
            next_due=_after(now,delay)
            # A matching explicit terminal observation may reconcile UNKNOWN.
            st.in_flight=st.lease_until=None;st.uncertain=False
            st.last_completed_run,st.last_completed_ok=run_id,ok
            if ok:
                st.last_success,st.attempts=now,0
                st.next_due=next_due
            elif st.attempts>=MAX_ATTEMPTS:
                st.exhausted=True;st.next_due=next_due
            else:st.next_due=next_due
            return 'recorded'

    def force_due(self, source_id:str) -> str:
        with self._lock:
            source=self._source(source_id);now=self._observe()
            st=self.state.get(source_id)
            if st is not None and st.in_flight is not None:
                if st.lease_until<=now:st.uncertain=True
                return 'UNKNOWN' if st.uncertain else 'in_flight'
            if not source.authorized:return 'blocked'
            if st is not None and st.exhausted:return 'exhausted'
            self._state(source_id).next_due=now
            return 'due'
