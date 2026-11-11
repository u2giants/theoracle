"""Step 0.3 gate: transcript speaker lines accept full-width colons."""

from __future__ import annotations

from brain.read.transcript import parse_turns


def test_fullwidth_colon_speaker() -> None:
    turns = parse_turns("张三：你好，今天的采购会我来主持。\n李四：好的，我来记录。")
    assert [(turn.speaker, turn.text) for turn in turns] == [
        ("张三", "你好，今天的采购会我来主持。"),
        ("李四", "好的，我来记录。"),
    ]


def test_ascii_colon_still_parses() -> None:
    turns = parse_turns("Marco: First sentence.\nIlona: Second turn here.")
    assert [(turn.speaker, turn.text) for turn in turns] == [
        ("Marco", "First sentence."),
        ("Ilona", "Second turn here."),
    ]


def test_clock_time_is_not_a_speaker() -> None:
    """Repair A7: "We agreed at 3:15 to ship" is speech, not a speaker."""
    turns = parse_turns(
        "Marco: When does the order leave?\n"
        "We agreed at 3:15 to ship\n"
        "Ilona: Fine by me."
    )
    assert [(turn.speaker, turn.text) for turn in turns] == [
        ("Marco", "When does the order leave? We agreed at 3:15 to ship"),
        ("Ilona", "Fine by me."),
    ]
    assert parse_turns("We agreed at 3:15 to ship")[0].speaker == "Unknown"


def test_speaker_label_rules() -> None:
    """A label is at most five words, holds no clock time, and its colon is
    followed by a space."""
    cases = {
        "Jessica Smith (Licensing): Signed off.": "Jessica Smith (Licensing)",
        "At 3:15 we said: ship it": "Unknown",
        "The thing I keep telling everyone about is: ship it": "Unknown",
        "See http://example.invalid/page for details": "Unknown",
        "王五： 好的": "王五",
    }
    for line, speaker in cases.items():
        assert parse_turns(line)[0].speaker == speaker, line
