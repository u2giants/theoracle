"""Opaque ingress custody; registry holds no originals or provider credentials.

The independently issued registry is mounted read-only. Updating/revoking it is
an explicit coordinator operation. Executor rechecks actual ledger authority;
ingress acceptance alone never grants source access or reports live completion.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
from uuid import UUID

from oracle_brain.operating_model.contracts import digest


def _load(path):
    if path.is_symlink() or not path.is_file():
        raise PermissionError('trusted custody registry unavailable')
    raw=path.read_bytes()
    if len(raw)>1_000_000:
        raise PermissionError('custody registry exceeds envelope')
    return json.loads(raw)


class FileCustody:
    def __init__(self, *, registry: Path, spool: Path, trusted_registry_hash: str,
                 runtime_hash: str, worker_uri: str, job_authority, clock=time.time):
        self.registry,self.spool,self.trusted_registry_hash=registry,spool,trusted_registry_hash
        self.runtime_hash,self.worker_uri,self.clock=runtime_hash,worker_uri,clock
        if not callable(getattr(job_authority,"resolve",None)) or not callable(getattr(job_authority,"hold",None)):
            raise PermissionError("current canonical job authority required")
        self.job_authority=job_authority
        if spool.is_symlink() or not spool.is_dir():
            raise PermissionError('dedicated opaque spool unavailable')

    def resolve(self, job, worker_uri, *, result=False):
        record=_load(self.registry)
        if digest(record)!=self.trusted_registry_hash:
            raise PermissionError('custody registry changed without admission')
        if worker_uri!=self.worker_uri or record.get('worker_uri')!=worker_uri:
            raise PermissionError('worker identity unavailable')
        now=int(self.clock())
        if (record.get('active') is not True or type(record.get('expires_at')) is not int
                or record['expires_at']<=now or job.expires_at<=now
                or job.runtime_hash!=self.runtime_hash or record.get('runtime_hash')!=self.runtime_hash):
            raise PermissionError('custody runtime, revocation or expiry denied')
        if set(record)!={'worker_uri','runtime_hash','active','expires_at','allowed_release_hashes'}:
            raise PermissionError('fixed external policy schema required')
        if set(record['allowed_release_hashes'])!=set(self.job_authority.allowed_release_hashes):
            raise PermissionError('external release policy differs from authority')
        resolver=self.job_authority.resolve_result if result else self.job_authority.resolve
        row=resolver(job.job_id,job.runtime_hash,job.admission_hash)
        allowed={'job_id','workspace_id','run_id','scope','admission_hash','active','expires_at'}
        if set(row)!=allowed or row.get('scope') not in {'documentary-view','finding-review','semantic-verification'}:
            raise PermissionError('only admitted documentary job scopes allowed')
        for key in ('job_id','workspace_id','run_id'):
            if not isinstance(row[key],str) or str(UUID(row[key]))!=row[key]:
                raise PermissionError('canonical job identity unavailable')
        if (row.get('active') is not True or row.get('admission_hash')!=job.admission_hash
                or type(row.get('expires_at')) is not int or not now<job.expires_at<=row['expires_at']):
            raise PermissionError('job admission, revocation or expiry denied')
        return row

    def admit(self, job, worker_uri):
        # One serial boundary across gateway threads/processes; exclusive enqueue
        # prevents repeated execution even if a caller changes its nonce.
        with (self.spool/'.custody-lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            row=self.resolve(job,worker_uri)
            # Current metadata is checked before any queue write. The executor
            # repeats authority before loading originals or delivering results.
            with self.job_authority.hold(row):
                self._enqueue(job)

    @contextmanager
    def result(self,job,worker_uri):
        # Both purposes consume the same durable nonce namespace before result authority.
        with (self.spool/'.custody-lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            self._consume_nonce(job)
            row=self.resolve(job,worker_uri,result=True)
        from .gateway import ResultLease
        with self.job_authority.hold_result(row,job) as lease:
            def before_write():
                # Externally pinned policy may be revoked without a database write.
                current=_load(self.registry)
                if (digest(current)!=self.trusted_registry_hash or current.get('active') is not True
                        or current.get('expires_at',0)<=self.clock() or job.expires_at<=self.clock()):
                    raise PermissionError('result custody revoked')
                lease.before_write()
            yield ResultLease(lease.status,lease.body,before_write)

    def _consume_nonce(self,job):
        _durable_nonce(self.spool,'nonce-'+job.nonce,
            hashlib.sha256(json.dumps(job.__dict__,sort_keys=True).encode()).hexdigest().encode())

    def _enqueue(self,job):
        marker=self.spool/('nonce-'+job.nonce)
        pending=self.spool/(job.job_id+'.pending')
        done=self.spool/(job.job_id+'.claimed')
        if marker.exists() or pending.exists() or done.exists():
            raise PermissionError('job or nonce already consumed')
        # Persist opaque immutable request, never private input/result text.
        payload=json.dumps(job.__dict__,sort_keys=True,separators=(',',':')).encode()
        self._consume_nonce(job)
        fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:os.write(fd,payload);os.fsync(fd)
        finally:os.close(fd)
        directory=os.open(self.spool,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)

    def claim(self):
        from .gateway import parse_job
        with (self.spool/'.custody-lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            for path in sorted(self.spool.glob('*.pending')):
                if path.is_symlink():raise PermissionError('opaque queue symlink denied')
                # A stale lease is retained, never silently refreshed or executed.
                job=parse_job(path.read_bytes(),now=int(self.clock()))
                row=self.resolve(job,self.worker_uri)
                target=path.with_suffix('.claimed')
                if target.exists():raise PermissionError('job already claimed')
                with self.job_authority.hold(row):
                    path.rename(target)
                return job,row
        return None


def _durable_nonce(spool,name,payload):
    """Retained custody exclusive-create/fsync primitive; no authority issuance."""
    marker=spool/name
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        os.write(fd,payload);os.fsync(fd)
    finally:os.close(fd)
    _sync_spool(spool)


def _sync_spool(spool):
    directory=os.open(spool,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(directory)
    finally:os.close(directory)


class DurableNonceSequenceV2:
    """Narrow appointment-scoped replay extension to an existing protected spool.

    Initialization receipt, lock and state must already be externally provisioned.
    No constructor/reset path creates an epoch or recreates missing state. Failed
    journal-before-state commits fence the epoch until external recovery; no retry
    can silently erase a consumed challenge or roll the highwater backwards.
    """
    def __init__(self,spool,*,namespace,appointment_hash,minimum_sequence,
                 initialization_receipt_hash):
        import re
        self.spool=Path(spool)
        if (not re.fullmatch(r'[a-z][a-z0-9-]{0,31}',namespace)
                or not re.fullmatch(r'[0-9a-f]{64}',appointment_hash)
                or not re.fullmatch(r'[0-9a-f]{64}',initialization_receipt_hash)
                or type(minimum_sequence) is not int or minimum_sequence<0):
            raise PermissionError('external replay namespace/appointment/initialization required')
        self.namespace,self.appointment_hash,self.minimum_sequence=namespace,appointment_hash,minimum_sequence
        self._check_owner(self.spool,directory=True)
        self.initial={'schema_version':2,'namespace':namespace,'appointment_hash':appointment_hash,
                      'minimum_sequence':minimum_sequence}
        from .runtime import protected_file
        self.init_path=self.spool/(namespace+'-init.json')
        self._check_owner(self.init_path)
        raw=protected_file(self.init_path,limit=4096)
        from .gateway import unique_object
        if (hashlib.sha256(raw).hexdigest()!=initialization_receipt_hash
                or json.loads(raw,object_pairs_hook=unique_object)!=self.initial):
            raise PermissionError('externally pinned replay initialization differs')
        self.lock_path=self.spool/(namespace+'-lock')
        self.state_path=self.spool/(namespace+'-state.json')
        self._check_owner(self.lock_path)
        self._read()

    @staticmethod
    def _check_owner(path,*,directory=False):
        import stat
        info=path.lstat()
        if (info.st_uid!=os.geteuid() or info.st_mode&0o077 or stat.S_ISLNK(info.st_mode)
                or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))):
            raise PermissionError('own protected replay object required')

    def _read(self):
        from .runtime import protected_file
        from .gateway import unique_object
        self._check_owner(self.state_path)
        state=json.loads(protected_file(self.state_path,limit=4096),object_pairs_hook=unique_object)
        if (not isinstance(state,dict) or set(state)!=set(self.initial)|{'sequence'}
                or any(state[k]!=v for k,v in self.initial.items())
                or type(state['sequence']) is not int or state['sequence']<self.minimum_sequence):
            raise PermissionError('missing, foreign or reset replay state')
        highwater=self.minimum_sequence
        for path in self.spool.glob(self.namespace+'-sequence-*.json'):
            self._check_owner(path)
            value=json.loads(protected_file(path,limit=4096),object_pairs_hook=unique_object)
            if (set(value)!=set(self.initial)|{'sequence','challenge_hash'}
                    or any(value[k]!=v for k,v in self.initial.items())
                    or type(value['sequence']) is not int or value['sequence']<=self.minimum_sequence
                    or path.name!=self.namespace+'-sequence-'+str(value['sequence'])+'.json'
                    or not isinstance(value['challenge_hash'],str) or len(value['challenge_hash'])!=64):
                raise PermissionError('partial or foreign replay sequence journal')
            highwater=max(highwater,value['sequence'])
        if highwater!=state['sequence']:
            raise PermissionError('partial commit or rolled-back replay highwater')
        return state

    @contextmanager
    def _locked(self):
        self._check_owner(self.spool,directory=True);self._check_owner(self.lock_path)
        fd=os.open(self.lock_path,os.O_RDWR|os.O_NOFOLLOW)
        try:
            if os.fstat(fd).st_uid!=os.geteuid() or os.fstat(fd).st_mode&0o077:
                raise PermissionError('protected replay lock required')
            fcntl.flock(fd,fcntl.LOCK_EX)
            yield
        finally:os.close(fd)

    def claim(self,challenge):
        import re
        if not isinstance(challenge,str) or not re.fullmatch(r'[0-9a-f]{64}',challenge):
            raise PermissionError('fresh exact 256-bit challenge required')
        with self._locked():
            state=self._read()
            _durable_nonce(self.spool,self.namespace+'-nonce-'+challenge,
                self.appointment_hash.encode())
            return state['sequence']

    def advance(self,challenge,sequence,*,verify):
        """Pure verifier executes under replay lock; never network/SQL callbacks."""
        import tempfile
        from oracle_brain.operating_model.contracts import canonical_bytes
        import re
        if not isinstance(challenge,str) or not re.fullmatch(r'[0-9a-f]{64}',challenge):
            raise PermissionError('exact claimed challenge required')
        with self._locked():
            state=self._read()
            challenge_hash=hashlib.sha256(challenge.encode()).hexdigest()
            for journal in self.spool.glob(self.namespace+'-sequence-*.json'):
                if json.loads(journal.read_bytes())['challenge_hash']==challenge_hash:
                    raise PermissionError('challenge already completed')
            marker=self.spool/(self.namespace+'-nonce-'+challenge)
            self._check_owner(marker)
            if marker.read_bytes()!=self.appointment_hash.encode():
                raise PermissionError('challenge was not durably claimed for appointment')
            if type(sequence) is not int or sequence<=state['sequence']:
                raise PermissionError('replayed or out-of-order observer sequence')
            _durable_nonce(self.spool,self.namespace+'-attempt-'+challenge,
                self.appointment_hash.encode())
            verify(state['sequence'])
            # Journal claim precedes state commit. A crash in between fences epoch.
            value={**self.initial,'sequence':sequence,
                   'challenge_hash':hashlib.sha256(challenge.encode()).hexdigest()}
            _durable_nonce(self.spool,self.namespace+'-sequence-'+str(sequence)+'.json',canonical_bytes(value))
            fd,name=tempfile.mkstemp(prefix='.'+self.namespace+'-',dir=self.spool)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(canonical_bytes({**self.initial,'sequence':sequence}));stream.flush();os.fsync(stream.fileno())
                os.replace(name,self.state_path);_sync_spool(self.spool)
                if self._read()['sequence']!=sequence:
                    raise PermissionError('replay highwater durable readback failed')
            finally:
                if os.path.exists(name):os.unlink(name)
