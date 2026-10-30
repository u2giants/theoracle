"""Request authentication for the brain API (plan §8).

The Next.js proxy is the only caller: it forwards the shared service token in
``x-brain-token`` and the logged-in Supabase auth user id in ``x-user-id``.
Upload, delete and run endpoints additionally require the employee's
``is_admin`` flag — no other permission model exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException

from brain.config import get_settings
from brain.db import get_pool

EMPLOYEE_LOOKUP_SQL = """
SELECT e.id::text, e.is_admin
FROM public.employee_identities AS ei
JOIN public.employees AS e ON e.id = ei.employee_id
WHERE ei.auth_user_id = %s AND e.disabled_at IS NULL
LIMIT 1
"""


@dataclass(frozen=True)
class User:
    """The logged-in employee behind a proxied request."""

    auth_user_id: str
    employee_id: str
    is_admin: bool


def current_user(
    x_brain_token: str = Header(default=""),
    x_user_id: str = Header(default=""),
) -> User:
    """Authenticate the shared token and resolve the proxied employee."""
    expected = get_settings().brain_shared_token
    if expected is None:
        raise HTTPException(status_code=503, detail="BRAIN_SHARED_TOKEN is not set")
    if x_brain_token != expected:
        raise HTTPException(status_code=401, detail="invalid x-brain-token")
    try:
        auth_user_id = str(UUID(x_user_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="invalid x-user-id") from exc
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(EMPLOYEE_LOOKUP_SQL, (auth_user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=403, detail="no active employee for x-user-id")
    employee_id, is_admin = row
    return User(
        auth_user_id=auth_user_id,
        employee_id=employee_id,
        is_admin=bool(is_admin),
    )


def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    """Reject non-admin callers of upload, delete and run endpoints."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin required")
    return user


def require_service(
    x_brain_token: str = Header(default=""),
    x_user_id: str | None = Header(default=None),
) -> None:
    """Accept a server-to-server call carrying only the shared token.

    Used by the Teams bot routes, which act for no logged-in employee.
    """
    expected = get_settings().brain_shared_token
    if expected is None:
        raise HTTPException(status_code=503, detail="BRAIN_SHARED_TOKEN is not set")
    if x_brain_token != expected:
        raise HTTPException(status_code=401, detail="invalid x-brain-token")

    if x_user_id is not None:
        raise HTTPException(status_code=403, detail="service calls must not carry x-user-id")


def admin_or_service(
    x_brain_token: str = Header(default=""),
    x_user_id: str = Header(default=""),
) -> User | None:
    """An admin employee, or ``None`` for a service call with no user header."""
    if not x_user_id:
        require_service(x_brain_token, None)
        return None
    user = current_user(x_brain_token=x_brain_token, x_user_id=x_user_id)
    return require_admin(user)
