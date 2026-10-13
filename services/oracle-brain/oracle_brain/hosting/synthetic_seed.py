"""Compile fixed invented rows and narrow LOGIN statements, never generic SQL."""
from datetime import datetime,timedelta,timezone
import json,re
from uuid import UUID
from psycopg import sql
from oracle_brain.operating_model.contracts import canonical_bytes
from .synthetic_fixture import fixture,WORKSPACE,ACTOR,OWNER,ARTIFACT,RUN,SOURCES,fixed_scenario,LEGACY_SCENARIO,FORWARD_SCENARIO

PARAMETERS={'runtime_hash','source_role_registry_hash','review_hash','expires_at','gateway_scram','executor_scram','projector_scram'}

def statement(template,*values):
    return sql.SQL(template).format(*(sql.Literal(v) for v in values)).as_string()+';\n'

def validate_seed_parameters(parameters):
    extra={'synthetic_scenario','synthetic_scenario_seal'}
    if set(parameters) not in (PARAMETERS,PARAMETERS|extra):raise PermissionError('fixed synthetic parameters required')
    scenario=fixed_scenario(parameters.get('synthetic_scenario',LEGACY_SCENARIO))
    if extra <= set(parameters) and parameters['synthetic_scenario_seal']!=scenario.seal():raise PermissionError('fixed scenario seal differs')
    WORKSPACE,ACTOR,OWNER,ARTIFACT,RUN=(scenario.workspace,scenario.actor,scenario.owner,scenario.artifact,scenario.run)
    for name in ('runtime_hash','source_role_registry_hash','review_hash'):
        if not re.fullmatch('[0-9a-f]{64}',parameters[name]):raise PermissionError('reviewed synthetic pins required')
    expires=datetime.fromisoformat(parameters['expires_at'])
    if expires.tzinfo is None or not datetime.now(timezone.utc)<expires<=datetime.now(timezone.utc)+timedelta(hours=2):raise PermissionError('unexpired synthetic scope required')
    # Password verifiers, not plaintext. Credentials are issued outside this
    # materializer under the root's exact-action review.
    for name in ('gateway_scram','executor_scram','projector_scram'):
        if not re.fullmatch(r'SCRAM-SHA-256\$4096:[A-Za-z0-9+/]+={0,2}\$[A-Za-z0-9+/]+={0,2}:[A-Za-z0-9+/]+={0,2}',parameters[name]):raise PermissionError('fixed SCRAM verifier required')
    return scenario,expires

def _login_sql(parameters):
    output=''
    output+="CREATE ROLE oracle_synthetic_gateway LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD "+sql.Literal(parameters['gateway_scram']).as_string()+";\nGRANT oracle2_gateway_metadata TO oracle_synthetic_gateway;\nALTER ROLE oracle_synthetic_gateway SET role='oracle2_gateway_metadata';\n"
    for role in ('executor','projector'):
        login='oracle_synthetic_'+role
        output+="CREATE ROLE "+login+" LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD "+sql.Literal(parameters[role+'_scram']).as_string()+";\nGRANT oracle2_documentary_executor TO "+login+";\nALTER ROLE "+login+" SET role='oracle2_documentary_executor';\n"
    return output

def compile_restore_roles(parameters):
    scenario,_=validate_seed_parameters(parameters)
    if scenario.scenario_id!=FORWARD_SCENARIO:raise PermissionError('only distinct forward roles can be restored')
    output='BEGIN;\n'
    for group in ('oracle2_gateway_metadata','oracle2_source_reader','oracle2_candidate_compiler','oracle2_documentary_executor'):
        output+='CREATE ROLE '+group+' NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;\n'
    return output+_login_sql(parameters)+'COMMIT;\n'

def compile_seed(parameters):
    scenario,expires=validate_seed_parameters(parameters)
    WORKSPACE,ACTOR,OWNER,ARTIFACT,RUN=(scenario.workspace,scenario.actor,scenario.owner,scenario.artifact,scenario.run)
    receipts,metadata,payload,manifest,release=fixture(parameters['runtime_hash'],parameters['review_hash'],scenario.scenario_id)
    output='-- FIXED PUBLIC INVENTED ROWS ONLY. New empty dedicated ledger only.\n'+_login_sql(parameters)
    output+=statement("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES({}, {}, {},'root',{})",scenario.root_appointment,WORKSPACE,OWNER,scenario.grantor)
    for index,(receipt,meta) in enumerate(zip(receipts,metadata)):
        source=receipt.ref.source_id;ref=receipt.ref
        output+=statement("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES({}, {}, {},'public-invented.txt','text/plain','draft')",source,WORKSPACE,ACTOR)
        output+=statement("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES({}, {}, {}, {},'public-invented','confirmed')",scenario.draft_ids[index],source,WORKSPACE,ACTOR)
        output+=statement("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES({}, {}, {}, {}, {}, {}, {})",scenario.appointment_ids[index],WORKSPACE,ACTOR,'source-read:'+str(source),OWNER,scenario.root_appointment,expires)
        for block_index,(kind,text) in enumerate([('original',receipt.reading),('original-metadata',canonical_bytes(meta).decode())]):
            output+=statement("INSERT INTO oracle2.source_blocks VALUES({}, {}, {}, {}, {}, {},0,{})",scenario.block_ids[index*2+block_index],source,WORKSPACE,block_index,kind,text,len(text))
        output+=statement("INSERT INTO oracle2.operating_model_source_receipts VALUES({}, {},1, {}, {}, {}, {}::jsonb)",WORKSPACE,source,ref.original_sha256,ref.reading_sha256,ref.parser_id,canonical_bytes(receipt.model_dump(mode='json')).decode())
        for role in ('executor','projector'):
            output+=statement("INSERT INTO oracle2.hosting_role_source_admissions VALUES({}, {}, {},1, {}, {}, {}, {}, {}, {}, {})",'oracle_synthetic_'+role,WORKSPACE,source,ACTOR,ref.original_sha256,ref.reading_sha256,ref.parser_id,parameters['runtime_hash'],parameters['source_role_registry_hash'],expires)
    for role in ('executor','projector'):
        output+=statement("INSERT INTO oracle2.hosting_role_runtime_admissions VALUES({}, {}, {}, {})",'oracle_synthetic_'+role,parameters['runtime_hash'],parameters['source_role_registry_hash'],expires)
    m=manifest
    output+=statement("INSERT INTO oracle2.artifact_manifests(workspace_id,artifact_id,version,kind,input_digest,source_digest,permission_digest,compiler_digest,dependency_digest,content_hash,private_object_key,state,manifest) VALUES({}, {},1, {}, {}, {}, {}, {}, {}, {}, {},'ready', {}::jsonb)",WORKSPACE,ARTIFACT,m.kind,m.input_digest,m.source_digest,m.permission_digest,m.compiler_digest,m.dependency_digest,m.content_hash,m.private_object_key,canonical_bytes(m.model_dump(mode='json')).decode())
    for receipt in receipts:output+=statement("INSERT INTO oracle2.artifact_dependencies VALUES({}, {},1,'source', {},'1')",WORKSPACE,ARTIFACT,str(receipt.ref.source_id))
    output+="DO $$ BEGIN IF (SELECT max(sequence) FROM oracle2.operating_model_change_log)<>11 THEN RAISE EXCEPTION 'synthetic fixture watermark differs'; END IF; END $$;\n"
    output+=statement("INSERT INTO oracle2.operating_release_manifests(workspace_id,release_id,content_hash,payload) VALUES({}, {}, {}, {}::jsonb)",WORKSPACE,release.release_id,release.content_hash(),canonical_bytes(release.model_dump(mode='json')).decode())
    output+=statement("INSERT INTO oracle2.operating_release_selectors VALUES({}, {},1,11)",WORKSPACE,release.release_id)
    output+=statement("INSERT INTO oracle2.operating_view_runs(run_id,workspace_id,actor_id,query_plan,release_id,release_hash,status,source_refs,expires_at) VALUES({}, {}, {}, {}::jsonb, {}, {},'pending', {}::jsonb, {})",RUN,WORKSPACE,ACTOR,canonical_bytes({'view':'company_overview','question':'invented blue card' if scenario.scenario_id==LEGACY_SCENARIO else 'invented amber parcel','max_bytes':16384,'page':0,'page_size':25}).decode(),release.release_id,release.content_hash(),canonical_bytes([r.ref.model_dump(mode='json') for r in receipts]).decode(),expires)
    if scenario.scenario_id==LEGACY_SCENARIO:
        output+="CREATE TABLE oracle2.synthetic_hosting_marker(marker text PRIMARY KEY CHECK(marker='public-invented-remote-v1'));\nINSERT INTO oracle2.synthetic_hosting_marker VALUES('public-invented-remote-v1');\nREVOKE ALL ON oracle2.synthetic_hosting_marker FROM PUBLIC;\n"
        return output,manifest,payload,release
    output+=statement('CREATE TABLE oracle2.synthetic_hosting_marker(marker text PRIMARY KEY CHECK(marker={}))',scenario.seed_marker)
    output+=statement('INSERT INTO oracle2.synthetic_hosting_marker VALUES({})',scenario.seed_marker)
    output+="REVOKE ALL ON oracle2.synthetic_hosting_marker FROM PUBLIC;\n"
    return output,manifest,payload,release
