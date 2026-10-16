"""Explicit purpose-worker protocol; no issuer, provider keys or legacy view job.

Phase jobs keep one original allocation/horizon. Durable metadata progress never
creates a future phase context or authorizes another paid attempt. Protected
runtime factories (not model/HTTP fields) supply all source/custody authority.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import stat
import time
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from .contracts import StrictRecord, SourceRef, canonical_bytes, digest
from .purpose_context import source_population_digest
from oracle_brain.hosting.custody import _durable_nonce, _sync_spool

HASH = r'^[0-9a-f]{64}$'
PHASES = ('census', 'extraction', 'assembly', 'assessment', 'compile')


def _require(value, message):
    if not value:
        raise PermissionError(message)


def _unique(pairs):
    result={}
    for key,value in pairs:
        _require(key not in result, 'duplicate purpose custody field')
        result[key]=value
    return result


class PurposeWorkerJobV2(StrictRecord):
    schema_version: Literal[2] = 2
    purpose: Literal['replacement-documentary-journey-v2'] = 'replacement-documentary-journey-v2'
    job_id: UUID
    journey_id: UUID
    workspace_id: UUID
    actor_id: UUID
    phase: Literal['census', 'extraction', 'assembly', 'assessment', 'compile']
    source_refs: tuple[SourceRef, ...]
    source_id: UUID | None = None
    allocation_hash: str = Field(pattern=HASH)
    parent_journal_hash: str | None = Field(default=None, pattern=HASH)
    prior_receipt_hash: str | None = Field(default=None, pattern=HASH)
    nonce: str = Field(pattern=r'^[0-9a-f]{32}$')
    runtime_hash: str = Field(pattern=HASH)
    admission_hash: str = Field(pattern=HASH)
    dispatch_id: UUID | None = None
    request_hash: str | None = Field(default=None, pattern=HASH)
    phase_registry_sha256: str | None = Field(default=None, pattern=HASH)
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def exact_population_and_phase(self):
        _require(3 <= len(self.source_refs) <= 4096
                 and len({r.source_id for r in self.source_refs}) == len(self.source_refs)
                 and all(r.workspace_id == self.workspace_id for r in self.source_refs),
                 'complete distinct three-plus original population required')
        _require(self.expires_at <= self.original_horizon, 'phase cannot extend original allocation horizon')
        _require((self.phase == 'extraction') == (self.source_id is not None)
                 and (self.source_id is None or self.source_id in {r.source_id for r in self.source_refs}),
                 'exact extraction source key required')
        _require((self.phase == 'census') == (self.parent_journal_hash is None and self.prior_receipt_hash is None),
                 'only initial census has no predecessor')
        if self.phase != 'census':
            _require(self.parent_journal_hash is not None and self.prior_receipt_hash is not None,
                     'exact already committed predecessor required')
        provider_fields = (self.dispatch_id, self.request_hash, self.phase_registry_sha256)
        _require(all(v is None for v in provider_fields) if self.phase == 'compile'
                 else all(v is not None for v in provider_fields), 'fixed phase dispatch metadata required')
        return self

    @property
    def phase_key(self):
        return self.phase + (':' + str(self.source_id) if self.source_id else '')


class PurposeJourneyJournalV2:
    """Existing custody lock/fsync primitives, metadata only; NO network under lock."""
    def __init__(self, spool, *, lock_seconds=2):
        self.spool = Path(spool)
        _require(self.spool.is_absolute() and self.spool.resolve() == self.spool
                 and self.spool.is_dir() and self.spool.stat().st_uid == os.getuid()
                 and self.spool.stat().st_mode & 0o077 == 0, 'private canonical owned phase spool required')
        _require(type(lock_seconds) in (int, float) and 0 < lock_seconds <= 5, 'bounded phase lock required')
        self.lock_seconds = lock_seconds

    @contextmanager
    def _locked(self):
        _require(self.spool.resolve()==self.spool and self.spool.stat().st_uid==os.getuid()
                 and self.spool.stat().st_mode & 0o077==0, 'phase spool changed')
        path = self.spool / '.custody-lock'
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                     and info.st_mode & 0o077 == 0, 'unsafe phase custody lock')
            deadline = time.monotonic() + self.lock_seconds
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    _require(time.monotonic() < deadline, 'phase custody lock busy')
                    time.sleep(0.01)
            yield
        finally:
            os.close(fd)

    def _path(self, journey):
        _require(type(journey) is UUID, 'canonical journey identity required')
        return self.spool / (str(journey) + '.journal-v2.jsonl')

    def read(self, journey):
        path = self._path(journey)
        if not path.exists() and not path.is_symlink():
            return []
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            before = os.fstat(stream.fileno())
            _require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1
                     and before.st_mode & 0o077 == 0 and before.st_size <= 16 * 1024**2, 'unsafe phase journal')
            raw = stream.read(16 * 1024**2 + 1)
            identity = lambda v: (v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
            _require(identity(before) == identity(os.fstat(stream.fileno())) == identity(path.lstat()),
                     'phase journal changed during read')
        _require(not raw or raw.endswith(b'\n'), 'incomplete journal append retained; no retry')
        rows=[]; previous=None
        for line in raw.splitlines():
            try: row=json.loads(line,object_pairs_hook=_unique,
                parse_constant=lambda _: _require(False,'nonfinite phase journal'))
            except (ValueError, UnicodeDecodeError) as error: raise PermissionError('corrupt phase journal') from error
            _require(type(row) is dict and type(row.get('schema_version')) is int and row.get('schema_version') == 2
                     and row.get('journey_id') == str(journey) and row.get('previous_hash') == previous
                     and type(row.get('revision')) is int and row.get('revision') == len(rows)+1
                     and row.get('state') in {'attempt-started','awaiting-external-phase-admission','qualified-model-outbox-committed'}
                     and row.get('phase') in PHASES, 'phase journal fork or schema drift')
            core={k:v for k,v in row.items() if k!='journal_hash'}
            _require(row.get('journal_hash') == digest(core), 'phase journal seal differs')
            previous=row['journal_hash']; rows.append(row)
        return rows

    def _append(self, job, rows, state, now, **extra):
        record={'schema_version':2,'journey_id':str(job.journey_id),'revision':len(rows)+1,
            'previous_hash':rows[-1]['journal_hash'] if rows else None,'state':state,'phase':job.phase,
            'phase_key':job.phase_key,'job_id':str(job.job_id),'job_hash':digest(job.model_dump(mode='json')),
            'workspace_id':str(job.workspace_id),'actor_id':str(job.actor_id),'runtime_hash':job.runtime_hash,
            'population_hash':source_population_digest(job.source_refs),'allocation_hash':job.allocation_hash,
            'original_horizon':job.original_horizon.isoformat(),'at':now.isoformat(),**extra}
        if not rows:record['source_ids']=[str(r.source_id) for r in job.source_refs]
        record['journal_hash']=digest(record)
        path=self._path(job.journey_id)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
        try:
            info=os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
                     and info.st_mode & 0o077==0, 'unsafe phase journal append')
            data=canonical_bytes(record)+b'\n'
            _require(os.write(fd,data)==len(data), 'partial phase journal append retained')
            os.fsync(fd)
        finally:os.close(fd)
        _sync_spool(self.spool)
        return record

    @staticmethod
    def _current(job, now):
        _require(type(job) is PurposeWorkerJobV2 and type(now) is datetime and now.tzinfo is not None
                 and now < job.expires_at <= job.original_horizon, 'phase job expired or unqualified')

    @staticmethod
    def _root(job, rows):
        root=rows[0]
        _require(all(root[k]==v for k,v in {'workspace_id':str(job.workspace_id),'actor_id':str(job.actor_id),
            'runtime_hash':job.runtime_hash,'population_hash':source_population_digest(job.source_refs),
            'allocation_hash':job.allocation_hash,'original_horizon':job.original_horizon.isoformat()}.items()),
            'phase cannot replace original source population, actor, allocation or horizon')

    def claim(self, job, *, now):
        self._current(job,now)
        with self._locked():
            rows=self.read(job.journey_id)
            if not rows:
                _require(job.phase=='census', 'initial independently admitted census required')
            else:
                self._root(job,rows)
                _require(not any(r['phase_key']==job.phase_key for r in rows), 'phase/source attempt already spent')
                committed=[r for r in rows if r['state']=='awaiting-external-phase-admission']
                if job.phase=='extraction':
                    barrier=next((r for r in committed if r['phase']=='census'),None)
                    _require(barrier and job.parent_journal_hash==barrier['journal_hash']
                             and job.prior_receipt_hash==barrier['receipt_hash'], 'authenticated census barrier required')
                    _require(not any(r['phase'] in ('assembly','assessment','compile') for r in rows),
                             'extraction after assembly cannot be admitted')
                else:
                    _require(job.parent_journal_hash==rows[-1]['journal_hash']
                             and job.prior_receipt_hash==rows[-1].get('receipt_hash'), 'stale phase predecessor/fork')
                    if job.phase=='assembly':
                        actual={r['phase_key'].split(':',1)[1] for r in committed if r['phase']=='extraction'}
                        _require(actual==set(rows[0]['source_ids']), 'assembly requires ALL exact original extractions')
                    else:
                        previous={'assessment':'assembly','compile':'assessment'}.get(job.phase)
                        _require(previous and rows[-1]['phase']==previous
                                 and rows[-1]['state']=='awaiting-external-phase-admission', 'fixed committed phase order required')
            # The retained exclusive nonce primitive precedes claim persistence.
            phase_marker=hashlib.sha256((str(job.journey_id)+'/'+job.phase_key).encode()).hexdigest()
            _durable_nonce(self.spool,'purpose-v2-phase-'+phase_marker,
                canonical_bytes({'job_hash':digest(job.model_dump(mode='json'))}))
            _durable_nonce(self.spool,'purpose-v2-nonce-'+job.nonce,canonical_bytes({'job_hash':digest(job.model_dump(mode='json'))}))
            return self._append(job,rows,'attempt-started',now)

    def commit(self, job, *, receipt_hash, native_receipt_hash, now):
        self._current(job,now)
        _require(all(type(v) is str and re.fullmatch(HASH,v) for v in (receipt_hash,native_receipt_hash)),
                 'actual phase/native custody seals required')
        with self._locked():
            rows=self.read(job.journey_id);_require(rows, 'phase was not claimed');self._root(job,rows)
            phase=[r for r in rows if r['phase_key']==job.phase_key]
            _require(len(phase)==1 and phase[0]['state']=='attempt-started'
                     and phase[0]['job_hash']==digest(job.model_dump(mode='json')), 'same immutable claimed phase required')
            return self._append(job,rows,'qualified-model-outbox-committed' if job.phase=='compile'
                else 'awaiting-external-phase-admission',now,receipt_hash=receipt_hash,native_receipt_hash=native_receipt_hash)


class CompilerPhaseClientConfigV2(StrictRecord):
    hostname: str
    port: int = Field(strict=True,ge=1,le=65535)
    server_uri: str
    client_uri: str
    ca_file: str
    certificate_file: str
    key_file: str


class CompilerWorkerConfigV2(StrictRecord):
    schema_version: Literal[2]=2
    role: Literal['compiler-worker']='compiler-worker'
    purpose: Literal['replacement-documentary-journey-v2']='replacement-documentary-journey-v2'
    workspace_id: UUID
    actor_id: UUID
    worker_uri: str=Field(pattern=r'^spiffe://oracle/[A-Za-z0-9._/-]+$')
    runtime_hash: str=Field(pattern=HASH)
    source_registry_hash: str=Field(pattern=HASH)
    expected_owner_role: str=Field(pattern=r'^[a-z_][a-z0-9_]{0,62}$')
    expected_session_role: str=Field(pattern=r'^[a-z_][a-z0-9_]{0,62}$')
    source_expires_at: AwareDatetime
    database_url_file: str
    jobs_registry_file: str
    jobs_registry_sha256: str=Field(pattern=HASH)
    worker_issuer_actor: UUID
    worker_reviewer_actor: UUID
    population_file: str
    population_sha256: str=Field(pattern=HASH)
    allocation_projection_file: str
    allocation_projection_sha256: str=Field(pattern=HASH)
    custody_appointment_file: str
    custody_appointment_sha256: str=Field(pattern=HASH)
    custody_issuer_actor: UUID
    custody_reviewer_actor: UUID
    parent_observer_admission_file: str
    parent_observer_admission_hash: str=Field(pattern=HASH)
    observer_client: CompilerPhaseClientConfigV2
    observer_spool: str
    observer_namespace: str
    observer_initialization_hash: str=Field(pattern=HASH)
    clients: dict[Literal['census','extraction','assembly','assessment'],CompilerPhaseClientConfigV2]
    spool: str
    blob_root: str
    semantic_registry_file: str
    semantic_registry_sha256: str=Field(pattern=HASH)
    semantic_issuer_actor: UUID
    semantic_reviewer_actor: UUID
    semantic_valid_from: AwareDatetime
    semantic_expires_at: AwareDatetime

    @model_validator(mode='after')
    def separate_appointments(self):
        _require(all(a!=b and self.actor_id not in {a,b} for a,b in (
            (self.worker_issuer_actor,self.worker_reviewer_actor),
            (self.custody_issuer_actor,self.custody_reviewer_actor),
            (self.semantic_issuer_actor,self.semantic_reviewer_actor))), 'independent external appointments required')
        _require(all(c.client_uri==self.worker_uri for c in (*self.clients.values(),self.observer_client)),
                 'actual worker client identity differs')
        return self


def _worker_file(path, seal=None, *, limit=20*1024**2):
    path=Path(path)
    _require(path.is_absolute() and path.parent.resolve()==path.parent, 'canonical exact worker file required')
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
        before=os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid() and before.st_nlink==1
                 and before.st_mode & 0o077==0 and before.st_size<=limit, 'private owned worker file required')
        raw=stream.read(limit+1)
        identity=lambda i:(i.st_dev,i.st_ino,i.st_mode,i.st_uid,i.st_nlink,i.st_size,i.st_mtime_ns,i.st_ctime_ns)
        _require(len(raw)<=limit and identity(before)==identity(os.fstat(stream.fileno()))==identity(path.lstat()),
                 'worker file changed during read')
    if seal is not None:_require(hashlib.sha256(raw).hexdigest()==seal,'external worker file pin changed')
    return raw


def _worker_json(path,seal,model):
    raw=_worker_file(path,seal)
    value=json.loads(raw,object_pairs_hook=_unique,parse_constant=lambda _:_require(False,'nonfinite worker metadata'))
    return model.model_validate_json(canonical_bytes(value))


class PurposeWorkerRegistryV2(StrictRecord):
    schema_version: Literal[2]=2
    purpose: Literal['replacement-documentary-journey-v2']='replacement-documentary-journey-v2'
    workspace_id: UUID
    actor_id: UUID
    worker_uri: str
    runtime_hash: str=Field(pattern=HASH)
    issuer_actor: UUID
    reviewer_actor: UUID
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    jobs: tuple[PurposeWorkerJobV2,...]


class CurrentPurposeWorkerJobsV2:
    """Pinned EXTERNAL metadata appointment, never a source grant or phase issuer."""
    def __init__(self,config,population,allocation):
        _require(type(config) is CompilerWorkerConfigV2,'fixed protected worker configuration required')
        self.config,self.population,self.allocation=config,population,allocation

    def current(self,job_id,*,now):
        c=self.config
        record=_worker_json(c.jobs_registry_file,c.jobs_registry_sha256,PurposeWorkerRegistryV2)
        _require(type(job_id) is UUID and record.valid_from<=now<record.expires_at
                 and now<min(c.source_expires_at,self.population.expires_at,self.allocation.original_expires_at)
                 and record.workspace_id==c.workspace_id and record.actor_id==c.actor_id
                 and record.worker_uri==c.worker_uri and record.runtime_hash==c.runtime_hash
                 and record.issuer_actor==c.worker_issuer_actor and record.reviewer_actor==c.worker_reviewer_actor
                 and len({j.job_id for j in record.jobs})==len(record.jobs), 'worker metadata appointment not current')
        matches=[j for j in record.jobs if j.job_id==job_id]
        _require(len(matches)==1,'exact current externally admitted phase job required')
        job=matches[0]
        _require(job.actor_id==c.actor_id and job.workspace_id==c.workspace_id and job.runtime_hash==c.runtime_hash
                 and job.source_refs==self.population.source_refs
                 and job.allocation_hash==self.allocation.allocation_hash
                 and job.original_horizon==self.allocation.original_expires_at
                 and now<job.expires_at<=min(record.expires_at,c.source_expires_at,job.original_horizon),
                 'worker job population/allocation/current authority differs')
        return job


class CompilerPhaseCustodyFileV2(StrictRecord):
    kind: Literal['phase_commit','native_receipt','raw_wire','native_job','extraction_qualification',
        'population','census_context','assessment_context','assembly_context','assembly_observer',
        'assembly_protocol','assembly_observed','census_wire','assessment_wire','assembly_wire',
        'assessment','semantic_admission','compile_inputs']
    path: str
    sha256: str=Field(pattern=HASH)
    dispatch_id: UUID|None=None
    native_job_hash: str|None=Field(default=None,pattern=HASH)
    phase_commit_hash: str|None=Field(default=None,pattern=HASH)
    native_custody_receipt_hash: str|None=Field(default=None,pattern=HASH)
    artifact_id: UUID|None=None
    artifact_version: int|None=Field(default=None,strict=True,ge=1)
    source_ref: SourceRef|None=None


class CompilerPhaseCustodyAppointmentV2(StrictRecord):
    schema_version: Literal[2]=2
    purpose: Literal['compiler-phase-result-custody-v2']='compiler-phase-result-custody-v2'
    workspace_id: UUID
    actor_id: UUID
    compiler_login: str
    runtime_hash: str=Field(pattern=HASH)
    population_digest: str=Field(pattern=HASH)
    issuer_actor: UUID
    reviewer_actor: UUID
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    files: dict[UUID,tuple[CompilerPhaseCustodyFileV2,...]]


from dataclasses import dataclass

@dataclass(frozen=True)
class CompilerWorkerSettingsV2:
    config: CompilerWorkerConfigV2
    config_path: Path
    config_sha256: str
    population: object
    allocation: object
    resolver: object
    observer: object
    semantic: object
    jobs: CurrentPurposeWorkerJobsV2
    clients: dict

    def _source_horizon(self,job):
        horizons=[]
        with self.resolver._connection() as conn:
            self.resolver._check(conn)
            for ref in job.source_refs:
                rows=conn.execute('SELECT * FROM oracle2.hosting_current_source_identity(%s,%s,%s,%s,%s)',
                    self.resolver._args(ref.workspace_id,ref.source_id)).fetchall()
                _require(len(rows)==1,'unique actual compiler source proof required')
                revision,original,reading,parser,until,checked=rows[0]
                actual=SourceRef(workspace_id=ref.workspace_id,source_id=ref.source_id,revision=revision,
                    original_sha256=original,reading_sha256=reading,parser_id=parser)
                _require(actual==ref and until.tzinfo is not None and checked.tzinfo is not None,
                    'current compiler original scope changed')
                horizons.append(until)
            self.resolver._check(conn)
        return min(horizons)

    def authority_horizon(self,job):
        from .authority_adapter import ProcessingArtifactResolver
        from oracle_brain.hosting.parent_observer_v2 import ParentCurrentnessConsumerV2
        _require(type(self.resolver) is ProcessingArtifactResolver and type(self.observer) is ParentCurrentnessConsumerV2,
                 'actual compiler SQL012 and external parent consumer required')
        _worker_file(self.config_path,self.config_sha256)
        current=self.jobs.current(job.job_id,now=datetime.now(timezone.utc))
        _require(current==job,'immutable externally admitted worker job changed')
        before=self._source_horizon(job)
        witness=self.observer.current(self.population)
        after=self._source_horizon(job)
        # No SQL/custody lock is held during observer network.
        until=min(before,after,witness.expires_at,self.config.source_expires_at,job.expires_at,
            self.population.expires_at,self.allocation.original_expires_at)
        _require(datetime.now(timezone.utc)<until,'actual compiler/parent authority expired')
        return until

    def authorize(self,job):
        self.authority_horizon(job)
        return job

    def custody(self,job):
        self.authorize(job)
        c=self.config
        appointed=_worker_json(c.custody_appointment_file,c.custody_appointment_sha256,CompilerPhaseCustodyAppointmentV2)
        now=datetime.now(timezone.utc)
        _require(appointed.workspace_id==c.workspace_id and appointed.actor_id==c.actor_id
            and appointed.compiler_login==c.expected_session_role and appointed.runtime_hash==c.runtime_hash
            and appointed.population_digest==source_population_digest(job.source_refs)
            and appointed.issuer_actor==c.custody_issuer_actor and appointed.reviewer_actor==c.custody_reviewer_actor
            and appointed.valid_from<=now<min(appointed.expires_at,job.expires_at), 'actual compiler phase custody appointment unavailable')
        files=appointed.files.get(job.job_id,())
        _require(files and len({(f.kind,f.artifact_id,f.artifact_version,f.dispatch_id) for f in files})==len(files)
                 and len({f.path for f in files})==len(files),
                 'exact independently qualified phase-result file whitelist required')
        return files

    def private(self,job,kind,*,artifact_id=None,artifact_version=None,dispatch_id=None):
        files=self.custody(job)
        matches=[f for f in files if f.kind==kind and (artifact_id is None or f.artifact_id==artifact_id)
                 and (artifact_version is None or f.artifact_version==artifact_version)
                 and (dispatch_id is None or f.dispatch_id==dispatch_id)]
        _require(len(matches)==1,'unique exact compiler file whitelist entry required')
        entry=matches[0]
        raw=_worker_file(entry.path,entry.sha256)
        self.authorize(job)
        return raw,entry


def load_purpose_worker_settings_v2(config_path,trusted_config_sha256):
    """Fixed protected startup; never coerce provider settings or install grants."""
    from .purpose_context import ParentPopulationAdmissionV2,BudgetAllocationPinsV2
    from .authority_adapter import ProcessingSourceBinding,ProcessingArtifactResolver
    from .semantic_registry_v3 import CurrentSemanticAdmissionsV3,SemanticRegistryAppointmentV3
    from oracle_brain.hosting.parent_observer_v2 import ParentObserverAdmissionV2,ParentCurrentnessConsumerV2
    from oracle_brain.hosting.purpose_transport import PurposeTLSBindingV2,ParentObserverClientV2,PurposeProviderClientV2
    from oracle_brain.hosting.custody import DurableNonceSequenceV2
    from oracle_brain.hosting.provider_runtime import tls_url
    c=_worker_json(config_path,trusted_config_sha256,CompilerWorkerConfigV2)
    population=_worker_json(c.population_file,c.population_sha256,ParentPopulationAdmissionV2)
    allocation=_worker_json(c.allocation_projection_file,c.allocation_projection_sha256,BudgetAllocationPinsV2)
    now=datetime.now(timezone.utc)
    _require(c.workspace_id==population.workspace_id and c.source_registry_hash==population.source_registry_hash
             and len(population.source_refs)>=3 and now<min(c.source_expires_at,population.expires_at,allocation.original_expires_at),
             'complete current worker source population required')
    jobs=CurrentPurposeWorkerJobsV2(c,population,allocation)
    # Load only the externally pinned opaque appointment before credentials or
    # any private phase/result/original input. At least one actual phase is ready.
    registry=_worker_json(c.jobs_registry_file,c.jobs_registry_sha256,PurposeWorkerRegistryV2)
    _require(registry.jobs,'no externally admitted current worker phase')
    for job in registry.jobs:jobs.current(job.job_id,now=now)
    url=tls_url(c.database_url_file)
    binding=ProcessingSourceBinding(runtime_hash=c.runtime_hash,source_registry_hash=c.source_registry_hash,
        expected_owner_role=c.expected_owner_role,expected_session_role=c.expected_session_role,
        principal=c.actor_id,profile='candidate-compiler',expires_at=c.source_expires_at,synthetic=False)
    resolver=ProcessingArtifactResolver(url,binding=binding)
    observer_admission=_worker_json(c.parent_observer_admission_file,c.parent_observer_admission_hash,ParentObserverAdmissionV2)
    _require(observer_admission.population==population and observer_admission.client_uri==c.worker_uri,
             'actual compiler parent observation appointment differs')
    def tls(b):
        return PurposeTLSBindingV2(b.hostname,b.port,b.server_uri,b.client_uri,
            Path(b.ca_file),Path(b.certificate_file),Path(b.key_file))
    replay=DurableNonceSequenceV2(c.observer_spool,namespace=c.observer_namespace,
        appointment_hash=c.parent_observer_admission_hash,minimum_sequence=observer_admission.minimum_sequence,
        initialization_receipt_hash=c.observer_initialization_hash)
    observer=ParentCurrentnessConsumerV2(admission=observer_admission,trusted_admission_hash=c.parent_observer_admission_hash,
        transport=ParentObserverClientV2(tls(c.observer_client)),replay=replay)
    semantic=CurrentSemanticAdmissionsV3(c.semantic_registry_file,c.semantic_registry_sha256,
        appointment=SemanticRegistryAppointmentV3(c.workspace_id,c.runtime_hash,'candidate-compiler',
            c.semantic_issuer_actor,c.semantic_reviewer_actor,c.semantic_valid_from,c.semantic_expires_at))
    clients={phase:PurposeProviderClientV2(tls(b)) for phase,b in c.clients.items()}
    settings=CompilerWorkerSettingsV2(c,Path(config_path),trusted_config_sha256,population,allocation,resolver,observer,semantic,jobs,clients)
    for job in registry.jobs:settings.authorize(job)
    PurposeJourneyJournalV2(Path(c.spool))
    return settings


class PurposeJourneyCustodyV2:
    """Versioned phase queue over existing opaque custody primitives, V1 untouched."""
    def __init__(self,settings):
        _require(type(settings) is CompilerWorkerSettingsV2,'protected compiler worker settings required')
        self.settings=settings;self.journal=PurposeJourneyJournalV2(Path(settings.config.spool))

    def admit(self,job_id):
        job=self.settings.jobs.current(job_id,now=datetime.now(timezone.utc))
        self.settings.authorize(job) # actual SQL/observer network BEFORE lock
        pending=self.journal.spool/(str(job.job_id)+'.purpose-v2.pending')
        with self.journal._locked():
            _require(self.settings.jobs.current(job_id,now=datetime.now(timezone.utc))==job,
                     'worker metadata changed before durable enqueue')
            _require(not pending.with_suffix('.claimed').exists(),'worker phase already claimed')
            _durable_nonce(self.journal.spool,pending.name,canonical_bytes(job.model_dump(mode='json')))
        return job

    def claim(self):
        candidates=sorted(self.journal.spool.glob('*.purpose-v2.pending'))
        _require(len(candidates)<=4096,'bounded phase queue required')
        for path in candidates:
            raw=_worker_file(path)
            job=PurposeWorkerJobV2.model_validate_json(raw)
            _require(path.name==str(job.job_id)+'.purpose-v2.pending','phase queue identity changed')
            self.settings.authorize(job) # no journal/queue lock during network
            attempt=self.journal.claim(job,now=datetime.now(timezone.utc))
            # From this point the immutable phase/source marker is spent even if
            # a crash prevents rename; no alias may create a second paid attempt.
            with self.journal._locked():
                _require(_worker_file(path)==raw,'phase queue changed before claim')
                _require(self.settings.jobs.current(job.job_id,now=datetime.now(timezone.utc))==job,
                         'phase metadata changed before claim')
                target=path.with_suffix('.claimed')
                _require(not target.exists() and not target.is_symlink(),'phase already claimed')
                path.rename(target);_sync_spool(self.journal.spool)
            return job,attempt
        return None


def _phase_commit_from_custody(settings,job,reply=None):
    """Consume actual authorized phase handoff, never turn HTTP hashes into a grant."""
    from .purpose_receipts_v2 import PhaseResponseCommitV2
    from oracle_brain.hosting.processing_extraction_runtime_v2 import ExtractionResponseCommitV2
    raw,entry=settings.private(job,'phase_commit',dispatch_id=job.dispatch_id)
    model=ExtractionResponseCommitV2 if job.phase=='extraction' else PhaseResponseCommitV2
    commit=model.model_validate_json(raw)
    seal=digest(commit.model_dump(mode='json'))
    _require(commit.dispatch_id==job.dispatch_id and commit.phase==job.phase
        and commit.workspace_id==job.workspace_id and commit.source_refs==job.source_refs
        and commit.population_digest==source_population_digest(job.source_refs)
        and commit.request_hash==job.request_hash
        and entry.dispatch_id==commit.dispatch_id and entry.native_job_hash==commit.job_hash
        and entry.phase_commit_hash==seal and entry.native_custody_receipt_hash==commit.native_custody_receipt_hash,
        'actual authorized phase commit differs from externally appointed custody')
    native_raw,native_entry=settings.private(job,'native_receipt',dispatch_id=job.dispatch_id)
    native=json.loads(native_raw,object_pairs_hook=_unique)
    _require(native_entry.native_job_hash==commit.job_hash
        and native_entry.native_custody_receipt_hash==commit.native_custody_receipt_hash
        and digest(native)==commit.native_custody_receipt_hash
        and native.get('failed') is False and native.get('job_hash')==commit.job_hash
        and native.get('request_hash')==commit.request_hash
        and native.get('raw_response_hash')==commit.raw_response_hash,'actual paid/native custody differs')
    if reply is not None:
        _require(type(reply) is dict and set(reply)=={'dispatch_id','request_hash','phase_registry_sha256','raw_response_hash','receipt_hash'}
            and reply=={'dispatch_id':str(job.dispatch_id),'request_hash':job.request_hash,
                'phase_registry_sha256':job.phase_registry_sha256,'raw_response_hash':commit.raw_response_hash,'receipt_hash':seal},
            'opaque metadata reply differs from actual authorized phase custody')
    settings.authorize(job)
    return commit


def observe_purpose_phase_commit_v2(settings,job_id):
    """Read-only/provider-observational: same dispatch, no enqueue/POST/renewal."""
    _require(type(settings) is CompilerWorkerSettingsV2,'actual compiler startup required')
    job=settings.jobs.current(job_id,now=datetime.now(timezone.utc));settings.authorize(job)
    journal=PurposeJourneyJournalV2(Path(settings.config.spool))
    claimed=journal.spool/(str(job.job_id)+'.purpose-v2.claimed')
    _require(PurposeWorkerJobV2.model_validate_json(_worker_file(claimed))==job,'exact retained claimed phase required')
    commit=_phase_commit_from_custody(settings,job)
    return journal.commit(job,receipt_hash=digest(commit.model_dump(mode='json')),
        native_receipt_hash=commit.native_custody_receipt_hash,now=datetime.now(timezone.utc))


class ProcessingCompilerExtractionGuardV2:
    """Actual compiler/source+external custody before bytes, persist AND read."""
    def __init__(self,settings,current_job):
        _require(type(settings) is CompilerWorkerSettingsV2 and type(current_job) is PurposeWorkerJobV2,
                 'actual current compiler worker constructor required')
        self.settings,self.job=settings,current_job

    def _entry(self,manifest,principal,now):
        from .contracts import ArtifactManifest
        s=self.settings;c=s.config
        _require(type(manifest) is ArtifactManifest and principal==c.actor_id==self.job.actor_id
            and manifest.workspace_id==c.workspace_id and manifest.compiler_digest==c.runtime_hash
            and manifest.kind in {'processing_extraction_v1','processing_failed_extraction_v1'},
            'exact current compiler extraction target required')
        until=s.authority_horizon(self.job)
        files=s.custody(self.job)
        targets=[f for f in files if f.kind=='native_job' and f.artifact_id==manifest.artifact_id
                 and f.artifact_version==manifest.version]
        _require(len(targets)==1,'artifact has no unique externally appointed paid extraction target')
        entry=targets[0]
        _require(entry.source_ref in self.job.source_refs and entry.dispatch_id is not None
            and entry.native_job_hash is not None
            and manifest.source_digest==digest({'refs':[entry.source_ref.model_dump(mode='json')]}),
            'extraction source/artifact/version differs from actual compiler custody appointment')
        return entry,until

    def authorize_manifest(self,manifest,principal,now):
        return self._entry(manifest,principal,now)[1]

    def _paid(self,manifest,principal,now):
        from oracle_brain.hosting.provider_runtime import JobContext
        from oracle_brain.hosting.processing_extraction_runtime_v2 import (
            ExtractionOperationQualificationV2,ExtractionResponseCommitV2,verify_extraction_paid_wire_v2)
        entry,until=self._entry(manifest,principal,now)
        s=self.settings;job=self.job
        selector={'artifact_id':manifest.artifact_id,'artifact_version':manifest.version,'dispatch_id':entry.dispatch_id}
        context_raw,_=s.private(job,'native_job',**selector)
        context=JobContext.model_validate_json(context_raw)
        qraw,qentry=s.private(job,'extraction_qualification',**selector)
        qualification=ExtractionOperationQualificationV2.model_validate_json(qraw)
        wire,wentry=s.private(job,'raw_wire',**selector)
        commit_raw,centry=s.private(job,'phase_commit',**selector)
        committed=ExtractionResponseCommitV2.model_validate_json(commit_raw)
        content,witness=verify_extraction_paid_wire_v2(context,committed,wire,qualification,s.population,
            expected_qualification_hash=qentry.sha256,artifact_version=manifest.version)
        _require(witness.artifact_id==manifest.artifact_id and witness.artifact_version==manifest.version
            and witness.source_ref==entry.source_ref and witness.native_dispatch_id==entry.dispatch_id
            and witness.native_job_hash==entry.native_job_hash
            and witness.source_refs==job.source_refs and witness.population_digest==source_population_digest(job.source_refs)
            and witness.parent_registry_hash==s.population.parent_registry_sha256
            and witness.raw_wire_hash==wentry.sha256
            and centry.phase_commit_hash==witness.phase_commit_hash
            and centry.native_custody_receipt_hash==witness.native_custody_receipt_hash
            and qualification.budget_allocation_projection_sha256==s.config.allocation_projection_sha256,
            'paid witness differs from externally appointed compiler/source/allocation custody')
        native_raw,nentry=s.private(job,'native_receipt',**selector)
        native=json.loads(native_raw,object_pairs_hook=_unique)
        _require(native.get('failed') is False and digest(native)==witness.native_custody_receipt_hash
            and nentry.native_custody_receipt_hash==witness.native_custody_receipt_hash
            and native.get('job_hash')==witness.native_job_hash and native.get('raw_response_hash')==witness.raw_wire_hash,
            'actual paid native receipt unavailable')
        return context,content,witness,until

    def __call__(self,manifest,payload,principal,now):
        from .extraction import validate_response
        _require(manifest.kind=='processing_extraction_v1','failed paid extraction requires explicit FAILED custody protocol')
        context,content,witness,until=self._paid(manifest,principal,now)
        response,observations=validate_response(context.receipt,content,inventories=context.inventories)
        expected={'source_refs':[witness.source_ref.model_dump(mode='json')],
            'observations':[o.model_dump(mode='json') for o in observations],
            'findings':[f.model_dump(mode='json') for f in response.findings],
            'raw_response':content,'complete':True}
        _require(payload==expected and manifest.content_hash==digest(expected)
            and manifest.permission_digest==context.permission_hash,
            'compiler extraction content differs from actual paid model response')
        self.settings.authority_horizon(self.job)
        return None

    def valid_until(self,manifest,payload,principal,now):
        self(manifest,payload,principal,now)
        return self.authorize_manifest(manifest,principal,now)
