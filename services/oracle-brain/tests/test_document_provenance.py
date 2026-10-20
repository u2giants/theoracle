"""S04 offline building block: structural provenance on the S01 fixtures.

Synthetic fixtures only.  Passing this file does not satisfy the S04 gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from oracle_brain.ingest.normalize import normalize

MANIFEST = Path(__file__).resolve().parents[3] / "evals/oracle2/synthetic-cases.jsonl"
FIXTURES = {
    case["id"]: case
    for case in map(json.loads, MANIFEST.read_text().splitlines())
    if case.get("kind") == "source_fixture"
}


def _blocks(fid: str):
    case = FIXTURES[fid]
    return normalize(case["source_ids"][0], case["source_format"], case["input_text"].encode())


def test_manifest_has_twelve_adversarial_fixtures():
    assert sorted(FIXTURES) == [f"F{n:02d}" for n in range(1, 13)]


@pytest.mark.parametrize("fid", [f"F{n:02d}" for n in range(1, 12)])
def test_every_block_keeps_source_and_locator(fid):
    blocks = _blocks(fid)
    assert blocks
    for block in blocks:
        assert block.source_id == FIXTURES[fid]["source_ids"][0]
        assert block.locator


def test_f01_table_columns_keep_reading_order():
    cells = {(b.attrs["row"], b.attrs["col"]): b.text for b in _blocks("F01")}
    assert cells[(1, 1)] == "Step 1: approve proof"
    assert cells[(1, 2)] == "Exception: hold if unsigned"
    assert cells[(2, 2)] == "Only after signoff"


def test_f02_low_confidence_ocr_routes_to_review():
    (block,) = _blocks("F02")
    assert block.needs_review and block.text == "l6 units"
    assert block.attrs["bbox"] == [10, 20, 90, 45]


def test_f03_tracked_deletion_excluded():
    blocks = _blocks("F03")
    assert [b.text for b in blocks] == ["New owner"]
    assert blocks[0].attrs["revision"] == "inserted"


def test_f04_merged_header_scopes_both_subcells():
    by_loc = {b.locator: b for b in _blocks("F04")}
    assert by_loc["cell:R2C1"].attrs["headers"] == ["Region"]
    assert by_loc["cell:R2C2"].attrs["headers"] == ["Region"]
    assert by_loc["cell:R1C1"].attrs["merged_span"] == [1, 2]


def test_f05_formula_never_executed_and_cache_untrusted():
    (block,) = _blocks("F05")
    assert block.kind == "formula_cell"
    assert block.attrs["formula"] == "SUM(B1:B3)"
    assert block.attrs["cached_value"] == "999"
    assert block.attrs["executed"] is False and block.attrs["cached_value_trusted"] is False


def test_f06_quoted_newline_is_one_record():
    blocks = _blocks("F06")
    assert len(blocks) == 2
    assert blocks[0].attrs["cells"]["comment"] == "First line, with comma\nsecond line"


def test_f07_arrow_direction_from_geometry_not_position():
    (edge,) = [b for b in _blocks("F07") if b.kind == "diagram_edge"]
    assert edge.attrs == {"from": "Ship", "to": "Review", "directed": True}


def test_f08_rotated_negation_kept_and_reviewed():
    (block,) = _blocks("F08")
    assert block.text == "NO RELEASE" and block.attrs["rotation"] == 90
    assert block.attrs["bbox"] == [12, 5, 30, 90] and block.needs_review


def test_f09_quotation_separate_from_sender_assertion():
    blocks = _blocks("F09")
    assertions = [b for b in blocks if b.kind == "assertion"]
    quotes = [b for b in blocks if b.kind == "quotation"]
    assert assertions[0].text == "Current note: approval pending."
    assert assertions[0].attrs["asserted_by"] == "current@example.invalid"
    assert any("approval granted" in q.text for q in quotes)
    assert all(q.attrs["asserted_by"] is None for q in quotes)


def test_f10_overlapping_speakers_need_review():
    blocks = _blocks("F10")
    assert [b.attrs["speaker"] for b in blocks] == ["Speaker A", "Speaker B"]
    assert all(b.needs_review and b.attrs["overlaps"] for b in blocks)


def test_f11_hostile_instruction_is_inert_text():
    blocks = _blocks("F11")
    hostile = [b for b in blocks if "Ignore all previous" in b.text]
    assert hostile and hostile[0].attrs["inert_source_text"] is True
    assert any(b.text == "Actual step: log the sample." for b in blocks)
