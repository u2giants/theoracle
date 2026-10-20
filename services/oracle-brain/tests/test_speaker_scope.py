"""Offline gate test retained from the building-block branch. Invented/synthetic only.

Import guard: oracle_brain.ingest.speakers is required; skip with reason when absent.
"""
from __future__ import annotations

import importlib.util

import pytest

_REQUIRED = 'oracle_brain.ingest.speakers'
try:
    _spec = importlib.util.find_spec(_REQUIRED)
except ModuleNotFoundError:
    _spec = None
if _spec is None:
    pytest.skip(
        "S07 speaker-scope implementation absent on main (held PR #143 / branch claude/s07-invited-meeting). Named offline gate test retained with the branch's real assertions; activates when ingest.speakers lands.",
        allow_module_level=True,
    )

from oracle_brain.ingest.speakers import resolve_speaker


def test_display_names_and_ambiguous_links_never_create_employee_identity():
    assert resolve_speaker('p', 'Albert', {}).employee_id is None
    assert resolve_speaker('p', 'Albert', {'p': ('a', 'b')}).employee_id is None
    assert resolve_speaker('', 'Albert', {'': ('a',)}).employee_id is None


def test_unique_verified_provider_link_preserves_original_name():
    speaker = resolve_speaker('p', '原名', {'p': ('a',)})
    assert speaker.employee_id == 'a'
    assert speaker.display_name == '原名'


def test_blank_or_non_string_verified_links_remain_unknown():
    for links in (("",), ("   ",), (None,), (7,), ([],), ("employee", "")):
        assert resolve_speaker("p", "Guest", {"p": links}).employee_id is None


def test_malformed_link_containers_and_padded_identifiers_remain_unknown():
    for mapping in (None, {"p": "a"}, {"p": 7}, {"p": ["a"]}, {"p": (" a ",)}):
        assert resolve_speaker("p", "Guest", mapping).employee_id is None
    for provider_id in (" ", " p ", None, 7):
        assert resolve_speaker(provider_id, "Guest", {provider_id: ("a",)}).employee_id is None
