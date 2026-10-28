"""Image (diagram) reading: the whole image goes through the vision reader.

Raster diagrams are transcribed with ``prompts/read_visual.md`` and become one
chunk carrying ``image: true`` and ``visual: true``. SVG sources have no
rasteriser in this service, so their visible text is read out instead of the
picture being sent to a model.
"""

from __future__ import annotations

import re

from brain.read.chunk import Chunk, window_chunks
from brain.read.vision import build_visual_text, visual_read

_SVG_TEXT = re.compile(r"<(?:text|tspan)[^>]*>(.*?)</(?:text|tspan)>", re.DOTALL)
_SVG_TAG = re.compile(r"<[^>]+>")


def _media_type(head: bytes) -> str:
    """Return the image media type implied by the leading bytes."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _svg_text(data: bytes) -> str:
    """Return the visible text of an SVG diagram."""
    source = data.decode("utf-8", errors="replace")
    pieces = [match.group(1) for match in _SVG_TEXT.finditer(source)]
    cleaned = [_SVG_TAG.sub("", piece).strip() for piece in pieces]
    return "\n".join(piece for piece in cleaned if piece)


def read_image(data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read one image source into chunks."""
    head = data[:512].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.lower().startswith(b"<svg") or (
        head.lower().startswith(b"<?xml") and b"<svg" in data[:4096].lower()
    ):
        return window_chunks(_svg_text(data), {"image": True})
    visual = visual_read(data, _media_type(data[:16]), usage=usage)
    return window_chunks(
        build_visual_text(visual),
        {"image": True, "visual": True},
    )
