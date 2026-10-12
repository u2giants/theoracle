"""Current, metadata-only gateway authority; no original/blob credentials."""
from contextlib import contextmanager
import json
import re
from uuid import UUID

import psycopg

from oracle_brain.knowledge.authority import _has_authority_conn, _lock
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.contracts import digest


class PostgresJobAuthority:
    def __init__(self, database_url: str, *, runtime_hash: str, synthetic: bool,
                 allowed_release_hashes: frozenset[str]):
        if (not re.fullmatch(r"[a-f0-9]{64}", runtime_hash) or type(synthetic) is not bool
                or not isinstance(allowed_release_hashes, frozenset) or not allowed_release_hashes
                or any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in allowed_release_hashes)):
            raise ValueError("exact runtime and environment required")
        self.url, self.runtime_hash, self.synthetic = database_url, runtime_hash, synthetic
        self.allowed_release_hashes = allowed_release_hashes

    def resolve(self, job_id: str, runtime_hash: str, admission_hash: str) -> dict:
        """An opaque job is its canonical existing run UUID, never supplied workspace.

        Caller admission must equal the sealed release documentary gate. Root's
        independently reviewed policy pins accepted release hashes externally.
        """
        identity = UUID(job_id)
        if str(identity) != job_id or runtime_hash != self.runtime_hash:
            raise PermissionError("opaque job/runtime identity denied")
        with psycopg.connect(self.url) as conn:
            rows = conn.execute("""SELECT workspace_id,run_id,'documentary-view',expires_at
                FROM oracle2.operating_view_runs WHERE run_id=%s AND status='pending' AND expires_at>clock_timestamp()
                UNION ALL
                SELECT workspace_id,run_id,CASE WHEN operation='finding_review' THEN 'finding-review' ELSE 'denied' END,expires_at
                FROM oracle2.operating_action_runs WHERE run_id=%s AND status='pending' AND expires_at>clock_timestamp()""",
                (identity, identity)).fetchall()
            if len(rows) != 1 or rows[0][2] == 'denied':
                raise PermissionError("unique canonical documentary job unavailable")
            workspace, run, scope, expiry = rows[0]
            row = {"job_id": job_id, "workspace_id": str(workspace), "run_id": str(run),
                   "scope": scope, "admission_hash": admission_hash, "active": True,
                   "expires_at": int(expiry.timestamp())}
            _lock(conn, workspace)
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                         ("operating-selector:" + str(workspace),))
            self._authorize(conn, row, workspace, run)
        return row

    @contextmanager
    def _result_connection(self):
        settings=psycopg.conninfo.conninfo_to_dict(self.url)
        if settings.get('sslmode')!='verify-full' or not settings.get('sslrootcert'):
            raise PermissionError('authenticated result ledger TLS required')
        with psycopg.connect(self.url) as conn:
            if conn.pgconn.ssl_in_use is not True: raise PermissionError('actual result ledger TLS required')
            yield conn

    def resolve_result(self,job_id,runtime_hash,admission_hash):
        if self.synthetic is not True or runtime_hash!=self.runtime_hash or str(UUID(job_id))!=job_id:
            raise PermissionError('synthetic fixed result denied')
        with self._result_connection() as conn:
            values=conn.execute("SELECT workspace_id,expires_at FROM oracle2.operating_view_runs WHERE run_id=%s AND status IN ('pending','completed') AND expires_at>clock_timestamp()",(UUID(job_id),)).fetchone()
            if not values: raise PermissionError('result unavailable')
            row={'job_id':job_id,'workspace_id':str(values[0]),'run_id':job_id,'scope':'documentary-view',
                 'admission_hash':admission_hash,'active':True,'expires_at':int(values[1].timestamp())}
            self._authorize(conn,row,values[0],UUID(job_id),completed=True)
        return row

    @contextmanager
    def hold_result(self,row,opaque):
        from .gateway import ResultLease
        if self.synthetic is not True or row.get('scope')!='documentary-view':
            raise PermissionError('synthetic result authority required')
        with self._result_connection() as conn:
            conn.execute("SET LOCAL lock_timeout='2s'")
            conn.execute("SET LOCAL statement_timeout='5s'")
            workspace,run=UUID(row['workspace_id']),UUID(row['run_id'])
            def current():
                result=conn.execute('SELECT * FROM oracle2.gateway_view_result(%s,%s,%s)',
                    (run,self.runtime_hash,row['admission_hash'])).fetchone()
                self._authorize(conn,row,workspace,run,completed=True)
                expiry=conn.execute('SELECT expires_at FROM oracle2.operating_view_runs WHERE run_id=%s',(run,)).fetchone()
                if not expiry or opaque.expires_at>expiry[0].timestamp() or conn.execute('SELECT clock_timestamp()').fetchone()[0].timestamp()>=min(opaque.expires_at,expiry[0].timestamp()):
                    raise PermissionError('result delivery expired')
                if not result: raise PermissionError('result unavailable')
                return result
            result=current()
            status,raw=result[0],result[1]
            body=b'{"state":"pending"}' if status=='pending' else bytes(raw)
            def before_write():
                if current()!=result: raise PermissionError('result changed during custody')
            yield ResultLease(202 if status=='pending' else 200,body,before_write)

    def __call__(self, row: dict) -> None:
        with self.hold(row):
            pass

    @contextmanager
    def hold(self, row: dict):
        """Root may hold appointment/selector locks through opaque enqueue.

        Executor must repeat current authority before originals and delivery;
        filesystem enqueue and PostgreSQL are not one atomic transaction.
        """
        with psycopg.connect(self.url) as conn:
            workspace, run = UUID(row["workspace_id"]), UUID(row["run_id"])
            _lock(conn, workspace)
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                         ("operating-selector:" + str(workspace),))
            actor = self._authorize(conn, row, workspace, run)
            yield actor
            # Catch permission/source/selector drift during enqueue as well.
            if self._authorize(conn, row, workspace, run) != actor:
                raise PermissionError("job identity changed during authorization")

    def _authorize(self, conn, row, workspace, run, *, completed=False):
        scope = row.get("scope")
        if scope == "documentary-view":
            job = conn.execute("""SELECT actor_id,release_id,release_hash,status
                FROM oracle2.operating_view_runs WHERE run_id=%s AND workspace_id=%s
                AND expires_at>clock_timestamp()""", (run, workspace)).fetchone()
            review_scope = None
        elif scope == "finding-review":
            result = conn.execute("SELECT * FROM oracle2.gateway_action_metadata(%s,%s)",
                                  (workspace, run)).fetchone()
            if not result or result[4] != "finding_review":
                raise PermissionError("bounded finding-review job unavailable")
            job, review_scope = result[:4], result[5]
            if not isinstance(review_scope, str) or not 1 <= len(review_scope) <= 512:
                raise PermissionError("bounded finding scope unavailable")
        else:
            raise PermissionError("scope has no authoritative gateway job metadata")
        if not job or job[3] not in ({"pending","completed"} if completed else {"pending"}):
            raise PermissionError("actor-owned pending job unavailable")
        actor, release_id, release_hash, _ = job
        selected = conn.execute("""SELECT m.payload,m.content_hash,s.watermark
            FROM oracle2.operating_release_selectors s JOIN oracle2.operating_release_manifests m
            ON m.workspace_id=s.workspace_id AND m.release_id=s.release_id
            WHERE s.workspace_id=%s AND s.release_id=%s""", (workspace, release_id)).fetchone()
        if not selected:
            raise PermissionError("current selected release unavailable")
        manifest = ReleaseManifest.model_validate_json(json.dumps(selected[0]))
        current = conn.execute("SELECT COALESCE(max(sequence),0) FROM oracle2.operating_model_change_log WHERE workspace_id=%s",
                               (workspace,)).fetchone()[0]
        if (manifest.workspace_id != workspace or manifest.release_id != release_id
                or manifest.content_hash() != selected[1] or selected[1] != release_hash
                or selected[1] not in self.allowed_release_hashes
                or manifest.documentary_gate_hash != row.get('admission_hash')
                or manifest.runtime_digest != self.runtime_hash
                or current != manifest.ledger_watermark or current != selected[2]
                or self.synthetic != (manifest.acceptance_state == "synthetic")
                or (not self.synthetic and manifest.acceptance_state != "admitted_hosted")):
            raise PermissionError("release, runtime, watermark or environment changed")
        artifact = conn.execute("""SELECT state,content_hash,permission_digest,source_digest
            FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s AND version=%s""",
            (workspace, manifest.artifact_id, manifest.artifact_version)).fetchone()
        invalid = conn.execute("""SELECT 1 FROM oracle2.artifact_invalidations
            WHERE workspace_id=%s AND artifact_id=%s AND version=%s LIMIT 1""",
            (workspace, manifest.artifact_id, manifest.artifact_version)).fetchone()
        if (not artifact or invalid or artifact[0] != "ready"
                or artifact[1] != manifest.artifact_content_hash or artifact[2] != manifest.permission_digest):
            raise PermissionError("current documentary artifact unavailable")
        dependencies = conn.execute("""SELECT upstream_id,upstream_revision FROM oracle2.artifact_dependencies
            WHERE workspace_id=%s AND artifact_id=%s AND version=%s AND upstream_kind='source'""",
            (workspace, manifest.artifact_id, manifest.artifact_version)).fetchall()
        expected = {(str(ref.source_id), str(ref.revision)) for ref in manifest.source_refs}
        if (len(manifest.source_refs) != len(expected) or len(dependencies) != len(expected)
                or set(dependencies) != expected
                or artifact[3] != digest({"refs": [ref.model_dump(mode="json") for ref in manifest.source_refs]})):
            raise PermissionError("release source dependency population changed")
        for ref in manifest.source_refs:
            if not _has_authority_conn(conn, workspace, actor, "source-read:" + str(ref.source_id)):
                raise PermissionError("current source appointment denied")
            source = conn.execute("""SELECT s.revision,s.status,d.status
                FROM oracle2.sources s JOIN oracle2.drafts d
                ON d.workspace_id=s.workspace_id AND d.source_id=s.source_id
                WHERE s.workspace_id=%s AND s.source_id=%s""", (workspace, ref.source_id)).fetchall()
            receipt = conn.execute("""SELECT original_hash,reading_hash,parser_id FROM oracle2.operating_model_source_receipts
                WHERE workspace_id=%s AND source_id=%s AND revision=%s""",
                (workspace, ref.source_id, ref.revision)).fetchone()
            if (len(source) != 1 or source[0][0] != ref.revision or source[0][1] not in {"draft", "confirmed"}
                    or source[0][2] != "confirmed" or receipt != (ref.original_sha256, ref.reading_sha256, ref.parser_id)):
                raise PermissionError("current source metadata unavailable or withdrawn")
        if review_scope and not _has_authority_conn(conn, workspace, actor, "finding-review:" + review_scope):
            raise PermissionError("current scoped finding-review appointment denied")
        return actor
