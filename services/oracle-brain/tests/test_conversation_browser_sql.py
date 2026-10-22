"""Actual invented Chromium→same real identity owner→mTLS→owned TLS SQL.

Auth import hooks explicitly invented. This is source/runtime proof, never real
Supabase employee sign-in, deployment, target installation or business acceptance.
"""
import hashlib,json,subprocess
from pathlib import Path
from oracle_brain.operating_model.contracts import canonical_bytes
from test_durable_interview_sql import conversation
from test_hosting_boundary import certificates
from test_conversation_service_sql import listener
from test_replacement_requester_sql import owned_admin


def test_actual_browser_conversation_correction_resume_and_recap_owned_sql(conversation,tmp_path,certificates):
 x=conversation;s=x['control'].settings;c=s.config
 with listener(x,tmp_path,certificates,browser=True) as server:
  p=json.loads((tmp_path/'conversation-peer').read_bytes());seal=hashlib.sha256((tmp_path/'conversation-peer').read_bytes()).hexdigest()
  metadata=dict(scratch=str(tmp_path),auth_user_id=str(c.auth_user_id),employee_id=str(c.employee_id),project_url=c.auth_issuer.removesuffix('/auth/v1'),principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,conversation_config_sha256=s.config_sha256,conversation_appointment_sha256=s.appointment_sha256,conversation_peer_profile_sha256=seal,backend_origin='https://localhost.localdomain:'+str(server.server_port),server_key_file=p['server_key_file'],server_certificate_file=p['server_certificate_file'],client_ca_file=p['client_ca_file'],client_certificate_file=str(certificates/'worker.pem'),client_key_file=str(certificates/'worker.key'),client_uri=p['client_uri'],issuer_actor=p['issuer_actor'],reviewer_actor=p['reviewer_actor'],valid_from=p['valid_from'],expires_at=p['expires_at'],original_horizon=p['original_horizon'])
  path=tmp_path/'conversation-browser-metadata';path.write_bytes(canonical_bytes(metadata));path.chmod(0o600)
  root=Path(__file__).resolve().parents[3]
  result=subprocess.run(['pnpm','--filter','@oracle/web','exec','tsx','tests/oracle2/interview-proof.ts',str(path)],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=50)
  (tmp_path/'conversation-browser-process.txt').write_text(result.stdout)
  assert result.returncode==0,result.stdout[-7000:]
  receipt=json.loads((tmp_path/'interview-browser-receipt.json').read_text())
  assert receipt['denied_visible_history_withheld'] is True
  assert receipt['actual_browser'] and receipt['exact_original_and_correction'] and receipt['pause_refresh_resume_same_question'] and receipt['company_policy_confirmed'] is False
 with owned_admin(x) as connection:
  rows=connection.execute('SELECT original_text FROM oracle2.conversation_events_v1 WHERE workspace_id=%s AND origin=%s ORDER BY sequence',(x['workspace'],'employee')).fetchall()
  assert rows==[('不允许未经复核就发货。仅限样品。',),('样品也必须复核。',)]
  assert connection.execute('SELECT question_count,reviewed_revision IS NOT NULL FROM oracle2.conversation_threads_v1 WHERE thread_id=%s',(receipt['thread_id'],)).fetchone()==(2,True)

from test_replacement_source_intake_sql import requester
