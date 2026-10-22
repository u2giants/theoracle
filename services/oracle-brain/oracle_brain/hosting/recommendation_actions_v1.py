"""Fixed advice composition; source numbers, personal feedback, no action effect."""
from datetime import datetime,timezone
from contextlib import ExitStack
import time
from typing import Literal
from pydantic import AwareDatetime
import hashlib,json,os
from pathlib import Path
from uuid import UUID
from ..operating_model.contracts import StrictRecord,canonical_bytes
from ..operating_model.consolidation_contracts_v1 import ConsolidationCoreV1
from ..operating_model.consolidation_recommendations_v1 import validate_recommendation_parent
from ..operating_model.contracts import ArtifactManifest
from ..operating_model.artifact_storage import _parent_fd,_read_private_at
from ..operating_model.request_deadline_v1 import request_remaining_v1,sql_remaining_v1,_request_fence_v1
from ..operating_model.consultant.recommendation_actions_v1 import (
    RecommendationSelectorV1,FeedbackCommandV1,MeasurementCommandV1,
    source_bound_measurement_v1,observed_difference_v1)
from ..operating_model.consultant.measurement_evidence_v1 import MeasurementEvidenceV1
from ..operating_model.consultant.recommendation_authority_v1 import RecommendationOutcomeUnknown
from .original_intake_v1 import _parse
from .recommendation_actions_settings_v1 import RecommendationSettingsV1

from ..operating_model.consultant.recommendation_presentation_v1 import readable_recommendation_evidence_v1

MAX_RESPONSE=262144
class ListRecommendationsV1(StrictRecord):
    operation:Literal['list'];caller_deadline:AwareDatetime

class InspectRecommendationV1(StrictRecord):
    operation:Literal['inspect'];selector:RecommendationSelectorV1;caller_deadline:AwareDatetime

class ReconcileFeedbackV1(StrictRecord):
    operation:Literal['reconcile-feedback'];selector:RecommendationSelectorV1;command_id:UUID;caller_deadline:AwareDatetime
class ReconcileMeasurementV1(StrictRecord):
    operation:Literal['reconcile-measurement'];selector:RecommendationSelectorV1;command_id:UUID;caller_deadline:AwareDatetime

def parse_recommendation_request_v1(raw):
    if type(raw) is not bytes or not 0<len(raw)<=16384:raise PermissionError('bounded closed advice request required')
    value=json.loads(raw)
    cls=({'list':ListRecommendationsV1,'inspect':InspectRecommendationV1,'feedback':FeedbackCommandV1,'measurement':MeasurementCommandV1,'reconcile-feedback':ReconcileFeedbackV1,'reconcile-measurement':ReconcileMeasurementV1}.get(value.get('operation')) if type(value) is dict else None)
    if cls is None:raise PermissionError('fixed advice operation required')
    return _parse(cls,raw)

class RecommendationFactoryV1:
    def __init__(self,settings):
        if type(settings) is not RecommendationSettingsV1:raise TypeError('three fixed advice consumers required')
        self.settings=settings;settings.current()
    def _time(self,deadline):
        request_remaining_v1();sql_remaining_v1(deadline)
        if not datetime.now(timezone.utc)<deadline<=self.settings.current():raise PermissionError('original advice horizon elapsed')
    def _body(self,manifest):
        c=self.settings.config;key=manifest.private_object_key
        if (type(key) is not str or key!=f'operating-model/{c.workspace_id}/{manifest.content_hash}.json'):
            raise PermissionError('canonical private advice object identity required')
        parent=_parent_fd(Path(c.storage_root),key.split('/')[:-1],create=False,expected_root=(c.storage_device,c.storage_inode,c.storage_uid))
        try:data=_read_private_at(parent,key.split('/')[-1],16*1024*1024)
        finally:os.close(parent)
        if hashlib.sha256(data).hexdigest()!=manifest.content_hash:raise PermissionError('immutable advice content changed')
        body=json.loads(data)
        if canonical_bytes(body)!=data:raise PermissionError('canonical advice bytes required')
        return body
    def _lease(self,status,deadline,leases):
        # SQL supplies the actual source-read lease. Retain its monotonic cap
        # until the enclosing execute (including encoding) finishes; later SQL
        # cannot renew a shorter earlier lease, even across wall-clock rollback.
        value=status.get('valid_until')
        if type(value) is not str:raise PermissionError('aware actual advice read lease required')
        try:until=datetime.fromisoformat(value)
        except ValueError:raise PermissionError('aware actual advice read lease required') from None
        if until.tzinfo is None or until.utcoffset() is None:
            raise PermissionError('aware actual advice read lease required')
        end=time.monotonic()+sql_remaining_v1(min(deadline,until))
        leases.enter_context(_request_fence_v1(float(end)))
        self._time(deadline)
    def _read(self,read,selector,deadline,leases):
        self._time(deadline)
        before=read.read_v1(selector,deadline=deadline,_runtime_recheck=self.settings.current)
        self._lease(before,deadline,leases)
        if before['redacted']:
            return before,None,None,None,None
        context=before['context']
        manifest=ArtifactManifest.model_validate_json(canonical_bytes(context['manifest']))
        parent=ArtifactManifest.model_validate_json(canonical_bytes(context['parentManifest']))
        # Metadata getter has committed and ACTUALLY CLOSED both sockets before
        # these private reads. Fresh independent currentness follows the bytes.
        self._time(deadline);payload=self._body(manifest);self._time(deadline)
        parent_payload=self._body(parent);self._time(deadline)
        body=validate_recommendation_parent(manifest,payload,parent,parent_payload)
        item=next((i for i in body.recommendations if i.recommendation_id==selector.recommendation_id),None)
        if item is None:raise PermissionError('exact selected recommendation required')
        core=ConsolidationCoreV1.model_validate_json(canonical_bytes(parent_payload['consolidation_core']))
        presentation=readable_recommendation_evidence_v1(core,item,parent_payload,now=datetime.now(timezone.utc))
        after=read.read_v1(selector,deadline=deadline,_runtime_recheck=self.settings.current)
        self._lease(after,deadline,leases)
        if (after['redacted'] or {k:v for k,v in after.items() if k!='valid_until'}!={k:v for k,v in before.items() if k!='valid_until'}):
            raise PermissionError('recommendation changed during private read; reload')
        self._time(deadline)
        return after,item,core,parent,presentation
    def _public(self,status,item,core,parent,presentation):
        # SQL context/paths/credentials/appointments remain internal. Old denied
        # bodies cannot be reconstructed from forensic history metadata.
        public={key:status[key] for key in ('schema_version','artifact_id','artifact_version','recommendation_id','head_revision','stale','redacted','events','valid_until','policy_accepted','effect_executed','causal_savings','realized_savings_verified','business_acceptance')}
        public['recommendation']=None if item is None else item.model_dump(mode='json')
        public['parent_version']=None if parent is None else parent.version
        public.update(presentation or {'measurement_sources':[],'measurement_coverage_gap':False,'evidence':{p:[] for p in ('supporting','opposing','unknown','temporal')},'evidence_coverage_gap':False})
        public['comparisons']=[]
        if item is not None:
            for plan in item.experiments:
                phases={e['kind']:e['payload'].get('measurement') for e in status['events']
                    if e['kind'] in ('baseline','followup') and e.get('payload') and e['payload'].get('experiment_id')==str(plan.experiment_id)}
                if set(phases)=={'baseline','followup'}:
                    comparison=observed_difference_v1(*(MeasurementEvidenceV1.model_validate_json(canonical_bytes(phases[k])) for k in ('baseline','followup')),now=datetime.now(timezone.utc))
                else:comparison={'state':'unavailable','observed_difference':None,'causal_savings':False,'realized_savings_verified':False}
                public['comparisons'].append({'experiment_id':str(plan.experiment_id),**comparison})
        return public
    def _list(self,read,deadline,leases):
        before=read.list_v1(deadline=deadline,_runtime_recheck=self.settings.current)
        self._lease(before,deadline,leases)
        entries=[]
        for value in before['selectors']:
            selector=RecommendationSelectorV1.model_validate_json(canonical_bytes(value))
            status,item,core,parent,presentation=self._read(read,selector,deadline,leases)
            if item is None:raise PermissionError('recommendation index changed; reload')
            entries.append({'selector':selector.model_dump(mode='json'),'label':item.problem[:160],
                'label_truncated':len(item.problem)>160,'lens':item.advice['lens']})
        after=read.list_v1(deadline=deadline,_runtime_recheck=self.settings.current)
        self._lease(after,deadline,leases)
        if {k:v for k,v in before.items() if k!='valid_until'}!={k:v for k,v in after.items() if k!='valid_until'}:
            raise PermissionError('recommendation index changed during private reads; reload')
        self._time(deadline)
        return {k:v for k,v in after.items() if k!='selectors'}|{'entries':entries}
    def execute_v1(self,raw):
        with ExitStack() as leases:
            return self._execute_v1(raw,leases)
    def _execute_v1(self,raw,leases):
        request=parse_recommendation_request_v1(raw);deadline=request.caller_deadline
        recorded=False
        try:
            self._time(deadline);read,feedback,measurement=self.settings.consumers()
            if type(request) is ListRecommendationsV1:
                encoded=canonical_bytes(self._list(read,deadline,leases));self._time(deadline)
                if not 0<len(encoded)<=MAX_RESPONSE:raise PermissionError('bounded recommendation index required')
                return encoded
            if type(request) in (ReconcileFeedbackV1,ReconcileMeasurementV1):
                consumer=feedback if type(request) is ReconcileFeedbackV1 else measurement
                selector=request.selector
                receipt=consumer.reconcile_v1(selector.artifact_id,selector.artifact_version,selector.recommendation_id,request.command_id,deadline=deadline,_runtime_recheck=self.settings.current)
                if receipt['artifact_sha256']!=selector.artifact_sha256:
                    raise PermissionError('exact immutable reconciliation artifact differs')
                result={**receipt,'policy_accepted':False,'effect_executed':False,'causal_savings':False,'business_acceptance':False}
                encoded=canonical_bytes(result)
                self._time(deadline)
                if not 0<len(encoded)<=4096:raise PermissionError('bounded exact receipt required')
                return encoded
            status,item,core,parent,presentation=self._read(read,request.selector,deadline,leases)
            if type(request) is not InspectRecommendationV1:
                if item is None:raise PermissionError('stale/redacted advice cannot accept feedback or measurement')
                # No callback/body/role selectors cross the public request boundary.
                if type(request) is FeedbackCommandV1:
                    receipt=feedback.feedback_v1(request,raw,_runtime_recheck=self.settings.current)
                else:
                    selected=source_bound_measurement_v1(core,item,request,now=datetime.now(timezone.utc))
                    receipt=measurement.measurement_v1(request,raw,canonical_bytes(selected['assertion']),_runtime_recheck=self.settings.current)
                recorded=True
                try:
                    self._time(deadline)
                    status,item,core,parent,presentation=self._read(read,request.selector,deadline,leases)
                    if status['redacted'] or not any(e['event_id']==receipt['event_id'] for e in status['events']):
                        raise PermissionError('recorded action cannot be delivered as current')
                    self._time(deadline)
                except Exception as error:
                    raise RecommendationOutcomeUnknown('action may be committed; same-command receipt reconciliation only, never resend') from error
            result=self._public(status,item,core,parent,presentation)
            encoded=canonical_bytes(result)
            if not 0<len(encoded)<=MAX_RESPONSE:raise PermissionError('bounded readable advice response required')
            self._time(deadline)
            return encoded
        except Exception as error:
            if recorded and not isinstance(error,RecommendationOutcomeUnknown):
                raise RecommendationOutcomeUnknown("action may be committed; read-only exact receipt reconciliation, never resend") from error
            raise
