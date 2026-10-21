"""Actual independently appointed native UTF8 original phases through SQL014.

These distinct source-pinned byte programs qualify exact original text ONLY.
They do not perform model-semantic review or confer business acceptance. No
provider/Budget purpose, paid reader/reviewer appointment or SourceRef supplied
by an API caller is reused. SQL014 remains the sole qualification owner.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import hashlib,os,stat,json
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.original_qualification_v1 import (
 RawOriginalPopulationV1,NativeUTF8ReadingCommitV1,NativeUTF8ReviewCommitV1,parse_original_response_commit_v1)
from oracle_brain.operating_model.original_source_authority_v1 import OriginalSourceBindingV1,OriginalSourceResolverV1
from oracle_brain.operating_model.artifact_storage import FileBlobStore,OriginalObjectRefV1,ReservationOriginalObjectRefV1
from oracle_brain.interviews import utf8_reader_v1,utf8_reviewer_v1
from .original_intake_v1 import ProtectedInputV1,_pinned,_parse
from .purpose_journey_v2 import _worker_file

HASH=r'^[a-f0-9]{64}$'
def program_identity_v1(phase):
    module=utf8_reader_v1 if phase=='source-original-reading' else utf8_reviewer_v1
    return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
def parser_identity_v1():
    return digest(dict(purpose='native-utf8-byte-roundtrip-only-v1',reader_program_sha256=program_identity_v1('source-original-reading'),reviewer_program_sha256=program_identity_v1('source-original-review')))

class _ConversationRecordV1(StrictRecord):
    @field_validator('schema_version',mode='before',check_fields=False)
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact integer conversation version required')
        return value

class ConversationOriginalConfigV1(_ConversationRecordV1):
    schema_version:Literal[1]
    purpose:Literal['conversation-native-utf8-original-v1']
    phase:Literal['source-original-reading','source-original-review']
    principal_id:UUID;expected_session_role:str;expected_owner_role:str
    population:RawOriginalPopulationV1
    original_allocation_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime;expires_at:AwareDatetime
    database_url:ProtectedInputV1;database_ca:ProtectedInputV1
    program_sha256:str=Field(pattern=HASH)
    storage_root:str;storage_device:int=Field(ge=0);storage_inode:int=Field(gt=0);storage_uid:int=Field(ge=0)
    storage_profile_hash:str=Field(pattern=HASH)
    reading_commit_sha256:str|None=Field(default=None,pattern=HASH)
    @model_validator(mode='after')
    def exact_phase(self):
        if (len(self.population.raw_refs)!=1 or self.population.raw_refs[0].media_type!='text/plain'
            or self.expected_owner_role==self.expected_session_role
            or not self.expires_at<=self.population.expires_at<=self.original_horizon
            or (self.phase=='source-original-review')!=(self.reading_commit_sha256 is not None)):
            raise ValueError('single exact text original and independently appointed finite phase required')
        return self

class ConversationOriginalAppointmentV1(_ConversationRecordV1):
    schema_version:Literal[1]
    purpose:Literal['conversation-native-utf8-original-v1']
    config_sha256:str=Field(pattern=HASH)
    phase:Literal['source-original-reading','source-original-review']
    principal_id:UUID;population_id:UUID
    program_sha256:str=Field(pattern=HASH)
    issuer_actor:UUID;reviewer_actor:UUID
    valid_from:AwareDatetime;expires_at:AwareDatetime;original_horizon:AwareDatetime
    @model_validator(mode='after')
    def finite_independent(self):
        if len({self.principal_id,self.issuer_actor,self.reviewer_actor})!=3 or not self.valid_from<self.expires_at<=self.original_horizon:raise ValueError('independent finite native byte appointment required')
        return self

@dataclass(frozen=True)
class ConversationOriginalSettingsV1:
    config:ConversationOriginalConfigV1;appointment:ConversationOriginalAppointmentV1
    config_path:Path;config_sha256:str;appointment_path:Path;appointment_sha256:str
    expected_issuer_actor:UUID;expected_reviewer_actor:UUID
    def current(self):
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1(required=False)
        c=_parse(ConversationOriginalConfigV1,_pinned(self.config_path,self.config_sha256));a=_parse(ConversationOriginalAppointmentV1,_pinned(self.appointment_path,self.appointment_sha256))
        if c!=self.config or a!=self.appointment or a.config_sha256!=self.config_sha256 or a.issuer_actor!=self.expected_issuer_actor or a.reviewer_actor!=self.expected_reviewer_actor:
            raise PermissionError('native original protected appointment changed')
        if (a.phase,a.principal_id,a.population_id,a.program_sha256,a.original_horizon)!=(c.phase,c.principal_id,c.population.population_id,c.program_sha256,c.original_horizon) or c.program_sha256!=program_identity_v1(c.phase):raise PermissionError('actual native original program differs')
        until=min(c.expires_at,a.expires_at,c.original_horizon,a.original_horizon,c.population.expires_at)
        if not a.valid_from<=datetime.now(timezone.utc)<until:raise PermissionError('native byte phase expired')
        _pinned(c.database_ca.path,c.database_ca.sha256,131072)
        raw=_pinned(c.database_url.path,c.database_url.sha256,16384).decode('utf-8')
        from psycopg.conninfo import conninfo_to_dict
        p=conninfo_to_dict(raw)
        if set(p)-{'host','hostaddr','port','dbname','user','password','sslmode','sslrootcert','connect_timeout'} or p.get('sslmode')!='verify-full' or p.get('sslrootcert')!=c.database_ca.path or p.get('user')!=c.expected_session_role:raise PermissionError('actual native original TLS pin differs')
        root=Path(c.storage_root)
        if not root.is_absolute() or root.resolve()!=root:raise PermissionError('fixed original custody root required')
        st=root.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_mode&0o077 or (st.st_dev,st.st_ino,st.st_uid)!=(c.storage_device,c.storage_inode,c.storage_uid) or st.st_uid!=os.getuid():raise PermissionError('actual original custody root differs')
        request_remaining_v1(required=False)
        return raw,until
    def resolver(self):
        raw,_=self.current();c=self.config
        return OriginalSourceResolverV1(raw,binding=OriginalSourceBindingV1(population=c.population,principal=c.principal_id,purpose=c.phase,
            expected_owner_role=c.expected_owner_role,expected_session_role=c.expected_session_role,
            original_allocation_hash=c.original_allocation_hash,original_horizon=c.original_horizon,expires_at=c.expires_at))

def load_conversation_original_settings_v1(config_path,config_sha256,appointment_path,appointment_sha256,issuer_actor,reviewer_actor):
    s=ConversationOriginalSettingsV1(_parse(ConversationOriginalConfigV1,_pinned(config_path,config_sha256)),
        _parse(ConversationOriginalAppointmentV1,_pinned(appointment_path,appointment_sha256)),Path(config_path),config_sha256,
        Path(appointment_path),appointment_sha256,issuer_actor,reviewer_actor)
    s.current();return s

class NativeConversationOriginalFactoryV1:
    def __init__(self,settings):
        if type(settings) is not ConversationOriginalSettingsV1:raise TypeError('separately protected native original phase required')
        settings.current();self.settings=settings
    def execute_v1(self):
        from ._protected_control_listener_v1 import request_remaining_v1
        request_remaining_v1()
        s=self.settings;c=s.config;_,deadline=s.current();resolver=s.resolver();ref=c.population.raw_refs[0]
        actual_program=resolver.original_native_program_identity_v1()
        expected_program=('oracle/native-utf8-reader-v1:' if c.phase=='source-original-reading' else 'oracle/native-utf8-reviewer-v1:')+c.program_sha256
        if actual_program.model_id!=expected_program:raise PermissionError('actual independently installed native program label differs')
        capability=resolver.original_revision_access_v1(ref.source_id,ref.revision)
        reservation=UUID(capability['private_object_key'].split('/')[-1])
        original=OriginalObjectRefV1(ref.workspace_id,ref.source_id,ref.revision,ref.original_sha256,ref.byte_count,'text/plain',c.storage_profile_hash)
        located=ReservationOriginalObjectRefV1(original,reservation)
        if located.key!=capability['private_object_key']:raise PermissionError('actual original locator differs')
        store=FileBlobStore._from_provisioned_original_root(Path(c.storage_root),(c.storage_device,c.storage_inode,c.storage_uid))
        request_remaining_v1()
        observation=_worker_file(store.root/'intake-observations'/str(reservation)/'custody.json')
        request_remaining_v1()
        expected=dict(schema_version=1,purpose='original-intake-byte-custody-v1',reservation_id=str(reservation),source_id=str(ref.source_id),workspace_id=str(ref.workspace_id),revision=ref.revision,private_object_key=located.key,original_sha256=ref.original_sha256,byte_count=ref.byte_count,storage_profile_hash=c.storage_profile_hash)
        if canonical_bytes(expected)!=observation or hashlib.sha256(observation).hexdigest()!=ref.custody_locator_seal_sha256:raise PermissionError('actual native original custody observation differs')
        request_remaining_v1()
        data=store._read_original_bytes(located)
        request_remaining_v1()
        s.current();resolver.original_population_current_v1(c.population.population_id)
        resolver.original_revision_access_v1(ref.source_id,ref.revision)
        if datetime.now(timezone.utc)>=min(deadline,datetime.fromisoformat(capability['valid_until'])):raise PermissionError('original read horizon elapsed')
        text=utf8_reader_v1.read_exact_utf8_v1(data)
        body=dict(schema_version=1,purpose='native-utf8-original-reading-body-v1',original_sha256=ref.original_sha256,reading_text=text,
            parser_id=parser_identity_v1(),byte_count=len(data),semantic_acceptance=False)
        reading_hash=digest(body)
        physical=dict(media_type='text/plain',original_sha256=ref.original_sha256,byte_count=len(data),view_count=1)
        pins=dict(raw_ref=ref,population_id=c.population.population_id,operation_registry_hash=c.population.operation_registry_hash,
            original_root_hash=c.population.original_root_hash,allocation_hash=c.original_allocation_hash,population_hash=c.population.population_digest,
            source_registry_hash=c.population.source_registry_hash,context_hash=digest(dict(physical=physical,principal_id=str(c.principal_id),program_sha256=c.program_sha256)),
            view_manifest_hash=digest(physical),locator_map_hash=digest(dict(start_utf8=0,end_utf8=len(data),original_sha256=ref.original_sha256)),
            reading_sha256=ref.original_sha256,parser_id=parser_identity_v1(),committed_at=datetime.now(timezone.utc),original_horizon=c.original_horizon,reading_body_hash=reading_hash)
        if c.phase=='source-original-reading':
            commit=NativeUTF8ReadingCommitV1(**pins);s.current()
            if resolver.original_native_program_identity_v1().model_id!=expected_program:raise PermissionError('native reader program drift')
            return resolver.commit_original_reading_response_v1(canonical_bytes(commit.model_dump(mode='json')))
        # This phase has its own SQL identity/population/appointment and program.
        retained=resolver.original_review_reading_input_v1(c.reading_commit_sha256)
        reader=parse_original_response_commit_v1(bytes.fromhex(retained.reading_commit_canonical_utf8_hex),phase='reading')
        if (retained.reader_model_id!='oracle/native-utf8-reader-v1:'+program_identity_v1('source-original-reading') or reader.transport!='native-utf8-byte-roundtrip-v1' or reader.raw_ref!=ref or reader.reading_body_hash!=reading_hash
            or reader.view_manifest_hash!=pins['view_manifest_hash'] or reader.locator_map_hash!=pins['locator_map_hash']
            or reader.parser_id!=pins['parser_id']):raise PermissionError('retained actual reader did not inspect this exact original')
        utf8_reviewer_v1.review_exact_utf8_v1(data,text)
        pins['review_body_hash']=digest(dict(reading_body_hash=reading_hash,reviewer_program_sha256=c.program_sha256,
            exact_original_utf8_roundtrip=True,semantic_acceptance=False))
        commit=NativeUTF8ReviewCommitV1(**pins,reading_commit_hash=retained.reading_commit_sha256,
            reading_population_id=retained.reader_population_id,reading_operation_registry_hash=retained.reader_operation_registry_hash,qualification_pass=True)
        s.current();review=resolver.commit_original_review_response_v1(canonical_bytes(commit.model_dump(mode='json')))
        s.current()
        if resolver.original_native_program_identity_v1().model_id!=expected_program:raise PermissionError('native reviewer program drift')
        return resolver.finalize_original_reading_qualification_v1(retained,review,text)
