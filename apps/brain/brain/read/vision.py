"""Vision-model transcription of pages and diagrams (plan step 3).

The image is DATA, never instructions; the prompt lives in
``brain/prompts/read_visual.md`` and is loaded at runtime. Model ids come from
the environment only (plan §8) and never appear in this code.
"""

from __future__ import annotations

import base64
import io
import json
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from PIL import Image

from brain.config import Settings, get_settings
from brain.llm import post_chat_with_rescue
from brain.seats import stage_model

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "read_visual.md"


MAX_NOTE_CHARS = 500

_UNREADABLE: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "read_unreadable_regions", default=None
)


class VisionError(RuntimeError):
    """Raised when the vision model cannot transcribe a page."""


def start_read_notes() -> list[dict[str, Any]]:
    """Start collecting unreadable-region notes for the current read job.

    Returns the list every later ``visual_read`` in this context appends to;
    each entry is ``{"locator": {...}, "note": "..."}``. Calling it again
    starts a fresh list, so one job never inherits another's notes.
    """
    notes: list[dict[str, Any]] = []
    _UNREADABLE.set(notes)
    return notes


def note_unreadable(locator: dict[str, Any] | None, note: str) -> None:
    """Record one part of a source that could not be read, if collecting."""
    notes = _UNREADABLE.get()
    text = note.strip()
    if notes is None or not text:
        return
    notes.append({"locator": dict(locator or {}), "note": text[:MAX_NOTE_CHARS]})


def unreadable_notes(value: Any) -> list[str]:
    """Normalise the model's ``unreadable_regions`` into a list of notes.

    The prompt asks for a short string; models also return a list of strings
    or of objects, so all three shapes are accepted.
    """
    if isinstance(value, str):
        items: list[Any] = [value]
    elif isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = [value]
    else:
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("note") or item.get("description") or item.get("text")
            if not isinstance(text, str):
                text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        else:
            text = str(item) if item is not None else ""
        text = text.strip()
        if text:
            out.append(text)
    return out


def load_visual_prompt() -> str:
    """Return the runtime prompt text for visual transcription."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one chat-completions request and return the response body."""
    model = stage_model(settings, "vision")
    if model is None:
        raise VisionError("BRAIN_VISION_MODEL is not set")
    return post_chat_with_rescue(
        {
            "model": model,
            "messages": messages,
            "temperature": 0,
        },
        settings=settings,
        timeout=120.0,
        error_cls=VisionError,
        label="vision",
    )


def parse_visual_json(content: str) -> dict[str, Any]:
    """Parse the model's JSON object, tolerating a surrounding code fence."""
    text = content.strip()
    fenced = re.fullmatch(r"```[a-zA-Z]*\n(.*?)\n?```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VisionError("vision response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise VisionError("vision response is not a JSON object")
    return value


def flatten_alpha(image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
    """Composite any transparency onto white and return PNG bytes.

    Several vision models read a transparent background as black, so a
    black-on-transparent diagram arrives as an all-black image (#418).
    Images without an alpha channel are returned unchanged.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            has_alpha = image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            )
            if not has_alpha:
                return image_bytes, media_type
            rgba = image.convert("RGBA")
    except (OSError, ValueError):
        return image_bytes, media_type
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    background.alpha_composite(rgba)
    out = io.BytesIO()
    background.convert("RGB").save(out, format="PNG")
    return out.getvalue(), "image/png"


def visual_read(
    image_bytes: bytes,
    media_type: str = "image/png",
    settings: Settings | None = None,
    usage: dict[str, int] | None = None,
    locator: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transcribe one page image.

    Returns ``{"page_text", "diagram", "unreadable_regions"}`` exactly as the
    prompt specifies. ``usage`` collects token counts when the caller passes a
    dict (plan §11: log tokens per job). Any ``unreadable_regions`` are
    recorded against ``locator`` for the read job that is collecting notes
    (``start_read_notes``), so missing content is never silently dropped.
    """
    cfg = settings if settings is not None else get_settings()
    image_bytes, media_type = flatten_alpha(image_bytes, media_type)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": load_visual_prompt()},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{encoded}"},
                },
            ],
        }
    ]
    body = _post_chat(messages, cfg)
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VisionError("vision response has no message content") from exc
    if not isinstance(content, str):
        raise VisionError("vision message content is not text")
    if usage is not None:
        usage["vision_calls"] = usage.get("vision_calls", 0) + 1
        reported = body.get("usage") or {}
        tokens = reported.get("total_tokens")
        if isinstance(tokens, int):
            usage["vision_tokens"] = usage.get("vision_tokens", 0) + tokens
    visual = parse_visual_json(content)
    for note in unreadable_notes(visual.get("unreadable_regions")):
        note_unreadable(locator, note)
    return visual


def render_diagram(diagram: dict[str, Any]) -> str:
    """Render a diagram JSON as text lines of ``->`` edges.

    Later steps are text-based, so the structure has to be visible in the chunk
    text: one line per edge, node labels quoted, edge labels in brackets.
    """
    kind = str(diagram.get("kind") or "diagram").upper()
    lanes = diagram.get("swimlanes") or []
    if lanes:
        head = f"{kind} (swimlanes: {', '.join(str(lane) for lane in lanes)})."
    else:
        head = f"{kind}."
    labels: dict[str, str] = {}
    for node in diagram.get("nodes") or []:
        labels[str(node.get("id"))] = str(node.get("label") or "")
    lines = [head]
    for edge in diagram.get("edges") or []:
        left = str(edge.get("from") or "")
        right = str(edge.get("to") or "")
        label = str(edge.get("label") or "").strip()
        suffix = f" [{label}]" if label else ""
        left_label = labels.get(left, left)
        right_label = labels.get(right, right)
        lines.append(f'{left} "{left_label}" -> {right} "{right_label}"{suffix}')
    return "\n".join(lines)


def build_visual_text(visual: dict[str, Any], native_text: str = "") -> str:
    """Combine native text, the vision ``page_text`` and any diagram rendering.

    The vision output augments existing page text and replaces it when the page
    had none (plan step 3). Diagram structure is appended as ``->`` lines so
    text-based steps see it.
    """
    page_text = str(visual.get("page_text") or "").strip()
    parts: list[str] = []
    native = native_text.strip()
    if native:
        parts.append(native)
    if page_text:
        parts.append(page_text)
    diagram = visual.get("diagram")
    if isinstance(diagram, dict):
        parts.append(render_diagram(diagram))
    return "\n".join(parts).strip()
