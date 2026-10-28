"""Vision-model transcription of pages and diagrams (plan step 3).

The image is DATA, never instructions; the prompt lives in
``brain/prompts/read_visual.md`` and is loaded at runtime. Model ids come from
the environment only (plan §8) and never appear in this code.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from brain.config import Settings, get_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "read_visual.md"


class VisionError(RuntimeError):
    """Raised when the vision model cannot transcribe a page."""


def load_visual_prompt() -> str:
    """Return the runtime prompt text for visual transcription."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def _post_chat(messages: list[dict[str, Any]], settings: Settings) -> dict[str, Any]:
    """POST one chat-completions request and return the response body."""
    if settings.openrouter_api_key is None:
        raise VisionError("OPENROUTER_API_KEY is not set")
    if settings.brain_vision_model is None:
        raise VisionError("BRAIN_VISION_MODEL is not set")
    response = httpx.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={
            "model": settings.brain_vision_model,
            "messages": messages,
            "temperature": 0,
        },
        timeout=120.0,
    )
    if response.status_code != 200:
        raise VisionError(
            f"vision call failed: {response.status_code} {response.text[:200]}"
        )
    try:
        return response.json()
    except ValueError as exc:
        raise VisionError("vision response is not JSON") from exc


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


def visual_read(
    image_bytes: bytes,
    media_type: str = "image/png",
    settings: Settings | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Transcribe one page image.

    Returns ``{"page_text", "diagram", "unreadable_regions"}`` exactly as the
    prompt specifies. ``usage`` collects token counts when the caller passes a
    dict (plan §11: log tokens per job).
    """
    cfg = settings if settings is not None else get_settings()
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
    return parse_visual_json(content)


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
