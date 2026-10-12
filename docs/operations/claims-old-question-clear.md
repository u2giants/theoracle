# Exact reversible cleanup of obsolete CLAIMS assignments

Status: prepared; no production mutation has occurred. Root coordinator retains the production decision.

Owner request, verbatim: “clear the questions that are currently under CLAIMS for Ilona and Jessica. they were generated under the old (incorrect) logic”.

Target: Oracle CURRENT PROD Supabase project eqccjfbyrywsqkxxpjvg, selected through its specific existing vault session-pooler credential. Never use connected unrelated Supabase MCP, old Oracle project, or shared POP database.

Live identity binding, verified read-only: Ilona Kereki = 0afd45f8-5ee1-4d41-a43c-36bcd59f4102; Jessica Cortazar = 52a0662e-f24b-46bb-87bf-706286c20255. The transaction rechecks these exact names and UUIDs before any UPDATE. Pooler target is strictly allowlisted by exact Supabase endpoint, exact project-bound database username, port5432 and databasepostgres; a substring or wrong host is rejected.

Read-only inventory found precisely 30 open claim_review_question gaps, 15 for each exact named employee. All belong to one October 6 legacy generation run. No new generation/grading permitted. Existing resolved history remains untouched. The existing admin gaps action supports rejected, and the dynamic employee CLAIMS page excludes rejected assignments.

Action: transactionally reject only the exact 30 frozen IDs, change updated_at, preserve all other columns and all claims, evidence, reviews, messages/answers. No deletions, schema changes, notices, provider calls, replacement questions or grading. Backup contains the complete original gap rows privately; no question contents or credential values are sent to reviewer. A table write-exclusion lock and exact whole-row comparison prevent stale inputs; active population must match the same 30 IDs. Exact changed count30, remainingactive0 and unrelatedgap checksum/count equality are mandatory. Claims/evidence/review/message counts are rechecked; any change aborts.

Run preview first (same changes rolled back), apply only after exact reviewer APPROVE and root task-gate database check, then independently re-read the live CLAIMS predicate and all preserved record counts. A failed connection, mismatch, timeout, incomplete backup or changed population stops before commit. Restore only when the complete post-clear rows remain unchanged; restore original status/timestamps from backup. Root checks COMMIT by exit0 plus independent readback, never stdout alone. Protected backup and receipts survive in owned ignored review storage.

Review is requested for this exact operation and script only; it grants no W01–W12 hosting, budget, private-source, question-generation or grading authority.

Script SHA256: fca023a1c07e572e0f5c8ca67e2b5a07035f75e5cc3b5a64f5cd223daf641fcf

```python
"""Root-only guarded production operation; requires exact reviewer/task gate before apply."""
import os,json,hashlib,pathlib,urllib.parse,sys,datetime
import psycopg
from psycopg.rows import dict_row
p=pathlib.Path(__file__).parent
blob=(p/'backup.json').read_bytes()
assert hashlib.sha256(blob).hexdigest()=='e67154eb8684f16bb6282d5149a3557bfbf96fb2174ebe4ee441ce4927259209'
b=json.loads(blob); ids=[r['id'] for r in b['rows']]; employees=[e['id'] for e in b['employees']]
assert len(ids)==len(set(ids))==30
assert set(employees)=={'0afd45f8-5ee1-4d41-a43c-36bcd59f4102','52a0662e-f24b-46bb-87bf-706286c20255'}
assert all(r['status']=='open' and r['gap_type']=='claim_review_question' and r['target_employee_id'] in employees for r in b['rows'])
u=urllib.parse.urlparse(os.environ['ORACLE_DIRECT_URL'])
assert u.scheme in ('postgres','postgresql') and u.port==5432
assert (u.hostname=='db.eqccjfbyrywsqkxxpjvg.supabase.co' and u.username=='postgres') or (u.hostname in ('aws-0-us-east-1.pooler.supabase.com','aws-1-us-east-1.pooler.supabase.com') and u.username=='postgres.eqccjfbyrywsqkxxpjvg')
assert u.path=='/postgres' 
def canon(value): return json.dumps(value,default=str,sort_keys=True,separators=(',',':'))
def save(name,value):
 data=canon(value).encode(); target=p/name
 with target.open('xb') as f: f.write(data)
 target.chmod(0o600); return hashlib.sha256(data).hexdigest()
def protected_counts(c):
 return {table:c.execute('SELECT count(*) n FROM '+table).fetchone()['n'] for table in ('claims','claim_evidence','claim_review_events','messages')}
mode=sys.argv[1] if len(sys.argv)==2 else 'preview'
assert mode in ('preview','apply','rollback')
with psycopg.connect(os.environ['ORACLE_DIRECT_URL'],connect_timeout=15,row_factory=dict_row) as c:
 c.execute("SET LOCAL lock_timeout='5s'"); c.execute("SET LOCAL statement_timeout='30s'")
 c.execute('LOCK TABLE gaps IN SHARE ROW EXCLUSIVE MODE')
 bound=c.execute('SELECT id,name FROM employees WHERE id=ANY(%s::uuid[]) ORDER BY name',(employees,)).fetchall()
 assert {str(e['id']):e['name'] for e in bound}=={'0afd45f8-5ee1-4d41-a43c-36bcd59f4102':'Ilona Kereki','52a0662e-f24b-46bb-87bf-706286c20255':'Jessica Cortazar'}
 assert all(sum(r['target_employee_id']==e for r in b['rows'])==15 for e in employees)
 original_counts=protected_counts(c)
 current=c.execute('SELECT * FROM gaps WHERE id=ANY(%s::uuid[]) ORDER BY target_employee_id,id FOR UPDATE',(ids,)).fetchall()
 assert len(current)==30
 if mode=='rollback':
  post=json.loads((p/'post.json').read_text())
  assert canon(current)==canon(post['rows']), 'Post-clear rows changed; rollback refused'
  for old in b['rows']:
   result=c.execute("UPDATE gaps SET status=%s::gap_status,updated_at=%s::timestamp WHERE id=%s::uuid AND status='rejected' RETURNING id",(old['status'],old['updated_at'],old['id'])).fetchall()
   assert len(result)==1
  restored=c.execute('SELECT * FROM gaps WHERE id=ANY(%s::uuid[]) ORDER BY target_employee_id,id',(ids,)).fetchall()
  assert canon(restored)==canon(b['rows'])
  receipt={'restored_count':30,'backup_sha256':hashlib.sha256(blob).hexdigest(),'at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  receipt_hash=save('rollback-receipt.json',receipt)
 else:
  assert canon(current)==canon(b['rows']), 'Exact original rows changed; clear refused'
  live=c.execute("SELECT id FROM gaps WHERE gap_type='claim_review_question' AND target_employee_id=ANY(%s::uuid[]) AND status IN ('open','queued','asked')",(employees,)).fetchall()
  assert {str(r['id']) for r in live}==set(ids), 'Active population changed; clear refused'
  other_before=c.execute("SELECT md5(COALESCE(string_agg(row_to_json(g)::text,'' ORDER BY id),'')) checksum,count(*) FROM gaps g WHERE NOT(id=ANY(%s::uuid[]))",(ids,)).fetchone()
  changed=c.execute("UPDATE gaps SET status='rejected',updated_at=now() WHERE id=ANY(%s::uuid[]) AND gap_type='claim_review_question' AND target_employee_id=ANY(%s::uuid[]) AND status='open' RETURNING id",(ids,employees)).fetchall()
  assert len(changed)==30
  remaining=c.execute("SELECT count(*) n FROM gaps WHERE gap_type='claim_review_question' AND target_employee_id=ANY(%s::uuid[]) AND status IN ('open','queued','asked')",(employees,)).fetchone()['n']
  assert remaining==0
  other_after=c.execute("SELECT md5(COALESCE(string_agg(row_to_json(g)::text,'' ORDER BY id),'')) checksum,count(*) FROM gaps g WHERE NOT(id=ANY(%s::uuid[]))",(ids,)).fetchone()
  assert other_before==other_after, 'Unrelated gap change'
  postrows=c.execute('SELECT * FROM gaps WHERE id=ANY(%s::uuid[]) ORDER BY target_employee_id,id',(ids,)).fetchall()
  assert protected_counts(c)==original_counts, 'Protected record count changed; fail closed'
  receipt={'protected_record_counts':original_counts,'mode':mode,'changed_count':30,'remaining_active':remaining,'unrelated_gaps_unchanged':True,'rows':postrows,'backup_sha256':hashlib.sha256(blob).hexdigest(),'at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  if mode=='preview': c.rollback(); receipt_hash=save('preview-receipt.json',receipt)
  else: receipt_hash=save('post.json',receipt)
 print(json.dumps({'mode':mode,'count':30,'receipt_sha256':receipt_hash,'committed':mode!='preview'}))

```

Exact metadata-only target manifest (no question text):

```json
{
  "backup_sha256": "e67154eb8684f16bb6282d5149a3557bfbf96fb2174ebe4ee441ce4927259209",
  "employee_ids": [
    "0afd45f8-5ee1-4d41-a43c-36bcd59f4102",
    "52a0662e-f24b-46bb-87bf-706286c20255"
  ],
  "project_ref": "eqccjfbyrywsqkxxpjvg",
  "rows": [
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "097572c3-4c65-40a6-8c05-0ce77d24d3c4",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "1bee42ef-dd58-4da1-8a36-3e741314f2b0",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "397ae4e7-bf4f-4d2d-8472-4094447e5ff8",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "4ee25eeb-2d05-4452-ae33-1f70c34f74ad",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "5f5acb1c-8af4-4b73-9c7f-322268db2ef4",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "626e90d1-a5a1-4171-af45-464962d172ed",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "6305c848-474c-4915-b6d8-51ef5add9010",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "7ef98102-eb67-4ec2-be6d-737be8848977",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "851215eb-e9a6-4d5c-af87-56d1e93cb910",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "9ff7aa1a-89b5-4ee3-954e-483d5ceb4b81",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "cb67c119-b061-40e6-87fc-ce74a2620456",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "d58bad02-50e8-4364-9a38-161fdb636785",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "d5b817e6-3bf9-44b6-9c0b-c0d73e00f372",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "d94f6efb-001f-4bc7-b300-1f7a6abb3fb9",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "da6546fb-dcd1-46c4-9c0e-c39f0e26b911",
      "status": "open",
      "target_employee_id": "0afd45f8-5ee1-4d41-a43c-36bcd59f4102"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "02ade2d0-7d8a-423a-8048-8babf1336767",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "18769305-c281-477b-b1c7-81f7792db7ea",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "1c994406-e58a-4f90-9cba-72efb8a012da",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "1e03f528-cea1-4ab9-b452-4751db060816",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "29ce1933-b46c-41a8-b601-e6a71c25bb34",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "32f4e1e1-67b1-4db5-9faf-c903271067d2",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "3de5fc0c-de22-48d3-88a9-98b512b0e0f3",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "53687cf7-f6f8-4fbe-af0e-9ab920c22b5d",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "5e59d6f8-d8b6-471f-9dfd-136d8e57d683",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "6ac36eb2-04a4-4aaa-9b53-44dad866f0b7",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "c092b120-404f-4631-beac-350dcec3e47c",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "c97adf41-0fd4-4674-abc5-9b8a35ebcb60",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "e7a19abb-d7eb-48bb-819d-157ec4d41ff1",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "ec408fda-1356-40a1-9b86-f8abd6296095",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    },
    {
      "created_at": "2026-10-06 23:19:08.050456",
      "id": "ee3b8ff0-ee01-4715-9ab0-d9f1b3805fcb",
      "status": "open",
      "target_employee_id": "52a0662e-f24b-46bb-87bf-706286c20255"
    }
  ]
}
```
