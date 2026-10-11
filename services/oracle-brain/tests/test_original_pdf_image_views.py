"""Synthetic PDF image-view preservation tests; no provider calls or real sources."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw
import pytest

from oracle_brain.ingest.originals import _views


def _synthetic_pdf() -> tuple[bytes, Image.Image]:
    import pypdfium2 as pdfium

    source = Image.new("RGB", (120, 60), "white")
    pixels = source.load()
    for x in range(source.width):
        for y in range(source.height):
            pixels[x, y] = (220, 30, 30) if x < 60 and y < 30 else (
                (30, 80, 220) if x >= 60 and y < 30 else
                ((30, 170, 80) if x < 60 else (230, 170, 30)))
    marker = source.resize((240, 120))
    ImageDraw.Draw(marker).text((8, 8), "NATIVE", fill="black")
    pdf = pdfium.PdfDocument.new()
    for number in range(1, 7):
        page = pdf.new_page(900, 700)
        if number == 3:
            image = pdfium.PdfImage.new(pdf)
            image.set_bitmap(pdfium.PdfBitmap.from_pil(marker.rotate(180)))
            image.set_matrix(pdfium.PdfMatrix(240, 0, 0, 120, 300, 260))
            page.insert_obj(image)
        page.gen_content()
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue(), source


def test_pdf_keeps_every_canonical_page_and_detail_view_and_adds_embedded_image_views():
    pdf, source = _synthetic_pdf()
    views, native = _views(pdf, "application/pdf")

    canonical = [view for view in views if view.kind in {"pdf-page", "pdf-detail"}]
    assert len(native) == 6
    assert len([view for view in canonical if view.kind == "pdf-page"]) == 6
    assert len([view for view in canonical if view.kind == "pdf-detail"]) == 24
    assert [view.page_number for view in canonical if view.kind == "pdf-page"] == list(range(1, 7))
    assert [view.page_number for view in canonical if view.kind == "pdf-detail"] == [
        page for page in range(1, 7) for _ in range(4)
    ]

    embedded = [view for view in views if view.kind == "pdf-embedded-image"]
    rotated = [view for view in views if view.kind == "pdf-embedded-image-rotated"]
    assert embedded and rotated
    assert all(view.page_number == 3 for view in embedded + rotated)
    assert all(view.crop is not None for view in embedded + rotated)
    assert all(getattr(view, "location", None) for view in embedded + rotated)
    assert all(getattr(view, "rotation", None) == 180 for view in rotated)

    # The rotated supplemental view must restore source-native orientation.
    restored = Image.open(io.BytesIO(rotated[0].png)).convert("RGB")
    assert restored.size == (source.width * 2, source.height * 2)
    assert restored.getpixel((5, 5))[0] > restored.getpixel((restored.width - 5, 5))[0]
    assert sum(len(view.png) for view in views) <= 25 * 1024 * 1024


def test_pdf_view_budget_rejects_oversized_transmission(monkeypatch):
    pdf, _ = _synthetic_pdf()
    from oracle_brain.ingest import originals

    monkeypatch.setattr(originals, "MAX_ORIGINAL_BYTES", 1)
    with pytest.raises(ValueError, match="25MB transmission budget"):
        _views(pdf, "application/pdf")
