"""Meeting-local speaker resolution; display names never establish identity."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Speaker:
    provider_id: str
    display_name: str
    employee_id: str | None = None


def resolve_speaker(provider_id: str, display_name: str,
                    verified_links: dict[str, tuple[str, ...]]) -> Speaker:
    """Only a unique provider identifier link can supply an employee identity."""
    raw_links = verified_links.get(provider_id, ()) if provider_id else ()
    # Any malformed link makes attribution unknown; never salvage a potentially
    # ambiguous map by silently dropping invalid entries.
    if any(not isinstance(link, str) or not link.strip() for link in raw_links):
        return Speaker(provider_id, display_name)
    links = set(raw_links)
    return Speaker(provider_id, display_name, next(iter(links)) if len(links) == 1 else None)
