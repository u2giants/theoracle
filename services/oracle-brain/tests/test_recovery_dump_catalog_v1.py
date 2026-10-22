"""Pure complete fixed metadata comparison only, never installed native authority."""
from copy import deepcopy
import pytest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.recovery_authority_v1 import validate_recovery_dump_catalog_v1
H='a'*64


def catalog():
 column=dict(ordinal=1,name='event_id',type_schema='pg_catalog',type_name='uuid',type_modifier=-1,collation=0,not_null=True,dimensions=0,storage='p',compression='',statistics_target=-1,identity='',generated='',acl=None,default_sha256=H)
 relation=dict(schema='oracle2',name='events',oid=17000,kind='r',owner=16000,acl=None,row_security=True,force_row_security=True,persistence='p',access_method=2,tablespace=0,is_partition=False,replica_identity='d',options=None,partition_bound_sha256=H,columns=[column],constraints=[dict(oid=17001,name='events_pkey',validated=True,definition_sha256=H)],triggers=[dict(oid=17002,name='immutable_events',enabled='O',internal=False,definition_sha256=H)],policies=[dict(oid=17003,name='current_owner',command='r',permissive=True,roles=[16000],using_sha256=H,check_sha256=H)],index_sha256=None,view_sha256=None,sequence=None)
 function=dict(schema='oracle2',name='fixed_current',oid=17004,owner=16000,kind='f',language=123,arguments='2950 1184',all_arguments=None,argument_modes=None,result=3802,set_result=False,security_definer=True,config_sha256=H,volatility='v',strict=False,parallel='u',acl='{owner=X/owner}',definition_sha256=H,body_sha256=H,binary_sha256=H,argument_defaults_sha256=H)
 return dict(schema_version=1,protocol='oracle-replacement-native-ddl-inventory-v1',schemas=[dict(name='oracle2',owner=16000,acl=None),dict(name='public',owner=6171,acl=None)],foreign_objects_present=False,unsupported_objects_present=False,relations=[relation],functions=[function],types=[],extensions=[],collations=[])


def test_full_native_metadata_pin_includes_owners_security_full_schema_and_ddl_without_authority():
 c=catalog()
 assert validate_recovery_dump_catalog_v1(c,digest(c))==('oracle2.events',)

@pytest.mark.parametrize('where,field,value',[('relation','owner',16001),('relation','acl','{PUBLIC=arwdDxt/owner}'),('relation','row_security',False),('relation','force_row_security',False),('relation','partition_bound_sha256','b'*64),('column','type_modifier',12),('column','collation',100),('column','identity','a'),('column','generated','s'),('column','default_sha256','b'*64),('function','body_sha256','b'*64),('function','definition_sha256','b'*64),('function','security_definer',False),('function','config_sha256','b'*64),('function','acl','{PUBLIC=X/owner}'),('constraint','definition_sha256','b'*64),('trigger','definition_sha256','b'*64),('policy','using_sha256','b'*64)])
def test_exact_actual_ddl_drift_cannot_be_blessed_by_table_names(where,field,value):
 c=catalog();pin=digest(c);changed=deepcopy(c)
 target={'relation':changed['relations'][0],'column':changed['relations'][0]['columns'][0],'function':changed['functions'][0],'constraint':changed['relations'][0]['constraints'][0],'trigger':changed['relations'][0]['triggers'][0],'policy':changed['relations'][0]['policies'][0]}[where]
 target[field]=value
 with pytest.raises(PermissionError):validate_recovery_dump_catalog_v1(changed,pin)

@pytest.mark.parametrize('mutation',[lambda c:c.update(foreign_objects_present=True),lambda c:c.update(unsupported_objects_present=True),lambda c:c.update(schema_version=True),lambda c:c['schemas'].append(dict(name='auth',owner=16000,acl=None)),lambda c:c['relations'][0].update(kind='f'),lambda c:c['relations'][0]['columns'][0].update(name='password_hash'),lambda c:c['relations'][0]['columns'][0].update(type_schema='foreign'),lambda c:c['relations'][0].pop('policies'),lambda c:c['functions'][0].pop('definition_sha256'),lambda c:c['relations'][0].update(row_security=1),lambda c:c['relations'][0]['columns'][0].update(not_null=1),lambda c:c['functions'][0].update(security_definer=1),lambda c:c['relations'][0].update(unknown='field')])
def test_unknown_credential_or_incomplete_metadata_quarantines_even_if_dto_hash_matches(mutation):
 c=catalog();mutation(c)
 with pytest.raises(PermissionError):validate_recovery_dump_catalog_v1(c,digest(c))


def test_unpinned_catalog_and_opaque_checkpoint_rows_are_never_certified():
 c=catalog()
 with pytest.raises(PermissionError):validate_recovery_dump_catalog_v1(c,None)
 # This metadata comparator has no payload input/credential-safe claim. A known
 # blob column cannot establish that serialized checkpoint values are safe.
 c['relations'][0]['columns'][0]['name']='blob';pin=digest(c)
 assert validate_recovery_dump_catalog_v1(c,pin)==('oracle2.events',)
 # Actual dump owner must separately prove empty or source-closed checkpoint state.


@pytest.mark.parametrize('name',['verifier_secret_sha256','queue_credential_sha256'])
def test_only_exact_source020_noncredential_fingerprints_preserve_mandatory_bindings(name):
 c=catalog();r=c['relations'][0];r['name']='meeting_capture_admissions_v1';column=r['columns'][0];column.update(name=name,type_name='text')
 assert validate_recovery_dump_catalog_v1(c,digest(c))==('oracle2.meeting_capture_admissions_v1',)
 for wrong in ('events','other_admissions_v1'):
  changed=deepcopy(c);changed['relations'][0]['name']=wrong
  with pytest.raises(PermissionError):validate_recovery_dump_catalog_v1(changed,digest(changed))
 for wrong in ('password_hash','secret_sha256','other_credential_sha256','queue_credential_sha512'):
  changed=deepcopy(c);changed['relations'][0]['columns'][0]['name']=wrong
  with pytest.raises(PermissionError):validate_recovery_dump_catalog_v1(changed,digest(changed))
 changed=deepcopy(c);changed['relations'][0]['columns'][0]['type_name']='bytea'
 with pytest.raises(PermissionError):validate_recovery_dump_catalog_v1(changed,digest(changed))
