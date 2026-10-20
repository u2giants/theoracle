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
    if (not isinstance(provider_id, str) or not provider_id.strip()
            or provider_id != provider_id.strip() or not isinstance(verified_links, dict)):
        return Speaker(provider_id, display_name)
    raw_links = verified_links.get(provider_id, ())
    if not isinstance(raw_links, tuple):
        return Speaker(provider_id, display_name)
    # Any malformed link makes attribution unknown; never salvage a potentially
    # ambiguous map by silently dropping invalid entries.
    if any(not isinstance(link, str) or not link.strip() or link != link.strip() for link in raw_links):
        return Speaker(provider_id, display_name)
    links = set(raw_links)
    return Speaker(provider_id, display_name, next(iter(links)) if len(links) == 1 else None)
