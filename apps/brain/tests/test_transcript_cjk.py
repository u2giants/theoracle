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
