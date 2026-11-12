"""PDF reading: pypdfium2 text per page, vision for low-text or drawn pages.

A page goes to the vision model (``prompts/read_visual.md``), rendered as a
150 dpi PNG, when it has fewer than 200 characters of native text **or** when
images and vector drawings cover more than ``PAGE_VISION_MIN_GRAPHIC_SHARE``
of its area (repair plan A6: a diagram on a text page is read too). The
vision output is appended to the page's own text, never substituted for it,
and the chunk locator then carries ``visual: true``.
"""

from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image

from brain.read.chunk import Chunk, window_chunks
from brain.read.vision import (
    VisionError,
    build_visual_text,
    note_unreadable,
    visual_read,
)

PAGE_VISION_MIN_CHARS = 200
# Share of the page area that images and vector drawings must cover before a
# page that already has enough text is also sent to the vision reader.
PAGE_VISION_MIN_GRAPHIC_SHARE = 0.15
# A drawn rule or underline is a path too; anything thinner than this in
# either direction (points) is decoration, not a diagram.
GRAPHIC_MIN_SIDE_POINTS = 4.0
GRAPHIC_OBJECT_TYPES = (
    pdfium.raw.FPDF_PAGEOBJ_IMAGE,
    pdfium.raw.FPDF_PAGEOBJ_PATH,
    pdfium.raw.FPDF_PAGEOBJ_SHADING,
)
RENDER_DPI = 150


class PdfReadError(ValueError):
    """Raised when a PDF cannot be opened or read."""


def _render_page_png(page: pdfium.PdfPage) -> bytes:
    """Render one PDF page to PNG bytes at 150 dpi."""
    scale = RENDER_DPI / 72.0
    bitmap = page.render(scale=scale)
    image: Image.Image = bitmap.to_pil()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def graphic_share(page: pdfium.PdfPage) -> float:
    """Return the share of the page covered by images and vector drawings.

    Sums the bounding boxes of image, path and shading objects, each clipped
    to the page, and caps the result at 1.0. Overlapping objects are counted
    more than once, which only errs toward reading a page that has drawings.
    """
    width, height = page.get_size()
    page_area = float(width) * float(height)
    if page_area <= 0:
        return 0.0
    covered = 0.0
    for obj in page.get_objects(filter=GRAPHIC_OBJECT_TYPES):
        left, bottom, right, top = obj.get_bounds()
        box_width = min(right, float(width)) - max(left, 0.0)
        box_height = min(top, float(height)) - max(bottom, 0.0)
        if box_width < GRAPHIC_MIN_SIDE_POINTS or box_height < GRAPHIC_MIN_SIDE_POINTS:
            continue
        covered += box_width * box_height
    return min(covered / page_area, 1.0)


def _new_lines(vision_text: str, native: str) -> str:
    """Drop vision lines that only repeat the page's own text."""
    have = {" ".join(line.split()).casefold() for line in native.splitlines()}
    kept = [
        line
        for line in vision_text.splitlines()
        if line.strip() and " ".join(line.split()).casefold() not in have
    ]
    return "\n".join(kept)


def _read_mixed_page(
    page: pdfium.PdfPage,
    native: str,
    locator: dict[str, object],
    usage: dict[str, int] | None,
) -> str:
    """Read a page that has real text and a diagram: text first, then vision.

    The native text is always kept. If the vision reader fails, the page still
    reads as its text and the gap is recorded as an unreadable region rather
    than failing a document whose text is fine.
    """
    try:
        visual = visual_read(
            _render_page_png(page), "image/png", usage=usage, locator=dict(locator)
        )
    except VisionError as exc:
        note_unreadable(
            dict(locator),
            f"A picture or drawing on this page could not be read ({exc}).",
        )
        return native
    locator["visual"] = True
    described = dict(visual)
    described["page_text"] = _new_lines(str(visual.get("page_text") or ""), native)
    return build_visual_text(described, native)


def read_pdf(data: bytes, usage: dict[str, int] | None = None) -> list[Chunk]:
    """Read every page of ``data`` into chunks with page locators."""
    try:
        document = pdfium.PdfDocument(data)
    except Exception as exc:
        raise PdfReadError("PDF could not be opened") from exc
    chunks: list[Chunk] = []
    try:
        for page_number in range(len(document)):
            page = document[page_number]
            try:
                textpage = page.get_textpage()
                try:
                    native = textpage.get_text_range()
                finally:
                    textpage.close()
                locator: dict[str, object] = {"page": page_number + 1}
                if len(native.strip()) < PAGE_VISION_MIN_CHARS:
                    png = _render_page_png(page)
                    visual = visual_read(
                        png, "image/png", usage=usage, locator=dict(locator)
                    )
                    text = build_visual_text(visual, native)
                    locator["visual"] = True
                elif graphic_share(page) > PAGE_VISION_MIN_GRAPHIC_SHARE:
                    text = _read_mixed_page(page, native, locator, usage)
                else:
                    text = native
                chunks.extend(window_chunks(text, locator))
            finally:
                page.close()
    except PdfReadError:
        raise
    except Exception as exc:
        raise PdfReadError("PDF text extraction failed") from exc
    finally:
        document.close()
    return chunks


def passage_windows(anchor: int, previous: int) -> tuple[int, ...]:
    """Indices of one relation window ending at passage ``anchor`` (plan E1).

    A window is the passage plus the ``previous`` passages before it, in
    full. ``read_pdf`` chunks per page, so a window may span a page break —
    a relation's ends and its quote may come from either side of it.
    """
    return tuple(range(max(0, anchor - previous), anchor + 1))
