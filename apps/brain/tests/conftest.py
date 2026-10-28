"""Shared setup for the apps/brain test suite.

Tests run against a real Postgres (the CI service or the local dev database):
the migrations are applied once per session, two stand-in employee tables
back the plan §8 admin lookup, and storage is faked so intake never talks to
Supabase.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from brain import storage as storage_mod
from brain.config import get_settings

TEST_TOKEN = "brain-test-token"
ADMIN_AUTH_USER_ID = "00000000-0000-4000-8000-0000000000a2"
EMPLOYEE_AUTH_USER_ID = "00000000-0000-4000-8000-0000000000b2"

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RECORDED_DIR = FIXTURES_DIR / "recorded"

_EMPLOYEE_STUBS_SQL = """
CREATE TABLE IF NOT EXISTS public.employees (
  id uuid PRIMARY KEY,
  email text UNIQUE,
  name text,
  role text,
  is_admin boolean NOT NULL DEFAULT false,
  disabled_at timestamp
);
CREATE TABLE IF NOT EXISTS public.employee_identities (
  id uuid PRIMARY KEY,
  employee_id uuid NOT NULL,
  auth_user_id uuid NOT NULL UNIQUE
);
INSERT INTO public.employees (id, email, name, role, is_admin) VALUES
  ('00000000-0000-4000-8000-0000000000a1', 'admin@test.invalid', 'Test Admin', 'Operations', true),
  ('00000000-0000-4000-8000-0000000000b1', 'employee@test.invalid', 'Test Employee', 'Design', false)
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.employee_identities (id, employee_id, auth_user_id) VALUES
  ('00000000-0000-4000-8000-0000000000a3', '00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-0000000000a2'),
  ('00000000-0000-4000-8000-0000000000b3', '00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-0000000000b2')
ON CONFLICT (id) DO NOTHING;
"""


class FakeStorage:
    """In-memory stand-in for Supabase Storage."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        del content_type
        self.objects[key] = data

    def download(self, key: str) -> bytes:
        if key not in self.objects:
            raise storage_mod.StorageError(f"no such key: {key}")
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def list(self, prefix: str = "") -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))


@pytest.fixture(scope="session", autouse=True)
def _brain_env() -> None:
    """Set the shared token, apply migrations and install employee stubs."""
    os.environ["BRAIN_SHARED_TOKEN"] = TEST_TOKEN
    get_settings.cache_clear()
    from brain.migrate import migrate

    migrate()
    settings = get_settings()
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        conn.execute(_EMPLOYEE_STUBS_SQL)
        conn.commit()


@pytest.fixture(autouse=True)
def _clean_cmap() -> None:
    """Empty the intake tables so every test starts from zero sources."""
    settings = get_settings()
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        conn.execute("TRUNCATE cmap.source, cmap.job CASCADE")
        conn.commit()


@pytest.fixture()
def db() -> Iterator[psycopg.Connection]:
    """Yield a psycopg connection to the test database."""
    conn = psycopg.connect(get_settings().database_url, connect_timeout=5)
    yield conn
    conn.close()


@pytest.fixture()
def storage(monkeypatch: pytest.MonkeyPatch) -> FakeStorage:
    """Swap Supabase Storage for an in-memory fake."""
    fake = FakeStorage()
    monkeypatch.setattr(storage_mod, "get_storage", lambda settings=None: fake)
    return fake


@pytest.fixture()
def client(storage: FakeStorage) -> TestClient:
    """Return a test client wired to the fake storage."""
    from brain.main import app

    return TestClient(app)


@pytest.fixture()
def admin_headers() -> dict[str, str]:
    """Headers for the admin test employee."""
    return {"x-brain-token": TEST_TOKEN, "x-user-id": ADMIN_AUTH_USER_ID}


@pytest.fixture()
def user_headers() -> dict[str, str]:
    """Headers for the non-admin test employee."""
    return {"x-brain-token": TEST_TOKEN, "x-user-id": EMPLOYEE_AUTH_USER_ID}


def load_recorded(name: str) -> dict[str, Any]:
    """Load one recorded model response from ``tests/fixtures/recorded/``."""
    return json.loads((RECORDED_DIR / name).read_text(encoding="utf-8"))


def fake_vision(monkeypatch: pytest.MonkeyPatch, name: str) -> list[list[dict[str, Any]]]:
    """Replay a recorded vision response; return the message log of the calls."""
    from brain.read import vision

    recorded = load_recorded(name)
    calls: list[list[dict[str, Any]]] = []

    def _post_chat(
        messages: list[dict[str, Any]],
        settings: Any,
    ) -> dict[str, Any]:
        del settings
        calls.append(messages)
        return {
            "choices": [{"message": {"content": json.dumps(recorded)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }

    monkeypatch.setattr(vision, "_post_chat", _post_chat)
    return calls


def fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace the embeddings transport; return the batch log of the calls."""
    from brain import embed as embed_mod

    calls: list[list[str]] = []

    def _post_embeddings(
        texts: list[str],
        settings: Any,
    ) -> tuple[list[list[float]], dict[str, int]]:
        calls.append(list(texts))
        vectors = [[0.001 * len(text)] * settings.brain_embed_dims for text in texts]
        return vectors, {"embedding_tokens": len(texts) * 3}

    monkeypatch.setattr(embed_mod, "_post_embeddings", _post_embeddings)
    return calls
