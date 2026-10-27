"""Pure regression for actual fixture constructor, not installed authority."""
import pytest
from test_recovery_authority_sql_v1 import capture_bindings
from test_recovery_contracts_v1 import descriptor,change,uid


def test_actual_fixture_constructor_keeps_required_separate_observe_binding():
 d=descriptor();capture,observe=d.purpose_bindings
 bindings=capture_bindings(capture.sql_identity,observe.sql_identity,capture.principal_id,observe.principal_id)
 actual=change(d,purpose_bindings=bindings)
 assert tuple(v.phase_authority for v in actual.purpose_bindings)==('capture','observe')
 assert len({v.sql_identity.session_role for v in actual.purpose_bindings})==2
 assert all(v.sql_identity.physical()==d.current_control_source.physical() for v in bindings)


def test_fixture_cannot_omit_observer_or_fake_two_roles_with_one_identity():
 d=descriptor();capture,observe=d.purpose_bindings
 for bindings in ((capture,),capture_bindings(capture.sql_identity,capture.sql_identity,capture.principal_id,observe.principal_id)):
  with pytest.raises(ValueError):change(d,purpose_bindings=bindings)


def test_lineage_diagnostics_name_exact_context_raise_before_wrong_purpose():
 from test_recovery_authority_sql_v1 import ROOT
 source=(ROOT/'services/oracle-brain/sql/026_operational_recovery.sql').read_text()
 body=source.split('CREATE FUNCTION oracle2._recovery_context_v1',1)[1].split('AS $f$',1)[1].split('END $f$;',1)[0]
 for marker in ("IF NOT rooted THEN RAISE insufficient_privilege;END IF;","IF appointment_row.appointment_id IS NULL THEN RAISE insufficient_privilege;END IF;","RAISE insufficient_privilege USING MESSAGE='actual current rooted recovery coverage required';END IF;"):
  assert body.count(marker)==1
  assert body[:body.index(marker)].count('\n')+1>0
