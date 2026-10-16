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
