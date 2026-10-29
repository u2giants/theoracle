"""Question answering endpoint (plan step 9).

``POST /answer`` answers one question in ``auto``, ``local`` or ``global``
mode. Any logged-in employee may ask; there is no approval gate and no
server-side session store — conversation history rides on the request.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from brain.answer.answer import HISTORY_TURNS, AnswerError, answer_question
from brain.api.deps import User, current_user

router = APIRouter()


class HistoryTurn(BaseModel):
    """One conversation turn sent with the question."""

    role: str
    content: str


class AnswerBody(BaseModel):
    """A question with its mode and the last conversation turns."""

    question: str
    mode: str = "auto"
    history: list[HistoryTurn] = []


@router.post("/answer")
def post_answer(
    body: AnswerBody,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    """Answer one question with citations back to sources."""
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if body.mode not in {"auto", "local", "global"}:
        raise HTTPException(status_code=400, detail="mode must be auto, local or global")
    history = [
        {"role": turn.role, "content": turn.content} for turn in body.history
    ][-HISTORY_TURNS:]
    try:
        return answer_question(question, body.mode, history)
    except AnswerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
