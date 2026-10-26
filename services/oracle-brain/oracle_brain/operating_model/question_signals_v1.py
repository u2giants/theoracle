"""Immutable question markers only. No retrieval scope, role or authority."""
_HISTORICAL_MARKERS = (
    "historical", "history", "used to", "previously", "earlier",
    "in the past", "over time", "before the", "last year", "last quarter",
)
_CONNECTED_MARKERS = (
    "across process", "between", "handoff", "downstream", "upstream",
    "connect", "related process", "interface", "depend", "along the",
    "end to end", "from design to",
)
_GLOBAL_MARKERS = (
    "company-wide", "companywide", "across the company", "across the org",
    "all processes", "entire company", "entire org", "whole company",
    "every process", "organization-wide", "org-wide", "overall",
)
_LOCAL_MARKERS = (
    "this process", "this source", "this document", "single process",
    "in this", "the process",
)


def _signals(question: str) -> tuple[bool, bool, bool, bool]:
    text = question.lower()
    return (
        any(m in text for m in _HISTORICAL_MARKERS),
        any(m in text for m in _CONNECTED_MARKERS),
        any(m in text for m in _GLOBAL_MARKERS),
        any(m in text for m in _LOCAL_MARKERS),
    )
