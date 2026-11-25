"""AI triage for employee-submitted Company Map correction notes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.llm import message_content, parse_json_reply, post_chat_json_body
from brain.seats import stage_model

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "correction_triage.md"

VALID_SUGGESTED_ACTIONS = frozenset(
    {
        "apply_ideal_policy",
        "apply_observed_practice",
        "needs_clarification",
        "dismiss",
    }
)

MAX_SUMMARY_CHARS = 500
MAX_REASON_CHARS = 500
MAX_CONTEXT_CHARS = 1500
TRIAGE_FALLBACK_STAGES = ("intake_gate", "flat", "relations")


class CorrectionTriageError(RuntimeError):
    """Raised when AI triage cannot produce a valid summary and action."""


def _candidate_models(cfg: Settings) -> list[str]:
    models: list[str] = []
    for stage in TRIAGE_FALLBACK_STAGES:
        model = stage_model(cfg, stage)
        if model and model not in models:
            models.append(model)
    if not models:
        raise CorrectionTriageError("no model configured for correction triage")
    return models


def _parse_triage(raw: str) -> dict[str, str]:
    try:
        parsed = parse_json_reply(raw)
    except ValueError as exc:
        raise CorrectionTriageError(f"correction triage reply is not JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise CorrectionTriageError("correction triage reply must be a JSON object")
    summary = str(parsed.get("summary") or "").strip()[:MAX_SUMMARY_CHARS]
    action = str(parsed.get("suggested_action") or "").strip()
    reason = str(parsed.get("reason") or "").strip()[:MAX_REASON_CHARS]
    if not summary:
        raise CorrectionTriageError("correction triage reply missing summary")
    if action not in VALID_SUGGESTED_ACTIONS:
        raise CorrectionTriageError(
            f"correction triage invalid suggested_action {action!r}"
        )
    if not reason:
        raise CorrectionTriageError("correction triage reply missing reason")
    return {
        "summary": summary,
        "suggested_action": action,
        "reason": reason,
    }


def _load_function_context(conn: Any, function_id: str | None) -> str:
    if not function_id:
        return "(none)"
    row = conn.execute(
        "SELECT title, report_md, findings "
        "FROM cmap.community "
        "WHERE level = 1 AND function_id = %s::uuid "
        "ORDER BY graph_version DESC, created_at DESC LIMIT 1",
        (function_id,),
    ).fetchone()
    if row is None:
        return "(none)"
    title, report_md, findings = row
    parts: list[str] = []
    if title:
        parts.append(str(title).strip())
    if report_md:
        parts.append(str(report_md).strip())
    if isinstance(findings, list):
        for item in findings[:5]:
            if isinstance(item, dict) and item.get("text"):
                parts.append(f"- {str(item['text']).strip()}")
    joined = "\n".join(part for part in parts if part)
    return joined[:MAX_CONTEXT_CHARS] or "(none)"


def triage_correction_note(
    note_id: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Generate and persist an AI summary + suggested action for one correction note."""
    cfg = settings if settings is not None else get_settings()
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT cn.id::text, cn.function_id::text, COALESCE(f.name, 'Company-wide'), "
            "COALESCE(cn.page_ref, '(none)'), cn.what_is_wrong, cn.correction_text "
            "FROM cmap.correction_note cn "
            "LEFT JOIN cmap.function f ON f.id = cn.function_id "
            "WHERE cn.id = %s::uuid",
            (note_id,),
        ).fetchone()
        if row is None:
            return {"skipped": True}
        _cid, function_id, function_name, page_ref, what_is_wrong, correction_text = row
        existing_context = _load_function_context(conn, function_id)

    template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template.replace("{{department}}", str(function_name or "Company-wide"))
        .replace("{{page_ref}}", str(page_ref or "(none)"))
        .replace("{{what_is_wrong}}", str(what_is_wrong or ""))
        .replace("{{correction_text}}", str(correction_text or ""))
        .replace("{{existing_context}}", existing_context)
    )
    models = _candidate_models(cfg)
    triage: dict[str, str] | None = None
    last_exc: Exception | None = None
    for model in models:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 800,
        }
        try:
            body = post_chat_json_body(
                payload,
                settings=cfg,
                timeout=45.0,
                error_cls=CorrectionTriageError,
                label="correction_triage",
                parse=_parse_triage,
            )
            triage = _parse_triage(message_content(body))
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "correction triage candidate model %r failed for %s: %s",
                model,
                note_id,
                str(exc)[:300],
            )
    if triage is None:
        err_msg = str(last_exc)[:500] if last_exc is not None else "triage failed"
        logger.warning("correction triage failed for %s: %s", note_id, err_msg)
        with get_pool().connection() as conn:
            conn.execute(
                "UPDATE cmap.correction_note "
                "SET ai_triage_error = %s "
                "WHERE id = %s::uuid",
                (err_msg, note_id),
            )
            conn.commit()
        if isinstance(last_exc, CorrectionTriageError):
            raise last_exc
        raise CorrectionTriageError(err_msg) from last_exc

    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.correction_note "
            "SET ai_summary = %s, ai_suggested_action = %s, ai_reason = %s, "
            "ai_triaged_at = now(), ai_triage_error = NULL "
            "WHERE id = %s::uuid",
            (
                triage["summary"],
                triage["suggested_action"],
                triage["reason"],
                note_id,
            ),
        )
        conn.commit()
    return {"note_id": note_id, **triage}


def handle_triage_correction_note(job: dict[str, Any]) -> None:
    """Worker handler for queued ``triage_correction_note`` jobs."""
    payload = job.get("payload") or {}
    note_id = str(payload.get("note_id") or "").strip()
    if not note_id:
        return
    triage_correction_note(note_id)
