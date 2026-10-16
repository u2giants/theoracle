"""Pure private view/reading lineage checks; never creates reading authority.

Callers must separately authenticate the supplied current ReadingProvenance.
Hashes and successful structural validation are not reviewer appointment,
source access, renderer qualification or an assertion of semantic completeness.
"""
from dataclasses import asdict
import hashlib
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .binary_documents import NativeBinaryView,MAX_BLOCKS,MAX_ORIGINAL_BYTES
from .originals import ReadingProvenance,MAX_PDF_PAGES

HASH=r'^[0-9a-f]{64}$'
def seal(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

class _Record(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,strict=True)

class OriginalViewV1(_Record):
    view_id:str=Field(min_length=1,max_length=256)
    kind:Literal['page','slide','sheet','notes','supplement']
    anchor:str=Field(min_length=1,max_length=2048)
    image_sha256:str=Field(pattern=HASH)
    width:int=Field(strict=True,gt=0,le=20000)
    height:int=Field(strict=True,gt=0,le=20000)
    coordinate_basis:Literal['image-pixels-top-left-v1']='image-pixels-top-left-v1'
    covered_locators:tuple[str,...]=Field(min_length=1,max_length=MAX_BLOCKS)
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.covered_locators))!=len(self.covered_locators):raise ValueError('duplicate covered locator')
        return self

class OriginalViewManifestV1(_Record):
    schema_version:Literal[1]=1
    protocol:Literal['original-view-manifest-v1']='original-view-manifest-v1'
    original_sha256:str=Field(pattern=HASH)
    content_type:str=Field(min_length=1)
    byte_count:int=Field(strict=True,gt=0,le=MAX_ORIGINAL_BYTES)
    native_inventory_hash:str=Field(pattern=HASH)
    renderer_hash:str=Field(pattern=HASH)
    renderer_profile_hash:str=Field(pattern=HASH)
    renderer_binary_hash:str=Field(pattern=HASH)
    fonts_hash:str=Field(pattern=HASH)
    views:tuple[OriginalViewV1,...]=Field(min_length=1,max_length=MAX_PDF_PAGES)
    unread_locators:tuple[str,...]=()
    unsupported:tuple[str,...]=()
    @model_validator(mode='after')
    def identities(self):
        ids=[v.view_id for v in self.views]
        locators=[p for v in self.views for p in v.covered_locators]+list(self.unread_locators)
        if len(set(ids))!=len(ids) or len(set(locators))!=len(locators):raise ValueError('ambiguous view/inventory identity')
        return self

class QualifiedReadingLocatorV1(_Record):
    source_locator:str=Field(min_length=1,max_length=2048)
    view_id:str=Field(min_length=1,max_length=256)
    image_sha256:str=Field(pattern=HASH)
    region:tuple[int,int,int,int]
    start:int=Field(strict=True,ge=0)
    end:int=Field(strict=True,gt=0)
    quote:str=Field(min_length=1)
    quote_sha256:str=Field(pattern=HASH)
    basis:Literal['exact-native','independently-reviewed-visual']
    ambiguous:bool=Field(strict=True)
    review_receipt:str=Field(pattern=HASH)

class QualifiedReadingLocatorMapV1(_Record):
    schema_version:Literal[1]=1
    protocol:Literal['qualified-reading-character-locators-v1']='qualified-reading-character-locators-v1'
    original_sha256:str=Field(pattern=HASH)
    reading_sha256:str=Field(pattern=HASH)
    parser_identity:str=Field(pattern=HASH)
    review_receipt:str=Field(pattern=HASH)
    manifest_hash:str=Field(pattern=HASH)
    native_inventory_hash:str=Field(pattern=HASH)
    entries:tuple[QualifiedReadingLocatorV1,...]=Field(min_length=1,max_length=MAX_BLOCKS)

def validate_original_view_lineage(native:NativeBinaryView,manifest:OriginalViewManifestV1,
                                   mapping:QualifiedReadingLocatorMapV1,*,original:bytes,
                                   reading:str,current_provenance:ReadingProvenance)->None:
    """Refuse unaccounted/unsupported/ambiguous citations; grants nothing.

    Offsets address Python Unicode characters of the CURRENT qualified reading,
    never original bytes or the native parser's different normalized reading.
    """
    if type(native) is not NativeBinaryView or type(manifest) is not OriginalViewManifestV1 or type(mapping) is not QualifiedReadingLocatorMapV1:
        raise ValueError('exact versioned view lineage records required')
    if type(original) is not bytes or type(reading) is not str or type(current_provenance) is not ReadingProvenance:
        raise ValueError('exact original/current independently qualified reading required')
    # Frozen models can still be produced by unchecked model_copy updates.
    manifest=OriginalViewManifestV1.model_validate_json(manifest.model_dump_json())
    mapping=QualifiedReadingLocatorMapV1.model_validate_json(mapping.model_dump_json())
    original_hash=hashlib.sha256(original).hexdigest();reading_hash=hashlib.sha256(reading.encode()).hexdigest()
    inventory_hash=seal(asdict(native));p=current_provenance
    if (manifest.original_sha256!=original_hash or native.original_sha256!=original_hash
        or manifest.byte_count!=len(original) or manifest.content_type!=native.content_type
        or manifest.native_inventory_hash!=inventory_hash or mapping.native_inventory_hash!=inventory_hash
        or mapping.manifest_hash!=seal(manifest.model_dump(mode='json'))
        or (mapping.original_sha256,mapping.reading_sha256,mapping.parser_identity,mapping.review_receipt)
           !=(p.original_hash,p.content_hash,p.parser_identity,p.review_receipt)
        or (p.original_hash,p.content_hash,p.content_type)!=(original_hash,reading_hash,native.content_type)
        or p.evidence_kind!='visual_transcription' or p.page_count!=len(manifest.views)):
        raise ValueError('original/current reading/review/view lineage differs')
    locators=[b.locator for b in native.blocks]
    covered=[loc for view in manifest.views for loc in view.covered_locators]
    if len(set(locators))!=len(locators) or set(covered+list(manifest.unread_locators))!=set(locators):
        raise ValueError('every exact native inventory locator must be accounted for')
    if manifest.unread_locators or manifest.unsupported:raise ValueError('unread or unsupported original regions refuse qualification linkage')
    entries=mapping.entries
    if len(entries)!=len(locators) or {e.source_locator for e in entries}!=set(locators):
        raise ValueError('missing/duplicate/extra reading locator')
    views={v.view_id:v for v in manifest.views};blocks={b.locator:b for b in native.blocks}
    previous_end=-1
    for e in entries:
        view=views.get(e.view_id)
        if (view is None or e.source_locator not in view.covered_locators or e.image_sha256!=view.image_sha256
            or e.ambiguous or e.review_receipt!=p.review_receipt or e.start<previous_end
            or e.end<=e.start or e.end>len(reading) or reading[e.start:e.end]!=e.quote
            or hashlib.sha256(e.quote.encode()).hexdigest()!=e.quote_sha256):
            raise ValueError('ambiguous/overlapping or inexact qualified reading citation')
        x,y,w,h=e.region
        if any(type(v) is not int for v in e.region) or min(x,y)<0 or min(w,h)<=0 or x+w>view.width or y+h>view.height:
            raise ValueError('citation region outside exact original view')
        if e.basis=='exact-native' and e.quote!=blocks[e.source_locator].text:
            raise ValueError('native mapping cannot invent normalized precision')
        previous_end=e.end
