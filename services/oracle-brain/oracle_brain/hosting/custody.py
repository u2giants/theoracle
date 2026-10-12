"""Opaque ingress custody; registry holds no originals or provider credentials.

The independently issued registry is mounted read-only. Updating/revoking it is
an explicit coordinator operation. Executor rechecks actual ledger authority;
ingress acceptance alone never grants source access or reports live completion.
"""
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

    def resolve(self, job, worker_uri):
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
        row=self.job_authority.resolve(job.job_id,job.runtime_hash,job.admission_hash)
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

    def _enqueue(self,job):
        marker=self.spool/('nonce-'+job.nonce)
        pending=self.spool/(job.job_id+'.pending')
        done=self.spool/(job.job_id+'.claimed')
        if marker.exists() or pending.exists() or done.exists():
            raise PermissionError('job or nonce already consumed')
        # Persist opaque immutable request, never private input/result text.
        payload=json.dumps(job.__dict__,sort_keys=True,separators=(',',':')).encode()
        nonce_fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            os.write(nonce_fd,hashlib.sha256(payload).hexdigest().encode());os.fsync(nonce_fd)
        finally:os.close(nonce_fd)
        fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
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
