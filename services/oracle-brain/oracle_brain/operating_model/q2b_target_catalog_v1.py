"""Q2b offline metadata-only catalog-proof tooling.

A separately admitted metadata-only catalog read must prove actual pg_proc
owner, SECURITY DEFINER flag, search_path, EXECUTE grants, role memberships and
target identity before any installation or live target action. UNKNOWN blocks
target execution and must not cause a substitute owner or admin path.

This module is pure SQL text plus parse/validate. It never reads source data,
secrets or environment values, never issues grants or roles, and never claims
Q2b. Receipts it emits keep ``admitted`` false until ``admit_target_catalog``
seals admission after real pin checks. The seal is a purpose-tagged Ed25519
signature over the admitted fact payload — the ``admitted`` boolean alone
never grants access. The expected search_path is fixed here and cannot be
weakened by a caller-supplied pin.

Authority is the Ed25519 signature alone. There is no mutable in-process
admission registry to forge or mutate through ``__closure__``.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Literal

from pydantic import Field

from .contracts import StrictRecord

# The six fact classes required by plan_oracle_source_processing_qualification.md §9.1.
FACT_CLASSES = (
    'pg_proc_owner',
    'security_definer',
    'search_path',
    'execute_grants',
    'role_memberships',
    'target_identity',
)

UNKNOWN: Literal['UNKNOWN'] = 'UNKNOWN'

# Purpose tag for the reader-seal signature over the six fact classes.
# A signature issued under a different purpose never satisfies admission.
READER_FACT_PURPOSE = 'q2b-reader-facts:v1'
# Purpose tag for the admission seal produced after real pin checks.
ADMISSION_PURPOSE = 'q2b-admission:v1'
# Purpose tag for a sealed connection capability issued by an adapter.
CONNECTION_PURPOSE = 'q2b-connection:v1'

# Exact proconfig expected on every reviewed helper. PostgreSQL stores the
# normalised form with a space after the comma; callers cannot substitute it.
EXPECTED_PROCONFIG = ('search_path=pg_catalog, oracle2',)

ROLE = r'^[a-z_][a-z0-9_]{0,62}$'

# Pure catalog statements. Relations touched: pg_proc, pg_roles, pg_namespace
# and catalog functions only. No source table, secret or environment value.
FUNCTION_CATALOG_SQL = """
SELECT requested.signature, owner.rolname, p.prosecdef, p.proconfig,
    coalesce(jsonb_agg(jsonb_build_array(coalesce(grantee.rolname,'PUBLIC'),acl.is_grantable))
        FILTER (WHERE acl.privilege_type='EXECUTE' AND acl.grantee<>p.proowner),'[]'::jsonb)
FROM unnest(%s::text[]) WITH ORDINALITY requested(signature,ordinal)
LEFT JOIN pg_proc p ON p.oid=to_regprocedure(requested.signature)
LEFT JOIN pg_namespace namespace ON namespace.oid=p.pronamespace
LEFT JOIN pg_roles owner ON owner.oid=p.proowner
LEFT JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) acl ON true
LEFT JOIN pg_roles grantee ON grantee.oid=acl.grantee
GROUP BY requested.signature,requested.ordinal,owner.rolname,p.prosecdef,p.proconfig
ORDER BY requested.ordinal
"""

ROLE_REACHABILITY_SQL = """
SELECT
  session_user,
  current_user,
  (SELECT row_to_json(o) FROM (
    SELECT r.rolname,
           pg_has_role(session_user,r.oid,'MEMBER') AS member,
           pg_has_role(session_user,r.oid,'SET') AS set,
           pg_has_role(session_user,r.oid,'USAGE') AS usage
    FROM pg_roles r WHERE r.rolname=%s) o),
  (SELECT COALESCE(jsonb_agg(rolname::text ORDER BY rolname),'[]'::jsonb)
   FROM pg_roles
   WHERE pg_has_role(session_user,oid,'MEMBER')
      OR pg_has_role(session_user,oid,'SET')
      OR pg_has_role(session_user,oid,'USAGE'))
"""

TARGET_IDENTITY_SQL = """
SELECT current_database() AS dbname, session_user, inet_server_port() AS port
"""

READER_SQL_STATEMENTS = (FUNCTION_CATALOG_SQL, ROLE_REACHABILITY_SQL, TARGET_IDENTITY_SQL)

# Any statement that could reach source data, secrets or environment values is
# refused before execution. The allowlist is catalog relations and the catalog
# set-returning functions used as FROM sources.
_FORBIDDEN_SQL = (
    'oracle2.', 'pg_authid', 'pg_auth_members', 'pg_shadow', 'pg_read_',
    'pg_ls_', 'pg_file_settings', 'pg_stat_file', 'current_setting', 'pg_settings',
    'pg_env', 'source_block', 'source_receipt', 'insert ', 'update ', 'delete ',
    'copy ', 'create ', 'alter ', 'drop ', 'grant ', 'revoke ', 'truncate ',
    'call ', 'do ', 'execute ', 'prepare ', 'pg_sleep', 'dblink', 'lo_import',
    'lo_export', 'pg_read_file', 'pg_stat_file',
)
_ALLOWED_FROM_RELATIONS = frozenset({
    'pg_proc', 'pg_roles', 'pg_namespace', 'unnest', 'aclexplode', 'pg_catalog',
})
_FROM_RE = re.compile(
    r'(?:FROM|JOIN)\s+(?:LATERAL\s+)?([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)',
    re.I,
)


def require_metadata_only_sql(sql: str) -> None:
    """Refuse any statement that is not a pure catalog SELECT. Fail closed."""
    if not isinstance(sql, str) or not sql.strip():
        raise PermissionError('Q2b catalog SQL text required')
    stripped = sql.strip().lower()
    if not (stripped.startswith('select') or stripped.startswith('with')):
        raise PermissionError('Q2b catalog read is metadata-only SELECT')
    lowered = re.sub(r'\s+', ' ', stripped)
    for token in _FORBIDDEN_SQL:
        if token in lowered:
            raise PermissionError('Q2b catalog SQL must not touch source data, secrets or env')
    for relation in _FROM_RE.findall(sql):
        root = relation.split('.')[0].lower()
        if root not in _ALLOWED_FROM_RELATIONS:
            raise PermissionError('Q2b catalog SQL relation outside metadata allowlist')


def _require_all_metadata_sql() -> None:
    for statement in READER_SQL_STATEMENTS:
        require_metadata_only_sql(statement)


_require_all_metadata_sql()


@dataclass(frozen=True)
class Q2bExpectedPins:
    """Reviewed expected descriptor and role scope.

    Incomplete pins refuse the read. These values come from the externally
    reviewed immutable installer/descriptor, never from a request. They confer
    no authority and invent no live fact.
    """
    expected_owner_role: str
    expected_session_role: str
    function_signatures: tuple[str, ...]
    expected_execute_grants: tuple[tuple[str, tuple[str, ...]], ...]
    role_scope: tuple[str, ...]
    expected_host: str
    expected_port: int
    expected_dbname: str
    expected_user: str
    expected_sslmode: str = 'verify-full'

    def __post_init__(self):
        roles = (self.expected_owner_role, self.expected_session_role)
        signatures = self.function_signatures
        raw_grants = self.expected_execute_grants
        grant_map = dict(raw_grants) if isinstance(raw_grants, tuple) else {}
        complete = (
            all(isinstance(r, str) and re.fullmatch(ROLE, r) for r in roles)
            and isinstance(signatures, tuple) and len(signatures) > 0
            and all(isinstance(s, str) and s for s in signatures)
            and isinstance(raw_grants, tuple) and len(raw_grants) > 0
            and set(grant_map) == set(signatures)
            and all(isinstance(g, tuple) and all(isinstance(n, str) and n for n in g)
                    for _, g in raw_grants)
            and isinstance(self.role_scope, tuple) and len(self.role_scope) > 0
            and all(isinstance(r, str) and re.fullmatch(ROLE, r) for r in self.role_scope)
            and self.expected_owner_role in self.role_scope
            and isinstance(self.expected_host, str) and self.expected_host != ''
            and type(self.expected_port) is int and 1 <= self.expected_port <= 65535
            and isinstance(self.expected_dbname, str) and self.expected_dbname != ''
            and isinstance(self.expected_user, str) and self.expected_user != ''
            and self.expected_sslmode == 'verify-full'
        )
        if not complete:
            raise PermissionError('complete Q2b expected descriptor/role scope required')


class Q2bExecuteGrant(StrictRecord):
    """One EXECUTE ACL entry. PUBLIC is spelled 'PUBLIC' as in aclexplode."""
    grantee: str = Field(min_length=1, max_length=63)
    is_grantable: bool


class Q2bProcOwnerFact(StrictRecord):
    fact_class: Literal['pg_proc_owner'] = 'pg_proc_owner'
    values: tuple[tuple[str, str | Literal['UNKNOWN']], ...] = Field(min_length=1)


class Q2bSecurityDefinerFact(StrictRecord):
    fact_class: Literal['security_definer'] = 'security_definer'
    values: tuple[tuple[str, bool | Literal['UNKNOWN']], ...] = Field(min_length=1)


class Q2bSearchPathFact(StrictRecord):
    fact_class: Literal['search_path'] = 'search_path'
    values: tuple[tuple[str, tuple[str, ...] | Literal['UNKNOWN']], ...] = Field(min_length=1)


class Q2bExecuteGrantsFact(StrictRecord):
    fact_class: Literal['execute_grants'] = 'execute_grants'
    values: tuple[tuple[str, tuple[Q2bExecuteGrant, ...] | Literal['UNKNOWN']], ...] = Field(min_length=1)


class Q2bRoleMembershipsFact(StrictRecord):
    fact_class: Literal['role_memberships'] = 'role_memberships'
    session_user: str | Literal['UNKNOWN'] = UNKNOWN
    current_user: str | Literal['UNKNOWN'] = UNKNOWN
    owner_reachable_member: bool | Literal['UNKNOWN'] = UNKNOWN
    owner_reachable_set: bool | Literal['UNKNOWN'] = UNKNOWN
    owner_reachable_usage: bool | Literal['UNKNOWN'] = UNKNOWN
    reachable_roles: tuple[str, ...] | Literal['UNKNOWN'] = UNKNOWN


class Q2bTargetIdentityFact(StrictRecord):
    fact_class: Literal['target_identity'] = 'target_identity'
    host: str | Literal['UNKNOWN'] = UNKNOWN
    port: int | Literal['UNKNOWN'] = UNKNOWN
    dbname: str | Literal['UNKNOWN'] = UNKNOWN
    user: str | Literal['UNKNOWN'] = UNKNOWN
    ssl_in_use: bool | Literal['UNKNOWN'] = UNKNOWN
    sslmode: str | Literal['UNKNOWN'] = UNKNOWN


def _fact_has_unknown(value) -> bool:
    """True when a fact class is UNKNOWN or any nested observation is UNKNOWN."""
    if value is UNKNOWN:
        return True
    values = getattr(value, 'values', None)
    if values is not None:
        for item in values:
            if len(item) == 2 and item[1] == UNKNOWN:
                return True
            if len(item) == 2 and isinstance(item[1], tuple) and item[1] == UNKNOWN:
                return True
        return False
    for name in ('session_user', 'current_user', 'owner_reachable_member', 'owner_reachable_set',
                 'owner_reachable_usage', 'reachable_roles',
                 'host', 'port', 'dbname', 'user', 'ssl_in_use', 'sslmode'):
        if getattr(value, name, None) == UNKNOWN:
            return True
    return False


class Q2bTargetCatalogReceipt(StrictRecord):
    """Six fact classes, UNKNOWN allowed, nothing invented.

    ``admitted`` stays false from this tooling. A separate sealed admission
    (``admit_target_catalog``) is a different artifact; the ``admitted``
    boolean alone never authorises target execution — the purpose-tagged
    ``admission_mac`` signature does. This receipt alone never authorises
    target execution.
    """
    purpose: Literal['q2b-target-catalog-proof-v1'] = 'q2b-target-catalog-proof-v1'
    pg_proc_owner: Q2bProcOwnerFact | Literal['UNKNOWN'] = UNKNOWN
    security_definer: Q2bSecurityDefinerFact | Literal['UNKNOWN'] = UNKNOWN
    search_path: Q2bSearchPathFact | Literal['UNKNOWN'] = UNKNOWN
    execute_grants: Q2bExecuteGrantsFact | Literal['UNKNOWN'] = UNKNOWN
    role_memberships: Q2bRoleMembershipsFact | Literal['UNKNOWN'] = UNKNOWN
    target_identity: Q2bTargetIdentityFact | Literal['UNKNOWN'] = UNKNOWN
    admitted: bool = False
    fact_mac: str = ''
    admission_mac: str = ''

    def fact_classes(self) -> tuple[str, ...]:
        return FACT_CLASSES

    def unknown_classes(self) -> tuple[str, ...]:
        return tuple(name for name in FACT_CLASSES if _fact_has_unknown(getattr(self, name)))


def parse_function_catalog(rows) -> tuple[
    Q2bProcOwnerFact, Q2bSecurityDefinerFact, Q2bSearchPathFact, Q2bExecuteGrantsFact
]:
    """Parse pg_proc owner/prosecdef/proconfig/ACL rows. Missing stays UNKNOWN."""
    owners: list[tuple[str, str | Literal['UNKNOWN']]] = []
    definers: list[tuple[str, bool | Literal['UNKNOWN']]] = []
    paths: list[tuple[str, tuple[str, ...] | Literal['UNKNOWN']]] = []
    grants: list[tuple[str, tuple[Q2bExecuteGrant, ...] | Literal['UNKNOWN']]] = []
    for row in rows:
        signature, owner_role, prosecdef, proconfig, acl = row
        present = owner_role is not None
        owners.append((signature, owner_role if present else UNKNOWN))
        definers.append((signature, bool(prosecdef) if present else UNKNOWN))
        paths.append((signature, tuple(proconfig) if present and proconfig is not None else UNKNOWN))
        if not present:
            grants.append((signature, UNKNOWN))
            continue
        entries: list[Q2bExecuteGrant] = []
        for item in (acl or []):
            grantee, is_grantable = item
            entries.append(Q2bExecuteGrant(grantee=str(grantee), is_grantable=bool(is_grantable)))
        grants.append((signature, tuple(entries)))
    if not owners:
        raise PermissionError('Q2b function catalog rows required')
    return (
        Q2bProcOwnerFact(values=tuple(owners)),
        Q2bSecurityDefinerFact(values=tuple(definers)),
        Q2bSearchPathFact(values=tuple(paths)),
        Q2bExecuteGrantsFact(values=tuple(grants)),
    )


def parse_role_memberships(row) -> Q2bRoleMembershipsFact:
    """Parse one pg_has_role reachability row. Absent row is all UNKNOWN."""
    if row is None:
        return Q2bRoleMembershipsFact()
    session_user, current_user, owner_row, reachable = row
    if owner_row is None:
        return Q2bRoleMembershipsFact(
            session_user=session_user if session_user is not None else UNKNOWN,
            current_user=current_user if current_user is not None else UNKNOWN,
        )
    return Q2bRoleMembershipsFact(
        session_user=session_user if session_user is not None else UNKNOWN,
        current_user=current_user if current_user is not None else UNKNOWN,
        owner_reachable_member=bool(owner_row['member']),
        owner_reachable_set=bool(owner_row['set']),
        owner_reachable_usage=bool(owner_row['usage']),
        reachable_roles=tuple(reachable) if reachable is not None else UNKNOWN,
    )


def parse_target_identity(identity_row, *, params, ssl_in_use) -> Q2bTargetIdentityFact:
    """Combine connection identity metadata with the catalog identity row."""
    params = params or {}
    host = params.get('host')
    sslmode = params.get('sslmode')
    dbname = port = user = None
    if identity_row is not None:
        row = identity_row
        if isinstance(row, dict):
            dbname, user, port = row.get('dbname'), row.get('user'), row.get('port')
        else:
            dbname, user, port = row[0], row[1], row[2]
    if dbname is None:
        dbname = params.get('dbname')
    if user is None:
        user = params.get('user')
    if port is None:
        raw_port = params.get('port')
        try:
            port = int(raw_port) if raw_port is not None else None
        except (TypeError, ValueError):
            port = None
    try:
        port_value: int | Literal['UNKNOWN'] = int(port) if port is not None else UNKNOWN
    except (TypeError, ValueError):
        port_value = UNKNOWN
    return Q2bTargetIdentityFact(
        host=host if host is not None else UNKNOWN,
        port=port_value,
        dbname=dbname if dbname is not None else UNKNOWN,
        user=user if user is not None else UNKNOWN,
        ssl_in_use=bool(ssl_in_use) if ssl_in_use is not None else UNKNOWN,
        sslmode=sslmode if sslmode is not None else UNKNOWN,
    )


def build_receipt(
    *,
    pg_proc_owner,
    security_definer,
    search_path,
    execute_grants,
    role_memberships,
    target_identity,
) -> Q2bTargetCatalogReceipt:
    """Assemble the six fact classes. ``admitted`` is always false here; a
    separate sealed admission is required and this tooling never supplies one."""
    return Q2bTargetCatalogReceipt(
        pg_proc_owner=pg_proc_owner,
        security_definer=security_definer,
        search_path=search_path,
        execute_grants=execute_grants,
        role_memberships=role_memberships,
        target_identity=target_identity,
        admitted=False,
    )


def _facts_payload(receipt: Q2bTargetCatalogReceipt) -> str:
    """Canonical JSON of the six fact classes for MAC binding.

    Excludes ``admitted``, ``fact_mac`` and ``admission_mac`` so the
    seal covers exactly the observed facts and nothing caller-writable
    about admission state.
    """
    data = receipt.model_dump(mode='json', exclude={'admitted', 'fact_mac', 'admission_mac'})
    return json.dumps(data, sort_keys=True, separators=(',', ':'))


class CatalogConnection:
    """Sealed connection capability issued by an adapter.

    Authority is the Ed25519 ``connection_mac`` over the connection
    identity under ``CONNECTION_PURPOSE``. Direct construction is refused.
    A duck-typed look-alike built with ``object.__new__`` carries no valid
    signature and is denied before any sign. There is no capability
    registry to mutate.
    """
    __slots__ = ('_connection', '_identity', '_connection_mac', '__weakref__')

    def __init__(self, *args, **kwargs) -> None:
        raise PermissionError('catalog connection capability cannot be forged')

    @property
    def connection(self):
        return self._connection

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def connection_mac(self) -> str:
        return self._connection_mac


def issue_catalog_connection(connection, *, identity: str,
                             connection_mac: str) -> CatalogConnection:
    """Adapter: wrap a DB-API connection in a sealed capability.

    ``connection_mac`` must be a host-issued Ed25519 seal over the
    connection identity under ``CONNECTION_PURPOSE``. Without a valid
    seal the call is denied. The capability carries its signature; there
    is no registry membership to forge.
    """
    if connection is None or not identity or not connection_mac:
        raise PermissionError('sealed catalog connection requires identity and signature')
    from oracle_brain.seal import verify_mac
    verify_mac(CONNECTION_PURPOSE, connection_mac, identity)
    capability = object.__new__(CatalogConnection)
    capability._connection = connection
    capability._identity = identity
    capability._connection_mac = connection_mac
    return capability


def _real_dbapi_connection_types() -> tuple:
    """Real DB-API connection classes, when the driver is installed."""
    types = []
    try:
        import psycopg
        types.append(psycopg.Connection)
    except Exception:  # noqa: BLE001 — driver absent is not fatal here
        pass
    try:
        import psycopg2.extensions
        types.append(psycopg2.extensions.connection)
    except Exception:  # noqa: BLE001
        pass
    return tuple(types)


def _require_catalog_connection(connection):
    """Accept only a real DB-API connection or a sealed capability.

    Duck-typed fakes are denied before any sign. A sealed capability's
    signature is re-verified here so a mutated look-alike never reaches
    the catalog.
    """
    real_types = _real_dbapi_connection_types()
    if real_types and isinstance(connection, real_types):
        return connection
    if isinstance(connection, CatalogConnection):
        from oracle_brain.seal import verify_mac
        verify_mac(CONNECTION_PURPOSE, connection.connection_mac,
                   connection.identity)
        return connection.connection
    raise PermissionError(
        'Q2b catalog connection must be a real DB-API connection '
        'or a sealed connection capability')


def _connection_params(connection) -> dict:
    info = getattr(connection, 'info', None)
    getter = getattr(info, 'get_parameters', None)
    if getter is None:
        return {}
    try:
        params = getter()
    except Exception:
        return {}
    return dict(params) if params else {}


def _connection_ssl_in_use(connection):
    pgconn = getattr(connection, 'pgconn', None)
    value = getattr(pgconn, 'ssl_in_use', None)
    return value if value is not None else None


def _fact_value(pairs, signature):
    for key, value in pairs:
        if key == signature:
            return value
    return UNKNOWN


def _require_all_pins(receipt: Q2bTargetCatalogReceipt,
                      expected: Q2bExpectedPins) -> None:
    """Deny unless every fact class is observed and matches the reviewed pins.

    UNKNOWN blocks target execution. A mismatch never falls back to a
    substitute owner or admin path.
    """
    unknown = receipt.unknown_classes()
    if unknown:
        raise PermissionError('Q2b target catalog UNKNOWN blocks target execution')

    owners = receipt.pg_proc_owner.values
    definers = receipt.security_definer.values
    paths = receipt.search_path.values
    grants = receipt.execute_grants.values
    for signature in expected.function_signatures:
        owner = _fact_value(owners, signature)
        if owner != expected.expected_owner_role:
            raise PermissionError('Q2b pg_proc owner differs')
        prosecdef = _fact_value(definers, signature)
        if prosecdef is not True:
            raise PermissionError('Q2b SECURITY DEFINER flag missing')
        proconfig = _fact_value(paths, signature)
        if proconfig != EXPECTED_PROCONFIG:
            raise PermissionError('Q2b search_path differs')
        actual = _fact_value(grants, signature)
        if actual == UNKNOWN:
            raise PermissionError('Q2b EXECUTE grants UNKNOWN')
        allowed = frozenset(dict(expected.expected_execute_grants)[signature])
        names = frozenset(g.grantee for g in actual)
        if names != allowed or any(g.is_grantable for g in actual):
            raise PermissionError('Q2b EXECUTE grants differ')

    memberships = receipt.role_memberships
    if (memberships.owner_reachable_member is not False
            or memberships.owner_reachable_set is not False
            or memberships.owner_reachable_usage is not False):
        raise PermissionError('Q2b owner reachable via membership')
    if memberships.session_user != expected.expected_session_role:
        raise PermissionError('Q2b session role differs')
    if memberships.current_user == expected.expected_owner_role:
        raise PermissionError('Q2b owner assumed via SET ROLE')
    if isinstance(memberships.reachable_roles, tuple):
        if expected.expected_owner_role in memberships.reachable_roles:
            raise PermissionError('Q2b owner reachable via membership')
        discovered = set(memberships.reachable_roles)
        allowed = set(expected.role_scope)
        if not discovered.issubset(allowed):
            raise PermissionError('Q2b unexpected reachable role')

    identity = receipt.target_identity
    if (identity.host != expected.expected_host
            or identity.port != expected.expected_port
            or identity.dbname != expected.expected_dbname
            or identity.user != expected.expected_user):
        raise PermissionError('Q2b target identity differs')
    if identity.ssl_in_use is not True or identity.sslmode != 'verify-full':
        raise PermissionError('Q2b TLS not in use')
    if expected.expected_sslmode != 'verify-full':
        raise PermissionError('Q2b TLS not in use')


def _install_sealed_catalog_api(*, mint, verify):
    """Sealed Q2b catalog API: bound mint/verify, signature-only admission.

    Receives the bound internal mint and verify callables from the seal
    closure and closes over them. There is no mutable registry: admission
    is a purpose-tagged Ed25519 signature over the admitted fact payload,
    and use-site checks re-verify that signature plus the reader seal and
    the pin expectations. A constructor copy with ``admitted=True`` and no
    valid ``admission_mac`` is denied — there is no identity table to
    mutate through ``__closure__``.
    """

    def read_target_catalog(connection, expected: Q2bExpectedPins) -> Q2bTargetCatalogReceipt:
        """Metadata-only catalog read. Refuses incomplete pins and any non-metadata SQL.

        The connection must be a real DB-API connection or a sealed
        connection capability; duck-typed fakes are denied before any
        sign. Reads only pg_proc owner/prosecdef/proconfig/ACL, pg_has_role
        reachability and target identity (host/port/dbname/user + TLS).
        Never source data, secrets or environment values. Emits UNKNOWN
        where the catalog holds nothing; invents no fact. Seals the six
        fact classes with a purpose-tagged MAC issued through the bound
        internal mint.
        """
        if not isinstance(expected, Q2bExpectedPins):
            raise PermissionError('complete Q2b expected descriptor/role scope required')
        conn = _require_catalog_connection(connection)
        execute = getattr(conn, 'execute', None)
        if execute is None:
            raise PermissionError('Q2b catalog connection execute required')
        params = _connection_params(conn)
        ssl_in_use = _connection_ssl_in_use(conn)

        for statement in READER_SQL_STATEMENTS:
            require_metadata_only_sql(statement)

        function_rows = execute(FUNCTION_CATALOG_SQL, (list(expected.function_signatures),)).fetchall()
        role_row_raw = execute(ROLE_REACHABILITY_SQL, (expected.expected_owner_role,)).fetchone()
        identity_row = execute(TARGET_IDENTITY_SQL).fetchone()

        pg_proc_owner, security_definer, search_path, execute_grants = parse_function_catalog(function_rows)
        role_memberships = parse_role_memberships(role_row_raw)
        target_identity = parse_target_identity(identity_row, params=params, ssl_in_use=ssl_in_use)
        receipt = build_receipt(
            pg_proc_owner=pg_proc_owner,
            security_definer=security_definer,
            search_path=search_path,
            execute_grants=execute_grants,
            role_memberships=role_memberships,
            target_identity=target_identity,
        )
        fact_mac = mint(READER_FACT_PURPOSE, _facts_payload(receipt))
        return receipt.model_copy(update={'fact_mac': fact_mac})

    def admit_target_catalog(receipt: Q2bTargetCatalogReceipt,
                             expected: Q2bExpectedPins) -> Q2bTargetCatalogReceipt:
        """Sealed admit: reader-seal MAC check, real pin checks, then seal.

        The receipt must carry a reader-produced ``fact_mac`` — an
        Ed25519 seal over the six fact classes issued by
        ``read_target_catalog`` via the isolated signer. Caller-constructed
        fact dicts are denied even when every value matches the pins:
        without the reader seal they prove nothing about where the facts
        came from. Pin checks follow. Only then is admission sealed with
        ``admission_mac`` — a purpose-tagged signature over the admitted
        fact payload. The signature is the authority; there is no
        registry.
        """
        if not isinstance(receipt, Q2bTargetCatalogReceipt) or not isinstance(expected, Q2bExpectedPins):
            raise PermissionError('Q2b target catalog receipt and complete pins required')
        if not receipt.fact_mac:
            raise PermissionError('Q2b reader-produced sealed facts required')
        verify(READER_FACT_PURPOSE, receipt.fact_mac, _facts_payload(receipt))
        _require_all_pins(receipt, expected)
        admission_mac = mint(ADMISSION_PURPOSE, _facts_payload(receipt))
        return receipt.model_copy(update={'admitted': True, 'admission_mac': admission_mac})

    def require_target_catalog(receipt: Q2bTargetCatalogReceipt,
                               expected: Q2bExpectedPins) -> None:
        """Use-site gate: signed admission plus real pin checks.

        The ``admitted`` boolean alone is never believed. The
        ``admission_mac`` signature over the admitted fact payload is the
        admission proof; a constructor copy with ``admitted=True`` and no
        valid signature is denied. The reader-seal MAC is rechecked so
        damage to the fact fields between admission and use never grants
        access. Pin checks are redone for the same reason.
        """
        if not isinstance(receipt, Q2bTargetCatalogReceipt) or not isinstance(expected, Q2bExpectedPins):
            raise PermissionError('Q2b target catalog receipt and complete pins required')
        if receipt.admitted is not True or not receipt.admission_mac:
            raise PermissionError('Q2b target catalog not admitted')
        verify(ADMISSION_PURPOSE, receipt.admission_mac, _facts_payload(receipt))
        if not receipt.fact_mac:
            raise PermissionError('Q2b reader-produced sealed facts required')
        verify(READER_FACT_PURPOSE, receipt.fact_mac, _facts_payload(receipt))
        _require_all_pins(receipt, expected)

    return read_target_catalog, admit_target_catalog, require_target_catalog


# Public catalog API is installed by oracle_brain.seal with bound mint/verify.
# Importing the seal module runs its factory wire, which calls
# _install_sealed_catalog_api and assigns the three public names here.
import oracle_brain.seal  # noqa: E402,F401
