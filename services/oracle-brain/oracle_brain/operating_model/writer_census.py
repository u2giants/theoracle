"""Stage 0 writer-census adjudication and stable digest for the global writer cut.

Converts the candidate inventory into an adjudicated confirmed/candidate/excluded
census with a stable SHA-256 digest. Unknown sites block the digest: the cut
cannot start with an unknown writer. F9 external classes are incompleteness
declarations, never fenced writers.

No POP shared-db claim. Legacy Oracle Supabase 'theoracle' is Oracle-owned.
"""
from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from .contracts import canonical_bytes


class SiteClassification(str, Enum):
    CONFIRMED = 'confirmed'
    CANDIDATE = 'candidate'
    EXTERNAL = 'external'
    EXCLUDED = 'excluded'
    UNKNOWN = 'unknown'


class WriterSite(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    file: str
    lines: tuple[int, ...] = ()
    op: str = ''
    family_id: str
    classification: SiteClassification
    notes: str = ''
    adjudication: SiteClassification | None = None
    adjudication_reason: str = ''


class CensusResult(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    adjudicated: bool
    unknown_count: int
    confirmed_count: int
    excluded_count: int
    external_count: int
    candidate_pending_count: int
    census_digest: str | None
    blocking_reasons: tuple[str, ...] = ()


# Deterministic exclusion patterns for lexical false positives.
_EXCLUDED_OP_MARKERS = (
    'hash-only',
    'hash helper',
    'hash verification',
    'HMAC',
    'encrypt/decrypt',
    'in-memory',
    'in-process',
    'URL parsing',
    'commented example',
    'crypto only',
)


def _is_excluded_candidate(site: WriterSite) -> bool:
    if site.classification is not SiteClassification.CANDIDATE:
        return False
    haystack = f'{site.op} {site.notes}'.lower()
    return any(marker.lower() in haystack for marker in _EXCLUDED_OP_MARKERS)


def adjudicate_site(site: WriterSite) -> WriterSite:
    """Return the site with an adjudication. Unknown blocks; candidates auto-exclude
    only when the lexical marker is unambiguously non-persistent."""
    if site.classification is SiteClassification.CONFIRMED:
        return site.model_copy(update={
            'adjudication': SiteClassification.CONFIRMED,
            'adjudication_reason': 'inventory classification confirmed persistent-state mutator',
        })
    if site.classification is SiteClassification.EXTERNAL:
        return site.model_copy(update={
            'adjudication': SiteClassification.EXTERNAL,
            'adjudication_reason': 'external uncontrolled class; incompleteness declaration',
        })
    if _is_excluded_candidate(site):
        return site.model_copy(update={
            'adjudication': SiteClassification.EXCLUDED,
            'adjudication_reason': 'lexical candidate matches non-persistent marker',
        })
    return site.model_copy(update={
        'adjudication': SiteClassification.UNKNOWN,
        'adjudication_reason': 'candidate requires manual adjudication before census digest',
    })


def load_inventory(path: Path) -> list[WriterSite]:
    raw = json.loads(path.read_text(encoding='utf-8'))
    sites: list[WriterSite] = []
    for family in raw.get('families', []):
        family_id = family['family_id']
        for entry in family.get('sites', []):
            classification = SiteClassification(entry.get('classification', 'unknown'))
            lines = entry.get('lines') or []
            sites.append(WriterSite(
                file=entry['file'],
                lines=tuple(int(x) for x in lines),
                op=entry.get('op', ''),
                family_id=family_id,
                classification=classification,
                notes=entry.get('notes', ''),
            ))
    return sites


def adjudicate_sites(sites: Iterable[WriterSite]) -> list[WriterSite]:
    return [adjudicate_site(s) for s in sites]


def _site_digest_key(site: WriterSite) -> dict:
    return {
        'file': site.file,
        'lines': list(site.lines),
        'family_id': site.family_id,
        'adjudication': site.adjudication.value if site.adjudication else None,
        'op': site.op,
    }


def compute_census_digest(adjudicated: Iterable[WriterSite]) -> CensusResult:
    """SHA-256 of the canonical sorted confirmed-writer list (file + line-range +
    family + owner module). Unknown sites block the digest."""
    sites = list(adjudicated)
    unknown = [s for s in sites if s.adjudication is SiteClassification.UNKNOWN]
    confirmed = [s for s in sites if s.adjudication is SiteClassification.CONFIRMED]
    excluded = [s for s in sites if s.adjudication is SiteClassification.EXCLUDED]
    external = [s for s in sites if s.adjudication is SiteClassification.EXTERNAL]
    pending = [s for s in sites if s.adjudication is SiteClassification.CANDIDATE]

    blocking: list[str] = []
    if unknown:
        blocking.append(f'{len(unknown)} unknown writer site(s) block the census digest')
    if pending:
        blocking.append(f'{len(pending)} candidate site(s) remain unadjudicated')

    digest_value: str | None = None
    if not blocking:
        keys = sorted((_site_digest_key(s) for s in confirmed),
                      key=lambda k: (k['file'], k['lines'], k['family_id']))
        digest_value = hashlib.sha256(canonical_bytes({'confirmed_writers': keys})).hexdigest()

    return CensusResult(
        adjudicated=not blocking,
        unknown_count=len(unknown),
        confirmed_count=len(confirmed),
        excluded_count=len(excluded),
        external_count=len(external),
        candidate_pending_count=len(pending),
        census_digest=digest_value,
        blocking_reasons=tuple(blocking),
    )


def run_census(inventory_path: Path) -> tuple[CensusResult, list[WriterSite]]:
    sites = adjudicate_sites(load_inventory(inventory_path))
    return compute_census_digest(sites), sites
