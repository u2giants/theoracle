"""Offline Q2b metadata-only catalog-proof tooling; no real target, no live read.

Synthetic/isolated fixtures only. These tests never connect to a production or
shared database and never read source data, secrets or environment values.
Q2b stays OPEN: actual target owner/caller/TLS remain UNKNOWN.
"""
from types import SimpleNamespace

import pytest

from oracle_brain.operating_model import q2b_target_catalog_v1 as q2b
from oracle_brain.operating_model.q2b_target_catalog_v1 import (
    EXPECTED_PROCONFIG,
    FACT_CLASSES,
    Q2bExecuteGrant,
    Q2bExpectedPins,
    Q2bTargetCatalogReceipt,
    admit_target_catalog,
    build_receipt,
    parse_function_catalog,
    parse_role_memberships,
    parse_target_identity,
    read_target_catalog,
    require_metadata_only_sql,
    require_target_catalog,
    READER_FACT_PURPOSE,
    _facts_payload,
)


def _test_mac(purpose, *fields):
    """Produce a purpose-tagged seal via the signer CLI (test host stand-in)."""
    from seal_testkit import sign_seal
    return sign_seal(purpose, *fields)


def _reseal(receipt):
    """Re-compute the reader-seal MAC after a deliberate fact mutation.

    Pin-check tests damage fact values but must still exercise the pin
    path, so they re-seal with the test keypair to bypass the seal gate.
    """
    return receipt.model_copy(update={
        'fact_mac': _test_mac(READER_FACT_PURPOSE, _facts_payload(receipt)),
    })

SIGNATURES = (
    'oracle2.invented_helper_alpha(integer)',
    'oracle2.invented_helper_beta(uuid,uuid)',
)
OWNER = 'invented_ledger_owner'
SESSION = 'invented_session_role'
GROUP = 'invented_reader_group'
HOST = 'invented-target.example.test'
PORT = 5432
DBNAME = 'invented_target_db'
USER = 'invented_session_role'


def pins(**overrides):
    base = dict(
        expected_owner_role=OWNER,
        expected_session_role=SESSION,
        function_signatures=SIGNATURES,
        expected_execute_grants=(
            (SIGNATURES[0], (GROUP,)),
            (SIGNATURES[1], ()),
        ),
        role_scope=(OWNER, SESSION, GROUP),
        expected_host=HOST,
        expected_port=PORT,
        expected_dbname=DBNAME,
        expected_user=USER,
        expected_sslmode='verify-full',
    )
    base.update(overrides)
    return Q2bExpectedPins(**base)


GOOD_PATH = ['search_path=pg_catalog, oracle2']
ALPHA_ACL = [[GROUP, False]]


def function_rows(damage=None):
    """Synthetic pg_proc rows: (signature, owner, prosecdef, proconfig, acl)."""
    alpha = [SIGNATURES[0], OWNER, True, GOOD_PATH, ALPHA_ACL]
    beta = [SIGNATURES[1], OWNER, True, GOOD_PATH, []]
    if damage == 'owner':
        alpha[1] = 'invented_wrong_owner'
    elif damage == 'invoker':
        alpha[2] = False
    elif damage == 'search-path':
        alpha[3] = ['search_path=oracle2, pg_catalog']
    elif damage == 'grantable':
        alpha[4] = [[GROUP, True]]
    elif damage == 'public':
        alpha[4] = [['PUBLIC', True]]
    elif damage == 'missing':
        alpha = [SIGNATURES[0], None, None, None, None]
    return [tuple(alpha), tuple(beta)]


class FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    """Duck-typed catalog connection. No network, no PostgreSQL, no secrets."""

    def __init__(self, *, function_rows, role_row, identity_row, params, ssl_in_use, log=None):
        self._function_rows = function_rows
        self._role_row = role_row
        self._identity_row = identity_row
        self.info = SimpleNamespace(get_parameters=lambda: dict(params))
        self.pgconn = SimpleNamespace(ssl_in_use=ssl_in_use)
        self.log = log if log is not None else []

    def execute(self, sql, params=None):
        self.log.append(sql)
        if 'to_regprocedure' in sql:
            return FakeResult(self._function_rows)
        if 'pg_has_role' in sql:
            return FakeResult([self._role_row] if self._role_row is not None else [])
        if 'current_database' in sql:
            return FakeResult([self._identity_row] if self._identity_row is not None else [])
        raise AssertionError('unexpected SQL in metadata-only catalog read: %r' % (sql,))


def good_connection(**overrides):
    options = dict(
        function_rows=function_rows(),
        role_row=(SESSION, SESSION, {'rolname': OWNER, 'member': False, 'set': False, 'usage': False},
                  [SESSION, GROUP]),
        identity_row=(DBNAME, USER, PORT),
        params={'host': HOST, 'port': str(PORT), 'dbname': DBNAME, 'user': USER, 'sslmode': 'verify-full'},
        ssl_in_use=True,
    )
    options.update(overrides)
    return FakeConnection(**options)


# --- reader emits the exact fact classes -----------------------------------

def test_reader_emits_exactly_the_six_fact_classes():
    receipt = read_target_catalog(good_connection(), pins())
    assert receipt.fact_classes() == FACT_CLASSES
    assert FACT_CLASSES == (
        'pg_proc_owner', 'security_definer', 'search_path',
        'execute_grants', 'role_memberships', 'target_identity',
    )
    assert receipt.unknown_classes() == ()
    assert receipt.admitted is False
    owners = dict(receipt.pg_proc_owner.values)
    assert owners == {SIGNATURES[0]: OWNER, SIGNATURES[1]: OWNER}
    assert dict(receipt.security_definer.values) == {SIGNATURES[0]: True, SIGNATURES[1]: True}
    assert dict(receipt.search_path.values) == {
        SIGNATURES[0]: EXPECTED_PROCONFIG, SIGNATURES[1]: EXPECTED_PROCONFIG,
    }
    alpha_grants = dict(receipt.execute_grants.values)[SIGNATURES[0]]
    assert [(g.grantee, g.is_grantable) for g in alpha_grants] == [(GROUP, False)]
    assert dict(receipt.execute_grants.values)[SIGNATURES[1]] == ()
    assert receipt.role_memberships.owner_reachable_member is False
    assert receipt.role_memberships.owner_reachable_set is False
    assert receipt.role_memberships.owner_reachable_usage is False
    assert receipt.role_memberships.session_user == SESSION
    identity = receipt.target_identity
    assert (identity.host, identity.port, identity.dbname, identity.user) == (HOST, PORT, DBNAME, USER)
    assert identity.ssl_in_use is True and identity.sslmode == 'verify-full'


def test_unknown_facts_are_recorded_not_invented():
    connection = good_connection(
        function_rows=[(SIGNATURES[0], None, None, None, None), (SIGNATURES[1], None, None, None, None)],
        role_row=None,
        identity_row=None,
        params={},
        ssl_in_use=None,
    )
    receipt = read_target_catalog(connection, pins())
    assert set(receipt.unknown_classes()) == set(FACT_CLASSES)
    assert receipt.admitted is False
    assert all(v == 'UNKNOWN' for _, v in receipt.pg_proc_owner.values)
    assert receipt.role_memberships.owner_reachable_member == 'UNKNOWN'
    assert receipt.target_identity.host == 'UNKNOWN'


def test_parse_helpers_keep_unknown_without_inventing_values():
    owners, definers, paths, grants = parse_function_catalog(
        [(SIGNATURES[0], None, None, None, None)]
    )
    assert owners.values == ((SIGNATURES[0], 'UNKNOWN'),)
    assert definers.values == ((SIGNATURES[0], 'UNKNOWN'),)
    assert paths.values == ((SIGNATURES[0], 'UNKNOWN'),)
    assert grants.values == ((SIGNATURES[0], 'UNKNOWN'),)
    assert parse_role_memberships(None).owner_reachable_member == 'UNKNOWN'
    identity = parse_target_identity(None, params={}, ssl_in_use=None)
    assert identity.ssl_in_use == 'UNKNOWN' and identity.port == 'UNKNOWN'


def test_receipt_admitted_false_until_separate_admission():
    receipt = read_target_catalog(good_connection(), pins())
    assert receipt.admitted is False
    with pytest.raises(PermissionError, match='not admitted'):
        require_target_catalog(receipt, pins())
    # Sealed admission after real pin checks.
    admitted = admit_target_catalog(receipt, pins())
    require_target_catalog(admitted, pins())
    # Copied receipt with admitted=True is not sealed and must not pass.
    forged = admitted.model_copy(update={'admitted': True})
    with pytest.raises(PermissionError, match='not admitted'):
        require_target_catalog(forged, pins())


def test_copied_receipt_with_admitted_true_is_denied():
    """Constructor copies with admitted=True must not pass the gate."""
    receipt = read_target_catalog(good_connection(), pins())
    forged = receipt.model_copy(update={'admitted': True})
    assert forged.admitted is True
    with pytest.raises(PermissionError, match='not admitted'):
        require_target_catalog(forged, pins())
    # Same for an unsealed read whose admitted flag is flipped.
    unsealed = read_target_catalog(good_connection(), pins())
    flipped = unsealed.model_copy(update={'admitted': True})
    with pytest.raises(PermissionError, match='not admitted'):
        require_target_catalog(flipped, pins())


def test_caller_built_facts_without_reader_seal_denied():
    """Facts not produced by the catalog reader are refused even when they match pins."""
    # Directly constructed receipt (no reader seal): denied.
    owners = ((SIGNATURES[0], OWNER), (SIGNATURES[1], OWNER))
    definers = ((SIGNATURES[0], True), (SIGNATURES[1], True))
    paths = ((SIGNATURES[0], EXPECTED_PROCONFIG), (SIGNATURES[1], EXPECTED_PROCONFIG))
    grants = (
        (SIGNATURES[0], (Q2bExecuteGrant(grantee=SESSION, is_grantable=False),)),
        (SIGNATURES[1], (Q2bExecuteGrant(grantee=SESSION, is_grantable=False),)),
    )
    from oracle_brain.operating_model.q2b_target_catalog_v1 import (
        Q2bProcOwnerFact, Q2bSecurityDefinerFact, Q2bSearchPathFact,
        Q2bExecuteGrantsFact, Q2bRoleMembershipsFact, Q2bTargetIdentityFact,
    )
    caller_built = Q2bTargetCatalogReceipt(
        pg_proc_owner=Q2bProcOwnerFact(values=owners),
        security_definer=Q2bSecurityDefinerFact(values=definers),
        search_path=Q2bSearchPathFact(values=paths),
        execute_grants=Q2bExecuteGrantsFact(values=grants),
        role_memberships=Q2bRoleMembershipsFact(
            session_user=SESSION, current_user=SESSION,
            owner_reachable_member=False, owner_reachable_set=False,
            owner_reachable_usage=False, reachable_roles=(SESSION, GROUP)),
        target_identity=Q2bTargetIdentityFact(
            host=HOST, port=PORT, dbname=DBNAME, user=USER,
            ssl_in_use=True, sslmode='verify-full'),
    )
    assert caller_built.fact_mac == ''
    with pytest.raises(PermissionError, match='reader-produced sealed facts'):
        admit_target_catalog(caller_built, pins())
    # Even a caller-built receipt with a forged fact_mac is denied.
    forged_mac = caller_built.model_copy(update={'fact_mac': '0' * 64})
    with pytest.raises(PermissionError, match='MAC mismatch'):
        admit_target_catalog(forged_mac, pins())
    # Allowed: reader-produced sealed facts with matching pins.
    admitted = admit_target_catalog(read_target_catalog(good_connection(), pins()), pins())
    assert admitted.admitted is True


def test_require_redoes_pin_checks_on_sealed_receipt():
    """A sealed receipt with a changed pin expectation is still denied."""
    receipt = admit_target_catalog(read_target_catalog(good_connection(), pins()), pins())
    with pytest.raises(PermissionError, match='target identity differs'):
        require_target_catalog(receipt, pins(expected_host='other.example.test'))


# --- damage cases are denied -----------------------------------------------

def test_damage_wrong_owner_denied():
    receipt = read_target_catalog(good_connection(function_rows=function_rows(damage='owner')), pins())
    with pytest.raises(PermissionError, match='pg_proc owner differs'):
        admit_target_catalog(receipt, pins())


def test_damage_missing_security_definer_denied():
    receipt = read_target_catalog(good_connection(function_rows=function_rows(damage='invoker')), pins())
    with pytest.raises(PermissionError, match='SECURITY DEFINER'):
        admit_target_catalog(receipt, pins())


def test_damage_wrong_search_path_denied():
    receipt = read_target_catalog(good_connection(function_rows=function_rows(damage='search-path')), pins())
    with pytest.raises(PermissionError, match='search_path differs'):
        admit_target_catalog(receipt, pins())


def test_damage_public_execute_grantable_denied():
    receipt = read_target_catalog(good_connection(function_rows=function_rows(damage='public')), pins())
    with pytest.raises(PermissionError, match='EXECUTE grants differ'):
        admit_target_catalog(receipt, pins())


def test_damage_grantable_execute_denied():
    receipt = read_target_catalog(good_connection(function_rows=function_rows(damage='grantable')), pins())
    with pytest.raises(PermissionError, match='EXECUTE grants differ'):
        admit_target_catalog(receipt, pins())


def test_damage_owner_reachable_via_membership_denied():
    for flag in ('member', 'set', 'usage'):
        role_row = (
            SESSION, SESSION,
            {'rolname': OWNER, 'member': False, 'set': False, 'usage': False},
            [SESSION, GROUP],
        )
        role_row = (
            role_row[0], role_row[1],
            {'rolname': OWNER, 'member': flag == 'member', 'set': flag == 'set', 'usage': flag == 'usage'},
            role_row[3],
        )
        receipt = read_target_catalog(good_connection(role_row=role_row), pins())
        with pytest.raises(PermissionError, match='owner reachable via membership'):
            admit_target_catalog(receipt, pins())


def test_damage_owner_in_reachable_roles_denied():
    role_row = (
        SESSION, SESSION,
        {'rolname': OWNER, 'member': False, 'set': False, 'usage': False},
        [SESSION, GROUP, OWNER],
    )
    receipt = read_target_catalog(good_connection(role_row=role_row), pins())
    with pytest.raises(PermissionError, match='owner reachable via membership'):
        admit_target_catalog(receipt, pins())


def test_damage_unexpected_reachable_role_denied():
    role_row = (
        SESSION, SESSION,
        {'rolname': OWNER, 'member': False, 'set': False, 'usage': False},
        [SESSION, GROUP, 'invented_extra_role'],
    )
    receipt = read_target_catalog(good_connection(role_row=role_row), pins())
    with pytest.raises(PermissionError, match='unexpected reachable role'):
        admit_target_catalog(receipt, pins())


def test_damage_tls_not_in_use_denied():
    plain = good_connection(
        ssl_in_use=False,
        params={'host': HOST, 'port': str(PORT), 'dbname': DBNAME, 'user': USER, 'sslmode': 'prefer'},
    )
    receipt = read_target_catalog(plain, pins())
    with pytest.raises(PermissionError, match='TLS not in use'):
        admit_target_catalog(receipt, pins())


def test_damage_sslmode_not_verify_full_denied():
    relaxed = good_connection(
        params={'host': HOST, 'port': str(PORT), 'dbname': DBNAME, 'user': USER, 'sslmode': 'require'},
    )
    receipt = read_target_catalog(relaxed, pins())
    with pytest.raises(PermissionError, match='TLS not in use'):
        admit_target_catalog(receipt, pins())


def test_damage_target_identity_mismatch_denied():
    receipt = read_target_catalog(good_connection(), pins(expected_host='other.example.test'))
    with pytest.raises(PermissionError, match='target identity differs'):
        admit_target_catalog(receipt, pins(expected_host='other.example.test'))


def test_damage_session_role_differs_denied():
    receipt = read_target_catalog(good_connection(), pins())
    broken = _reseal(receipt.model_copy(update={
        'role_memberships': receipt.role_memberships.model_copy(update={'session_user': 'other_role'}),
    }))
    with pytest.raises(PermissionError, match='session role differs'):
        admit_target_catalog(broken, pins())


def test_damage_owner_assumed_via_set_role_denied():
    receipt = read_target_catalog(good_connection(), pins())
    broken = _reseal(receipt.model_copy(update={
        'role_memberships': receipt.role_memberships.model_copy(update={'current_user': OWNER}),
    }))
    with pytest.raises(PermissionError, match='SET ROLE'):
        admit_target_catalog(broken, pins())


def test_unknown_blocks_target_execution():
    connection = good_connection(function_rows=function_rows(damage='missing'))
    receipt = read_target_catalog(connection, pins())
    assert 'pg_proc_owner' in receipt.unknown_classes()
    with pytest.raises(PermissionError, match='UNKNOWN blocks target execution'):
        admit_target_catalog(receipt, pins())


# --- missing pins fail-closed ----------------------------------------------

@pytest.mark.parametrize('field,value', [
    ('expected_owner_role', ''),
    ('expected_owner_role', None),
    ('expected_session_role', ''),
    ('function_signatures', ()),
    ('function_signatures', None),
    ('expected_execute_grants', ()),
    ('expected_execute_grants', None),
    ('role_scope', ()),
    ('role_scope', (SESSION, GROUP)),
    ('expected_host', ''),
    ('expected_port', 0),
    ('expected_port', '5432'),
    ('expected_dbname', ''),
    ('expected_user', ''),
    ('expected_sslmode', 'require'),
    ('expected_sslmode', None),
])
def test_missing_pins_fail_closed(field, value):
    with pytest.raises(PermissionError, match='complete Q2b expected descriptor/role scope required'):
        pins(**{field: value})


def test_incomplete_grant_coverage_fails_closed():
    with pytest.raises(PermissionError, match='complete Q2b expected descriptor/role scope required'):
        pins(expected_execute_grants=((SIGNATURES[0], (GROUP,)),))


def test_unlisted_signature_grants_fail_closed():
    with pytest.raises(PermissionError, match='complete Q2b expected descriptor/role scope required'):
        pins(expected_execute_grants=(
            (SIGNATURES[0], (GROUP,)),
            (SIGNATURES[1], ()),
            ('oracle2.invented_extra()', ()),
        ))


def test_reader_refuses_incomplete_descriptor_before_any_sql():
    log = []
    connection = good_connection(log=log)
    for bad in (None, 'not-pins', object()):
        with pytest.raises(PermissionError, match='complete Q2b expected descriptor/role scope required'):
            read_target_catalog(connection, bad)
    assert log == []


def test_reader_refuses_connection_without_execute():
    with pytest.raises(PermissionError, match='execute required'):
        read_target_catalog(SimpleNamespace(info=None, pgconn=None), pins())


# --- reader SQL text contains no source-data SELECTs ------------------------

def test_reader_sql_text_contains_no_source_data_selects():
    assert q2b.READER_SQL_STATEMENTS == (
        q2b.FUNCTION_CATALOG_SQL, q2b.ROLE_REACHABILITY_SQL, q2b.TARGET_IDENTITY_SQL,
    )
    for statement in q2b.READER_SQL_STATEMENTS:
        require_metadata_only_sql(statement)
        lowered = statement.lower()
        assert 'select' in lowered
        for forbidden in (
            'oracle2.', 'pg_authid', 'pg_shadow', 'source_block', 'pg_read_file',
            'current_setting', 'insert ', 'update ', 'delete ', 'grant ', 'copy ',
        ):
            assert forbidden not in lowered
        assert 'pg_proc' in lowered or 'pg_roles' in lowered or 'current_database' in lowered


@pytest.mark.parametrize('statement', [
    'SELECT * FROM oracle2.source_blocks',
    'SELECT * FROM oracle2.sources',
    'SELECT pg_read_file(%s)',
    "SELECT current_setting('password')",
    'SELECT * FROM pg_authid',
    'INSERT INTO pg_proc VALUES (1)',
    'UPDATE pg_proc SET prosecdef = true',
    'DELETE FROM pg_proc',
    'GRANT EXECUTE ON FUNCTION oracle2.x() TO PUBLIC',
    'COPY pg_proc TO PROGRAM %s',
    'SELECT * FROM secrets_store',
    'SELECT * FROM pg_shadow',
])
def test_non_metadata_sql_is_refused(statement):
    with pytest.raises(PermissionError):
        require_metadata_only_sql(statement)


def test_reader_executes_only_the_three_catalog_statements():
    log = []
    read_target_catalog(good_connection(log=log), pins())
    assert len(log) == 3
    assert log[0] == q2b.FUNCTION_CATALOG_SQL
    assert log[1] == q2b.ROLE_REACHABILITY_SQL
    assert log[2] == q2b.TARGET_IDENTITY_SQL
    for statement in log:
        require_metadata_only_sql(statement)


def test_build_receipt_never_sets_admitted_without_separate_admission():
    owners, definers, paths, grants = parse_function_catalog(function_rows())
    receipt = build_receipt(
        pg_proc_owner=owners,
        security_definer=definers,
        search_path=paths,
        execute_grants=grants,
        role_memberships=parse_role_memberships(None),
        target_identity=parse_target_identity(None, params={}, ssl_in_use=None),
    )
    assert receipt.admitted is False
    assert isinstance(receipt, Q2bTargetCatalogReceipt)
