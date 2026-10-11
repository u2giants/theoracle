from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from PIL import Image

from oracle_brain.ingest.originals import OriginalProviderError, read_original
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest


def _admission(name: str, *, expiry=None):
    request = ProcessingRequest(provider="synthetic", account=name, endpoint="loopback",
                                data_classes=frozenset({"synthetic"}), purpose="original-reading",
                                terms_hash="a" * 64)
    approval = ProcessingApproval(**request.model_dump(), register_ref="test",
                                  expires_at=expiry or datetime.now(timezone.utc) + timedelta(minutes=5))
    return request, [approval]


def _reading(pages=1, *, uncertainty=False, empty=False, ambiguities=None):
    return json.dumps({"pages": [{"page_number": i, "text": "" if empty else "Diagram text",
                                   "visual_elements": [], "connections": [],
                                   "uncertainties": ["uncertain"] if uncertainty else [],
                                   "source_ambiguities": ambiguities or []}
                                  for i in range(1, pages + 1)], "complete": not uncertainty})


def _png(*, pages=1) -> bytes:
    images = [Image.new("RGB", (120, 80), "white") for _ in range(pages)]
    stream = BytesIO()
    images[0].save(stream, format="PNG", save_all=pages > 1, append_images=images[1:])
    return stream.getvalue()


def _pdf_two_pages() -> bytes:
    images = [Image.new("RGB", (120, 80), "white") for _ in range(2)]
    stream = BytesIO()
    images[0].save(stream, format="PDF", save_all=True, append_images=[images[1]])
    return stream.getvalue()


def _review(pages):
    return json.dumps({"complete_supported": True, "checked_pages": list(range(1, pages + 1)),
                       "unsupported": [], "omissions": [], "uncertainties": []})


def test_original_hash_denies_before_reader_callback():
    reader_request, approvals = _admission("reader")
    reviewer_request, _ = _admission("reviewer")
    calls = []
    with pytest.raises(ValueError, match="hash mismatch"):
        read_original(data=b"source", content_type="image/png", expected_hash="0" * 64,
                      reader=lambda *_: calls.append(1), reviewer=lambda *_: _reading(),
                      reader_request=reader_request, reviewer_request=reviewer_request,
                      approvals=approvals)
    assert calls == []


@pytest.mark.parametrize("content_type", ["text/plain", "text/markdown"])
def test_native_text_and_markdown_are_lossless_without_model_calls(content_type):
    data = "Line one\nLine two — exact UTF-8".encode()
    rr, _ = _admission("expired-reader", expiry=datetime.now(timezone.utc) - timedelta(seconds=1))
    vr, _ = _admission("expired-reviewer", expiry=datetime.now(timezone.utc) - timedelta(seconds=1))
    def forbidden(*_):
        raise AssertionError("native text must not invoke visual reader or reviewer")
    result = read_original(data=data, content_type=content_type,
                           expected_hash=hashlib.sha256(data).hexdigest(), reader=forbidden,
                           reviewer=forbidden, reader_request=rr, reviewer_request=vr, approvals=[])
    assert result.normalized_text == data.decode("utf-8")
    assert result.page_count == 1


def test_blank_native_text_is_rejected_before_callbacks():
    rr, _ = _admission("reader"); vr, _ = _admission("reviewer")
    with pytest.raises(ValueError, match="empty"):
        read_original(data=b"", content_type="text/plain", expected_hash=hashlib.sha256(b"").hexdigest(),
                      reader=lambda *_: pytest.fail("called"), reviewer=lambda *_: pytest.fail("called"),
                      reader_request=rr, reviewer_request=vr, approvals=[])


def test_image_views_preserve_owner_and_arrow_direction_and_prompt_schema():
    data = _png(); rr, ra = _admission("reader-v1"); vr, va = _admission("reviewer-v1")
    prompts = []
    def reader(prompt, views):
        prompts.append(json.loads(prompt))
        return json.dumps({"pages": [{"page_number": 1, "text": "Role A to Role B", "visual_elements": [
            {"element_id": "a", "kind": "role", "literal_text": "Role A", "owner": "Team A"},
            {"element_id": "b", "kind": "role", "literal_text": "Role B", "owner": "Team B"}],
            "connections": [{"from": "a", "to": "b", "label": "handoff", "style": "solid"}],
            "uncertainties": []}], "complete": True})
    def reviewer(prompt, views):
        prompts.append(json.loads(prompt))
        return _review(1)
    result = read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                           reader=reader, reviewer=reviewer, reader_request=rr, reviewer_request=vr,
                           approvals=ra + va, reader_model="reader-v1", reviewer_model="reviewer-v1")
    assert "a->b" in result.normalized_text and "owner=Team A" in result.normalized_text
    assert all("png_base64" not in prompt for prompt in prompts)
    assert any("views" in prompt and "task" in prompt and "response_schema" in prompt
               for prompt in prompts)
    assert result.parser_identity


def test_uncertainty_repair_is_bounded_and_fresh_review_required():
    data = _png(); rr, ra = _admission("reader-v1"); vr, va = _admission("reviewer-v1")
    seen = []
    def reader(prompt, views):
        seen.append(prompt)
        return _reading(uncertainty=len(seen) == 1)
    result = read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                           reader=reader, reviewer=lambda *_: _review(1), reader_request=rr,
                           reviewer_request=vr, approvals=ra + va, reader_model="reader-v1",
                           reviewer_model="reviewer-v1")
    assert result.review.complete_supported and len(seen) == 2


def test_intrinsic_source_ambiguity_is_retained_but_reading_doubt_rejects():
    data = _png(); rr, ra = _admission("reader-v1"); vr, va = _admission("reviewer-v1")
    result = read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                           reader=lambda *_: _reading(ambiguities=["clipped original label"]),
                           reviewer=lambda *_: _review(1), reader_request=rr, reviewer_request=vr,
                           approvals=ra + va, reader_model="reader-v1", reviewer_model="reviewer-v1")
    assert "ORIGINAL SOURCE AMBIGUITY" in result.normalized_text

    with pytest.raises(ValueError, match="after one repair"):
        read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                      reader=lambda *_: _reading(uncertainty=True), reviewer=lambda *_: _review(1),
                      reader_request=rr, reviewer_request=vr, approvals=ra + va,
                      reader_model="reader-v1", reviewer_model="reviewer-v1")


def test_provider_callback_failure_is_terminal_and_dispatched_once():
    data = _png(); rr, ra = _admission("reader-v1"); vr, va = _admission("reviewer-v1")
    calls = []
    def reader(*_):
        calls.append(1)
        raise RuntimeError("provider detail must not escape")
    with pytest.raises(OriginalProviderError, match="no automatic retry"):
        read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                      reader=reader, reviewer=lambda *_: _review(1), reader_request=rr,
                      reviewer_request=vr, approvals=ra + va, reader_model="reader-v1",
                      reviewer_model="reviewer-v1")
    assert len(calls) == 1


def test_review_omission_fails_after_one_repair():
    data = _png(); rr, ra = _admission("reader-v1"); vr, va = _admission("reviewer-v1")
    reviewer = lambda *_: json.dumps({"complete_supported": False, "checked_pages": [1],
                                       "unsupported": [], "omissions": ["missing arrow"],
                                       "uncertainties": []})
    with pytest.raises(ValueError, match="after one repair"):
        read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                      reader=lambda *_: _reading(), reviewer=reviewer, reader_request=rr,
                      reviewer_request=vr, approvals=ra + va, reader_model="reader-v1",
                      reviewer_model="reviewer-v1")


def test_reader_admission_denies_before_visual_dispatch():
    data = _png(); rr, _ = _admission("reader-v1", expiry=datetime.now(timezone.utc) - timedelta(seconds=1))
    vr, va = _admission("reviewer-v1"); calls = []
    with pytest.raises(PermissionError):
        read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                      reader=lambda *_: calls.append(1), reviewer=lambda *_: _reading(),
                      reader_request=rr, reviewer_request=vr, approvals=va,
                      reader_model="reader-v1", reviewer_model="reviewer-v1")
    assert calls == []


def test_empty_visual_page_text_is_rejected_after_reader_response():
    data = _png(); rr, ra = _admission("reader-v1"); vr, va = _admission("reviewer-v1")
    with pytest.raises(ValueError, match="after one repair"):
        read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                      reader=lambda *_: _reading(empty=True), reviewer=lambda *_: _review(1),
                      reader_request=rr, reviewer_request=vr, approvals=ra + va,
                      reader_model="reader-v1", reviewer_model="reviewer-v1")


def test_expired_reviewer_denies_after_reader_without_reviewer_dispatch():
    data = _png(); rr, ra = _admission("reader-v1")
    vr, _ = _admission("reviewer-v1", expiry=datetime.now(timezone.utc) - timedelta(seconds=1))
    calls = []
    with pytest.raises(PermissionError):
        read_original(data=data, content_type="image/png", expected_hash=hashlib.sha256(data).hexdigest(),
                      reader=lambda *_: _reading(), reviewer=lambda *_: calls.append(1),
                      reader_request=rr, reviewer_request=vr, approvals=ra,
                      reader_model="reader-v1", reviewer_model="reviewer-v1")
    assert calls == []


def test_two_page_pdf_sends_every_rendered_page_and_requires_exact_review_pages():
    data = _pdf_two_pages(); rr, ra = _admission("reader-v1"); vr, va = _admission("reviewer-v1")
    observed = []
    def reader(prompt, views):
        observed.append([(view.page_number, view.kind, view.crop, view.width, view.height) for view in views])
        return _reading(2)
    def reviewer(prompt, views):
        observed.append([(view.page_number, view.kind, view.crop, view.width, view.height) for view in views])
        return _review(2)
    result = read_original(data=data, content_type="application/pdf",
                           expected_hash=hashlib.sha256(data).hexdigest(), reader=reader,
                           reviewer=reviewer, reader_request=rr, reviewer_request=vr,
                           approvals=ra + va, reader_model="reader-v1", reviewer_model="reviewer-v1")
    assert result.page_count == 2
    assert observed[0] == observed[1]
    assert [item[0:2] for item in observed[0] if item[1] in {"pdf-page", "pdf-detail"}] == (
        [(1, "pdf-page")] + [(1, "pdf-detail")] * 4 +
        [(2, "pdf-page")] + [(2, "pdf-detail")] * 4)
    for page_number in (1, 2):
        page_views = [item for item in observed[0] if item[0] == page_number]
        full = next(item for item in page_views if item[1] == "pdf-page")
        details = [item for item in page_views if item[1] == "pdf-detail"]
        assert len(details) == 4
        assert min(item[2][0] for item in details) == 0
        assert min(item[2][1] for item in details) == 0
        assert max(item[2][2] for item in details) == full[3]
        assert max(item[2][3] for item in details) == full[4]
    assert result.review.checked_pages == [1, 2]
