"""Model-seat reporting for the admin model page (plan §11).

Seating lives in the Coolify env for app ``oracle-brain``; this endpoint
mirrors those values so the admin page can show the live seats without
inventing a second config store. No model id is hard-coded here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from brain.api.deps import require_service
from brain.config import chat_model, eval_model, get_settings

router = APIRouter()


@router.get("/models", dependencies=[Depends(require_service)])
def get_models() -> dict[str, dict[str, Any]]:
    """Report the env-configured model seats for the nine pipeline stages."""
    settings = get_settings()
    frontier = settings.brain_frontier_model
    return {
        "models": {
            "vision": settings.brain_vision_model,
            "embed": settings.brain_embed_model,
            "embed_dims": settings.brain_embed_dims,
            "flat_fallback": frontier,
            "relations": frontier,
            "resolve": frontier,
            "reports": frontier,
            "answer": chat_model(settings),
            "recommend": frontier,
            "grade": eval_model(settings),
            "scaledown_enabled": settings.brain_scaledown_enabled,
        }
    }
