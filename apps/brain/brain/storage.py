"""Supabase Storage access for the brain service.

The storage bucket is ``company_documents`` (plan §2); intake stores every
source under the ``cmap/<uuid>/<filename>`` key scheme so keys are always
uuid-based and never carry caller-controlled path segments.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from brain.config import Settings, get_settings

BUCKET_COMPANY_DOCUMENTS = "company_documents"


class StorageError(RuntimeError):
    """Raised when the storage service refuses an operation."""


class StorageClient(Protocol):
    """The storage operations source intake needs."""

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        """Store ``data`` under ``key``."""

    def download(self, key: str) -> bytes:
        """Return the bytes stored under ``key``."""

    def delete(self, key: str) -> None:
        """Remove ``key`` (missing keys are not an error)."""

    def list(self, prefix: str) -> list[str]:
        """Return every key under ``prefix``."""


class SupabaseStorage:
    """StorageClient talking to the Supabase Storage REST API."""

    def __init__(self, base_url: str, service_role_key: str, bucket: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._bucket = bucket
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {service_role_key}"},
            timeout=60.0,
        )

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        response = self._client.post(
            f"/storage/v1/object/{self._bucket}/{key}",
            content=data,
            headers={"Content-Type": content_type},
        )
        if response.status_code not in (200, 201):
            raise StorageError(
                f"storage upload failed for {key}: "
                f"{response.status_code} {response.text[:200]}"
            )

    def download(self, key: str) -> bytes:
        response = self._client.get(f"/storage/v1/object/{self._bucket}/{key}")
        if response.status_code != 200:
            raise StorageError(
                f"storage download failed for {key}: "
                f"{response.status_code} {response.text[:200]}"
            )
        return response.content

    def delete(self, key: str) -> None:
        response = self._client.delete(f"/storage/v1/object/{self._bucket}/{key}")
        if response.status_code not in (200, 204, 404):
            raise StorageError(
                f"storage delete failed for {key}: "
                f"{response.status_code} {response.text[:200]}"
            )

    def list(self, prefix: str) -> list[str]:
        """Return every file key under ``prefix``, walking sub-folders."""
        keys: list[str] = []
        self._list_level(prefix, keys)
        return keys

    def _list_level(self, prefix: str, keys: list[str]) -> None:
        offset = 0
        page_limit = 100
        while True:
            response = self._client.post(
                f"/storage/v1/object/list/{self._bucket}",
                json={
                    "prefix": prefix,
                    "limit": page_limit,
                    "offset": offset,
                    "sortBy": {"column": "name", "order": "asc"},
                },
            )
            if response.status_code != 200:
                raise StorageError(
                    f"storage list failed for {prefix}: "
                    f"{response.status_code} {response.text[:200]}"
                )
            page: list[dict[str, Any]] = response.json()
            for entry in page:
                name = entry.get("name")
                if not isinstance(name, str) or not name:
                    continue
                key = f"{prefix}{name}" if prefix else name
                if entry.get("id") is None:
                    self._list_level(f"{key}/", keys)
                else:
                    keys.append(key)
            if len(page) < page_limit:
                return
            offset += page_limit


def get_storage(settings: Settings | None = None) -> StorageClient:
    """Return the process storage client."""
    cfg = settings if settings is not None else get_settings()
    if cfg.supabase_url is None or cfg.supabase_service_role_key is None:
        raise StorageError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return SupabaseStorage(
        cfg.supabase_url,
        cfg.supabase_service_role_key,
        BUCKET_COMPANY_DOCUMENTS,
    )
