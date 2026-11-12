"""Build the Office fixtures for links, charts, large sheets and tables.

Run with the brain venv:
``uv run python tests/fixtures/build_office_fixtures.py``.

Everything here is invented (the same fictional licensing material as
``build_fixtures.py``) and written as raw OOXML zips, so no Office library is
needed. The builders are also imported by ``tests/test_read.py``.

- ``with_hyperlink.docx``  a memo whose text carries an external hyperlink
- ``with_chart.pptx``      a slide with a chart and its embedded workbook
- ``large_sheet.xlsx``     4,000 rows x 10 columns = 40,000 cells
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent

HYPERLINK_DOCX_NAME = "with_hyperlink.docx"
CHART_PPTX_NAME = "with_chart.pptx"
LARGE_SHEET_NAME = "large_sheet.xlsx"

LARGE_SHEET_ROWS = 4000
LARGE_SHEET_COLUMNS = 10

PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

# A cell is ``None`` (absent from the file), text, or ``(number, style index)``.
Cell = str | tuple[str, int] | None


def zip_package(members: dict[str, bytes | str]) -> bytes:
    """Return a zip of ``members`` with fixed headers (stable bytes)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            # ZipInfo.create_system defaults to the build platform (0 Windows,
            # 3 Unix) and lands in the central directory; pin it so the bytes
            # are identical everywhere, like the fixed date_time above.
            info.create_system = 3
            data = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(info, data)
    return buffer.getvalue()


def content_types(overrides: dict[str, str], defaults: dict[str, str] | None = None) -> str:
    """Return ``[Content_Types].xml`` for the given part overrides."""
    all_defaults = {
        "rels": "application/vnd.openxmlformats-package.relationships+xml",
        "xml": "application/xml",
        **(defaults or {}),
    }
    body = "".join(
        f'<Default Extension="{ext}" ContentType="{kind}"/>'
        for ext, kind in all_defaults.items()
    ) + "".join(
        f'<Override PartName="{part}" ContentType="{kind}"/>'
        for part, kind in overrides.items()
    )
    return (
        f"{XML_HEAD}<Types "
        'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f"{body}</Types>"
    )


def relationships(items: list[tuple[str, str, str, bool]]) -> str:
    """Return a ``.rels`` part from ``(id, type suffix, target, external)``."""
    body = "".join(
        f'<Relationship Id="{identifier}" Type="{DOC_RELS}/{kind}" Target="{target}"'
        + (' TargetMode="External"' if external else "")
        + "/>"
        for identifier, kind, target, external in items
    )
    return f'{XML_HEAD}<Relationships xmlns="{PACKAGE_RELS}">{body}</Relationships>'


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------

DOCX_MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def docx_paragraph(text: str) -> str:
    return f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def docx_table(rows: list[list[str]]) -> str:
    """Return a ``w:tbl`` with one single-paragraph cell per string."""
    body = "".join(
        "<w:tr>"
        + "".join(f"<w:tc>{docx_paragraph(cell)}</w:tc>" for cell in row)
        + "</w:tr>"
        for row in rows
    )
    return f"<w:tbl>{body}</w:tbl>"


def docx_picture(identifier: str, linked: bool = False) -> str:
    """Return a paragraph holding one inline picture (embedded or linked)."""
    attribute = "r:link" if linked else "r:embed"
    return (
        "<w:p><w:r><w:drawing><wp:inline><a:graphic><a:graphicData><pic:pic>"
        f'<pic:blipFill><a:blip {attribute}="{identifier}"/></pic:blipFill>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
    )


def build_docx(
    body: str,
    relations: list[tuple[str, str, str, bool]] | None = None,
    media: dict[str, bytes] | None = None,
) -> bytes:
    """Return a .docx whose ``w:body`` is ``body`` (already XML)."""
    document = (
        f'{XML_HEAD}<w:document xmlns:w="{W_NS}" xmlns:r="{DOC_RELS}" '
        f'xmlns:a="{A_NS}" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f"<w:body>{body}</w:body></w:document>"
    )
    members: dict[str, bytes | str] = {
        "[Content_Types].xml": content_types(
            {"/word/document.xml": DOCX_MAIN},
            {"png": "image/png", "jpeg": "image/jpeg"},
        ),
        "_rels/.rels": relationships([("rId1", "officeDocument", "word/document.xml", False)]),
        "word/document.xml": document,
    }
    if relations:
        members["word/_rels/document.xml.rels"] = relationships(relations)
    for name, data in (media or {}).items():
        members[f"word/media/{name}"] = data
    return zip_package(members)


def build_hyperlink_docx() -> bytes:
    """Return the memo fixture: body text with an external hyperlink."""
    link = (
        '<w:p><w:r><w:t xml:space="preserve">The current style guide is on the </w:t></w:r>'
        '<w:hyperlink r:id="rId7"><w:r><w:t>licensor portal</w:t></w:r></w:hyperlink>'
        '<w:r><w:t xml:space="preserve"> and is checked before every submission.</w:t></w:r>'
        "</w:p>"
    )
    body = (
        docx_paragraph("Artwork Submission Memo")
        + docx_paragraph("Document: LIC-MEMO-011    Owner: Licensing")
        + link
        + docx_paragraph(
            "Submissions that do not match the style guide are returned by the "
            "licensor and restart the five business day sign-off window."
        )
    )
    return build_docx(
        body,
        [("rId7", "hyperlink", "https://portal.example.com/style-guide", True)],
    )


# --------------------------------------------------------------------------
# XLSX
# --------------------------------------------------------------------------

XLSX_MAIN = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
XLSX_SHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
XLSX_STYLES = "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"


def column_letters(number: int) -> str:
    letters = ""
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def xlsx_sheet(rows: list[list[Cell]]) -> str:
    """Return a worksheet part; ``None`` cells are left out of the file."""
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column_index, cell in enumerate(row, start=1):
            if cell is None:
                continue
            ref = f"{column_letters(column_index)}{row_index}"
            if isinstance(cell, tuple):
                value, style = cell
                cells.append(f'<c r="{ref}" s="{style}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
                    f"{escape(cell)}</t></is></c>"
                )
        if cells:
            xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        f'{XML_HEAD}<worksheet xmlns="{S_NS}"><sheetData>'
        + "".join(xml_rows)
        + "</sheetData></worksheet>"
    )


def xlsx_styles(formats: list[tuple[int, str | None]]) -> str:
    """Return a styles part: one cell style per ``(numFmtId, custom code)``."""
    custom = "".join(
        f'<numFmt numFmtId="{format_id}" formatCode="{escape(code, {chr(34): "&quot;"})}"/>'
        for format_id, code in formats
        if code is not None
    )
    xfs = "".join(f'<xf numFmtId="{format_id}"/>' for format_id, _code in formats)
    return (
        f'{XML_HEAD}<styleSheet xmlns="{S_NS}">'
        f"<numFmts>{custom}</numFmts><cellXfs>{xfs}</cellXfs></styleSheet>"
    )


def build_xlsx(
    rows: list[list[Cell]],
    sheet_name: str = "Sheet1",
    styles: list[tuple[int, str | None]] | None = None,
    extra_relations: list[tuple[str, str, str, bool]] | None = None,
) -> bytes:
    """Return a one-sheet .xlsx."""
    overrides = {"/xl/workbook.xml": XLSX_MAIN, "/xl/worksheets/sheet1.xml": XLSX_SHEET}
    relations = [("rId1", "worksheet", "worksheets/sheet1.xml", False)]
    members: dict[str, bytes | str] = {}
    if styles is not None:
        overrides["/xl/styles.xml"] = XLSX_STYLES
        relations.append(("rId2", "styles", "styles.xml", False))
        members["xl/styles.xml"] = xlsx_styles(styles)
    relations.extend(extra_relations or [])
    members = {
        "[Content_Types].xml": content_types(overrides),
        "_rels/.rels": relationships([("rId1", "officeDocument", "xl/workbook.xml", False)]),
        "xl/workbook.xml": (
            f'{XML_HEAD}<workbook xmlns="{S_NS}" xmlns:r="{DOC_RELS}"><sheets>'
            f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": relationships(relations),
        "xl/worksheets/sheet1.xml": xlsx_sheet(rows),
        **members,
    }
    return zip_package(members)


LARGE_SHEET_HEADER = [
    "PO Number",
    "Program",
    "Licensor",
    "Buyer",
    "Status",
    "Units",
    "Carton Qty",
    "Factory",
    "Ship Window",
    "Note",
]


def large_sheet_rows() -> list[list[Cell]]:
    """Return the 4,000 x 10 grid: a header row and 3,999 invented PO lines."""
    programs = ["Spring", "Summer", "Back to School", "Holiday"]
    licensors = ["Northwind Studios", "Bluebird Pictures", "Cobalt Animation"]
    buyers = ["Marco", "Ilona", "Priya", "Tomas"]
    statuses = ["Awaiting licensor sign-off", "Released", "On hold", "In production"]
    rows: list[list[Cell]] = [list(LARGE_SHEET_HEADER)]
    for index in range(1, LARGE_SHEET_ROWS):
        rows.append(
            [
                f"PO-{30000 + index}",
                programs[index % len(programs)],
                licensors[index % len(licensors)],
                buyers[index % len(buyers)],
                statuses[index % len(statuses)],
                str(120 + (index * 7) % 900),
                str(6 + index % 18),
                f"Factory {1 + index % 12}",
                f"Week {1 + index % 52}",
                f"Line {index} of the open order review",
            ]
        )
    return rows


def build_large_sheet_xlsx() -> bytes:
    return build_xlsx(large_sheet_rows(), sheet_name="Open Orders")


# --------------------------------------------------------------------------
# PPTX
# --------------------------------------------------------------------------

PPTX_MAIN = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
)
PPTX_SLIDE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
PPTX_CHART = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"


def pptx_slide(paragraphs: list[str], extra: str = "") -> str:
    runs = "".join(f"<a:p><a:r><a:t>{escape(text)}</a:t></a:r></a:p>" for text in paragraphs)
    return (
        f'{XML_HEAD}<p:sld xmlns:a="{A_NS}" xmlns:p="{P_NS}" xmlns:r="{DOC_RELS}" '
        f'xmlns:c="{C_NS}"><p:cSld><p:spTree>{runs}{extra}</p:spTree></p:cSld></p:sld>'
    )


def build_pptx(
    slide: str,
    slide_relations: list[tuple[str, str, str, bool]] | None = None,
    extra_members: dict[str, bytes | str] | None = None,
    extra_overrides: dict[str, str] | None = None,
) -> bytes:
    """Return a one-slide .pptx whose slide part is ``slide``."""
    members: dict[str, bytes | str] = {
        "[Content_Types].xml": content_types(
            {
                "/ppt/presentation.xml": PPTX_MAIN,
                "/ppt/slides/slide1.xml": PPTX_SLIDE,
                **(extra_overrides or {}),
            },
            {"png": "image/png", "xlsx": "application/vnd.ms-excel"},
        ),
        "_rels/.rels": relationships([("rId1", "officeDocument", "ppt/presentation.xml", False)]),
        "ppt/presentation.xml": (
            f'{XML_HEAD}<p:presentation xmlns:p="{P_NS}" xmlns:r="{DOC_RELS}">'
            '<p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>'
        ),
        "ppt/_rels/presentation.xml.rels": relationships(
            [("rId1", "slide", "slides/slide1.xml", False)]
        ),
        "ppt/slides/slide1.xml": slide,
    }
    if slide_relations:
        members["ppt/slides/_rels/slide1.xml.rels"] = relationships(slide_relations)
    members.update(extra_members or {})
    return zip_package(members)


def build_chart_pptx() -> bytes:
    """Return the deck fixture: a slide with a chart and its embedded workbook."""
    frame = (
        "<p:graphicFrame><a:graphic><a:graphicData>"
        '<c:chart r:id="rId2"/></a:graphicData></a:graphic></p:graphicFrame>'
    )
    chart = (
        f'{XML_HEAD}<c:chartSpace xmlns:c="{C_NS}" xmlns:r="{DOC_RELS}">'
        "<c:chart><c:plotArea><c:barChart><c:ser>"
        "<c:cat><c:strLit><c:pt idx=\"0\"><c:v>Week 10</c:v></c:pt></c:strLit></c:cat>"
        "<c:val><c:numLit><c:pt idx=\"0\"><c:v>12</c:v></c:pt></c:numLit></c:val>"
        '</c:ser></c:barChart></c:plotArea></c:chart><c:externalData r:id="rId1"/>'
        "</c:chartSpace>"
    )
    return build_pptx(
        pptx_slide(
            [
                "Open POs waiting on licensor sign-off",
                "Twelve POs were waiting at the end of week 10",
            ],
            frame,
        ),
        [("rId2", "chart", "../charts/chart1.xml", False)],
        {
            "ppt/charts/chart1.xml": chart,
            "ppt/charts/_rels/chart1.xml.rels": relationships(
                [("rId1", "package", "../embeddings/Microsoft_Excel_Sheet1.xlsx", False)]
            ),
            # Deliberately not a workbook: the reader must never open it.
            "ppt/embeddings/Microsoft_Excel_Sheet1.xlsx": b"embedded workbook, never opened",
        },
        {"/ppt/charts/chart1.xml": PPTX_CHART},
    )


def main() -> None:
    """Write the three generated Office fixtures into this folder."""
    (HERE / HYPERLINK_DOCX_NAME).write_bytes(build_hyperlink_docx())
    (HERE / CHART_PPTX_NAME).write_bytes(build_chart_pptx())
    (HERE / LARGE_SHEET_NAME).write_bytes(build_large_sheet_xlsx())
    print("fixtures written:", HYPERLINK_DOCX_NAME, CHART_PPTX_NAME, LARGE_SHEET_NAME)


if __name__ == "__main__":
    main()
