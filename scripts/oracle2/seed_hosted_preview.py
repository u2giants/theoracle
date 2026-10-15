#!/usr/bin/env python3
"""Seed the isolated hosted S03 preview database with invented data only.

Reviewed plan: docs/implementation/s03-graph-preview-provisioning-plan.md.
Refuses any target other than the one Supabase project ref named on the command
line, and refuses the known production/legacy refs. Writes generated role
passwords and identifiers to a new 0600 JSON file; prints only non-secret ids.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from oracle_brain.authz import appoint_owner, delegate
from oracle_brain import holistic_runtime

FORBIDDEN_REFS = {"eqccjfbyrywsqkxxpjvg", "vokucjpanhvqunimlvsp", "aaxtrlfpnoutziwhshlt",
                  "xupnyeifmpsacrqahwwm", "qsllyeztdwjgirsysgai", "ryltkzzernhwnojzouyb"}
DOC_ONE = "Intake Lead sends the packet to Review Team. Review Team follows the signed policy."
DOC_TWO = ("Review Team reviews the packet. If the packet is incomplete, "
           "Review Team returns it to Intake Lead.")
ROLES = ("oracle2_extract", "oracle2_project", "oracle2_checkpoint",
         "oracle2_pilot_web", "oracle2_holistic")


def _require_target(url: str, ref: str) -> None:
    """Exact Supabase shapes only: direct host db.<ref>.supabase.co, or the
    shared pooler host with tenant user postgres.<ref>. TLS is mandatory."""
    if ref in FORBIDDEN_REFS or not re.fullmatch(r"[a-z]{20}", ref):
        raise PermissionError("target is not the reviewed preview project")
    parts = urlsplit(url)
    host, user = parts.hostname or "", parts.username or ""
    direct = host == f"db.{ref}.supabase.co" and user == "postgres"
    pooled = (re.fullmatch(r"aws-[0-9]+-[a-z0-9-]+\.pooler\.supabase\.com", host) is not None
              and user == f"postgres.{ref}")
    if not (direct or pooled):
        raise PermissionError("admin URL does not name the reviewed preview project")
    if "sslmode=require" not in (parts.query or "") and "sslmode=verify-full" not in (parts.query or ""):
        raise PermissionError("admin URL must require TLS (sslmode=require or verify-full)")


def _require_outside_repo(path: Path, root: Path) -> None:
    resolved = path.resolve()
    if resolved == root or root in resolved.parents:
        raise PermissionError("credential output must be outside the repository tree")


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream)
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    admin_url = os.environ["ORACLE2_PREVIEW_ADMIN_URL"]
    _require_target(admin_url, args.project_ref)
    root = Path(__file__).resolve().parents[2]
    out_path = Path(args.out)
    _require_outside_repo(out_path, root)
    if out_path.exists():
        raise FileExistsError("credential output already exists; refusing to overwrite")
    workspace, actor, owner = uuid4(), uuid4(), uuid4()
    source_ids, draft_ids = (uuid4(), uuid4()), (uuid4(), uuid4())
    out = {"projectRef": args.project_ref, "workspaceId": str(workspace), "actorId": str(actor),
           "sourceIds": [str(x) for x in source_ids], "draftIds": [str(x) for x in draft_ids],
           "rolePasswords": {role: secrets.token_urlsafe(32) for role in ROLES},
           "pilotToken": secrets.token_urlsafe(32), "corpusDigest": None, "complete": False}
    # Credentials are persisted before any database change, so a failure never
    # leaves roles with unknown passwords.
    _write(out_path, out)
    with psycopg.connect(admin_url) as conn:
        with conn.transaction():
            if conn.execute("SELECT to_regnamespace('oracle2')").fetchone()[0] is not None:
                raise RuntimeError("oracle2 schema already present; target is not a fresh preview")
            for filename in ("001_foundation.sql", "002_pilot.sql"):
                conn.execute((root / "services/oracle-brain/sql" / filename).read_text())
            # Roles get random passwords directly; the committed local passwords
            # in dev/oracle2/init-postgres.sql are never applied here.
            for role, password in out["rolePasswords"].items():
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)))
            conn.execute((root / "dev/oracle2/grant-postgres.sql").read_text())
            for index, (sid, did, filename, text) in enumerate(
                    ((source_ids[0], draft_ids[0], "intake.txt", DOC_ONE),
                     (source_ids[1], draft_ids[1], "review.txt", DOC_TWO))):
                conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,"
                             "content_type,status) VALUES (%s,%s,%s,%s,'text/plain','confirmed')",
                             (sid, workspace, actor, filename))
                conn.execute("INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,"
                             "block_index,kind,text,span_start,span_end) "
                             "VALUES (%s,%s,%s,0,'original',%s,0,%s)",
                             (uuid4(), sid, workspace, text, len(text)))
                conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,"
                             "process_name,status) VALUES (%s,%s,%s,%s,%s,'confirmed')",
                             (did, sid, workspace, actor, f"Synthetic process {index + 1}"))
    # Throwaway self-issued owner key: valid ONLY for this isolated synthetic
    # preview database; never reuse this bootstrap for a durable environment.
    key = Ed25519PrivateKey.generate()
    os.environ["ORACLE2_OWNER_PUBLIC_KEY"] = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw).hex()
    appointment = uuid4()
    message = f"oracle2-owner-appointment-v1:{workspace}:{owner}:{appointment}".encode()
    appoint_owner(admin_url, workspace_id=workspace, owner_id=owner, appointed_by=uuid4(),
                  appointment_id=appointment, owner_signature_hex=key.sign(message).hex())
    for scope in ("review", "confirm"):
        delegate(admin_url, workspace_id=workspace, grantor_id=owner, actor_id=actor, scope=scope)
    os.environ["ORACLE2_HOLISTIC_SOURCE_IDS"] = json.dumps(out["sourceIds"])
    with psycopg.connect(admin_url) as conn:
        digest = holistic_runtime.evidence_digest(holistic_runtime.read_corpus(conn, workspace))
    out.update(corpusDigest=digest, complete=True)
    os.unlink(out_path)
    _write(out_path, out)
    print(json.dumps({"workspaceId": out["workspaceId"], "corpusDigest": digest,
                      "sourceIds": out["sourceIds"], "draftIds": out["draftIds"],
                      "seedSha256": hashlib.sha256((DOC_ONE + DOC_TWO).encode()).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
