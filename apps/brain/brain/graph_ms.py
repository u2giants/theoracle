"""Shared Microsoft Graph helpers for brain intake (plan_pm_message_intake.md 1.3).

App-only (client-credentials) token from the same Entra app the web uses, a
retrying GET (429 and 5xx, honouring Retry-After) and a paging helper that
follows ``@odata.nextLink`` and refuses to loop or to return one item twice.

Environment: AZURE_TENANT_ID, AZURE_GRAPH_CLIENT_ID, AZURE_GRAPH_CLIENT_SECRET.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import Any

import httpx

GRAPH = "https://graph.microsoft.com/v1.0"


class GraphPagingError(RuntimeError):
    """Paging repeated a link or an item. The caller stops; it must not retry."""


def graph_token() -> str:
    """App-only Graph access token from the client-credentials grant."""
    r = httpx.post(
        f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["AZURE_GRAPH_CLIENT_ID"],
            "client_secret": os.environ["AZURE_GRAPH_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def get_retry(client: httpx.Client, url: str, **kw: Any) -> httpx.Response:
    """GET with up to eight tries on 429 and 5xx; other errors raise at once."""
    for attempt in range(8):
        r = client.get(url, **kw)
        if r.status_code != 429 and r.status_code < 500:
            r.raise_for_status()
            return r
        wait = r.headers.get("Retry-After")
        reset = r.headers.get("X-RateLimit-Reset")
        if wait:
            delay = min(max(float(wait), 1.0), 60.0)
        elif reset:
            delay = min(max(float(reset) - time.time(), 1.0), 60.0)
        else:
            delay = min(2**attempt, 60)
        time.sleep(delay)
    r.raise_for_status()
    return r


def graph_pages(
    client: httpx.Client, url: str, params: dict | None = None
) -> Iterator[dict[str, Any]]:
    """Yield every ``value`` item across pages, following ``@odata.nextLink``.

    Raises GraphPagingError if a link repeats (a loop) or if an item id
    appears twice (paging returned a duplicate). Lazy: stop iterating to stop
    requesting pages.
    """
    seen_links: set[str] = set()
    seen_ids: set[str] = set()
    while url:
        if url in seen_links:
            raise GraphPagingError("Graph paging loop: a nextLink repeated")
        seen_links.add(url)
        body = get_retry(client, url, params=params).json()
        params = None  # the nextLink already carries the query
        for item in body.get("value", []):
            item_id = item.get("id") if isinstance(item, dict) else None
            if item_id is not None:
                if item_id in seen_ids:
                    raise GraphPagingError("Graph paging returned a duplicate item")
                seen_ids.add(item_id)
            yield item
        url = body.get("@odata.nextLink")
