"""Model seats for the admin model page.

Each stage's live model is the seat chosen on the page (``cmap.model_seat``)
or, without one, the env seat in the Coolify app ``oracle-brain`` (plan §11).
No model id is hard-coded here.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Json
from pydantic import BaseModel

from brain.api.deps import User, require_admin, require_service
from brain.config import get_settings
from brain.db import get_pool
from brain.seats import STAGES, clear_cache, seat_report, set_seat, stage_model

router = APIRouter()


@router.get("/models", dependencies=[Depends(require_service)])
def get_models() -> dict[str, Any]:
    """Report the live model for each pipeline stage."""
    settings = get_settings()
    seats = seat_report(settings)
    return {
        "models": {
            "vision": seats["vision"]["model"],
            "embed": seats["embed"]["model"],
            "embed_dims": settings.brain_embed_dims,
            "flat_fallback": seats["flat"]["model"],
            "relations": seats["relations"]["model"],
            "resolve": seats["resolve"]["model"],
            "reports": seats["reports"]["model"],
            "answer": seats["answer"]["model"],
            "recommend": seats["recommend"]["model"],
            "grade": seats["grade"]["model"],
            "scaledown_enabled": settings.brain_scaledown_enabled,
        },
        "seats": seats,
    }


class SeatBody(BaseModel):
    model: str


@router.put("/models/{stage}")
def put_model(
    stage: str,
    body: SeatBody,
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    """Seat one stage's model from the admin page.

    Changing the embeddings model re-embeds every stored vector (a queued
    ``reembed`` job): vectors from two models cannot be compared.
    """
    if stage not in STAGES:
        raise HTTPException(status_code=404, detail=f"unknown stage {stage!r}")
    model = body.model.strip()
    if not model:
        raise HTTPException(status_code=422, detail="model is required")
    settings = get_settings()
    before = stage_model(settings, stage)
    reembed = stage == "embed" and model != before
    # The seat and its reembed job land together or not at all: a seat change
    # without the job would leave every stored vector in the old model's space.
    with get_pool().connection() as conn:
        set_seat(stage, model, user.auth_user_id, conn)
        if reembed:
            conn.execute(
                "INSERT INTO cmap.job (kind, payload) VALUES ('reembed', %s)",
                (Json({"model": model}),),
            )
        conn.commit()
    clear_cache()
    return {"stage": stage, "model": model, "reembed_queued": reembed}
