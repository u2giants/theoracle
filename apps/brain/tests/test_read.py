"""Step 3 gate: reading, page images, chunking and embeddings.

One test per source format, plus the named vision test and the queued-to-read
proof the step-2 page walkthrough was deferred to (plan step 3 done-when).
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import psycopg
import pytest
from conftest import (
    FIXTURES_DIR,
    fake_embeddings,
    fake_vision,
)
from fastapi.testclient import TestClient
from fixtures.build_fixtures import build_pdf

from brain.read.chunk import WINDOW_TOKENS
from brain.read.image import read_image
from brain.read.office import read_docx, read_pptx, read_xlsx
from brain.read.pdf import read_pdf
from brain.read.pipeline import handle_read_source, read_chunks
from brain.read.transcript import parse_turns, read_transcript

CONTENT_TYPES_PPTX = """<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>
"""

RELS_ROOT = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>
"""

PRESENTATION = """<?xml version="1.0"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rId1"/>
    <p:sldId id="257" r:id="rId2"/>
  </p:sldIdLst>
</p:presentation>
"""

PRESENTATION_RELS = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/>
</Relationships>
"""


def _slide_xml(paragraphs: list[str]) -> str:
    runs = "".join(
        f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p>" for text in paragraphs
    )
    return (
        '<?xml version="1.0"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        f"<p:cSld><p:spTree>{runs}</p:spTree></p:cSld>"
        "</p:sld>"
    )


def build_pptx(slide_paragraphs: list[list[str]], picture: bytes | None = None) -> bytes:
    """Return a minimal two-slide .pptx; slide 2 carries ``picture`` if given."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_PPTX)
        archive.writestr("_rels/.rels", RELS_ROOT)
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/_rels/presentation.xml.rels", PRESENTATION_RELS)
        archive.writestr("ppt/slides/slide1.xml", _slide_xml(slide_paragraphs[0]))
        archive.writestr("ppt/slides/slide2.xml", _slide_xml(slide_paragraphs[1]))
        if picture is not None:
            archive.writestr(
                "ppt/slides/_rels/slide2.xml.rels",
                '<?xml version="1.0"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                'Target="../media/image1.png"/>'
                "</Relationships>",
            )
            archive.writestr("ppt/media/image1.png", picture)
    return buffer.getvalue()


def build_blank_page_pdf(first_page: str) -> bytes:
    """Return a two-page PDF whose second page has no text at all."""
    lines = [first_page[index : index + 60] for index in range(0, len(first_page), 60)]
    return build_pdf([lines, []])


def test_pdf_yields_page_chunks() -> None:
    """The fixture PDF yields one chunk per page, with page locators."""
    data = (FIXTURES_DIR / "licensing-approval-procedure.pdf").read_bytes()
    chunks = read_pdf(data)
    assert len(chunks) == 3
    assert [chunk.locator for chunk in chunks] == [
        {"page": 1},
        {"page": 2},
        {"page": 3},
    ]
    assert all(chunk.token_count <= WINDOW_TOKENS for chunk in chunks)
    assert "Licensing Approval Procedure" in chunks[0].text
    assert "4. Procedure" in chunks[1].text
    assert "6. Exceptions" in chunks[2].text


def test_blank_pdf_page_uses_vision(monkeypatch) -> None:
    """A page with no native text goes to the vision reader.

    The vision client is mocked with a recorded response under
    ``tests/fixtures/recorded/``; its output replaces the empty page text and
    the chunk locator then carries ``visual: true``.
    """
    calls = fake_vision(monkeypatch, "vision_blank_page.json")
    data = build_blank_page_pdf(
        "Step 3 read proof page one holds enough native text to stay off the "
        "vision path entirely and land as its own page chunk. It repeats the "
        "service standard: licensor sign-off is expected within five business "
        "days of submission, and the Licensing Manager escalates on day six to "
        "the licensor account manager when nothing has come back yet."
    )
    chunks = read_pdf(data)
    assert len(calls) == 1
    assert len(chunks) == 2
    assert chunks[0].locator == {"page": 1}
    assert "native text" in chunks[0].text
    assert chunks[1].locator == {"page": 2, "visual": True}
    assert "Approved by J. Smith 2026-03-14" in chunks[1].text


MIXED_PAGE_LINES = [
    "Sample hand-off between the design room and the licensing desk.",
    "The designer uploads the artwork and records the style number.",
    "The licensing desk checks the artwork against the style guide.",
    "Rejected artwork returns to the designer with written reasons.",
    "Approved artwork moves to the buyer, who may then release the order.",
    "The drawing below shows the same hand-off as boxes and arrows.",
]


def build_text_and_drawing_pdf(lines: list[str]) -> bytes:
    """Return a one-page PDF with text lines above a large filled drawing.

    The drawing is a 400 x 300 point rectangle on a 612 x 792 page (about a
    quarter of the page), standing in for a diagram on a text page.
    """
    operations = ["BT", "/F1 11 Tf", "72 740 Td"]
    for index, line in enumerate(lines):
        if index:
            operations.append("0 -15 Td")
        operations.append(f"({line}) Tj")
    operations += ["ET", "0.8 g", "100 100 400 300 re", "f"]
    stream = "\n".join(operations).encode("latin-1")
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(bodies) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def test_mixed_page_text_and_diagram_both_read(monkeypatch) -> None:
    """A page with plenty of text AND a large drawing is read both ways.

    The page's own text stays, and the vision description of the drawing is
    appended to it (repair plan A6); before, 200 characters of text kept the
    page off the vision reader and the diagram was lost.
    """
    calls = fake_vision(monkeypatch, "vision_flowchart.json")
    data = build_text_and_drawing_pdf(MIXED_PAGE_LINES)
    chunks = read_pdf(data)
    assert len(calls) == 1
    text = "\n".join(chunk.text for chunk in chunks)
    assert len("".join(MIXED_PAGE_LINES)) > 200
    for line in MIXED_PAGE_LINES:
        assert line in text
    assert "FLOWCHART (swimlanes: Design, Licensing, Buyer)." in text
    assert "->" in text
    assert text.index(MIXED_PAGE_LINES[0]) < text.index("FLOWCHART")
    assert all(chunk.locator == {"page": 1, "visual": True} for chunk in chunks)


def test_text_only_page_stays_off_vision(monkeypatch) -> None:
    """A text page with no drawing is still read without the vision reader."""
    calls = fake_vision(monkeypatch, "vision_flowchart.json")
    data = (FIXTURES_DIR / "licensing-approval-procedure.pdf").read_bytes()
    chunks = read_pdf(data)
    assert calls == []
    assert all("visual" not in chunk.locator for chunk in chunks)


def test_unreadable_regions_recorded(
    client: TestClient,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
    monkeypatch,
    db,
) -> None:
    """What the vision reader could not read is stored on the source.

    The notes land in ``cmap.source.read_notes->'unreadable_regions'`` as
    ``{locator, note}`` objects and the source page's endpoint returns them.
    """
    from brain.read import vision

    note = "Handwritten margin note beside the second box is illegible."

    def _post_chat(messages, settings):
        del messages, settings
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "page_text": "Design room to licensing desk",
                                "diagram": None,
                                "unreadable_regions": note,
                            }
                        )
                    }
                }
            ],
            "usage": {"total_tokens": 20},
        }

    monkeypatch.setattr(vision, "_post_chat", _post_chat)
    fake_embeddings(monkeypatch)

    response = client.post(
        "/sources",
        headers=admin_headers,
        files={
            "file": (
                "design-handoff.pdf",
                build_text_and_drawing_pdf(MIXED_PAGE_LINES),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 200, response.text
    job_id, source_id = db.execute(
        "SELECT id::text, payload->>'source_id' FROM cmap.job WHERE kind = 'read_source'"
    ).fetchone()
    before = db.execute(
        "SELECT read_notes FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    assert before[0] == {}

    handle_read_source(
        {"id": job_id, "kind": "read_source", "payload": {"source_id": source_id}}
    )

    regions = db.execute(
        "SELECT read_notes->'unreadable_regions' FROM cmap.source WHERE id = %s",
        (source_id,),
    ).fetchone()[0]
    assert regions == [{"locator": {"page": 1}, "note": note}]

    body = client.get(f"/sources/{source_id}/chunks", headers=user_headers).json()
    assert body["source"]["read_notes"] == {"unreadable_regions": regions}
    assert any("Design room to licensing desk" in c["text"] for c in body["chunks"])


def test_image_flowchart_renders_edges(monkeypatch) -> None:
    """The flowchart PNG becomes one chunk of rendered ``->`` diagram edges."""
    calls = fake_vision(monkeypatch, "vision_flowchart.json")
    data = (FIXTURES_DIR / "licensing-approval-flowchart.png").read_bytes()
    chunks = read_image(data)
    assert len(calls) == 1
    assert len(chunks) == 1
    text = chunks[0].text
    assert "->" in text
    assert "Licensor" in text
    assert "Jessica" in text
    assert "FLOWCHART (swimlanes: Design, Licensing, Buyer)." in text
    assert chunks[0].locator == {"image": True, "visual": True}


def test_docx_paragraphs_chunked() -> None:
    """The fixture DOCX reads into paragraph-range chunks."""
    data = (FIXTURES_DIR / "sample-room-checklist.docx").read_bytes()
    chunks = read_docx(data)
    assert len(chunks) == 1
    assert chunks[0].locator == {"paragraph": "1-23"}
    assert "Sample Room Checklist" in chunks[0].text
    assert "provisional release" in chunks[0].text


def test_xlsx_sheet_range_chunks() -> None:
    """The fixture XLSX reads into sheet/range chunks with a row overlap.

    The sheet holds 19 rows (~635 tokens): one 400-token window, then a second
    window repeating rows 11-12 so the 60-token overlap is visible in the
    ranges.
    """
    data = (FIXTURES_DIR / "open-po-exceptions.xlsx").read_bytes()
    chunks = read_xlsx(data)
    assert [chunk.locator for chunk in chunks] == [
        {"sheet": "Exceptions", "range": "A1:H12"},
        {"sheet": "Exceptions", "range": "A11:H19"},
    ]
    assert "PO-24118" in chunks[0].text
    assert "Awaiting licensor sign-off" in chunks[0].text
    assert "PO-24213" in chunks[1].text


def test_pptx_slide_chunks() -> None:
    """PPTX text is chunked per slide with slide locators."""
    data = build_pptx(
        [
            ["Spring program status", "Twelve POs are waiting on sign-off"],
            ["Next steps", "Escalate to the licensor account manager"],
        ]
    )
    chunks = read_pptx(data)
    assert [chunk.locator for chunk in chunks] == [{"slide": 1}, {"slide": 2}]
    assert "Twelve POs are waiting" in chunks[0].text
    assert "Escalate to the licensor" in chunks[1].text


def test_pptx_slide_with_picture_uses_vision(monkeypatch) -> None:
    """A PPTX slide with a picture sends that picture to the vision reader."""
    calls = fake_vision(monkeypatch, "vision_flowchart.json")
    picture = (FIXTURES_DIR / "licensing-approval-flowchart.png").read_bytes()
    data = build_pptx([["Title slide"], ["Flow behind the delay"]], picture=picture)
    chunks = read_pptx(data)
    assert len(calls) == 1
    assert chunks[0].locator == {"slide": 1}
    assert chunks[1].locator == {"slide": 2, "visual": True}
    assert "->" in chunks[1].text
    assert "Record sign-off (Jessica)" in chunks[1].text


def test_svg_image_reads_its_text() -> None:
    """An SVG has no rasteriser here, so its visible text is read instead."""
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        b"<text x=\"10\" y=\"20\">Licensor approval</text>"
        b"<text x=\"10\" y=\"40\">Record sign-off</text>"
        b"</svg>"
    )
    chunks = read_image(svg)
    assert len(chunks) == 1
    assert "Licensor approval" in chunks[0].text
    assert "Record sign-off" in chunks[0].text
    assert chunks[0].locator == {"image": True}


def test_text_windows() -> None:
    """Plain text becomes 400-token windows with 60-token overlap."""
    sentence = (
        "The buyer cannot release the purchase order until the artwork log "
        "shows the licensor sign-off date for the program. "
    )
    chunks = read_chunks("text", (sentence * 40).encode("utf-8"))
    assert len(chunks) >= 2
    assert all(chunk.locator == {} for chunk in chunks)
    assert all(chunk.token_count <= WINDOW_TOKENS for chunk in chunks)
    assert chunks[1].text[:25] in chunks[0].text


def test_transcript_turn_chunks() -> None:
    """The fixture transcript yields one chunk per speaker run, with speakers.

    The fixture holds 300 single-line turns; consecutive turns from the same
    speaker merge (plan step 3, transcript.py), which on this file is 246 runs.
    The step text's "~60" counted on multi-line turns; see the PR note.
    """
    text = (FIXTURES_DIR / "teams-approval-2026-03-14.txt").read_text(encoding="utf-8")
    chunks = read_transcript(text)
    assert len(chunks) == 246
    assert all(chunk.locator["turn"] >= 1 for chunk in chunks)
    assert all(chunk.locator["speaker"] in {"Ilona", "Marco"} for chunk in chunks)
    assert all(
        chunk.text.startswith(f"{chunk.locator['speaker']}: ") for chunk in chunks
    )
    assert "Jessica" in chunks[3].text
    assert all(chunk.token_count <= WINDOW_TOKENS for chunk in chunks)


def test_transcript_json_and_vtt_normalise() -> None:
    """Recall.ai JSON and VTT inputs both normalise into turns with speakers."""
    recall = json.dumps(
        [
            {
                "participant": {"id": 3, "name": "Ilona"},
                "words": [
                    {"text": "Morning", "start_timestamp": 2.0},
                    {"text": "Marco.", "start_timestamp": 2.4},
                ],
            },
            {
                "participant": {"id": 7, "name": "Marco"},
                "words": [{"text": "Morning.", "start_timestamp": 5.5}],
            },
        ]
    )
    turns = parse_turns(recall)
    assert turns[0].speaker == "Ilona"
    assert turns[0].t0 == "00:00:02"
    assert turns[0].text == "Morning Marco."
    assert turns[1].speaker == "Marco"

    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:04.000\n"
        "<v Ilona>Which approval do you mean?\n\n"
        "00:00:04.200 --> 00:00:07.000\n"
        "Marco: The licensor sign-off.\n"
    )
    turns = parse_turns(vtt)
    assert turns[0].speaker == "Ilona"
    assert turns[0].text == "Which approval do you mean?"
    assert turns[1].speaker == "Marco"
    assert turns[1].t0 == "00:00:04"


def test_five_fixtures_reach_read_state(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
    db,
) -> None:
    """The five fixtures go from ``queued`` to ``read`` through the read job.

    This is the deferred step-2 proof: the same endpoints the ``/map/sources``
    page calls, then the ``read_source`` handler end to end. Model calls are
    the recorded vision responses and a deterministic embeddings fake.
    """
    fake_vision(monkeypatch, "vision_flowchart.json")
    fake_embeddings(monkeypatch)

    for name in [
        "licensing-approval-procedure.pdf",
        "licensing-approval-flowchart.png",
        "sample-room-checklist.docx",
        "open-po-exceptions.xlsx",
    ]:
        data = (FIXTURES_DIR / name).read_bytes()
        response = client.post(
            "/sources",
            headers=admin_headers,
            files={"file": (name, data, "application/octet-stream")},
        )
        assert response.status_code == 200, response.text
    transcript = (FIXTURES_DIR / "teams-approval-2026-03-14.txt").read_text(
        encoding="utf-8"
    )
    response = client.post(
        "/sources/transcript",
        headers=admin_headers,
        json={"text": transcript, "title": "Teams approval 2026-03-14"},
    )
    assert response.status_code == 200, response.text

    queued = db.execute(
        "SELECT id::text, payload->>'source_id' FROM cmap.job "
        "WHERE kind = 'read_source' ORDER BY created_at"
    ).fetchall()
    assert len(queued) == 5
    states_before = db.execute(
        "SELECT count(*) FROM cmap.source WHERE read_state = 'queued'"
    ).fetchone()
    assert states_before[0] == 5

    for job_id, source_id in queued:
        handle_read_source(
            {
                "id": job_id,
                "kind": "read_source",
                "payload": {"source_id": source_id},
            }
        )

    rows = db.execute(
        "SELECT kind, read_state, read_error FROM cmap.source ORDER BY kind"
    ).fetchall()
    assert [(kind, state) for kind, state, _ in rows] == [
        ("docx", "extracting"),
        ("image", "extracting"),
        ("pdf", "extracting"),
        ("transcript", "extracting"),
        ("xlsx", "extracting"),
    ]
    assert all(error is None for _, _, error in rows)

    per_kind = dict(
        db.execute(
            "SELECT s.kind, count(c.id) FROM cmap.source s "
            "JOIN cmap.chunk c ON c.source_id = s.id GROUP BY s.kind"
        ).fetchall()
    )
    assert per_kind["pdf"] == 3
    assert per_kind["image"] == 1
    assert per_kind["transcript"] == 246
    assert per_kind["docx"] == 1
    assert per_kind["xlsx"] == 2

    extraction_jobs = db.execute(
        "SELECT count(*) FROM cmap.job WHERE kind = 'classify_extract'"
    ).fetchone()
    assert extraction_jobs[0] == 5

    usage_rows = db.execute(
        "SELECT payload->'usage' FROM cmap.job WHERE kind = 'read_source'"
    ).fetchall()
    assert all(usage is not None for (usage,) in usage_rows)

    embedded = db.execute(
        "SELECT count(*) FROM cmap.chunk WHERE embedding IS NOT NULL"
    ).fetchone()
    assert embedded[0] == sum(per_kind.values())


def test_source_with_no_content_is_failed_not_read(
    db: psycopg.Connection,
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repair A2/A7: a source that yields no passages is never shown as read."""
    fake_embeddings(monkeypatch)
    storage.upload("test/empty.txt", b"   \n\n  ", "text/plain")
    source_id = str(
        db.execute(
            "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes) "
            "VALUES ('text', 'empty', 'test/empty.txt', 'empty-sha', 7) RETURNING id"
        ).fetchone()[0]
    )
    db.commit()
    handle_read_source({"id": None, "payload": {"source_id": source_id}})
    state, error = db.execute(
        "SELECT read_state, read_error FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    assert (state, error) == ("failed", "no readable content")
    assert (
        db.execute(
            "SELECT count(*) FROM cmap.job WHERE kind = 'classify_extract'"
        ).fetchone()[0]
        == 0
    )
