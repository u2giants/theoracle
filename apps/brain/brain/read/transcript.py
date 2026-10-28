"""Transcript reading: normalise to turns, then one turn per chunk.

Accepted inputs match the step-2 intake: VTT, Teams-style JSON, Recall.ai
final-transcript JSON, and plain "Speaker: text" lines. Consecutive turns from
the same speaker merge into one chunk up to 400 tokens; a longer turn splits at
sentence boundaries (plan step 3, transcript.py).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from brain.read.chunk import (
    WINDOW_TOKENS,
    Chunk,
    count_tokens,
    window_chunks,
)


class TranscriptError(ValueError):
    """Raised when a transcript cannot be normalised into turns."""


@dataclass(frozen=True)
class Turn:
    """One speaker utterance with its optional start time."""

    speaker: str
    t0: str | None
    text: str


def _format_t0(value: Any) -> str | None:
    """Return a HH:MM:SS start time, or None when the input has none."""
    if value is None:
        return None
    if isinstance(value, int | float):
        seconds = int(value)
        hours, rest = divmod(seconds, 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    text = str(value).strip()
    if not text:
        return None
    long_form = re.match(r"(\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?$", text)
    if long_form:
        return f"{int(long_form.group(1)):02d}:{long_form.group(2)}:{long_form.group(3)}"
    short_form = re.match(r"(\d{1,2}):(\d{2})(?:\.\d+)?$", text)
    if short_form:
        return f"00:{int(short_form.group(1)):02d}:{short_form.group(2)}"
    try:
        return _format_t0(float(text))
    except ValueError:
        return text


def _speaker_of(item: dict[str, Any]) -> str | None:
    """Return the speaker name a JSON turn declares, under any common key."""
    participant = item.get("participant")
    if isinstance(participant, dict):
        name = participant.get("name") or participant.get("id")
        if name is not None:
            return str(name)
    elif isinstance(participant, str) and participant:
        return participant
    for key in ("speaker", "name", "displayName", "display_name", "author"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            nested = value.get("name")
            if isinstance(nested, str) and nested:
                return nested
    return None


def _turn_from_object(item: dict[str, Any]) -> Turn:
    """Build one turn from a Recall.ai or Teams-style JSON object."""
    speaker = _speaker_of(item)
    text = ""
    t0_raw = None
    words = item.get("words")
    if isinstance(words, list) and words:
        text = " ".join(
            str(word.get("text") or "")
            for word in words
            if isinstance(word, dict)
        ).strip()
        first = words[0]
        if isinstance(first, dict):
            t0_raw = first.get("start_timestamp")
    if not text:
        for key in ("text", "content", "message"):
            value = item.get(key)
            if isinstance(value, str) and value:
                text = value.strip()
                break
    if t0_raw is None:
        for key in ("t0", "start_time", "start_timestamp", "timestamp"):
            if item.get(key) is not None:
                t0_raw = item[key]
                break
    if speaker is None:
        raise TranscriptError("transcript JSON turn has no speaker")
    if not text:
        raise TranscriptError("transcript JSON turn has no text")
    return Turn(speaker=speaker, t0=_format_t0(t0_raw), text=text)


def _turns_from_json(value: Any) -> list[Turn]:
    """Build turns from a decoded JSON transcript payload."""
    if isinstance(value, dict):
        for key in ("transcript", "turns", "segments", "items"):
            inner = value.get(key)
            if isinstance(inner, list):
                value = inner
                break
        else:
            raise TranscriptError("transcript JSON has no turn list")
    if not isinstance(value, list):
        raise TranscriptError("transcript JSON must hold a list of turns")
    turns: list[Turn] = []
    for item in value:
        if not isinstance(item, dict):
            raise TranscriptError("transcript JSON turn must be an object")
        turns.append(_turn_from_object(item))
    return turns


def _turns_from_vtt(raw: str) -> list[Turn]:
    """Build turns from a WebVTT transcript."""
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    turns: list[Turn] = []
    for block in blocks:
        lines = block.splitlines()
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        start = lines[timing_index].split("-->")[0].strip()
        body = [line.strip() for line in lines[timing_index + 1 :] if line.strip()]
        if not body:
            continue
        joined = " ".join(body)
        speaker: str | None = None
        voiced = re.match(r"<v\s*([^>]+)>(.*)$", joined)
        if voiced:
            speaker = voiced.group(1).strip()
            joined = re.sub(r"</v>", "", voiced.group(2)).strip()
        else:
            named = re.match(r"([^:]{1,60}):\s+(.*)$", joined)
            if named:
                speaker = named.group(1).strip()
                joined = named.group(2).strip()
        turns.append(
            Turn(
                speaker=speaker or "Unknown",
                t0=_format_t0(start),
                text=joined,
            )
        )
    return turns


def _turns_from_speaker_lines(raw: str) -> list[Turn]:
    """Build turns from plain "Speaker: text" lines."""
    turns: list[Turn] = []
    for line in raw.replace("\r\n", "\n").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        named = re.match(r"^([^:]{1,60}):\s+(.*)$", stripped)
        if named:
            turns.append(
                Turn(
                    speaker=named.group(1).strip(),
                    t0=None,
                    text=named.group(2).strip(),
                )
            )
        elif turns:
            previous = turns[-1]
            turns[-1] = Turn(
                speaker=previous.speaker,
                t0=previous.t0,
                text=f"{previous.text} {stripped}".strip(),
            )
        else:
            turns.append(Turn(speaker="Unknown", t0=None, text=stripped))
    return turns


def parse_turns(text: str) -> list[Turn]:
    """Normalise any accepted transcript format into turns."""
    raw = text.replace("\r\n", "\n")
    stripped = raw.lstrip()
    if stripped.startswith("WEBVTT"):
        turns = _turns_from_vtt(raw)
    elif stripped.startswith("[") or stripped.startswith("{"):
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise TranscriptError("transcript JSON is not valid JSON") from exc
        turns = _turns_from_json(value)
    else:
        turns = _turns_from_speaker_lines(raw)
    if not turns:
        raise TranscriptError("transcript has no turns")
    return turns


def _split_long_turn(text: str) -> list[str]:
    """Split an over-long turn at sentence boundaries within the window."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    pieces: list[str] = []
    current: list[str] = []
    tokens = 0
    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if sentence_tokens > WINDOW_TOKENS:
            if current:
                pieces.append(" ".join(current))
                current = []
                tokens = 0
            pieces.extend(chunk.text for chunk in window_chunks(sentence, {}))
            continue
        if current and tokens + sentence_tokens > WINDOW_TOKENS:
            pieces.append(" ".join(current))
            current = []
            tokens = 0
        current.append(sentence)
        tokens += sentence_tokens
    if current:
        pieces.append(" ".join(current))
    return pieces


def _turn_chunk(turn: Turn, number: int, text: str) -> Chunk:
    """Build one chunk for a turn, prefixed so text steps see who spoke."""
    body = f"{turn.speaker}: {text}"
    locator: dict[str, Any] = {"turn": number, "speaker": turn.speaker}
    if turn.t0 is not None:
        locator["t0"] = turn.t0
    return Chunk(locator, body, count_tokens(body))


def chunk_turns(turns: Sequence[Turn]) -> list[Chunk]:
    """Chunk turns: one chunk per speaker run, at most 400 tokens."""
    usable = [turn for turn in turns if turn.text.strip()]
    chunks: list[Chunk] = []
    index = 0
    while index < len(usable):
        speaker = usable[index].speaker
        first_number = index + 1
        group: list[str] = []
        tokens = 0
        cursor = index
        while cursor < len(usable) and usable[cursor].speaker == speaker:
            text = usable[cursor].text.strip()
            piece = count_tokens(text)
            if group and tokens + piece > WINDOW_TOKENS:
                break
            if not group and piece > WINDOW_TOKENS:
                break
            group.append(text)
            tokens += piece
            cursor += 1
        if not group:
            turn = usable[cursor]
            for piece_text in _split_long_turn(turn.text):
                chunks.append(_turn_chunk(turn, cursor + 1, piece_text))
            index = cursor + 1
            continue
        chunks.append(_turn_chunk(usable[index], first_number, " ".join(group)))
        index = cursor
    return chunks


def read_transcript(text: str) -> list[Chunk]:
    """Read a transcript into turn chunks (plan step 3, transcript.py)."""
    return chunk_turns(parse_turns(text))
