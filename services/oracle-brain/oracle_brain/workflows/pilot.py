"""Pilot journey workflow: ingest, draft, correct, confirm, question, answer."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from ..authz import has_authority
from ..consultant.pilot import PilotAnswer, answer_question
from ..ingest.document import parse_text_to_blocks
from ..knowledge.authority import confirm_draft, correct_draft
from ..retrieval.pilot import retrieve_spans


@dataclass(frozen=True)
class JourneyResult:
    source_id: UUID
    draft_id: UUID
    run_id: UUID
    answer: PilotAnswer


def upload_source(database_url: str, *, workspace_id: UUID, actor_id: UUID,
                  filename: str, content_type: str, text: str) -> tuple[UUID, list[dict]]:
    """Ingest a document and return the source ID and parsed blocks."""
    source_id = uuid4()
    blocks = parse_text_to_blocks(text, source_id=source_id)
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute(
                """INSERT INTO oracle2.sources
                   (source_id,workspace_id,uploaded_by,filename,content_type,status)
                   VALUES (%s,%s,%s,%s,%s,'draft')""",
                (source_id, workspace_id, actor_id, filename, content_type),
            )
            for block in blocks:
                connection.execute(
                    """INSERT INTO oracle2.source_blocks
                       (block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (block.block_id, source_id, workspace_id, block.block_index,
                     block.kind, block.text, block.span_start, block.span_end),
                )
    block_dicts = [
        {"block_id": b.block_id, "source_id": b.source_id,
         "span_start": b.span_start, "span_end": b.span_end, "text": b.text}
        for b in blocks
    ]
    return source_id, block_dicts


def create_draft(database_url: str, *, source_id: UUID, workspace_id: UUID,
                 actor_id: UUID, process_name: str,
                 connections: list[dict]) -> UUID:
    draft_id = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO oracle2.drafts
               (draft_id,source_id,workspace_id,created_by,process_name,connections)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (draft_id, source_id, workspace_id, actor_id, process_name,
             Jsonb(connections)),
        )
    return draft_id


def run_question(database_url: str, *, workspace_id: UUID, actor_id: UUID,
                 source_id: UUID, draft_id: UUID | None, question: str) -> JourneyResult:
    """Execute a question against confirmed or draft knowledge and return a cited answer."""
    if not question.strip():
        raise ValueError("question must be non-empty")
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """SELECT block_id,source_id,span_start,span_end,text
               FROM oracle2.source_blocks
               WHERE source_id=%s AND workspace_id=%s
               ORDER BY block_index""",
            (source_id, workspace_id),
        ).fetchall()
    blocks = [
        {"block_id": r[0], "source_id": r[1], "span_start": r[2],
         "span_end": r[3], "text": r[4]}
        for r in rows
    ]
    spans = retrieve_spans(question, blocks)
    answer = answer_question(question, spans)
    run_id = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO oracle2.runs
               (run_id,workspace_id,actor_id,source_id,draft_id,question,status,answer)
               VALUES (%s,%s,%s,%s,%s,%s,'completed',%s)""",
            (run_id, workspace_id, actor_id, source_id, draft_id, question,
             Jsonb({
                 "answer_text": answer.answer_text,
                 "citations": [
                     {"source_id": str(c.source_id), "span_start": c.span_start,
                      "span_end": c.span_end, "quote": c.quote}
                     for c in answer.citations
                 ],
                 "hypothetical": (
                     {"label": answer.hypothetical.label,
                      "description": answer.hypothetical.description,
                      "measure": answer.hypothetical.measure,
                      "missing_inputs": answer.hypothetical.missing_inputs}
                     if answer.hypothetical else None
                 ),
                 "is_established_fact": answer.is_established_fact,
             })),
        )
    return JourneyResult(source_id=source_id, draft_id=draft_id or uuid4(),
                         run_id=run_id, answer=answer)
