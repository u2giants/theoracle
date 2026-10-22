"""Descriptive retained ACK evidence with a separate current recipient read lease.

Only the actual own-role SQL022 consumer supplies runtime currentness. Constructing
these records grants no access, generation, projection, provider or spend right.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,field_validator,model_validator
from .contracts import StrictRecord,ProcessingProjectionReceiptBodyV3,digest
from .source_receipts import SourceRef,_StrictModel

HASH=r'^[a-f0-9]{64}$'
DELIVERY_SIGNATURE='hosting_consolidated_projection_delivery_v1(uuid,integer,timestamp with time zone,timestamp with time zone,uuid,text,text,text,timestamp with time zone)'
DELIVERY_FUNCTIONS=(DELIVERY_SIGNATURE,'_purpose_deadlines_v2()',
 '_retained_processing_projection_receipt_v1(uuid,uuid,integer,jsonb)',
 '_processing_projection_receipt_v3(uuid,uuid,integer,jsonb)',
 '_processing_model_admission_v1(uuid,text,text,text,text,timestamp with time zone)',
 '_processing_history_metadata_v1(oracle2.processing_model_admissions_v1,uuid,integer)',
 '_processing_canonical_jsonb_v1(jsonb)')

class AsOfAssertionSelectionV1(_StrictModel):
    assertion_id:UUID
    revision:int=Field(ge=1)

class AsOfDecisionObservationV1(_StrictModel):
    event_id:UUID
    recorded_at:AwareDatetime
    decision_kind:Literal['employee-account','process-policy','company-policy']
    scope_sha256:str=Field(pattern=HASH)
    assertions:tuple[AsOfAssertionSelectionV1,...]=Field(min_length=1,max_length=2048)
    challenged_as_of:bool
    withdrawn_as_of:bool
    @model_validator(mode='after')
    def exact_selection(self):
        if len(set(self.assertions))!=len(self.assertions):raise ValueError('distinct retained assertion decisions required')
        return self

class ConsolidatedReadDeliveryV1(StrictRecord):
    protocol:Literal['consolidated-readonly-delivery-v1']
    workspace_id:UUID
    model_id:UUID
    version:int=Field(ge=1)
    model_content_hash:str=Field(pattern=HASH)
    source_refs:tuple[SourceRef,...]=Field(min_length=1,max_length=64)
    mode:Literal['current','historical']
    valid_at:AwareDatetime|None
    known_at:AwareDatetime|None
    retained_receipt:ProcessingProjectionReceiptBodyV3
    retained_signature:str=Field(pattern=HASH)
    retained_receipt_body_sha256:str=Field(pattern=HASH)
    retained_delivered_at:AwareDatetime
    retained_receipt_recorded_at:AwareDatetime
    business_decisions_as_of:tuple[AsOfDecisionObservationV1,...]=Field(max_length=128)
    checked_at:AwareDatetime
    valid_until:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact retained read version required')
        return value

    @model_validator(mode='after')
    def bound_proof_and_read_lease(self):
        r=self.retained_receipt
        if ((r.workspace_id,r.artifact_id,r.version,r.content_hash)!=(str(self.workspace_id),str(self.model_id),self.version,self.model_content_hash)
                or digest(r.model_dump(mode='json'))!=self.retained_receipt_body_sha256
                or len(set(self.source_refs))!=len(self.source_refs)
                or len({ref.source_id for ref in self.source_refs})!=len(self.source_refs)
                or any(ref.workspace_id!=self.workspace_id for ref in self.source_refs)
                or not self.checked_at<self.valid_until
                or self.retained_delivered_at>self.checked_at or self.retained_receipt_recorded_at>self.checked_at):
            raise ValueError('actual complete retained receipt and current read lease must agree')
        lease=datetime.fromisoformat(r.lease_until)
        if lease.tzinfo is None or lease.utcoffset() is None or self.retained_delivered_at>=lease:
            raise ValueError('retained original projection lease is unchanged and was valid at delivery')
        if (self.mode=='historical')!=(self.valid_at is not None and self.known_at is not None):
            raise ValueError('exact historical selectors required')
        if self.mode=='current' and (self.valid_at is not None or self.known_at is not None or self.business_decisions_as_of):
            raise ValueError('current decisions use separate current metadata only')
        if self.known_at is not None and (self.known_at>self.checked_at or any(d.recorded_at>self.known_at for d in self.business_decisions_as_of)):
            raise ValueError('decision observations must be known at the requested time')
        return self


def validate_direct_history_getter_acl_v1(connection,oid,*,required_login=None,deadline=None):
    """Validate this one getter's cumulative external LOGIN installs; no grants.

    Canonical fixtures normalize only these validated recipient identities. Actual
    consumers additionally require their own direct grant and actual SQL017 scope.
    """
    from .request_deadline_v1 import request_remaining_v1,sql_execute_v1
    request_remaining_v1(required=False)
    query="""SELECT coalesce(r.rolname,'PUBLIC'),x.is_grantable,r.rolcanlogin,
        r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,r.rolreplication,
        EXISTS(SELECT 1 FROM pg_catalog.pg_roles other WHERE other.oid<>r.oid
         AND (pg_catalog.pg_has_role(r.oid,other.oid,'MEMBER')
          OR pg_catalog.pg_has_role(r.oid,other.oid,'SET') OR pg_catalog.pg_has_role(r.oid,other.oid,'USAGE')))
        FROM pg_catalog.pg_proc p CROSS JOIN LATERAL pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) x
        LEFT JOIN pg_catalog.pg_roles r ON r.oid=x.grantee
        WHERE p.oid=%s AND x.privilege_type='EXECUTE' AND x.grantee<>p.proowner"""
    # Canonical installation inspection retains its existing raw connection;
    # serving consumers require the captured prearmed query window as well.
    rows=(connection.execute(query,(oid,)) if deadline is None else sql_execute_v1(connection,deadline,query,(oid,))).fetchall()
    request_remaining_v1(required=False)
    if (any(row[1:]!=(False,True,False,False,False,False,False,False) for row in rows)
            or required_login is not None and required_login not in {row[0] for row in rows}):
        raise PermissionError('only explicit direct unprivileged history LOGIN grants without grant option are permitted')
    return tuple(sorted(row[0] for row in rows))
