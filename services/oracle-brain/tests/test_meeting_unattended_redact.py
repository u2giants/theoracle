"""Offline unit tests for the §5 allow-list (meeting_unattended_redact).

These prove the M1 class of bug is gone: the packet's fixed hyphenated
tokens survive redact_record, while paths/hosts/secrets still redact.
No Docker, no SQL, no network.
"""
from meeting_unattended_redact import redact_record,_value_allowed

def test_pre_child_step_names_survive():
    for name in ('install-wraps','queue-diagnostic','cycle-diagnostic',
                 'warmup-queue-reads','refused-prepare-warmup','sql-zero-asserts',
                 'child-spawn-ready','warmup-observations','child-wait','stdout-redact',
                 'collect-diagnostics','returncode-assert','outcome-parse','repeated-claim',
                 'post-create-current-queue','terminal-loop','terminal-asserts','unattended-outcome',
                 'start_unattended'):
        out=redact_record(dict(step=name))
        assert out['step']==name,(name,out)

def test_teardown_step_names_survive():
    for name in ('supervision-scope','replay-spool-copy','selected-state','provider-routes',
                 'observer-files','stack-close','jsonl-close-then-copy','owned-process-cleanup',
                 'private-cleanup'):
        out=redact_record(dict(step=name,ok=True))
        assert out['step']==name,(name,out)
        assert out.get('step_kind') is None

def test_claim_stages_and_placeholder_survive():
    for stage in ('-','pre-stop-consistency','post-stop-terminal'):
        out=redact_record(dict(stage=stage))
        assert out['stage']==stage,(stage,out)

def test_observation_kinds_survive():
    for kind in ('create-observed','leave-observed','metadata-observed'):
        out=redact_record(dict(kind=kind,complete=True))
        assert out['kind']==kind,(kind,out)

def test_header_keywords_and_values_survive():
    headers=[['Content-Length','0'],['Cache-Control','no-store'],['Connection','close'],
             ['Content-Type','application/json'],['Content-Length','1234'],
             ['Server','BaseHTTP/0.6 Python/3.12.3'],
             ['Date','Sat, 25 Oct 2026 14:09:52 GMT']]
    out=redact_record(dict(headers=headers))
    assert out['headers']==headers,out
    assert 'headers_kind' not in out

def test_effect_and_wrap_names_survive():
    out=redact_record(dict(effect='capture-create',wrap='execute_v1',outcome='refused'))
    assert out['effect']=='capture-create' and out['wrap']=='execute_v1' and out['outcome']=='refused'

def test_paths_and_hosts_redact():
    out=redact_record(dict(path='/tmp/pytest-xyz/file',host='localhost',other='C:\\Users\\x'))
    assert out['path']=='REDACTED' and out['path_kind']=='unlisted'
    assert out['host']=='REDACTED' and out['host_kind']=='unlisted'
    assert out['other']=='REDACTED' and out['other_kind']=='unlisted'

def test_localhost_localdomain_survives():
    out=redact_record(dict(server_dns='localhost.localdomain'))
    assert out['server_dns']=='localhost.localdomain'

def test_free_form_message_redacts():
    out=redact_record(dict(message='something went wrong at /home/alice/secret'))
    assert out['message']=='REDACTED' and out['message_kind']=='unlisted'

def test_fixed_refusal_string_survives():
    out=redact_record(dict(error_message='Replacement control unavailable'))
    assert out['error_message']=='Replacement control unavailable'

def test_bytes_redact():
    out=redact_record(dict(raw=b'\x00\x01'))
    assert out['raw']=='REDACTED' and out['raw_kind']=='unlisted'

def test_list_element_flag_sets_field_kind():
    out=redact_record(dict(members=['install-wraps','/tmp/nope']))
    assert out['members'][0]=='install-wraps'
    assert out['members'][1]=='REDACTED'
    assert out['members_kind']=='unlisted'

def test_list_of_clean_elements_has_no_kind():
    out=redact_record(dict(members=['install-wraps','selected-state']))
    assert out['members']==['install-wraps','selected-state']
    assert 'members_kind' not in out

def test_uuid_hex_iso_mode_digits_survive():
    out=redact_record(dict(
        claim_id='123e4567-e89b-12d3-a456-426614174000',
        sha256='a'*64,
        created_at='2026-10-25T14:09:52.123456Z',
        mode='0600',
        count='42'))
    assert out['claim_id']=='123e4567-e89b-12d3-a456-426614174000'
    assert out['sha256']=='a'*64
    assert out['created_at']=='2026-10-25T14:09:52.123456Z'
    assert out['mode']=='0600'
    assert out['count']=='42'

def test_nested_dict_and_list_markers():
    out=redact_record(dict(diag=dict(step='install-wraps',trace=[dict(wrap='execute_v1',event='enter'),dict(wrap='execute_v1',event='error',error_type='PermissionError')])))
    assert out['diag']['step']=='install-wraps'
    assert out['diag']['trace'][0]['wrap']=='execute_v1'
    assert 'diag_kind' not in out

def test_value_allowed_rejects_pathy_ident():
    assert not _value_allowed('/tmp/x')
    assert not _value_allowed('localhost')
    assert _value_allowed('install-wraps')
    assert _value_allowed('-')

def test_postgres_timestamptz_text_survives():
    for ts in ('2026-10-25 14:09:52.123456+00',
               '2026-10-25 14:09:52+00',
               '2026-10-25 19:39:52.123456+05:30',
               '2026-10-25T14:09:52.123456Z',
               '2026-10-25T14:09:52+00:00'):
        out=redact_record(dict(original_deadline=ts,created_at=ts,capture_until=ts))
        assert out['original_deadline']==ts,(ts,out)
        assert 'original_deadline_kind' not in out

def test_postgres_timestamptz_exact_example_survives():
    out=redact_record(dict(created_at='2026-10-25 14:09:52.123456+00'))
    assert out['created_at']=='2026-10-25 14:09:52.123456+00'

def test_tuple_rows_become_lists_and_survive():
    out=redact_record(dict(head=('capture_status_unknown',False,'terminal_observed')))
    assert out['head']==['capture_status_unknown',False,'terminal_observed'],out
    assert isinstance(out['head'],list)
    assert 'head_kind' not in out

def test_tuple_row_list_survives():
    row=( { 'claim_id':'123e4567-e89b-12d3-a456-426614174000','effect':'capture-create' }, )
    out=redact_record(dict(rows=[row]))
    assert out['rows'][0][0]['effect']=='capture-create',out
    assert 'rows_kind' not in out

def test_tuple_with_pathy_member_marks_list():
    out=redact_record(dict(rows=[('ok','/tmp/nope')]))
    assert out['rows'][0][0]=='ok'
    assert out['rows'][0][1]=='REDACTED'
    assert out['rows_kind']=='unlisted'

def test_supervisor_purpose_strings_survive():
    for purpose in ('meeting-scheduler-process-v1','meeting-stop-worker-process-v1','meeting-scheduler-runtime-v1','meeting-stop-process-runtime-v1','meeting-supervision-queue-consumer-v1','meeting-supervision-current-queue-v1','meeting-supervision-service-peer-v1','meeting-supervision-service-binding-v1','meeting-process-currentness-v2','meeting-supervisor-currentness-v2','meeting-supervisor-observer-owner-v2','meeting-supervisor-peer-v2','meeting-supervisor-client-installation-v1','meeting-supervisor-replay-installation-v1','meeting-create-operation-stop-relation-v1','replacement-meeting-worker-binding-v1','replacement-meeting-capture-worker-peer-v1','meeting-worker-receipt-root-v1','meeting-capture-worker-consumer-v1'):
        out=redact_record(dict(purpose=purpose))
        assert out['purpose']==purpose,(purpose,out)

def test_provider_route_strings_survive():
    routes=['POST /api/v1/bot/ HTTP/1.1',
            'GET /api/v1/bot/123e4567-e89b-12d3-a456-426614174000/ HTTP/1.1',
            'POST /api/v1/bot/123e4567-e89b-12d3-a456-426614174000/leave_call/ HTTP/1.1']
    out=redact_record(dict(provider_routes=routes))
    assert out['provider_routes']==routes,out
    assert 'provider_routes_kind' not in out

def test_non_api_route_still_redacts():
    out=redact_record(dict(route='POST /home/alice/secret HTTP/1.1'))
    assert out['route']=='REDACTED'
    assert out['route_kind']=='unlisted'

def test_marker_propagates_through_dict_members():
    out=redact_record(dict(members=[dict(step='install-wraps'),dict(path='/tmp/nope'),dict(step='selected-state')]))
    assert out['members'][0]['step']=='install-wraps'
    assert out['members'][1]['path']=='REDACTED'
    assert out['members'][1]['path_kind']=='unlisted'
    assert out['members_kind']=='unlisted',out

def test_dict_with_redacted_leaf_sets_field_kind():
    out=redact_record(dict(diag=dict(step='install-wraps',path='/tmp/x')))
    assert out['diag']['step']=='install-wraps'
    assert out['diag']['path']=='REDACTED'
    assert out['diag']['path_kind']=='unlisted'
    assert out['diag_kind']=='unlisted',out

def test_raise_site_with_lambda_code_name_survives():
    out=redact_record(dict(raise_site='PermissionError:<lambda>',error_type='PermissionError'))
    assert out['raise_site']=='PermissionError:<lambda>',out
    assert out['error_type']=='PermissionError'

def test_raise_site_listcomp_survives():
    out=redact_record(dict(raise_site='KeyError:<listcomp>'))
    assert out['raise_site']=='KeyError:<listcomp>',out

def test_raise_site_with_path_code_name_still_redacts():
    out=redact_record(dict(raise_site='PermissionError:/tmp/x'))
    assert out['raise_site']=='REDACTED'

def test_replay_spool_member_names_and_note_survive():
    out=redact_record(dict(
        members=['meeting-create-init.json','meeting-create-state.json','meeting-create-lock'],
        note='nonce-sequence state and appointment hashes only; no secrets'))
    assert out['members']==['meeting-create-init.json','meeting-create-state.json','meeting-create-lock'],out
    assert out['note']=='nonce-sequence state and appointment hashes only; no secrets',out

def test_redact_text_replaces_path_tokens():
    from meeting_unattended_redact import redact_text
    text='FAILED tests/test_x.py::test_y - assert\n'+'cwd=/tmp/pytest-abc123\n'
    out=redact_text(text)
    assert '/tmp/pytest-abc123' not in out
    assert 'test_y' in out
