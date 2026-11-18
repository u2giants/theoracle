"""Replay real interview exchanges through the composer (issue #604, plan Step 6).

Read-only. Takes the six real exchanges from plan §6.3–6.5, runs each through
``converse.compose_next`` with the live ``converse`` seat, and prints the old
reply next to the new one. It is a check, not only a printout: it exits 1 if
any new reply equals the old fixed string, came from the deterministic
fallback instead of the model, has no reflection of an answer, or names a
person or system the employee never mentioned.

    cd apps/brain && uv run python scripts/replay_interview.py

Needs ``DATABASE_URL`` (opened with ``default_transaction_read_only=on``) and
the OpenRouter key used by the ``converse`` seat. Nothing is written or sent.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import psycopg

from brain.config import Settings, get_settings
from brain.interview import converse, followup

OLD_REPLY = "Thanks, that's recorded."

# (question, employee message, kind of the employee turn), from plan §6.3–6.5.
EXCHANGES: list[tuple[str, str, str]] = [
    (
        "Who is responsible for checking the shared mailbox for new licensor "
        "approvals, and how often is it checked?",
        "Yes, in Design Flow Item Library.",
        "answer",
    ),
    (
        "What are Elizabeth's and Angie's responsibilities when a new design "
        "is handed to production?",
        "Editable illustrator file and pdf to send.",
        "answer",
    ),
    (
        "Walk me through how a new product goes from concept to approval.",
        "that's a vague question about many steps that are not explicitly called out",
        "unclear",
    ),
    (
        "Walk me through how a new product goes from concept to approval.",
        "ask the question properly, with all the detail that an answerer would "
        "reasonably need",
        "unclear",
    ),
    (
        "Which system do you use to track sample requests?",
        "Can you number your questions so I can answer them one by one?",
        "request",
    ),
    (
        "How are artwork files checked before they go to the factory?",
        "I don't know, I'm not the design team",
        "dont_know",
    ),
]

QUEUE: list[tuple[str, str, str]] = [
    (
        "00000000-0000-0000-0000-000000000001",
        "Who approves a design before it is sent to the licensor?",
        "Who approves a design before it is sent to the licensor?",
    ),
]


def build(question: str, message: str, kind: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    conv = {
        "id": "replay",
        "employee_id": "00000000-0000-0000-0000-000000000000",
        "lang": "en",
        "exchanges": 1,
        "state": "processing",
    }
    tlist = [
        {"seq": 1, "direction": "out", "kind": "question", "text": question,
         "source_id": None, "question_id": QUEUE[0][0]},
        {"seq": 2, "direction": "in", "kind": kind, "text": message,
         "source_id": None, "question_id": None},
    ]
    return conv, tlist


def problems(result: dict[str, Any], question: str, message: str, kind: str) -> list[str]:
    text = " ".join(str(result.get("text") or "").split())
    found = []
    if not text or text == OLD_REPLY:
        found.append("empty or old fixed reply")
    if result.get("path") == "fallback":
        found.append("model failed; deterministic fallback used")
    if kind == "answer" and result.get("action") != "close" and not result.get("reflect"):
        found.append("no reflection of the answer")
    # The composer's own guard: names in the reflection or in a follow-up.
    allowed = f"{message}\n{question}\n" + "\n".join(q for _, q, _ in QUEUE)
    guarded = str(result.get("reflect") or "")
    if result.get("action") == "followup":
        guarded += f" {text}"
    invented = followup.invented_names(guarded, allowed)
    if invented:
        found.append(f"names not from the employee or question: {sorted(invented)}")
    return found


def compose(
    conn: Any, conv: dict[str, Any], tlist: list[dict[str, Any]], question: str,
    settings: Settings,
) -> dict[str, Any]:
    """The reply production would write: a pushback gets a clarified question."""
    if tlist[-1]["kind"] != "unclear":
        return converse.compose_next(conn, conv, tlist, list(QUEUE), settings)
    real = converse.conv_mod.question_text
    converse.conv_mod.question_text = lambda c, qid: question
    try:
        text = converse._clarified(conn, QUEUE[0][0], conv["lang"], settings)
    finally:
        converse.conv_mod.question_text = real
    return {
        "action": "clarify",
        "text": text,
        "path": "model" if text else "fallback",
        "question_id": QUEUE[0][0],
    }


def replay(conn: Any, settings: Settings) -> int:
    failures = 0
    for n, (question, message, kind) in enumerate(EXCHANGES, 1):
        conv, tlist = build(question, message, kind)
        result = compose(conn, conv, tlist, question, settings)
        bad = problems(result, question, message, kind)
        failures += bool(bad)
        print(f"--- exchange {n} ({kind}) {'FAIL' if bad else 'ok'}")
        print(f"Q:      {question}")
        print(f"A:      {message}")
        print(f"before: {OLD_REPLY}")
        print(f"after:  [{result.get('action')}/{result.get('path')}] {result.get('text')}")
        for b in bad:
            print(f"  ! {b}")
    print(f"\n{len(EXCHANGES) - failures}/{len(EXCHANGES)} passed")
    return 1 if failures else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    if settings.database_url is None:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(
        settings.database_url, options="-c default_transaction_read_only=on"
    ) as conn:
        return replay(conn, settings)


if __name__ == "__main__":
    sys.exit(main())
