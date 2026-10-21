"""Fixed current-original viewer. SQL authorizes; pinned custody verifies bytes."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import ipaddress
from pathlib import Path
from typing import Literal
from uuid import UUID

import psycopg
from pydantic import AwareDatetime, Field
from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes
from oracle_brain.operating_model.artifact_storage import FileBlobStore, OriginalObjectRefV1, ReservationOriginalObjectRefV1
from .original_intake_v1 import _pinned
from .purpose_journey_v2 import _worker_file
from .original_view_settings_v1 import OriginalViewerSettingsV1, MAX_BYTES, HASH

GROUP = 'oracle2_source_original_viewer'
FUNCTIONS = (
    ('original_revision_view_v1', 'oracle2.original_revision_view_v1(uuid,integer)'),
    ('_original_revision_access', 'oracle2._original_revision_access(uuid,integer,text)'),
    ('_original_revision_member_access', 'oracle2._original_revision_member_access(uuid,integer,text)'),
    ('_replacement_scope', 'oracle2._replacement_scope(uuid,uuid,text)'),
)
# Static OID selection: caller search_path/rendering cannot select another object.
OWNER_QUERY = 'WITH expected(label,oid) AS (VALUES ' + ','.join(
    "('" + name + "',pg_catalog.to_regprocedure('" + signature + "'))" for name, signature in FUNCTIONS
) + ") SELECT e.label,n.nspname,p.proname,pg_catalog.pg_get_userbyid(p.proowner),p.prosecdef FROM expected e JOIN pg_catalog.pg_proc p ON p.oid=e.oid JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace"


class ViewerCapabilityV1(StrictRecord):
    schema_version: Literal[1]
    workspace_id: UUID
    source_id: UUID
    revision: int = Field(strict=True, ge=1)
    principal_id: UUID
    original_sha256: str = Field(pattern=HASH)
    byte_count: int = Field(strict=True, ge=1, le=MAX_BYTES)
    media_type: Literal['application/pdf']
    private_object_key: str = Field(max_length=255)
    runtime_hash: str = Field(pattern=HASH)
    registry_hash: str = Field(pattern=HASH)
    population_id: None
    valid_until: AwareDatetime
    checked_at: AwareDatetime


@dataclass(frozen=True)
class ViewedOriginalV1:
    data: bytes
    valid_until: datetime


class OriginalViewerUnavailable(PermissionError):
    """No success, retry, qualification or remote delivery assertion."""


class OriginalViewerFactoryV1:
    def __init__(self, settings):
        if type(settings) is not OriginalViewerSettingsV1:
            raise TypeError('fixed separate viewer settings required')
        settings.current()
        self.settings = settings

    def _current(self, deadline):
        if type(deadline) is not datetime or deadline.tzinfo is None or deadline.utcoffset() is None:
            raise PermissionError('aware absolute original viewer deadline required')
        horizon = self.settings.current()
        now = datetime.now(timezone.utc)
        if not now < deadline <= horizon:
            raise PermissionError('original viewer deadline elapsed or excessive')
        return max(1, int((deadline - now).total_seconds() * 1000))

    def _check(self, conn, target, deadline):
        c = self.settings.config
        remaining = self._current(deadline)
        actual = conn.info.get_parameters()
        if (not conn.pgconn.ssl_in_use
                or any(str(actual.get(k, '')) != str(target.get(k, '')) for k in ('host', 'dbname', 'user', 'sslmode', 'sslrootcert'))
                or conn.info.port != int(target.get('port', 5432))
                or (target.get('hostaddr') and conn.info.hostaddr != target['hostaddr'])):
            raise PermissionError('actual viewer TLS SQL target differs')
        conn.execute("SELECT set_config('statement_timeout',%s,true),set_config('lock_timeout',%s,true)",
                     (str(min(5000, remaining)), str(min(2000, remaining))))
        row = conn.execute('SELECT session_user,current_user,rolcanlogin,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=session_user').fetchone()
        if (not row or row[:2] != (c.expected_session_role, c.expected_session_role)
                or row[2] is not True or any(row[3:])):
            raise PermissionError('actual viewer login differs')
        reachable = conn.execute("SELECT rolname::text FROM pg_roles WHERE pg_has_role(session_user,oid,'MEMBER') OR pg_has_role(session_user,oid,'SET') OR pg_has_role(session_user,oid,'USAGE')").fetchall()
        if {r[0] for r in reachable} != {c.expected_session_role, GROUP}:
            raise PermissionError('exclusive actual viewer role required')
        flags = conn.execute('SELECT rolcanlogin,rolinherit,rolsuper,rolbypassrls,rolcreatedb,rolcreaterole,rolreplication FROM pg_roles WHERE rolname=%s', (GROUP,)).fetchone()
        if flags is None or any(flags):
            raise PermissionError('fixed viewer group flags differ')
        owner = conn.execute("SELECT r.rolname,pg_has_role(session_user,r.oid,'MEMBER') FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner WHERE n.nspname='oracle2'").fetchone()
        if owner != (c.expected_owner_role, False):
            raise PermissionError('viewer schema owner differs')
        rows = conn.execute(OWNER_QUERY).fetchall()
        expected = {(name, 'oracle2', name, c.expected_owner_role, True) for name, _ in FUNCTIONS}
        if len(rows) != len(FUNCTIONS) or set(rows) != expected:
            raise PermissionError('viewer fixed function identities differ')
        self._current(deadline)

    def _capability(self, conn, ref, deadline):
        row = conn.execute('SELECT oracle2.original_revision_view_v1(%s,%s)', (ref.source_id, ref.revision)).fetchone()
        if row is None:
            raise PermissionError('current original view unavailable')
        cap = ViewerCapabilityV1.model_validate_json(canonical_bytes(row[0]))
        c = self.settings.config
        if ((cap.workspace_id, cap.principal_id, cap.source_id, cap.revision, cap.original_sha256,
                cap.byte_count, cap.media_type, cap.runtime_hash, cap.registry_hash) !=
                (c.workspace_id, c.principal_id, ref.source_id, ref.revision, ref.original_sha256,
                ref.byte_count, ref.media_type, c.runtime_hash, c.registry_hash)):
            raise PermissionError('current original viewer tuple differs')
        now = datetime.now(timezone.utc)
        if not cap.checked_at <= now < cap.valid_until or now - cap.checked_at > timedelta(seconds=5):
            raise PermissionError('original viewer capability expired or stale')
        self._current(deadline)
        return cap

    def _private(self, cap, ref, deadline):
        self._current(deadline)
        c = self.settings.config
        original = OriginalObjectRefV1(c.workspace_id, ref.source_id, ref.revision, ref.original_sha256,
                                      ref.byte_count, ref.media_type, c.storage_profile_hash)
        item = ReservationOriginalObjectRefV1(original, ref.reservation_id)
        if item.key != cap.private_object_key:
            raise PermissionError('exact viewer private locator differs')
        root = Path(c.storage_root)
        store = FileBlobStore._from_provisioned_original_root(root, (c.storage_device, c.storage_inode, c.storage_uid))
        observation = dict(schema_version=1, purpose='original-intake-byte-custody-v1',
            reservation_id=str(ref.reservation_id), source_id=str(ref.source_id), workspace_id=str(c.workspace_id),
            revision=ref.revision, private_object_key=item.key, original_sha256=ref.original_sha256,
            byte_count=ref.byte_count, storage_profile_hash=c.storage_profile_hash)
        if _worker_file(root / 'intake-observations' / str(ref.reservation_id) / 'custody.json',
                        ref.custody_seal_sha256, limit=4096) != canonical_bytes(observation):
            raise PermissionError('independently pinned original custody differs')
        self._current(deadline)
        data = store._read_original_bytes(item)
        self._current(deadline)
        if not data.startswith(b'%PDF-'):
            raise PermissionError('fixed PDF source framing required')
        if hashlib.sha256(data).hexdigest() != ref.original_sha256 or len(data) != ref.byte_count:
            raise PermissionError('original viewer bytes differ')
        return data

    def read_pdf_v1(self, source_id, revision, *, caller_deadline):
        # No cached capability and no retry, including close or uncertain I/O.
        try:
            if type(source_id) is not UUID or type(revision) is not int or revision < 1:
                raise PermissionError('exact original selector required')
            now = datetime.now(timezone.utc)
            if type(caller_deadline) is not datetime or caller_deadline.tzinfo is None or caller_deadline > now + timedelta(seconds=30):
                raise PermissionError('bounded original viewer deadline required')
            self._current(caller_deadline)
            c = self.settings.config
            matches = [r for r in c.sources if (r.source_id, r.revision) == (source_id, revision)]
            if len(matches) != 1:
                raise PermissionError('externally appointed source required')
            ref = matches[0]
            raw = _pinned(c.database_url.path, c.database_url.sha256, 16384).decode('utf-8')
            _pinned(c.database_ca.path, c.database_ca.sha256, 131072)
            target = psycopg.conninfo.conninfo_to_dict(raw)
            if (set(target) - {'host', 'hostaddr', 'port', 'dbname', 'user', 'password', 'sslmode', 'sslrootcert'}
                    or target.get('sslmode') != 'verify-full' or target.get('sslrootcert') != c.database_ca.path
                    or target.get('user') != c.expected_session_role or not target.get('dbname')):
                raise PermissionError('fixed viewer SQL target required')
            ipaddress.ip_address(target.get('hostaddr') or target.get('host', ''))
            data = None
            for phase in range(2):
                remaining = self._current(caller_deadline)
                if remaining < 1000:
                    raise PermissionError('insufficient original SQL connection budget')
                # DNS is excluded above. Libpq and server wait bounds narrow the
                # same absolute deadline; no failure issues a replacement query.
                with psycopg.connect(raw, connect_timeout=min(5, remaining // 1000),
                        tcp_user_timeout=remaining,
                        options=f'-c statement_timeout={min(5000, remaining)} -c lock_timeout={min(2000, remaining)}') as conn:
                    self._check(conn, target, caller_deadline)
                    before = self._capability(conn, ref, caller_deadline)
                    caller_deadline = min(caller_deadline, before.valid_until)
                    if phase == 0:
                        data = self._private(before, ref, caller_deadline)
                    after = self._capability(conn, ref, caller_deadline)
                    caller_deadline = min(caller_deadline, after.valid_until)
                    if before.private_object_key != after.private_object_key:
                        raise PermissionError('original viewer locator changed')
                    self._check(conn, target, caller_deadline)
                    self._current(min(caller_deadline, before.valid_until, after.valid_until))
                    conn.commit()
                # Actual close must succeed; only then start independent phase2.
                self._current(min(caller_deadline, before.valid_until, after.valid_until))
            return ViewedOriginalV1(data, caller_deadline)
        except Exception:
            raise OriginalViewerUnavailable('original view unavailable; delivery unproved') from None
