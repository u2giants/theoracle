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


def require_service(x_brain_token: str = Header(default="")) -> None:
    """Accept a server-to-server call carrying only the shared token.

    Used by the Teams bot routes, which act for no logged-in employee.
    """
    expected = get_settings().brain_shared_token
    if expected is None:
        raise HTTPException(status_code=503, detail="BRAIN_SHARED_TOKEN is not set")
    if x_brain_token != expected:
        raise HTTPException(status_code=401, detail="invalid x-brain-token")


def admin_or_service(
    x_brain_token: str = Header(default=""),
    x_user_id: str = Header(default=""),
) -> User | None:
    """An admin employee, or ``None`` for a service call with no user header."""
    if not x_user_id:
        require_service(x_brain_token)
        return None
    user = current_user(x_brain_token=x_brain_token, x_user_id=x_user_id)
    return require_admin(user)


def employee_or_service(
    x_brain_token: str = Header(default=""),
    x_user_id: str = Header(default=""),
) -> User | None:
    """An active employee, or ``None`` for a service call with no user header."""
    if not x_user_id:
        require_service(x_brain_token)
        return None
    return current_user(x_brain_token=x_brain_token, x_user_id=x_user_id)


def _interviews_enabled() -> bool:
    """The tick's own send condition: env flag and admin-page switch both on."""
    # Imported lazily: brain.interview.tick pulls in the api package, so a
    # module-level import here would be circular.
    from brain.interview.tick import interviews_enabled

    with get_pool().connection() as conn:
        return interviews_enabled(conn, get_settings())


def admin_or_enabled_service(
    x_brain_token: str = Header(default=""),
    x_user_id: str = Header(default=""),
) -> User | None:
    """Gate for the endpoints behind the proactive Teams send (#591).

    The proactive channel used to answer to the shared token alone. Now an
    ``x-user-id`` caller must be an admin — the sanctioned nudge/invite
    pattern carries the brain token plus an admin user context — and a
    token-only service call is accepted only while the interview feature is
    enabled, the very condition the interview tick sends under, so the tick
    keeps working while the free-form channel stays closed otherwise.
    """
    if not x_user_id:
        require_service(x_brain_token)
        if not _interviews_enabled():
            raise HTTPException(status_code=403, detail="interviews are disabled")
        return None
    return require_admin(current_user(x_brain_token=x_brain_token, x_user_id=x_user_id))
