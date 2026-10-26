"""Fixed uninstalled advice mTLS path; shared current peer/framing/lifecycle owner."""
from .recommendation_actions_settings_v1 import RecommendationSettingsV1
from .recommendation_actions_v1 import RecommendationFactoryV1,parse_recommendation_request_v1,MAX_RESPONSE
from ._protected_control_listener_v1 import _protected_control_listener_v1

PATH='/v1/replacement/recommendation-actions'
def protected_recommendation_actions_server_v1(settings):
    if type(settings) is not RecommendationSettingsV1:raise TypeError('fixed advice installation required')
    return _protected_control_listener_v1(settings,RecommendationFactoryV1(settings),path=PATH,
        parse_request=parse_recommendation_request_v1,encode_response=lambda value:value,
        maximum_request_bytes=16384,maximum_response_bytes=MAX_RESPONSE)


class _RecommendationWebEnvelopeV1:
    """Fixed web-only reply binding; the existing internal factory API is retained."""
    def __init__(self,settings):
        if type(settings) is not RecommendationSettingsV1:raise TypeError('fixed advice installation required')
        self.settings=settings
        self.factory=RecommendationFactoryV1(settings)

    def execute_v1(self,raw):
        import hashlib,json
        from datetime import datetime,timezone
        from ..operating_model.contracts import canonical_bytes
        from ..operating_model.consultant.recommendation_authority_v1 import RecommendationOutcomeUnknown
        from .recommendation_actions_v1 import FeedbackCommandV1,MeasurementCommandV1
        request=parse_recommendation_request_v1(raw)
        possible_write=type(request) in (FeedbackCommandV1,MeasurementCommandV1)
        try:
            self.factory._time(request.caller_deadline)
            result=json.loads(self.factory.execute_v1(raw))
            self.factory._time(request.caller_deadline)
            until=datetime.fromisoformat(result['valid_until'])
            if not datetime.now(timezone.utc)<until<=min(request.caller_deadline,self.settings.current()):
                raise PermissionError('original finite advice reply required')
            config=self.settings.config
            encoded=canonical_bytes({'schema_version':1,'principal_id':str(config.principal_id),
                'workspace_id':str(config.workspace_id),'model_id':str(config.model_id),
                'request_sha256':hashlib.sha256(raw).hexdigest(),'operation':request.operation,
                'command_id':str(request.command_id) if hasattr(request,'command_id') else None,
                'expected_head':request.expected_head if hasattr(request,'expected_head') else None,'result':result})
            self.factory._time(request.caller_deadline)
            if not 0<len(encoded)<=MAX_RESPONSE:raise PermissionError('bounded advice web reply required')
            return encoded
        except Exception as error:
            from ..operating_model.consultant.recommendation_authority_v1 import RecommendationActionRefused
            if possible_write and not isinstance(error,(RecommendationOutcomeUnknown,RecommendationActionRefused)):
                raise RecommendationOutcomeUnknown('possible action write; exact receipt reconciliation only, never resend') from error
            raise


def protected_recommendation_web_server_v1(settings):
    """Separately installed fixed web listener; always requires reply envelope."""
    if type(settings) is not RecommendationSettingsV1:raise TypeError('fixed advice installation required')
    return _protected_control_listener_v1(settings,_RecommendationWebEnvelopeV1(settings),path=PATH,
        parse_request=parse_recommendation_request_v1,encode_response=lambda value:value,
        maximum_request_bytes=16384,maximum_response_bytes=MAX_RESPONSE)
