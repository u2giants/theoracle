"""SQL source/parsing controls only. No migration or database execution proof."""
from pathlib import Path
import re
from oracle_brain.operating_model.recovery_contracts_v1 import OPERATIONAL_TABLES_V1,CURRENT_POLICY_TABLES_V1
from oracle_brain.operating_model.recovery_authority_v1 import PUBLIC_RECOVERY_SIGNATURES_V1,PRIVATE_RECOVERY_SIGNATURES_V1
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'services/oracle-brain/sql/026_operational_recovery.sql'

def test_only_fixed_new_recovery_functions_are_authored():
 source=SOURCE.read_text()
 names=re.findall(r'^CREATE FUNCTION (oracle2\.[a-z0-9_]+)\(',source,re.M)
 assert sorted(names)==sorted(signature.split('(')[0] for signature in PUBLIC_RECOVERY_SIGNATURES_V1+PRIVATE_RECOVERY_SIGNATURES_V1)
 assert source.count('END $f$;')==8


def test_new_schema_has_no_role_creation_runtime_grant_or_old_function_replacement():
 source=SOURCE.read_text()
 assert not re.search(r'^\s*(CREATE ROLE|GRANT |CREATE OR REPLACE FUNCTION)',source,re.M)
 assert 'PASSWORD ' not in source


def test_all_mandatory_owners_are_explicit_before_census_not_optional_discovery():
 source=SOURCE.read_text()
 lock=re.search(r' LOCK TABLE (.*?) IN SHARE MODE;',source).group(1)
 assert set(lock.split(','))=={'oracle2.'+t for t in CURRENT_POLICY_TABLES_V1}
 assert len(OPERATIONAL_TABLES_V1)==56
 for table in CURRENT_POLICY_TABLES_V1:
  assert "WHEN '"+table+"' THEN query:=" in source
 assert "unknown current policy table refused" in source
 assert "'complete',true" in source and 'LIMIT 100001' in source


def test_effect_and_observation_owners_are_fixed_and_append_only():
 source=SOURCE.read_text()
 assert len(PUBLIC_RECOVERY_SIGNATURES_V1)==4 and len(PRIVATE_RECOVERY_SIGNATURES_V1)==4
 for signature in PUBLIC_RECOVERY_SIGNATURES_V1+PRIVATE_RECOVERY_SIGNATURES_V1:assert signature in source
 assert 'PRIMARY KEY(operation_id,phase)' in source
 assert 'PRIMARY KEY(resource_kind,resource_sha256)' in source
 assert 'BEFORE UPDATE OR DELETE' in source
 assert "'fresh',false" in source
 assert "preclaim refusal cannot fabricate an effect or deadline" in source
 assert 'rolpassword IS NOT NULL' in source and 'restored application LOGIN/password forbidden' in source


def test_future_migration_custody_cannot_be_silently_omitted_by_new_catalog_pin():
 source=SOURCE.read_text()
 guard=source[source.index(" IF (SELECT array_agg(c.relname::text"):source.index(" IF cap.key LIKE")]
 assert "c.relname LIKE 'migration_%'" in guard
 assert "IS DISTINCT FROM ARRAY[" in guard and "RAISE insufficient_privilege" in guard
 assert 'migration_admissions_v1' in OPERATIONAL_TABLES_V1 # exact frozen027 source only, never lifecycle acceptance
 assert 'migration_unknown_future_v1' not in OPERATIONAL_TABLES_V1
 assert 'complete exact current027 operational tail and owner source pins required' in source


def test_frozen_processing_successor_complete_rows_and_exact_parent_custody_are_mandatory():
 import hashlib
 source=SOURCE.read_text()
 new={'meeting_capture_final_fetch_claims_v1','meeting_capture_processing_links_v1','meeting_capture_enqueue_claims_v1','meeting_capture_enqueue_receipts_v1'}
 assert new<=set(OPERATIONAL_TABLES_V1) and len(OPERATIONAL_TABLES_V1)==56
 frozen=(ROOT/'services/oracle-brain/sql/020_meeting_capture.sql').read_bytes()
 assert hashlib.sha256(frozen).hexdigest()=='79c6d0c28c91c337d88ab3680de7c83deb79700d4cd69441107479fc5a23ed7e'
 for table in new:assert "WHEN '"+table+"' THEN query:=" in source
 assert 'LEFT JOIN oracle2.meeting_capture_final_fetch_claims_v1 q ON q.fetch_claim_id=l.fetch_claim_id' in source
 assert 'final.payload_sha256 IS DISTINCT FROM' in source and 'q.population_sha256 IS DISTINCT FROM' in source
 assert "'possible-effect-unreconciled','effective_at',NULL::timestamptz" in source
 assert "r.observation->>'kind'='enqueue-observed'" in source
 assert 'missing foreign or malformed complete meeting processing custody' in source


def test_postgres_repeat_limit_preserves_exact_256_character_queue_identifier():
 source=SOURCE.read_text()
 assert "r.observation->>'run_id'!~'^[A-Za-z0-9_-]+$' OR char_length(r.observation->>'run_id') NOT BETWEEN 1 AND 256" in source
 assert not any(int(end)>255 for _,end in re.findall(r'\{([0-9]+),([0-9]+)\}',source))
 pattern=r'^[A-Za-z0-9_-]+$'
 for value in ['a','a'*255,'a'*256,'run_id-2']:
  assert re.fullmatch(pattern,value) and 1<=len(value)<=256
 for value in ['', 'a'*257,'space not allowed','界','a\n']:
  assert not(re.fullmatch(pattern,value) and 1<=len(value)<=256)


def test_direct_sql_uses_same_complete_catalog_expression_without_new_digest_owner():
 from oracle_brain.operating_model.recovery_authority_v1 import _CATALOG_SQL_V1
 source=SOURCE.read_text()
 embedded=source.split('-- BEGIN SAME_RECOVERY_CATALOG_SQL_V1\n',1)[1].split('-- END SAME_RECOVERY_CATALOG_SQL_V1',1)[0]
 actual=embedded.split('oracle2._replacement_metadata_json((\n',1)[1].split('\n )),',1)[0]
 assert actual==_CATALOG_SQL_V1
 assert "actual_catalog_sha256 IS DISTINCT FROM b->>'schema_catalog_sha256'" in source
 context=source.split('CREATE FUNCTION oracle2._recovery_context_v1',1)[1]
 assert context.index('exact independent retained canonicalizer body required')<context.index('d:=oracle2._recovery_json_v1')


def test_independent_canonicalizer_pin_is_exact_retained_source_body():
 import hashlib
 from pglast import parse_sql
 source=(ROOT/'services/oracle-brain/sql/014_replacement_source_custody.sql').read_text()
 body=None
 for raw in parse_sql(source):
  n=raw.stmt
  if type(n).__name__=='CreateFunctionStmt' and n.funcname[-1].sval=='_replacement_metadata_json':
   body=next(o.arg[0].sval for o in n.options if o.defname=='as')
 assert body is not None
 assert "canonical.prosrc,'UTF8')),'hex')='"+hashlib.sha256(body.encode()).hexdigest()+"'" in SOURCE.read_text()



def test_all_three_lineage_reads_require_actual_grantor_and_exact_scope():
 source=SOURCE.read_text()
 assert "parent.actor_id=appointment_row.granted_by AND parent.workspace_id=(scope->>'workspace_id')::uuid AND parent.scope IN(scope->>'scope','root')" in source
 assert "p.actor_id=l.granted_by AND p.scope IN(l.leaf_scope,'root')" in source
 assert "p.actor_id=x.granted_by AND p.workspace_id=x.workspace_id AND p.scope IN(x.leaf_scope,'root')" in source
 assert "appointment_row.appointment_id=(scope->>'root_appointment_id')::uuid" in source


def test_embedded_catalog_aliases_do_not_shadow_plpgsql_records():
 source=SOURCE.read_text()
 bodies=re.findall(r'CREATE FUNCTION ([^(]+).*? AS \$f\$(.*?)END \$f\$;',source,re.S)
 callsites=[]
 for name,body in bodies:
  if '-- BEGIN SAME_RECOVERY_CATALOG_SQL_V1' not in body:continue
  callsites.append(name)
  declaration=body.split('DECLARE',1)[1].split('BEGIN',1)[0]
  declared=set(re.findall(r'(?:^|;)\s*([a-z_][a-z0-9_]*)\s+',declaration))
  catalog=body.split('-- BEGIN SAME_RECOVERY_CATALOG_SQL_V1',1)[1].split('-- END SAME_RECOVERY_CATALOG_SQL_V1',1)[0]
  aliases=set(re.findall(r'\b(?:FROM|JOIN)\s+[a-z_][a-z0-9_]*\s+([a-z_][a-z0-9_]*)',catalog))
  assert {'a','p'}<=aliases
  assert not declared&aliases,(name,declared&aliases)
  assert 'admission_row' in declared and 'appointment_row' in declared
 assert callsites==['oracle2._recovery_context_v1']


def _normalize_context_record_identifiers(text):
 # Scanner token ranges exclude SQL literals, quoted identifiers and comments.
 from pglast import scan
 assert text.isascii()
 result=text
 for token in reversed(scan(text)):
  word=text[token.start:token.end+1]
  if token.name=='IDENT' and word in {'admission_row','appointment_row'}:
   result=result[:token.start]+{'admission_row':'a','appointment_row':'p'}[word]+result[token.end+1:]
 return result


def test_record_rename_preserves_every_original_nonidentifier_byte():
 import hashlib
 source=SOURCE.read_text()
 context=source.split('CREATE FUNCTION oracle2._recovery_context_v1',1)[1].split('END $f$;',1)[0]+'END $f$;'
 prefix='CREATE FUNCTION oracle2._recovery_context_v1'
 whole=prefix+context
 start=whole.index('AS $f$')+len('AS $f$');end=whole.rindex('END $f$;')+len('END')
 normalized=whole[:start]+_normalize_context_record_identifiers(whole[start:end])+whole[end:]
 assert hashlib.sha256(normalized.encode()).hexdigest()=='cf672ad1108312d028122d706db2575c2d53c6f0ada547043ffc6c4e2139c7cb'
 assert "c.relkind IN('r','p')" in whole
 assert '-- static union, even if someone supplies a new aggregate catalog pin.' in whole


def test_identifier_normalization_never_rewrites_literals_or_comments():
 sample="DECLARE admission_row record; appointment_row record; BEGIN -- p a appointment_row admission_row\n /* a p admission_row appointment_row */ IF c.relkind IN('p','a','appointment_row','admission_row') THEN appointment_row.id:=admission_row.id; END IF; END"
 expected="DECLARE a record; p record; BEGIN -- p a appointment_row admission_row\n /* a p admission_row appointment_row */ IF c.relkind IN('p','a','appointment_row','admission_row') THEN p.id:=a.id; END IF; END"
 assert _normalize_context_record_identifiers(sample)==expected


def test_no_removed_record_identifier_remains_in_executable_context():
 from pglast import scan
 source=SOURCE.read_text()
 whole=source.split('CREATE FUNCTION oracle2._recovery_context_v1',1)[1].split('END $f$;',1)[0]
 body=whole.split('AS $f$',1)[1]
 before,rest=body.split('-- BEGIN SAME_RECOVERY_CATALOG_SQL_V1',1)
 _,after=rest.split('-- END SAME_RECOVERY_CATALOG_SQL_V1',1)
 executable=before+'\n'+after
 tokens=scan(executable)
 assert not any(t.name=='IDENT' and executable[t.start:t.end+1]=='a' for t in tokens)
 p_lines=set()
 for token in tokens:
  if token.name=='IDENT' and executable[token.start:token.end+1]=='p':
   line=executable[:token.start].split('\n')[-1]+executable[token.start:].split('\n')[0]
   p_lines.add(line)
 assert len(p_lines)==2
 for line in p_lines:
  assert 'FROM jsonb_array_elements(admission_row.scope_coverage) s JOIN oracle2.appointments p ON p.appointment_id=' in line
  assert 'p.actor_id=admission_row.principal_id AND p.scope=' in line
 assert sum("p.scope=phase_scope" in line for line in p_lines)==1
 assert sum("IF admission_row.phase_authority='capture'" in line and "p.scope='recovery-deny-census:'||wanted::text" in line for line in p_lines)==1
