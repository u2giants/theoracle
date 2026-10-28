"""Build the invented but realistic test fixtures in this folder.

Run with the brain venv: ``uv run python tests/fixtures/build_fixtures.py``.

The five fixtures (plan step 2 conventions) are fictional POP Creations
material designed so that "where does licensing approval stall?" needs the
PDF procedure, the flowchart and the Teams transcript together:

- ``licensing-approval-procedure.pdf``  3-page procedure (policy side)
- ``licensing-approval-flowchart.png``  the same procedure as a flowchart
- ``teams-approval-2026-03-14.txt``     300-line transcript (practice side,
  hand-authored text kept in this folder, not generated)
- ``sample-room-checklist.docx``        unrelated sample-room checklist
- ``open-po-exceptions.xlsx``           PO exception rows that mention the
  same stall under both names

Only Pillow is required; the office files and the PDF are written as raw
zips and raw PDF bytes so the generator runs in the plain brain venv.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

PDF_NAME = "licensing-approval-procedure.pdf"
PNG_NAME = "licensing-approval-flowchart.png"
DOCX_NAME = "sample-room-checklist.docx"
XLSX_NAME = "open-po-exceptions.xlsx"


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(pages: list[list[str]]) -> bytes:
    """Return a minimal multi-page PDF of Helvetica text lines."""
    page_count = len(pages)
    bodies: dict[int, bytes] = {}
    bodies[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for index, lines in enumerate(pages):
        page_num = 4 + 2 * index
        content_num = 5 + 2 * index
        operations = ["BT", "/F1 11 Tf", "72 740 Td"]
        first = True
        for line in lines:
            if not first:
                operations.append("0 -15 Td")
            operations.append(f"({_pdf_escape(line)}) Tj")
            first = False
        operations.append("ET")
        stream = "\n".join(operations).encode("latin-1")
        bodies[content_num] = (
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
        bodies[page_num] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> "
            + f"/Contents {content_num} 0 R >>".encode()
        )
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(page_count))
    bodies[2] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode()
    )
    bodies[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    object_count = 4 + 2 * page_count
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for num in range(1, object_count):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + bodies[num] + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {object_count}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, object_count):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {object_count} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


PDF_PAGES: list[list[str]] = [
    [
        "POP Creations / Spruce Line",
        "Licensing Approval Procedure",
        "Document: LIC-PROC-004    Revision: 3    Effective: 2025-11-03",
        "Owner: Licensing Department",
        "",
        "1. Purpose",
        "This procedure governs artwork and concept approval for licensed",
        "properties. No purchase order for a licensed SKU may be released",
        "until licensor sign-off has been recorded.",
        "",
        "2. Scope",
        "All new licensed programs, seasonal extensions and reorder SKUs",
        "with artwork changes. Applies to Design, Licensing, Merchandising",
        "and Product Development.",
        "",
        "3. Roles",
        "- Design Lead: prepares the concept package and artwork files.",
        "- Licensing Manager: reviews packages, submits to the licensor,",
        "  records sign-off in the Artwork Log.",
        "- Buyer: creates purchase orders after sign-off is recorded.",
        "- QA: verifies artwork against the licensor style guide on request.",
    ],
    [
        "4. Procedure",
        "4.1 Design submits the concept package (concept form, artwork",
        "    PDFs, SKU list) to the Licensing queue.",
        "4.2 The Licensing Manager reviews the package for compliance with",
        "    the licensor style guide within 2 business days.",
        "4.3 The Licensing Manager submits the package to the licensor for",
        "    sign-off through the Licensing Portal.",
        "4.4 On licensor approval the Licensing Manager records the sign-off",
        "    in the Artwork Log (column \"Licensor sign-off date\").",
        "4.5 Design releases the artwork to QA and to the buyer.",
        "4.6 The Buyer may create the purchase order only after the",
        "    Artwork Log shows the sign-off date.",
        "",
        "5. Service standard",
        "Licensor sign-off is expected within 5 business days of submission.",
        "The Licensing Manager escalates to the licensor account manager on",
        "day 6. Packages returned by the licensor must be corrected and",
        "resubmitted within 2 business days.",
    ],
    [
        "6. Exceptions",
        "6.1 Reorder SKUs below 5,000 units with unchanged artwork may",
        "    proceed on the prior sign-off, except when the licensor has",
        "    issued a style-guide update since that approval.",
        "6.2 Rush programs: the VP of Product may authorise provisional",
        "    artwork release, but purchase-order release still requires",
        "    recorded licensor sign-off.",
        "6.3 When the Licensing Manager is out of office, the Backup",
        "    Licensing Coordinator may record sign-off, but only after",
        "    the licensor email is filed in the shared mailbox.",
        "",
        "7. Revision history",
        "Rev 3 - 2025-11-03 - Added backup coordinator rule (6.3)",
        "Rev 2 - 2025-06-12 - Added service standard in section 5",
        "Rev 1 - 2024-09-01 - First release",
    ],
]


# --------------------------------------------------------------------------
# DOCX / XLSX (raw OOXML zips)
# --------------------------------------------------------------------------

CONTENT_TYPES_DOCX = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

RELS_ROOT_DOCX = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""


def _docx_document(paragraphs: list[str]) -> str:
    body = []
    for text in paragraphs:
        safe = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        body.append(
            f'<w:p><w:r><w:t xml:space="preserve">{safe}</w:t></w:r></w:p>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(body)
        + "</w:body></w:document>"
    )


def build_docx(paragraphs: list[str]) -> bytes:
    """Return a minimal .docx holding one paragraph per string."""
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_DOCX)
        archive.writestr("_rels/.rels", RELS_ROOT_DOCX)
        archive.writestr("word/document.xml", _docx_document(paragraphs))
    return buffer.getvalue()


CONTENT_TYPES_XLSX = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""

RELS_ROOT_XLSX = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Exceptions" sheetId="1" r:id="rId1"/></sheets>
</workbook>
"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""


def _xlsx_sheet(rows: list[list[str]]) -> str:
    letters = "ABCDEFGH"
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            if column_index >= len(letters):
                break
            ref = f"{letters[column_index]}{row_index}"
            safe = (
                value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{safe}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">' + "".join(cells) + "</row>")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        + "".join(xml_rows)
        + "</sheetData></worksheet>"
    )


def build_xlsx(rows: list[list[str]]) -> bytes:
    """Return a minimal .xlsx with one sheet of inline-string cells."""
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XLSX)
        archive.writestr("_rels/.rels", RELS_ROOT_XLSX)
        archive.writestr("xl/workbook.xml", WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(rows))
    return buffer.getvalue()


DOCX_PARAGRAPHS = [
    "Sample Room Checklist",
    "Document: QA-SMP-002    Revision: 5    Owner: QA",
    "",
    "Use this checklist for every new and revised sample before the sample",
    "room date. Record pass or fail per line and file the sheet with the",
    "sample photo set.",
    "",
    "1. Physical sample matches the approved artwork file.",
    "2. Colors match the licensed style guide palette (pass / fail).",
    "3. Character proportions match the licensor reference sheet.",
    "4. Labels and hangtags carry the correct legal line.",
    "5. Carton and inner-pack marks match the PO.",
    "6. Lighting check: photograph the sample under showroom lighting.",
    "7. Weigh and measure against the tech pack tolerances.",
    "8. Function test: zippers, hooks, batteries, moving parts.",
    "9. Retail-ready packaging review with Merchandising present.",
    "10. Sign-off sheet uploaded to the sample room folder within 2 days.",
    "",
    "Notes",
    "Samples without recorded artwork sign-off may be prepared under",
    "provisional release, but may not ship. See LIC-PROC-004 section 6.2.",
    "Failed lines must be corrected and the sample re-presented at the next",
    "sample room date. Track failures in the sample room log.",
]

XLSX_ROWS = [
    ["PO", "Vendor", "SKU", "Program", "Issue", "Aging Days", "Owner", "Status"],
    [
        "PO-24118",
        "Ceramic Arts Ltd",
        "ML-1140",
        "Meadow Lane",
        "Awaiting licensor sign-off",
        "12",
        "Marco",
        "Open",
    ],
    [
        "PO-24119",
        "Ceramic Arts Ltd",
        "ML-1141",
        "Meadow Lane",
        "Jessica approval pending",
        "12",
        "Marco",
        "Open",
    ],
    [
        "PO-24120",
        "Softline House",
        "ML-2210",
        "Meadow Lane",
        "Awaiting licensor sign-off",
        "11",
        "Marco",
        "Open",
    ],
    [
        "PO-23990",
        "Harbor Works",
        "HV-0782",
        "Harbor View reorder",
        "Licensor sign-off not filed (email granted)",
        "9",
        "Marco",
        "Escalated",
    ],
    [
        "PO-23991",
        "Harbor Works",
        "HV-0783",
        "Harbor View reorder",
        "Jessica approval pending",
        "9",
        "Marco",
        "Escalated",
    ],
    [
        "PO-24201",
        "Paper & Pine",
        "SS-0450",
        "Summer Shade",
        "Artwork package in licensing review",
        "4",
        "Ilona",
        "Open",
    ],
    [
        "PO-24202",
        "Paper & Pine",
        "SS-0451",
        "Summer Shade",
        "Vendor cut-off pressure; no sign-off yet",
        "4",
        "Ilona",
        "Open",
    ],
    [
        "PO-24055",
        "Glassform",
        "CJ-3300",
        "Coastal Journal",
        "Returned by licensor for colorway correction",
        "17",
        "Ilona",
        "Blocked",
    ],
    [
        "PO-24056",
        "Glassform",
        "CJ-3301",
        "Coastal Journal",
        "Returned by licensor for character pose",
        "17",
        "Ilona",
        "Blocked",
    ],
    [
        "PO-24177",
        "Ceramic Arts Ltd",
        "ML-1142",
        "Meadow Lane",
        "Awaiting licensor sign-off",
        "10",
        "Marco",
        "Open",
    ],
    [
        "PO-24178",
        "Softline House",
        "ML-2211",
        "Meadow Lane",
        "Jessica approval pending",
        "10",
        "Marco",
        "Open",
    ],
    [
        "PO-24179",
        "Softline House",
        "ML-2212",
        "Meadow Lane",
        "Awaiting licensor sign-off",
        "10",
        "Marco",
        "Open",
    ],
    [
        "PO-23880",
        "Northstar Metal",
        "GV-1120",
        "Garden View",
        "Vendor capacity; not in approval yet",
        "21",
        "Marco",
        "Blocked",
    ],
    [
        "PO-23881",
        "Northstar Metal",
        "GV-1121",
        "Garden View",
        "Artwork not submitted yet",
        "21",
        "Ilona",
        "Blocked",
    ],
    [
        "PO-24210",
        "Paper & Pine",
        "SS-0452",
        "Summer Shade",
        "Awaiting licensor sign-off",
        "2",
        "Ilona",
        "Open",
    ],
    [
        "PO-24211",
        "Ceramic Arts Ltd",
        "SS-0453",
        "Summer Shade",
        "Jessica approval pending",
        "2",
        "Ilona",
        "Open",
    ],
    [
        "PO-24212",
        "Glassform",
        "SS-0454",
        "Summer Shade",
        "In licensing review",
        "2",
        "Ilona",
        "Open",
    ],
    [
        "PO-24213",
        "Harbor Works",
        "SS-0455",
        "Summer Shade",
        "Awaiting licensor sign-off",
        "1",
        "Ilona",
        "Open",
    ],
]


# --------------------------------------------------------------------------
# PNG flowchart
# --------------------------------------------------------------------------


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    for path in (
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def _arrow(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    fill: tuple[int, int, int],
) -> None:
    draw.line(points, fill=fill, width=3)
    (x1, y1), (x2, y2) = points[-2], points[-1]
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 > x1 else -1
        head = [
            (x2, y2),
            (x2 - direction * 14, y2 - 8),
            (x2 - direction * 14, y2 + 8),
        ]
    else:
        direction = 1 if y2 > y1 else -1
        head = [
            (x2, y2),
            (x2 - 8, y2 - direction * 14),
            (x2 + 8, y2 - direction * 14),
        ]
    draw.polygon(head, fill=fill)


def _centered_text(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    lines: list[str],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    heights = []
    for line in lines:
        bounds = draw.textbbox((0, 0), line, font=font)
        heights.append(bounds[3] - bounds[1])
    total = sum(heights) + 4 * (len(lines) - 1)
    y = y0 + ((y1 - y0) - total) / 2
    for line, height in zip(lines, heights, strict=True):
        bounds = draw.textbbox((0, 0), line, font=font)
        width = bounds[2] - bounds[0]
        draw.text(
            (x0 + ((x1 - x0) - width) / 2, y),
            line,
            font=font,
            fill=fill,
        )
        y += height + 4


def build_png() -> bytes:
    """Return the licensing approval flowchart PNG."""
    from io import BytesIO

    width, height = 1600, 1000
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    ink = (33, 37, 41)
    accent = (25, 82, 140)
    lane_fill = (238, 243, 248)
    box_fill = (255, 255, 255)

    title_font = _font(30)
    lane_font = _font(22)
    box_font = _font(19)
    small_font = _font(17)

    draw.text(
        (60, 30),
        "Licensing approval flow (LIC-PROC-004)",
        font=title_font,
        fill=ink,
    )

    lanes = [
        ("Design", 110, 350),
        ("Licensing", 380, 720),
        ("Buyer", 750, 940),
    ]
    for name, y0, y1 in lanes:
        draw.rounded_rectangle((160, y0, 1560, y1), radius=12, fill=lane_fill)
        draw.text((20, y0 + 12), name, font=lane_font, fill=accent)

    boxes = {
        "submit": (220, 180, 480, 270),
        "fix": (520, 180, 780, 270),
        "review": (220, 460, 480, 550),
        "record": (1100, 460, 1430, 550),
        "po": (1100, 800, 1430, 880),
    }
    labels = {
        "submit": ["Submit concept", "package"],
        "fix": ["Fix package", "and resubmit"],
        "review": ["Compliance", "review"],
        "record": ["Record sign-off", "(Jessica)"],
        "po": ["Create PO"],
    }
    for key, box in boxes.items():
        draw.rounded_rectangle(box, radius=10, fill=box_fill, outline=ink, width=3)
        _centered_text(draw, box, labels[key], box_font, ink)

    cx, cy = 760, 505
    dw, dh = 150, 90
    diamond = [(cx, cy - dh), (cx + dw, cy), (cx, cy + dh), (cx - dw, cy)]
    draw.polygon(diamond, fill=box_fill, outline=ink)
    draw.line(diamond + [diamond[0]], fill=ink, width=3)
    _centered_text(
        draw,
        (cx - dw + 20, cy - 40, cx + dw - 20, cy + 40),
        ["Licensor", "approval?"],
        small_font,
        ink,
    )

    submit = boxes["submit"]
    fix = boxes["fix"]
    review = boxes["review"]
    record = boxes["record"]
    po = boxes["po"]

    _arrow(
        draw,
        [((submit[0] + submit[2]) // 2, submit[3]), ((review[0] + review[2]) // 2, review[1])],
        ink,
    )
    _arrow(draw, [(review[2], (review[1] + review[3]) // 2), (cx - dw, cy)], ink)
    _arrow(draw, [(cx + dw, cy), (record[0], (record[1] + record[3]) // 2)], accent)
    _arrow(draw, [(cx, cy + dh), (cx, cy + dh + 60), (650, cy + dh + 60), (650, fix[3])], ink)
    _arrow(draw, [(fix[0], (fix[1] + fix[3]) // 2), (submit[2], (submit[1] + submit[3]) // 2)], ink)
    _arrow(
        draw,
        [((record[0] + record[2]) // 2, record[3]), ((po[0] + po[2]) // 2, po[1])],
        accent,
    )

    draw.text((cx + dw + 16, cy - 40), "yes", font=small_font, fill=accent)
    draw.text((cx + dw + 16, cy + 12), "Licensor sign-off", font=small_font, fill=accent)
    draw.text((cx + 8, cy + dh + 10), "no", font=small_font, fill=ink)
    draw.text((1100, 562), "Artwork Log entry", font=small_font, fill=accent)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> None:
    """Write every generated fixture into this folder."""
    (HERE / PDF_NAME).write_bytes(build_pdf(PDF_PAGES))
    (HERE / PNG_NAME).write_bytes(build_png())
    (HERE / DOCX_NAME).write_bytes(build_docx(DOCX_PARAGRAPHS))
    (HERE / XLSX_NAME).write_bytes(build_xlsx(XLSX_ROWS))
    print("fixtures written:", PDF_NAME, PNG_NAME, DOCX_NAME, XLSX_NAME)


if __name__ == "__main__":
    main()
