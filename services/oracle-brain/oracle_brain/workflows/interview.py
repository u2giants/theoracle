"""Single SQL-owned interview projection and server-origin original linkage.

No serialized InterviewState is persistence. Every mutation goes through the
same protected own-principal SQL owner; user wording never becomes policy.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4, uuid5
import hashlib
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.conversation_control_v1 import ConversationControlV1,ConversationUnknown
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1

QUESTIONS={
 'recent-example':'Please describe one recent example of this work.',
 'trigger':'What started that example?', 'steps':'What steps happened next?',
 'handoffs':'Who received the work, and what did they need?',
 'result':'What was the result?', 'exceptions':'What exceptions or failures happened?',
 'decision-criteria':'How was the decision made?', 'conflicts':'What remains unclear or disputed?'}

def present(snapshot,*,now=None):
    """Display only; SQL remains the owner of question identity and total count."""
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:raise ValueError('aware display clock required')
    pending=snapshot['pending_question_id'];need=None
    for event in snapshot['events']:
        if event['question_id']==pending and pending is not None:need=event['need']
        if event['payload'].get('next_question_id')==pending and pending is not None:need=event['payload']['next_need']
    active=snapshot['state']=='active' and now<datetime.fromisoformat(snapshot['segment_deadline'])
    answer=next((e['payload']['direct_question_answer'] for e in reversed(snapshot['events']) if e['payload'].get('direct_question_answer')),None)
    claimed={e['payload']['event_id'] for e in snapshot['recap']['events'] if e['operation']=='claim_original'}
    linked={e['payload']['event_id'] for e in snapshot['recap']['events'] if e['operation']=='link_original'}
    registration='UNKNOWN' if claimed-linked else 'registered' if linked else 'not_registered'
    return dict(snapshot,original_registration_state=registration,question=QUESTIONS.get(need) if active else None,
        question_id=pending if active else None,answer_first=answer,
        offer_start_interview=snapshot['mode']=='ordinary',
        qualification_state='pending',company_policy_confirmed=False,account_acknowledgement_only=True)

class InterviewWorkflowV1:
    def __init__(self,control):
        if type(control) is not ConversationControlV1:raise TypeError('actual protected durable conversation owner required')
        self.control=control
    def execute_v1(self,raw):return present(self.control.execute_v1(raw))
    def resume_view_v1(self,thread_id):return present(self.control.snapshot_v1(thread_id))
    def register_original_v1(self,thread_id,event_id,intake):
        """Copy exact committed employee original into the existing byte owner.

        Registration has no retry loop. Any uncertain SQL/custody outcome is
        retained by existing owners; no SourceRef is created here.
        """
        if type(thread_id) is not UUID or type(event_id) is not UUID or type(intake) is not OriginalIntakeFactoryV1:raise TypeError('fixed exact original registration required')
        c=self.control.settings.config;i=intake.settings.config
        if (c.principal_id,c.workspace_id)!=(i.principal_id,i.workspace_id):raise PermissionError('independently appointed intake must match actual conversation principal')
        snapshot=self.control.snapshot_v1(thread_id)
        events=snapshot['recap']['events']
        matching=[e for e in events if e['event_id']==str(event_id) and e['origin']=='employee']
        if len(matching)!=1:raise PermissionError('exact committed employee event required')
        original=matching[0];data=original['original_text'].encode('utf-8')
        if hashlib.sha256(data).hexdigest()!=original['original_sha256']:raise PermissionError('committed original hash differs')
        if any(e['operation']=='link_original' and e['payload'].get('event_id')==str(event_id) for e in events):return snapshot
        if any(e['operation']=='claim_original' and e['payload'].get('event_id')==str(event_id) for e in events):raise ConversationUnknown('Original registration retained UNKNOWN; no automatic resubmit')
        claim=dict(schema_version=1,command_id=str(uuid5(event_id,'original-registration-claim-v1')),caller_deadline=self.control.settings.current().isoformat(),
            thread_id=str(thread_id),expected_revision=snapshot['revision'],operation='claim_original',event_id=str(event_id))
        snapshot=self.control._call('apply',(canonical_bytes(claim),))
        key=uuid5(event_id,'conversation-original-intake-v1')
        # Existing intake owns reserve/file/receipt/finalize and UNKNOWN failures.
        observed=intake.intake_text_v1(source_id=None,expected_head=0,idempotency_key=key,
            filename=str(event_id)+'.txt',original_sha256=original['original_sha256'],data=data)
        # Never append caller-provided custody metadata. SQL independently checks
        # this actual returned source against the exact retained employee bytes.
        body=dict(schema_version=1,command_id=str(uuid5(event_id,'original-link-v1')),
            caller_deadline=self.control.settings.current().isoformat(),thread_id=str(thread_id),
            expected_revision=snapshot['revision'],operation='link_original',event_id=str(event_id),
            source_id=str(observed.sourceId),source_revision=observed.revision)
        return self.control._call('apply',(canonical_bytes(body),))
