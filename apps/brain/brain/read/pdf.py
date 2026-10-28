"""PDF reading: pypdfium2 text per page, vision for low-text pages.

A page with fewer than 200 characters of native text is rendered to a 150 dpi
PNG and sent to the vision model (``prompts/read_visual.md``); the vision
output augments or replaces the page text and the chunk locator then carries
``visual: true`` (plan step 3).
"""

from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image

from brain.read.chunk import Chunk, window_chunks
from brain.read.vision import build_visual_text, visual_read

PAGE_VISION_MIN_CHARS = 200
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
                    visual = visual_read(png, "image/png", usage=usage)
                    text = build_visual_text(visual, native)
                    locator["visual"] = True
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
