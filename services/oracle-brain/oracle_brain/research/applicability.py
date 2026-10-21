"""Exact descriptive industry-reference comparisons, never legal/policy authority.

No fetch, scheduler, source qualification, permission or current-version proof
is created here. A caller supplies independently obtained current metadata.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, field_validator, model_validator
from ..operating_model.contracts import StrictRecord,digest
from .registry import Source

TOKEN=r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$'
HEX=r'^[0-9a-f]{64}$'
MAX_REFERENCES=256


class DecisionContext(StrictRecord):
    jurisdiction: str|None=Field(default=None,pattern=TOKEN)
    product_scope: str|None=Field(default=None,pattern=TOKEN)
    channel_scope: str|None=Field(default=None,pattern=TOKEN)
    required_review_after: AwareDatetime|None=None


class ExternalReference(StrictRecord):
    reference_id: str=Field(pattern=TOKEN)
    source_id: str=Field(pattern=TOKEN)
    source_version: str|None=Field(default=None,pattern=TOKEN)
    content_sha256: str|None=Field(default=None,pattern=HEX)
    original_url: str|None=Field(default=None,min_length=1,max_length=2048)
    publisher: str|None=Field(default=None,min_length=1,max_length=200)
    jurisdiction: str|None=Field(default=None,pattern=TOKEN)
    product_scope: str|None=Field(default=None,pattern=TOKEN)
    channel_scope: str|None=Field(default=None,pattern=TOKEN)
    license_permission: str|None=Field(default=None,min_length=1,max_length=500)
    publication_date: date|None=None
    effective_date: date|None=None
    retrieved_at: AwareDatetime|None=None
    reviewed_at: AwareDatetime|None=None
    refresh_due: AwareDatetime|None=None
    review_due: AwareDatetime|None=None
    withdrawn: bool=False

    @field_validator('publisher','license_permission')
    @classmethod
    def nonblank(cls,value):
        if value is not None and not value.strip():raise ValueError('metadata cannot be blank')
        return value

    @field_validator('original_url')
    @classmethod
    def descriptive_https(cls,value):
        if value is None:return value
        try:
            parts=urlsplit(value)
            valid=(parts.scheme=='https' and parts.hostname and not parts.username
                and not parts.password and parts.port in (None,443))
        except ValueError:valid=False
        if not valid or any(ord(c)<=32 or ord(c)==127 for c in value):
            raise ValueError('uncredentialed HTTPS reference metadata required')
        return value

    @model_validator(mode='after')
    def date_order(self):
        if self.retrieved_at is not None and self.reviewed_at is not None and self.reviewed_at<self.retrieved_at:
            raise ValueError('review precedes retrieval')
        for due in (self.refresh_due,self.review_due):
            if due is not None and self.reviewed_at is not None and due<=self.reviewed_at:
                raise ValueError('due date must follow observed review')
        return self


class CurrentReference(StrictRecord):
    reference_id: str=Field(pattern=TOKEN)
    source_id: str=Field(pattern=TOKEN)
    source_version: str=Field(pattern=TOKEN)
    content_sha256: str=Field(pattern=HEX)
    withdrawn: bool=False


class Applicability(StrictRecord):
    reference_id: str=Field(pattern=TOKEN)
    reference_digest: str=Field(pattern=HEX)
    state: Literal['APPLICABLE','INAPPLICABLE','UNKNOWN']
    reasons: tuple[str,...]=Field(min_length=1,max_length=32)
    comparison_only: Literal[True]=True
    company_policy: Literal[False]=False
    source_qualified: Literal[False]=False
    legal_ruling: Literal[False]=False
    fetch_authorized: Literal[False]=False
    serving_authorized: Literal[False]=False


def _unknown(value):
    return value is None or (type(value) is str and value.lower() in {'unknown','global','all'})


def _source(source):
    if type(source) is not Source:raise TypeError('exact registered source required')
    Source(**asdict(source))
    # Older registered Source objects predate stricter booleans. Do not let
    # their truthy integers grant even descriptive comparison eligibility.
    if type(source.enabled) is not bool or type(source.rights_confirmed) is not bool:
        raise ValueError('registered source access flags must be actual booleans')


def assess_applicability(context:DecisionContext,reference:ExternalReference,*,
                         source:Source,current:CurrentReference|None,now:datetime)->Applicability:
    if type(context) is not DecisionContext or type(reference) is not ExternalReference or type(source) is not Source:
        raise TypeError('exact decision/reference/source metadata required')
    DecisionContext.model_validate(context.model_dump(mode='python'))
    ExternalReference.model_validate(reference.model_dump(mode='python'))
    _source(source)  # reuse registered identity; never issue rights
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('timezone-aware observed clock required')
    if current is not None:
        if type(current) is not CurrentReference:raise TypeError('exact current reference metadata required')
        CurrentReference.model_validate(current.model_dump(mode='python'))
    for observed in (reference.retrieved_at,reference.reviewed_at,context.required_review_after):
        if observed is not None and observed>now:raise ValueError('future observation or decision-review fence')
    def result(state,*reasons):
        return Applicability(reference_id=reference.reference_id,
            reference_digest=digest(reference.model_dump(mode='json')),state=state,reasons=tuple(reasons))
    if reference.source_id!=source.source_id:return result('INAPPLICABLE','foreign_source_identity')
    if current is not None and (current.reference_id!=reference.reference_id or current.source_id!=reference.source_id):
        return result('INAPPLICABLE','foreign_current_reference_identity')
    if reference.withdrawn or (current is not None and current.withdrawn):return result('INAPPLICABLE','withdrawn')
    if not source.enabled:return result('INAPPLICABLE','disabled_source')
    if current is not None and ((not _unknown(reference.source_version) and not _unknown(current.source_version)
            and reference.source_version!=current.source_version)
            or (reference.content_sha256 is not None and reference.content_sha256!=current.content_sha256)):
        return result('INAPPLICABLE','current_version_or_content_differs')
    if reference.original_url is not None and reference.original_url!=source.url:
        return result('INAPPLICABLE','registered_original_url_differs')
    if reference.publisher is not None and reference.publisher!=source.publisher:
        return result('INAPPLICABLE','registered_publisher_differs')
    for name in ('jurisdiction','product_scope','channel_scope'):
        wanted,actual=getattr(context,name),getattr(reference,name)
        if not _unknown(wanted) and not _unknown(actual) and wanted!=actual:
            return result('INAPPLICABLE',name+'_mismatch')
    if reference.publication_date is not None and reference.publication_date>now.date():
        return result('INAPPLICABLE','not_yet_published')
    if reference.effective_date is not None and reference.effective_date>now.date():
        return result('INAPPLICABLE','not_yet_effective')
    if (reference.publication_date is not None and reference.retrieved_at is not None
            and reference.retrieved_at.date()<reference.publication_date):
        raise ValueError('published reference retrieval precedes publication')
    if reference.review_due is not None and reference.review_due<=now:
        return result('INAPPLICABLE','expired_review')
    if reference.refresh_due is not None and reference.refresh_due<=now:
        return result('INAPPLICABLE','expired_refresh')
    missing=[]
    if current is None or _unknown(current.source_version):missing.append('current_source_revision_unknown')
    for name in ('source_version','content_sha256','original_url','publisher','license_permission',
                 'publication_date','effective_date','retrieved_at','reviewed_at','refresh_due','review_due'):
        if _unknown(getattr(reference,name)):missing.append(name+'_unknown')
    for name in ('jurisdiction','product_scope','channel_scope'):
        if _unknown(getattr(context,name)) or _unknown(getattr(reference,name)):missing.append(name+'_unknown')
    if not source.authorized:missing.append('rights_gap')
    if missing:return result('UNKNOWN',*missing)
    if context.required_review_after is not None and (reference.reviewed_at<context.required_review_after
            or reference.retrieved_at<context.required_review_after):
        return result('INAPPLICABLE','sensitive_decision_requires_newer_review')
    return result('APPLICABLE','explicit_scopes_current_metadata_match')


def assess_references(context:DecisionContext,references:tuple[ExternalReference,...],*,
                      sources:tuple[Source,...],current:tuple[CurrentReference,...],now:datetime)->tuple[Applicability,...]:
    if any(type(value) is not tuple or len(value)>MAX_REFERENCES for value in (references,sources,current)):
        raise ValueError('bounded immutable reference populations required')
    source_map={};current_map={};reference_ids=set()
    for source in sources:
        if type(source) is not Source:raise TypeError('exact registered source required')
        _source(source)
        if source.source_id in source_map:raise ValueError('duplicate registered source identity')
        source_map[source.source_id]=source
    for item in current:
        if type(item) is not CurrentReference:raise TypeError('exact current reference required')
        CurrentReference.model_validate(item.model_dump(mode='python'))
        if item.reference_id in current_map:raise ValueError('duplicate current reference identity')
        current_map[item.reference_id]=item
    for reference in references:
        if type(reference) is not ExternalReference:raise TypeError('exact external reference required')
        if reference.reference_id in reference_ids:raise ValueError('duplicate external reference identity')
        reference_ids.add(reference.reference_id)
        if reference.source_id not in source_map:raise ValueError('external reference has no registered source')
    return tuple(assess_applicability(context,reference,source=source_map[reference.source_id],
        current=current_map.get(reference.reference_id),now=now) for reference in references)
