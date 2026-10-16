"""Refresh scheduler with injected clock: due selection, dedup, retries and missed-run catch-up."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable
import uuid

from .registry import Source

RETRY_BACKOFF = (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=6))
LEASE = timedelta(hours=1)
MAX_ATTEMPTS = 1 + len(RETRY_BACKOFF)  # initial attempt plus three retries


@dataclass
class SourceState:
    next_due: datetime | None = None
    last_success: datetime | None = None
    attempts: int = 0
    exhausted: bool = False
    in_flight: str | None = None
    lease_until: datetime | None = None


@dataclass
class Scheduler:
    sources: tuple[Source, ...]
    clock: Callable[[], datetime]
    new_run_id: Callable[[], str] = field(default=lambda: uuid.uuid4().hex)
    state: dict[str, SourceState] = field(default_factory=dict)

    def _state(self, source_id: str) -> SourceState:
        return self.state.setdefault(source_id, SourceState())

    def due(self) -> list[Source]:
        now = self.clock()
        out = []
        for s in self.sources:
            if not s.authorized:
                continue
            st = self._state(s.source_id)
            if st.in_flight and st.lease_until and st.lease_until > now:
                continue
            if st.in_flight and st.attempts >= MAX_ATTEMPTS:
                # A lost final receipt must consume the same budget as a failure.
                st.in_flight = st.lease_until = None
                st.exhausted = True
                st.next_due = now + s.interval
            if st.next_due is None or st.next_due <= now:
                out.append(s)
        return out

    def dispatch(self) -> list[tuple[str, str]]:
        """Claim due sources once; a missed backlog collapses into a single catch-up run."""
        now = self.clock()
        runs = []
        for s in self.due():
            st = self._state(s.source_id)
            if st.exhausted:
                st.attempts, st.exhausted = 0, False
            st.attempts += 1
            run_id = self.new_run_id()
            st.in_flight, st.lease_until = run_id, now + LEASE
            runs.append((s.source_id, run_id))
        return runs

    def complete(self, source_id: str, run_id: str, ok: bool) -> None:
        st = self._state(source_id)
        if st.in_flight != run_id:
            return  # stale or duplicate receipt
        now = self.clock()
        st.in_flight = st.lease_until = None
        if ok:
            source = next(s for s in self.sources if s.source_id == source_id)
            st.last_success, st.attempts = now, 0
            st.next_due = now + source.interval
        else:
            if st.attempts >= MAX_ATTEMPTS:
                source = next(s for s in self.sources if s.source_id == source_id)
                st.exhausted = True
                st.next_due = now + source.interval
            else:
                st.next_due = now + RETRY_BACKOFF[st.attempts - 1]

    def force_due(self, source_id: str) -> None:
        """Immediately before a time-sensitive recommendation."""
        st = self._state(source_id)
        if not st.exhausted:
            st.next_due = self.clock()
