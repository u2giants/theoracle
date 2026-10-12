"""Immutable engineering comparison checkpoint; time never permits activation."""
from datetime import datetime
from zoneinfo import ZoneInfo
from uuid import UUID
import json
import psycopg
from psycopg.types.json import Jsonb
from .contracts import digest

_ZONE = ZoneInfo('America/New_York')

def _time(value):
    instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('comparison timestamps require a timezone')
    return instant

def checkpoint_due(events, now):
    if not events or events[0]['kind'] != 'begun':
        raise ValueError('comparison has not begun')
    begun = _time(events[0]['at'])
    now = _time(now)
    if now < begun:
        raise ValueError('comparison clock moved backwards')
    return (sum(e['kind'] == 'run' for e in events) >= 3 or
            (now.astimezone(_ZONE).date() - begun.astimezone(_ZONE).date()).days >= 7)

class ComparisonLedger:
    def __init__(self, database_url):
        self.url = database_url

    @staticmethod
    def _read(conn, workspace_id, comparison_id):
        rows = conn.execute('SELECT sequence,content_hash,payload FROM oracle2.operating_comparison_events WHERE workspace_id=%s AND comparison_id=%s ORDER BY sequence', (workspace_id, comparison_id)).fetchall()
        for i, (sequence, seal, payload) in enumerate(rows):
            if sequence != i or digest(payload) != seal:
                raise ValueError('comparison ledger seal or sequence mismatch')
        return [row[2] for row in rows]

    def read(self, workspace_id, comparison_id):
        with psycopg.connect(self.url) as conn:
            return self._read(conn, workspace_id, comparison_id)

    def append(self, workspace_id: UUID, comparison_id: UUID, *, kind, at,
               release_hash, evidence_hash, admitted_hashes: frozenset[str], run_id=None,
               decision=None):
        if kind not in {'begun', 'run', 'checkpoint'}:
            raise ValueError('unknown comparison event')
        for seal in (release_hash, evidence_hash):
            if not isinstance(seal, str) or len(seal) != 64 or any(c not in '0123456789abcdef' for c in seal):
                raise ValueError('exact release and evidence hashes required')
        payload = dict(kind=kind, at=_time(at).isoformat(), release_hash=release_hash,
                       evidence_hash=evidence_hash, run_id=str(run_id) if run_id else None,
                       decision=decision)
        if digest(payload) not in admitted_hashes:
            raise PermissionError('exact comparison event has no independent admission')
        with psycopg.connect(self.url) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (f'operating-comparison:{workspace_id}:{comparison_id}',))
            events = self._read(conn, workspace_id, comparison_id)
            if payload in events:
                return events.index(payload)
            if any(e['kind'] == 'checkpoint' for e in events):
                raise PermissionError('comparison is closed; a fresh admission is required')
            if events and _time(at) < _time(events[-1]['at']):
                raise ValueError('comparison clock moved backwards')
            if kind == 'begun':
                if events or run_id or decision:
                    raise ValueError('comparison can begin exactly once')
            elif not events:
                raise ValueError('comparison has not begun')
            elif kind == 'run':
                if checkpoint_due(events, at):
                    raise PermissionError('comparison checkpoint required before another run')
                if not isinstance(run_id, UUID) or decision:
                    raise ValueError('comparison run requires exact run identity')
                if any(e['run_id'] == str(run_id) for e in events):
                    raise ValueError('comparison run identity reused')
            elif decision not in {'accept', 'revise', 'blocked'} or run_id:
                raise ValueError('checkpoint requires accept/revise/blocked and evidence')
            conn.execute('INSERT INTO oracle2.operating_comparison_events(workspace_id,comparison_id,sequence,content_hash,payload) VALUES(%s,%s,%s,%s,%s)', (workspace_id, comparison_id, len(events), digest(payload), Jsonb(payload)))
            return len(events)

    def require_accepted(self, workspace_id, comparison_id, release_hash):
        events = self.read(workspace_id, comparison_id)
        if not events or events[-1]['kind'] != 'checkpoint' or events[-1]['decision'] != 'accept' or events[-1]['release_hash'] != release_hash:
            raise PermissionError('accepted exact comparison checkpoint required')
        # This grants no activation: the independent cutover gates still apply.
        return events[-1]
