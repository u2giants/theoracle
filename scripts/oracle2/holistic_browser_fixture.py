#!/usr/bin/env python3
"""Synthetic loopback fixture for the holistic browser proof.

It seeds one isolated workspace, builds the real SDK/Falkor snapshot with fixed
providers, and exposes only the Trigger HTTP receipt endpoint.  Source text and
questions never cross that endpoint; the worker executes locally in this process.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from graphrag_sdk.core.models import LLMResponse
from graphrag_sdk.core.providers import Embedder, LLMInterface

from oracle_brain.authz import appoint_owner, delegate
from oracle_brain.graph.graphrag import (
    AdmittedEmbedder, AdmittedLLM, CallBudget, Corpus, CorpusSource,
    HolisticGraphPilot,
)
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest
from oracle_brain import holistic_runtime


DOC_ONE = "Intake Lead sends the packet to Review Team. Review Team follows the signed policy."
DOC_TWO = "Review Team reviews the packet. If the packet is incomplete, Review Team returns it to Intake Lead."
WORKSPACE = uuid4()
ACTOR = UUID("00000000-0000-4000-8000-0000000000f2")
OWNER = UUID("00000000-0000-4000-8000-0000000000f3")


class FixedLLM(LLMInterface):
    def __init__(self, first_id: str, second_id: str):
        super().__init__("fixed-synthetic-llm", max_concurrency=1)
        self.first_id, self.second_id = first_id, second_id

    def invoke(self, prompt: str, **kwargs) -> LLMResponse:
        if "GROUNDING REVIEW" in prompt:
            payload = {"supported": True, "unsupported_statements": [],
                       "omitted_required_exceptions": [], "concealed_conflicts": []}
        elif "FULL ORIGINAL SOURCE DATA" in prompt:
            payload = {"explanation": [{
                "text": "Intake sends the packet and Review Team reviews it; incomplete packets return to Intake Lead.",
                "citations": [
                    {"source_id": self.first_id, "quote": "Intake Lead sends the packet to Review Team."},
                    {"source_id": self.second_id, "quote": "If the packet is incomplete, Review Team returns it to Intake Lead."},
                ],
            }], "conflicts": [], "unknowns": ["The approval owner is not stated."],
                "hypothetical_improvements": []}
        elif "incomplete" in prompt:
            payload = {"objects": [
                {"key": "review", "kind": "Role", "name": "Review Team", "scope": "licensed",
                 "description": "reviews packets", "quote": "Review Team reviews the packet"},
                {"key": "return", "kind": "Exception", "name": "Incomplete packet return", "scope": "licensed",
                 "description": "return path", "quote": "If the packet is incomplete"},
            ], "links": [{"source": "review", "target": "return", "kind": "EXCEPTION_TO",
                           "description": "incomplete packets use the return path",
                           "quote": "If the packet is incomplete"}],
                "missing_information": [], "conflicts": []}
        else:
            payload = {"objects": [
                {"key": "intake", "kind": "Role", "name": "Intake Lead", "scope": "licensed",
                 "description": "sends packets", "quote": "Intake Lead sends the packet to Review Team"},
                {"key": "review", "kind": "Role", "name": "Review Team", "scope": "licensed",
                 "description": "receives packets", "quote": "Review Team"},
            ], "links": [{"source": "intake", "target": "review", "kind": "HANDOFF_TO",
                           "description": "intake hands the packet to review",
                           "quote": "sends the packet to Review Team"}],
                "missing_information": [], "conflicts": []}
        return LLMResponse(content=json.dumps(payload))


class FixedEmbedder(Embedder):
    @property
    def model_name(self):
        return "fixed-synthetic-embedder"

    def embed_query(self, text: str, **kwargs):
        return [0.0, 1.0, 0.0, 1.0]


def _require_loopback(url: str) -> None:
    if urlsplit(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise PermissionError("holistic browser fixture requires loopback services")


def _source(source_id: UUID, filename: str, text: str, revision: str) -> CorpusSource:
    return CorpusSource(source_id=source_id, revision=revision, filename=filename, text=text,
                        content_hash=hashlib.sha256(text.encode()).hexdigest(), complete=True)


def _seed_database(admin_url: str, source_ids: tuple[UUID, UUID], draft_ids: tuple[UUID, UUID]):
    root = Path(__file__).resolve().parents[2]
    with psycopg.connect(admin_url, autocommit=True) as conn:
        for filename in ("001_foundation.sql", "002_pilot.sql"):
            conn.execute((root / "services/oracle-brain/sql" / filename).read_text())
        conn.execute((root / "dev/oracle2/init-postgres.sql").read_text())
        conn.execute((root / "dev/oracle2/grant-postgres.sql").read_text())
        for index, (source_id, draft_id, filename, text) in enumerate(
                ((source_ids[0], draft_ids[0], "intake.txt", DOC_ONE),
                 (source_ids[1], draft_ids[1], "review.txt", DOC_TWO))):
            conn.execute("INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) "
                         "VALUES (%s,%s,%s,%s,'text/plain','confirmed')",
                         (source_id, WORKSPACE, ACTOR, filename))
            conn.execute("INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) "
                         "VALUES (%s,%s,%s,0,'original',%s,0,%s)",
                         (uuid4(), source_id, WORKSPACE, text, len(text)))
            conn.execute("INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) "
                         "VALUES (%s,%s,%s,%s,%s,'confirmed')",
                         (draft_id, source_id, WORKSPACE, ACTOR, f"Synthetic process {index + 1}"))
    key = Ed25519PrivateKey.generate()
    os.environ["ORACLE2_OWNER_PUBLIC_KEY"] = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw).hex()
    appointment = uuid4()
    message = f"oracle2-owner-appointment-v1:{WORKSPACE}:{OWNER}:{appointment}".encode()
    appoint_owner(admin_url, workspace_id=WORKSPACE, owner_id=OWNER, appointed_by=uuid4(),
                  appointment_id=appointment, owner_signature_hex=key.sign(message).hex())
    delegate(admin_url, workspace_id=WORKSPACE, grantor_id=OWNER, actor_id=ACTOR, scope="review")
    with psycopg.connect(admin_url) as conn:
        revision_rows = conn.execute(
            "SELECT s.source_id,s.revision,d.updated_at FROM oracle2.sources s "
            "JOIN oracle2.drafts d ON d.source_id=s.source_id WHERE s.workspace_id=%s",
            (WORKSPACE,)).fetchall()
    revision_map = {row[0]: f"{row[1]}:{row[2].isoformat()}" for row in revision_rows}
    revisions = tuple(revision_map[source_id] for source_id in source_ids)
    return (admin_url.replace("oracle2_admin:oracle2_local_admin_only",
                              "oracle2_holistic:oracle2_local_holistic_only"), revisions)


async def _build(graph_url: str, source_ids: tuple[UUID, UUID], revisions: tuple[str, str]):
    first = _source(source_ids[0], "intake.txt", DOC_ONE, revisions[0])
    second = _source(source_ids[1], "review.txt", DOC_TWO, revisions[1])
    corpus = Corpus(workspace_id=WORKSPACE, sources=(first, second),
                    expected_source_ids=frozenset(source_ids))
    request = ProcessingRequest(provider="local-synthetic", account="loopback", endpoint=graph_url,
                                data_classes=frozenset({"synthetic"}), purpose="holistic-browser-fixture",
                                terms_hash="b" * 64)
    approval = ProcessingApproval(**request.model_dump(), register_ref="loopback-fixture",
                                  expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    def factory(current):
        llm = FixedLLM(str(first.source_id), str(second.source_id))
        return HolisticGraphPilot(current, graph_url, AdmittedLLM(llm, request, [approval], CallBudget(64)),
                                  AdmittedEmbedder(FixedEmbedder(), request, [approval], CallBudget(64)),
                                  config_id="holistic-browser-fixture-v1", dimensions=4)
    pilot = factory(corpus)
    proof = await pilot.build()
    await pilot.close()
    holistic_runtime.make_pilot = factory
    return proof


class TriggerHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/v1/tasks/oracle2-holistic-answer/trigger":
            self.send_error(404)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
            payload = body.get("payload") if isinstance(body, dict) else None
            if isinstance(payload, str):
                payload = json.loads(payload)
            if isinstance(payload, dict) and set(payload) == {"json"}:
                payload = payload["json"]
            if not isinstance(payload, dict) or set(payload) != {"runId", "workspaceId", "corpusDigest"}:
                raise ValueError("opaque identifiers only")
            receipt = f"run_synthetic_{uuid4().hex}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": receipt}).encode())
            def worker():
                try:
                    asyncio.run(holistic_runtime.execute("answer", payload))
                except Exception as error:
                    with psycopg.connect(os.environ["ORACLE2_DATABASE_URL"]) as conn:
                        conn.execute("UPDATE oracle2.runs SET status='error', error=%s, updated_at=now() "
                                     "WHERE run_id=%s AND workspace_id=%s AND status IN ('pending','processing')",
                                     (f"synthetic fixture failed: {type(error).__name__}", UUID(payload["runId"]), UUID(payload["workspaceId"])))
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            self.send_error(400)

    def log_message(self, format, *args):
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-url", default=os.environ.get("ORACLE2_TEST_ADMIN_URL", ""))
    parser.add_argument("--falkordb-url", default=os.environ.get("ORACLE2_TEST_FALKORDB_URL", ""))
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    if not args.admin_url or not args.falkordb_url:
        parser.error("admin and FalkorDB loopback URLs are required")
    _require_loopback(args.admin_url); _require_loopback(args.falkordb_url)
    parsed = urlsplit(args.admin_url)
    if (parsed.username != "oracle2_admin" or parsed.password != "oracle2_local_admin_only"
            or parsed.path != "/oracle2"):
        raise PermissionError("fixture requires the published synthetic local admin identity")
    source_ids, draft_ids = (uuid4(), uuid4()), (uuid4(), uuid4())
    holistic_url, revisions = _seed_database(args.admin_url, source_ids, draft_ids)
    proof = asyncio.run(_build(args.falkordb_url, source_ids, revisions))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), TriggerHandler)
    trigger_url = f"http://127.0.0.1:{server.server_port}"
    os.environ.update({
        "ORACLE2_ENVIRONMENT": "preview", "ORACLE2_DATABASE_URL": holistic_url,
        "ORACLE2_CANDIDATE_GRAPH_URL": args.falkordb_url,
        "ORACLE2_HOLISTIC_WORKSPACE_ID": str(WORKSPACE),
        "ORACLE2_HOLISTIC_SOURCE_IDS": json.dumps([str(x) for x in source_ids]),
        "ORACLE2_HOLISTIC_CORPUS_DIGEST": proof["corpus_digest"],
        "ORACLE2_HOLISTIC_CONFIG_ID": "holistic-browser-fixture-v1",
    })
    env = {
        "ORACLE2_DATABASE_URL": args.admin_url.replace("oracle2_admin:oracle2_local_admin_only",
                            "oracle2_pilot_web:oracle2_local_pilot_web_only"),
        "ORACLE2_PILOT_TOKEN": "synthetic-browser-token",
        "ORACLE2_PILOT_ACTOR": str(ACTOR), "ORACLE2_PILOT_WORKSPACE_ID": str(WORKSPACE),
        "ORACLE2_HOLISTIC_TRIGGER_SECRET_KEY": "synthetic-trigger-secret",
        "ORACLE2_HOLISTIC_CORPUS_DIGEST": proof["corpus_digest"],
        "ORACLE2_HOLISTIC_WORKSPACE_ID": str(WORKSPACE), "ORACLE2_HOLISTIC_SOURCE_IDS": json.dumps([str(x) for x in source_ids]),
        "ORACLE2_HOLISTIC_CONFIG_ID": "holistic-browser-fixture-v1", "TRIGGER_API_URL": trigger_url,
        "TRIGGER_ACCESS_TOKEN": "synthetic-trigger-secret", "ORACLE2_HOLISTIC_FIXTURE_SOURCE_ID": str(source_ids[0]),
        "ORACLE2_HOLISTIC_FIXTURE_DRAFT_ID": str(draft_ids[0]), "ORACLE2_HOLISTIC_FIXTURE_SOURCE_IDS": json.dumps([str(x) for x in source_ids]),
    }
    target = Path(args.env_file); target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write("\n".join(f"{key}={json.dumps(value)}" for key, value in env.items()) + "\n")
    print(json.dumps({"ready": True, "workspaceId": str(WORKSPACE), "corpusDigest": proof["corpus_digest"],
                      "triggerApiUrl": trigger_url, "envFile": str(target)}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
