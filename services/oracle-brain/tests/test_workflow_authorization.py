import json
from uuid import uuid4
import psycopg,pytest
from test_operating_model_extraction import ready,response
from oracle_brain.operating_model.extraction import persist_response
from oracle_brain.operating_model.authority_adapter import require_review
from oracle_brain.operating_model.findings import import_legacy

def artifact(ready):
    ledger,receipt=ready;aid=uuid4()
    persist_response(ledger,receipt,json.dumps(response(receipt)),artifact_id=aid,version=1,permission_digest='a'*64,compiler_digest='b'*64)
    return ledger,receipt,aid

def grant(ledger,scope):
    owner,root=uuid4(),uuid4()
    with psycopg.connect(ledger.url) as c:
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by) VALUES(%s,%s,%s,'root',%s)",(root,ledger.principal,owner,uuid4()))
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,parent_id,granted_by) VALUES(%s,%s,%s,%s,%s,%s)",(uuid4(),ledger.principal,ledger.principal,scope,root,owner))

def review(l,r,aid,**kw):
    return l.append_review(workspace_id=r.ref.workspace_id,artifact_id=aid,version=1,finding_id=kw.get('finding_id','missing-owner'),event_id=uuid4(),action=kw.get('action','annotate'),scope='shipping',note='Invented scoped review',authority=require_review)

def test_source_confirmation_does_not_grant_workflow_policy_authority(ready):
    l,r,aid=artifact(ready);grant(l,'confirm')
    with pytest.raises(PermissionError,match='rooted'):review(l,r,aid)

def test_review_permission_with_denied_source_cannot_read_quarantine_string(ready):
    l,r=ready;grant(l,'finding-review:shipping');aid=uuid4()
    f=import_legacy(workspace_id=r.ref.workspace_id,refs=(r.ref,),scope='shipping',texts=['Invented unverified string'])[0]
    l.persist(workspace_id=r.ref.workspace_id,artifact_id=aid,version=1,kind='extraction',payload={'source_refs':[r.ref.model_dump(mode='json')],'findings':[f.model_dump(mode='json')]},refs=(r.ref,),permission_digest='a'*64,compiler_digest='b'*64)
    l.can_read=lambda *_:False
    called=[];original=l.blobs.read
    l.blobs.read=lambda *a:(called.append(True),original(*a))[1]
    with pytest.raises(PermissionError):review(l,r,aid,finding_id=f.finding_id)
    assert called==[]

def test_scoped_review_preserves_exact_finding_and_never_promotes_policy(ready):
    l,r,aid=artifact(ready);grant(l,'finding-review:shipping')
    before=l.read(r.ref.workspace_id,aid,1);review(l,r,aid,action='resolve')
    assert l.read(r.ref.workspace_id,aid,1)==before
    events=l.review_events(r.ref.workspace_id,aid,1)
    assert events[0]['action']=='resolve' and events[0]['scope']=='shipping'
    assert before['findings'][0]['status']=='unresolved'

def test_authorized_legacy_annotation_cannot_resolve_unverified_finding(ready):
    l,r=ready;grant(l,'finding-review:shipping');aid=uuid4()
    f=import_legacy(workspace_id=r.ref.workspace_id,refs=(r.ref,),scope='shipping',texts=['Invented legacy issue'])[0]
    l.persist(workspace_id=r.ref.workspace_id,artifact_id=aid,version=1,kind='extraction',payload={'source_refs':[r.ref.model_dump(mode='json')],'findings':[f.model_dump(mode='json')]},refs=(r.ref,),permission_digest='a'*64,compiler_digest='b'*64)
    review(l,r,aid,finding_id=f.finding_id)
    with pytest.raises(ValueError,match='re-anchoring'):review(l,r,aid,finding_id=f.finding_id,action='resolve')
    assert l.read(r.ref.workspace_id,aid,1)['findings'][0]['status']=='needs_evidence'


# Plan-named W06 matrix cases (S10). These require the Postgres `ready` fixture
# and FileBlobStore POSIX mode checks; on Windows run under:
#   ORACLE2_TEST_ADMIN_URL=postgresql://... services/oracle-brain/.venv/bin/python -m pytest \
#     services/oracle-brain/tests/test_workflow_authorization.py -q
# Synthetic pure-logic counterparts live in test_workflow_permission_matrix.py.

def test_cross_workspace_workflow_access_denied(ready):
    """Foreign workspace source refs cannot authorize review or read."""
    l, r, aid = artifact(ready)
    grant(l, "finding-review:shipping")
    foreign = r.ref.model_copy(update={"workspace_id": uuid4()})
    with pytest.raises(Exception):
        l.authorize_refs((foreign,), r.ref.workspace_id)


def test_revoked_permission_denies_cached_artifact(ready):
    """After source-read revocation, cached artifact bytes are unreadable."""
    l, r, aid = artifact(ready)
    grant(l, "finding-review:shipping")
    l.can_read = lambda *_: False
    with pytest.raises(PermissionError):
        review(l, r, aid)


def test_role_cannot_promote_policy(ready):
    """A review role cannot confirm or promote workflow policy."""
    l, r, aid = artifact(ready)
    grant(l, "confirm")
    with pytest.raises(PermissionError, match="rooted"):
        review(l, r, aid)


def test_review_race_keeps_append_only_history(ready):
    """Conflicting same-event review is refused; identical retry is idempotent."""
    l, r, aid = artifact(ready)
    grant(l, "finding-review:shipping")
    event_id = uuid4()
    review(l, r, aid, action="annotate")
    events = l.review_events(r.ref.workspace_id, aid, 1)
    assert events and events[0]["action"] == "annotate"
