"""S06 uses the SAME actual S09 evidence answer before its sole SQL question.

This owns no conversation event, question selection, truth, grant or paid effect.
Optional fixed server startup accepts only independently installed own-recipient
settings. Every answer is freshly read; absent evidence remains a visible gap.
"""
from datetime import datetime,timezone,timedelta
from uuid import UUID
import psycopg
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.conversation_control_v1 import ConversationControlV1
from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1,_request_end_v1
from oracle_brain.workflows.natural_answer_v1 import NaturalQuestionRequestV1
from .connected_answer_settings_v1 import ConnectedAnswerSettingsV1
from .connected_answer_service_v1 import ProtectedConnectedAnswerServiceV1
from .replacement_result_service_v1 import _ResultOwnedLoopV1

class ConversationAnswerV1:
    def __init__(self,control,settings,*,effects=None):
        if type(control) is not ConversationControlV1 or type(settings) is not ConnectedAnswerSettingsV1:
            raise TypeError('actual own conversation and separately appointed evidence consumer required')
        c=control.settings.config;s=settings.config
        if (c.principal_id,c.workspace_id)!=(s.principal_id,s.workspace_id) or settings.peer.channel!='web':
            raise PermissionError('independent answer recipient differs from conversation owner')
        control.settings.current();settings.current();self.control=control;self.settings=settings
        self.owned=_ResultOwnedLoopV1(ProtectedConnectedAnswerServiceV1(settings))
        self.effect_owned=None
        if effects is not None:
            from .question_effect_factory_v1 import ProtectedQuestionEffectFactoryV1
            if type(effects) is not ProtectedQuestionEffectFactoryV1 or(effects.owner.config.enduser_principal_id,effects.owner.config.workspace_id)!=(c.principal_id,c.workspace_id):
                self.owned.close();raise PermissionError('exact separate same employee question effect installation required')
            try:self.effect_owned=_ResultOwnedLoopV1(effects)
            except BaseException:self.owned.close();raise
    def close(self):
        try:
            if self.effect_owned is not None:self.effect_owned.close()
        finally:self.owned.close()
    def _unobserved_v1(self,snapshot,state):
        from oracle_brain.operating_model.question_effect_public_v1 import nonobserved_question_effect_v1
        request_remaining_v1();checked=datetime.now(timezone.utc)
        end=min(self.control.settings.current(),checked+timedelta(seconds=min(30,request_remaining_v1())))
        return nonobserved_question_effect_v1(snapshot,state=state,checked_at=checked,expires_at=end).model_dump(mode='json')
    def present_turn_v1(self,snapshot,turn_id):
        from oracle_brain.workflows.interview import present
        request_remaining_v1();self.control.settings.current()
        events=[e for e in snapshot['recap']['events'] if e['origin']=='employee' and e['turn_id']==turn_id]
        if len(events)!=1:raise PermissionError('exact immutable employee original required for evidence question')
        event=events[0];thread=UUID(snapshot['thread_id']);revision=snapshot['revision']
        capability_gap=None
        if self.effect_owned is not None:
            from .question_effect_factory_v1 import QuestionEffectUnknown,QuestionEffectPostDispatchFailure
            try:
                effect=self.effect_owned.result(self.control,snapshot,absolute_monotonic_deadline=_request_end_v1.get())
            except QuestionEffectUnknown:
                # The employee turn is already durable. Never rerun lexical or
                # native work after a possible claim/paid/uncertain effect.
                latest=self.control.snapshot_v1(thread)
                if latest['revision']!=revision:raise PermissionError('conversation changed after uncertain question effect')
                result=present(latest);result['qualified_answer']=None
                result['qualified_effect']=self._unobserved_v1(latest,'unknown')
                result['answer_first']='The response outcome is unknown. Your original words are saved; no request has been repeated.'
                return result
            except QuestionEffectPostDispatchFailure:
                # Paid dispatch completed; outcome is uncertain. Never mask
                # as unavailable/not-dispatched; surface the truthful unknown.
                latest=self.control.snapshot_v1(thread)
                if latest['revision']!=revision:raise PermissionError('conversation changed after uncertain question effect')
                result=present(latest);result['qualified_answer']=None
                result['qualified_effect']=self._unobserved_v1(latest,'unknown')
                result['answer_first']='The response outcome is unknown. Your original words are saved; no request has been repeated.'
                return result
            except (PermissionError,psycopg.Error,ValueError):
                if self.effect_owned.service._cleanup_unknown and any(not t.done() for t in self.effect_owned.service._owned_closes):raise
                capability_gap='The independently authorized search or synthesis capability is unavailable. This answer uses existing qualified records only.'
            else:
                latest=self.control.snapshot_v1(thread)
                if latest['revision']!=revision:raise PermissionError('conversation changed after qualified effect')
                result=present(latest);result['qualified_answer']=None
                if effect['state']=='clarification' and latest['mode']=='interview':
                    # No extra scope question can bypass the one SQL question.
                    effect=self._unobserved_v1(latest,'unavailable')
                result['qualified_effect']=effect
                result['answer_first']='Current qualified evidence is shown below.' if effect.get('answer') is not None else 'Current qualified records do not establish an answer. The existing interview question is unchanged.'
                return result
        packet=None;gap='Current qualified records do not establish an answer. No extra interview question has been added.'
        try:
            self.settings.current()
            authority,blobs=self.settings.consumer();deadline=min(self.settings.current(),self.control.settings.current(),datetime.now(timezone.utc)+timedelta(seconds=min(30,request_remaining_v1())))
            core,_,_,initial_delivery=authority.read_serving_packet_v1(self.settings.config.model_id,blobs=blobs,deadline=deadline)
            # The immutable employee original is the question; the same qualified
            # owner resolves scope without caller process IDs or invented context.
            q=NaturalQuestionRequestV1(caller_deadline=min(deadline,datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+request_remaining_v1(),timezone.utc)),question=event['original_text'])
            raw=canonical_bytes(q.model_dump(mode='json'))
            packet=self.owned.result(None,raw,absolute_monotonic_deadline=_request_end_v1.get())
            # This is a structured quoted record answer, never a second native
            # interviewer. A scope clarification is displayed as an honest gap.
        except (PermissionError,psycopg.Error):
            if any(not t.done() for t in self.owned.service._owned_closes):raise
        latest=self.control.snapshot_v1(thread)
        if latest['revision']!=revision:raise PermissionError('conversation changed during evidence answer')
        if packet is not None:
            try:
                self.settings.current()
                observed=authority.projection_delivery_v1(self.settings.config.model_id,packet['answer']['model_version'] if packet['answer'] is not None else core.model.version,deadline=deadline)
                if observed.retained_receipt_body_sha256!=packet['retained_receipt_body_sha256'] or observed.model_content_hash!=(packet['answer']['model_content_hash'] if packet['answer'] is not None else initial_delivery.model_content_hash):
                    raise PermissionError('interview evidence changed after actual thread recheck')
            except (PermissionError,psycopg.Error):packet=None
        request_remaining_v1()
        result=present(latest)
        result['qualified_answer']=packet
        result['answer_first']='Current qualified evidence is shown below.' if packet is not None else gap
        if capability_gap is not None:
            result['qualified_effect']=self._unobserved_v1(latest,'unavailable')
            result['answer_first']=capability_gap+' '+result['answer_first']
        # The existing present() receives unchanged actual pending question/count.
        return result
