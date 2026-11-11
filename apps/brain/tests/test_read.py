"""Step 3 gate: reading, page images, chunking and embeddings.

One test per source format, plus the named vision test and the queued-to-read
proof the step-2 page walkthrough was deferred to (plan step 3 done-when).
"""

from __future__ import annotations

import io
import json
import re
import socket
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from typing import Any

import httpx
import psycopg
import pytest
from conftest import (
    FIXTURES_DIR,
    fake_embeddings,
    fake_vision,
)
from fastapi.testclient import TestClient
from fixtures.build_fixtures import build_pdf
from fixtures.build_office_fixtures import (
    LARGE_SHEET_COLUMNS,
    LARGE_SHEET_HEADER,
    LARGE_SHEET_ROWS,
    build_chart_pptx,
    build_hyperlink_docx,
    build_large_sheet_xlsx,
    docx_paragraph,
    docx_picture,
    docx_table,
    pptx_slide,
)
from fixtures.build_office_fixtures import build_docx as build_office_docx
from fixtures.build_office_fixtures import build_pptx as build_office_pptx
from fixtures.build_office_fixtures import build_xlsx as build_office_xlsx
from PIL import Image

from brain.read import detect, office, vision
from brain.read.chunk import WINDOW_TOKENS
from brain.read.image import read_image
from brain.read.office import PICTURE_GAP, read_docx, read_pptx, read_xlsx
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


# --------------------------------------------------------------------------
# Repair plan A4, A5 and A7 (PPTX pictures)
# --------------------------------------------------------------------------


def _table_cells(line: str) -> list[str]:
    """Split one Markdown table line into its cells."""
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:-1]]


def _refuse_network(monkeypatch) -> list[str]:
    """Make every network entry point fail loudly; return the attempt log."""
    attempts: list[str] = []

    def refuse(name: str):
        def _refused(*args, **kwargs):
            del args, kwargs
            attempts.append(name)
            raise AssertionError(f"network call attempted through {name}")

        return _refused

    monkeypatch.setattr(socket.socket, "connect", refuse("socket.connect"))
    monkeypatch.setattr(socket, "create_connection", refuse("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", refuse("socket.getaddrinfo"))
    monkeypatch.setattr(urllib.request, "urlopen", refuse("urllib.urlopen"))
    monkeypatch.setattr(httpx.Client, "send", refuse("httpx.Client.send"))
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse("httpx.AsyncClient.send"))
    return attempts


def _rezip(data: bytes, changes: dict[str, bytes]) -> bytes:
    """Return the zip ``data`` with the members in ``changes`` replaced or added."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        with zipfile.ZipFile(buffer, "w") as archive:
            for name in source.namelist():
                if name not in changes:
                    archive.writestr(name, source.read(name))
            for name, content in changes.items():
                archive.writestr(name, content)
    return buffer.getvalue()


def test_office_fixtures_with_links_and_charts_read(monkeypatch) -> None:
    """Files with a hyperlink, a chart or 40k cells each read to chunks (A4)."""
    calls = fake_vision(monkeypatch, "vision_flowchart.json")
    docx = read_docx((FIXTURES_DIR / "with_hyperlink.docx").read_bytes())
    assert len(docx) > 0
    assert "licensor portal" in docx[0].text
    pptx = read_pptx((FIXTURES_DIR / "with_chart.pptx").read_bytes())
    assert len(pptx) > 0
    assert "Twelve POs were waiting" in pptx[0].text
    xlsx = read_xlsx((FIXTURES_DIR / "large_sheet.xlsx").read_bytes())
    assert len(xlsx) > 0
    assert calls == []


def test_office_fixtures_match_their_builder() -> None:
    """The committed Office fixtures are exactly what the builder writes."""
    assert (FIXTURES_DIR / "with_hyperlink.docx").read_bytes() == build_hyperlink_docx()
    assert (FIXTURES_DIR / "with_chart.pptx").read_bytes() == build_chart_pptx()
    assert (FIXTURES_DIR / "large_sheet.xlsx").read_bytes() == build_large_sheet_xlsx()


def test_external_relationship_never_fetched(monkeypatch) -> None:
    """External links are ignored: the file is read and nothing is fetched.

    Covers a hyperlink and a linked (not embedded) picture in a DOCX, a
    linked picture in a PPTX and a linked workbook in an XLSX. Every network
    entry point is patched to fail, and the vision reader is never handed a
    linked picture.
    """
    attempts = _refuse_network(monkeypatch)
    calls = fake_vision(monkeypatch, "vision_flowchart.json")

    docx = build_office_docx(
        docx_paragraph("Sign-off steps are on the portal.")
        + docx_picture("rId8", linked=True)
        + docx_paragraph("Escalate on day six."),
        [
            ("rId7", "hyperlink", "https://portal.example.com/style-guide", True),
            ("rId8", "image", "https://portal.example.com/flow.png", True),
        ],
    )
    chunks = read_docx(docx)
    assert len(chunks) == 1
    assert "Sign-off steps are on the portal." in chunks[0].text
    assert PICTURE_GAP in chunks[0].text
    assert "Escalate on day six." in chunks[0].text

    pptx = build_office_pptx(
        pptx_slide(["Linked picture slide"]),
        [
            ("rId2", "image", "https://portal.example.com/flow.png", True),
            ("rId3", "hyperlink", "https://portal.example.com/", True),
        ],
    )
    chunks = read_pptx(pptx)
    assert [chunk.locator for chunk in chunks] == [{"slide": 1}]
    assert "Linked picture slide" in chunks[0].text

    xlsx = build_office_xlsx(
        [["PO", "Status"], ["PO-1", "Open"]],
        extra_relations=[
            ("rId9", "externalLinkPath", "https://portal.example.com/book.xlsx", True)
        ],
    )
    chunks = read_xlsx(xlsx)
    assert len(chunks) == 1
    assert "| PO-1 | Open |" in chunks[0].text

    assert attempts == []
    assert calls == []


def test_embedded_object_is_skipped_not_parsed() -> None:
    """A member under ``embeddings/`` does not reject the file and is never opened."""
    data = (FIXTURES_DIR / "with_chart.pptx").read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        embedded = [name for name in archive.namelist() if "embeddings/" in name]
    assert embedded == ["ppt/embeddings/Microsoft_Excel_Sheet1.xlsx"]
    package = office._Package(data)
    try:
        assert embedded[0] not in package.names
        with pytest.raises(office.OfficeReadError):
            package.read(embedded[0])
        assert package.relations("ppt/charts/chart1.xml") == []
    finally:
        package.zip.close()


def test_office_safety_checks_still_refuse() -> None:
    """Reading links and charts did not relax the package safety checks."""
    escaping = build_office_pptx(
        pptx_slide(["Slide"]),
        [("rId2", "image", "../../../outside.png", False)],
    )
    with pytest.raises(office.OfficeReadError, match="outside package"):
        read_pptx(escaping)

    plain = build_office_docx(docx_paragraph("Body"))
    with zipfile.ZipFile(io.BytesIO(plain)) as archive:
        document = archive.read("word/document.xml")
    declared = document.replace(
        b"<w:document",
        b'<!DOCTYPE x [<!ENTITY a "aaaa">]><w:document',
        1,
    )
    with pytest.raises(office.OfficeReadError, match="entities denied"):
        read_docx(_rezip(plain, {"word/document.xml": declared}))

    with pytest.raises(office.OfficeReadError, match="active content"):
        read_docx(_rezip(plain, {"word/vbaProject.bin": b"macro"}))

    deep = b"<a>" * 200 + b"</a>" * 200
    with pytest.raises(office.OfficeReadError, match="structure limit"):
        read_docx(_rezip(plain, {"word/document.xml": deep}))

    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b" " * (office.MAX_EXPANDED_BYTES + 1))
    with pytest.raises(office.OfficeReadError, match="expansion limit"):
        read_docx(bomb.getvalue())
    assert office.MAX_EXPANDED_BYTES == detect.MAX_OFFICE_UNCOMPRESSED_BYTES


def test_large_sheet_streamed(monkeypatch) -> None:
    """The 40,000-cell sheet is read as a stream, whatever its node count.

    The sheet holds more XML nodes than the old 100,000-node limit and is far
    larger than the whole-tree byte cap set here, so it only reads because
    rows are streamed. Every row arrives whole, under the repeated header.
    """
    data = (FIXTURES_DIR / "large_sheet.xlsx").read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml")
    assert sum(1 for _ in ET.fromstring(sheet).iter()) > 100_000
    monkeypatch.setattr(office, "MAX_TREE_XML_BYTES", 64 * 1024)
    assert len(sheet) > office.MAX_TREE_XML_BYTES

    chunks = read_xlsx(data)
    header = "| " + " | ".join(LARGE_SHEET_HEADER) + " |"
    seen: set[str] = set()
    for chunk in chunks:
        lines = chunk.text.split("\n")
        assert lines[0] == header
        assert chunk.locator["sheet"] == "Open Orders"
        for line in lines[2:]:
            cells = _table_cells(line)
            assert len(cells) == LARGE_SHEET_COLUMNS
            seen.add(cells[0])
    assert seen == {f"PO-{30000 + index}" for index in range(1, LARGE_SHEET_ROWS)}
    assert chunks[0].locator["range"].startswith("A1:J")
    assert chunks[-1].locator["range"].endswith(f":J{LARGE_SHEET_ROWS}")


def test_xlsx_header_repeated_and_columns_aligned() -> None:
    """Every sheet chunk repeats the header and empty cells keep their column."""
    header = ["PO", "Vendor", "Issue", "Owner", "Status"]
    rows: list[list[str | tuple[str, int] | None]] = [[None] * 5, list(header)]
    for index in range(60):
        rows.append(
            [
                f"PO-{500 + index}",
                None if index % 3 == 0 else f"Vendor {index}",
                "Awaiting licensor sign-off on the revised artwork file",
                None if index % 4 == 0 else "Marco",
                "Open",
            ]
        )
    chunks = read_xlsx(build_office_xlsx(rows, sheet_name="Exceptions"))
    assert len(chunks) > 1
    data_lines: list[str] = []
    for chunk in chunks:
        lines = chunk.text.split("\n")
        assert lines[0] == "| PO | Vendor | Issue | Owner | Status |"
        assert lines[1] == "| --- | --- | --- | --- | --- |"
        assert all(len(_table_cells(line)) == 5 for line in lines)
        data_lines.extend(lines[2:])
    by_po = {_table_cells(line)[0]: _table_cells(line) for line in data_lines}
    assert len(by_po) == 60
    # Row 0 has no vendor and no owner: both cells stay, empty, in place.
    assert by_po["PO-500"] == [
        "PO-500",
        "",
        "Awaiting licensor sign-off on the revised artwork file",
        "",
        "Open",
    ]
    assert by_po["PO-501"][1] == "Vendor 1" and by_po["PO-501"][3] == "Marco"
    # The header sits on sheet row 2 (row 1 is empty); ranges say so.
    assert chunks[0].locator["range"].startswith("A2:E")
    assert chunks[-1].locator["range"].endswith(":E62")


def test_csv_rows_never_split() -> None:
    """CSV and TSV files read as tables: whole records under a repeated header."""
    assert detect.read_kind("text", "cmap/abc/open-orders.csv") == "csv"
    assert detect.read_kind("text", "cmap/abc/OPEN.TSV") == "tsv"
    assert detect.read_kind("text", "cmap/abc/notes.txt") == "text"
    assert detect.read_kind("transcript", "cmap/abc/call.csv") == "transcript"
    assert detect.detect_kind("orders.tsv", b"PO\tStatus\n") == "text"

    lines = ["PO,Vendor,Note,Owner"]
    expected: list[str] = []
    for index in range(200):
        vendor = "" if index % 5 == 0 else f"Vendor {index}"
        note = f'"Held, waiting on sign-off\nsecond line {index}"'
        lines.append(f"PO-{index},{vendor},{note},Marco")
        expected.append(
            f"| PO-{index} | {vendor} | Held, waiting on sign-off second line {index} | Marco |"
        )
    chunks = read_chunks("csv", "\n".join(lines).encode("utf-8"))
    assert len(chunks) > 1
    found: list[str] = []
    for chunk in chunks:
        body = chunk.text.split("\n")
        assert body[0] == "| PO | Vendor | Note | Owner |"
        assert body[1] == "| --- | --- | --- | --- |"
        assert all(line in expected for line in body[2:])
        found.extend(body[2:])
    assert set(found) == set(expected)
    assert chunks[0].locator["range"].startswith("A1:D")
    assert chunks[-1].locator["range"].endswith(":D201")

    tsv = read_chunks("tsv", b"PO\tNote\nPO-1\tHeld, one cell\n")
    assert tsv[0].text.split("\n")[2] == "| PO-1 | Held, one cell |"


def test_tsv_upload_reads_as_table(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch,
    db,
) -> None:
    """An uploaded .tsv is stored as text and read by the table reader."""
    fake_embeddings(monkeypatch)
    response = client.post(
        "/sources",
        headers=admin_headers,
        files={"file": ("orders.tsv", b"PO\tStatus\nPO-1\tOpen\n", "text/plain")},
    )
    assert response.status_code == 200, response.text
    job_id, source_id = db.execute(
        "SELECT id::text, payload->>'source_id' FROM cmap.job WHERE kind = 'read_source'"
    ).fetchone()
    handle_read_source(
        {"id": job_id, "kind": "read_source", "payload": {"source_id": source_id}}
    )
    kind, state = db.execute(
        "SELECT kind, read_state FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    assert (kind, state) == ("text", "read")
    text = db.execute(
        "SELECT text FROM cmap.chunk WHERE source_id = %s", (source_id,)
    ).fetchone()[0]
    assert text == "| PO | Status |\n| --- | --- |\n| PO-1 | Open |"


def test_xlsx_dates_are_iso() -> None:
    """Date-styled cells become ISO dates; plain numbers are left alone."""
    serial = (date(2026, 3, 14) - date(1899, 12, 30)).days
    styles: list[tuple[int, str | None]] = [
        (0, None),
        (14, None),
        (164, "yyyy-mm-dd hh:mm"),
        (2, None),
        (165, '#,##0.00 "USD"'),
        (20, None),
    ]
    rows: list[list[str | tuple[str, int] | None]] = [
        ["PO", "Due", "Signed", "Units", "Cost", "Cutoff", "Raw"],
        [
            "PO-1",
            (str(serial), 1),
            (f"{serial}.75", 2),
            (str(serial), 3),
            (str(serial), 4),
            ("0.5", 5),
            (str(serial), 0),
        ],
    ]
    chunks = read_xlsx(build_office_xlsx(rows, styles=styles))
    cells = _table_cells(chunks[0].text.split("\n")[2])
    assert cells == [
        "PO-1",
        "2026-03-14",
        "2026-03-14T18:00:00",
        str(serial),
        str(serial),
        "12:00:00",
        str(serial),
    ]


def test_docx_table_and_image_read(monkeypatch) -> None:
    """A DOCX table is a Markdown table in place and a picture is read in place."""
    calls = fake_vision(monkeypatch, "vision_flowchart.json")
    picture = (FIXTURES_DIR / "licensing-approval-flowchart.png").read_bytes()
    body = (
        docx_paragraph("Approval steps")
        + docx_table(
            [
                ["Step", "Owner", "Days"],
                ["Submit artwork", "Design", "1"],
                ["Licensor review", "", "5"],
            ]
        )
        + docx_paragraph("The flow is drawn below.")
        + docx_picture("rId5")
        + docx_paragraph("Escalate on day six.")
    )
    usage: dict[str, int] = {}
    chunks = read_docx(
        build_office_docx(
            body,
            [("rId5", "image", "media/image1.png", False)],
            {"image1.png": picture},
        ),
        usage,
    )
    assert len(calls) == 1
    assert usage["vision_calls"] == 1
    url = calls[0][0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    text = "\n".join(chunk.text for chunk in chunks)
    table = (
        "| Step | Owner | Days |\n"
        "| --- | --- | --- |\n"
        "| Submit artwork | Design | 1 |\n"
        "| Licensor review |  | 5 |"
    )
    assert table in text
    order = [
        text.index("Approval steps"),
        text.index(table),
        text.index("The flow is drawn below."),
        text.index("Record sign-off (Jessica)"),
        text.index("Escalate on day six."),
    ]
    assert order == sorted(order)
    assert any(chunk.locator.get("visual") for chunk in chunks)


def test_docx_long_table_repeats_header() -> None:
    """A DOCX table longer than one chunk keeps whole rows under its header."""
    rows = [["Step", "Owner", "Detail"]] + [
        [f"Step {index}", "Licensing", "Check the artwork log before releasing the PO"]
        for index in range(80)
    ]
    chunks = read_docx(build_office_docx(docx_paragraph("Steps") + docx_table(rows)))
    assert len(chunks) > 1
    for chunk in chunks[1:]:
        lines = chunk.text.split("\n")
        assert lines[0] == "| Step | Owner | Detail |"
        assert all(len(_table_cells(line)) == 3 for line in lines)


def test_pptx_bad_picture_does_not_fail_deck(monkeypatch) -> None:
    """One unreadable picture is a noted gap; the rest of the deck is read."""
    calls = fake_vision(monkeypatch, "vision_flowchart.json")
    usage: dict[str, int] = {}
    data = build_pptx(
        [["Title slide"], ["Flow behind the delay"]],
        picture=b"this is not an image",
    )
    chunks = read_pptx(data, usage)
    assert calls == []
    assert [chunk.locator for chunk in chunks] == [
        {"slide": 1},
        {"slide": 2, "visual": True},
    ]
    assert "Title slide" in chunks[0].text
    assert "Flow behind the delay" in chunks[1].text
    assert PICTURE_GAP in chunks[1].text
    assert usage["picture_gaps"] == 1

    def failing(messages, settings):
        del messages, settings
        raise vision.VisionError("vision model refused the picture")

    monkeypatch.setattr(vision, "_post_chat", failing)
    picture = (FIXTURES_DIR / "licensing-approval-flowchart.png").read_bytes()
    chunks = read_pptx(build_pptx([["Title slide"], ["Flow"]], picture=picture))
    assert len(chunks) == 2
    assert PICTURE_GAP in chunks[1].text


def test_pptx_picture_true_image_type(monkeypatch) -> None:
    """Vision is told the picture's real type, not the one its name claims."""
    calls = fake_vision(monkeypatch, "vision_flowchart.json")
    jpeg = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(jpeg, format="JPEG")
    # build_pptx stores the picture as ppt/media/image1.png.
    chunks = read_pptx(build_pptx([["Title"], ["Flow"]], picture=jpeg.getvalue()))
    assert len(calls) == 1
    url = calls[0][0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert chunks[1].locator == {"slide": 2, "visual": True}

    bitmap = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(bitmap, format="BMP")
    read_pptx(build_pptx([["Title"], ["Flow"]], picture=bitmap.getvalue()))
    assert len(calls) == 2
    url = calls[1][0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
