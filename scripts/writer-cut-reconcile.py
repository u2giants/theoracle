#!/usr/bin/env python3
"""Inventory/reconciliation tool for the S14 global writer cut.

Walks writer-cut-complete-inventory.json, adjudicates every site, and emits:
  - census digest (or blocking reasons)
  - per-family confirmed/candidate/excluded counts
  - reconciliation report of confirmed files vs inventory totals

Offline only. No database, platform, production, or POP shared-db access.
Legacy Oracle Supabase 'theoracle' is Oracle-owned; no POP claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installation.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'oracle-brain'))

from oracle_brain.operating_model.writer_census import (  # noqa: E402
    SiteClassification,
    adjudicate_sites,
    compute_census_digest,
    load_inventory,
)


def reconcile(inventory_path: Path) -> dict:
    sites = load_inventory(inventory_path)
    adjudicated = adjudicate_sites(sites)
    result = compute_census_digest(adjudicated)

    by_family: dict[str, dict[str, int]] = {}
    for site in adjudicated:
        bucket = by_family.setdefault(site.family_id, {
            'confirmed': 0, 'excluded': 0, 'external': 0, 'unknown': 0, 'pending': 0,
        })
        label = {
            SiteClassification.CONFIRMED: 'confirmed',
            SiteClassification.EXCLUDED: 'excluded',
            SiteClassification.EXTERNAL: 'external',
            SiteClassification.UNKNOWN: 'unknown',
            SiteClassification.CANDIDATE: 'pending',
        }[site.adjudication or SiteClassification.UNKNOWN]
        bucket[label] += 1

    unknown_sites = [
        {'file': s.file, 'lines': list(s.lines), 'family_id': s.family_id, 'op': s.op}
        for s in adjudicated
        if s.adjudication is SiteClassification.UNKNOWN
    ]

    return {
        'artifact': 'S14 writer-cut inventory reconciliation',
        'inventory': str(inventory_path),
        'total_sites': len(sites),
        'adjudicated': result.adjudicated,
        'census_digest': result.census_digest,
        'blocking_reasons': list(result.blocking_reasons),
        'counts': {
            'confirmed': result.confirmed_count,
            'excluded': result.excluded_count,
            'external': result.external_count,
            'unknown': result.unknown_count,
            'candidate_pending': result.candidate_pending_count,
        },
        'by_family': by_family,
        'unknown_sites': unknown_sites,
        'boundaries': {
            'no_pop_shared_db_claim': True,
            'business_acceptance_held': True,
            'company_comparison_held': True,
            'live_cutover_held': True,
            'consistent_boundary_proven': False if not result.adjudicated else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--inventory',
        type=Path,
        default=ROOT / 'docs' / 'verification' / 'oracle2' / 's14-writer-cut' / 'writer-cut-complete-inventory.json',
    )
    parser.add_argument('--json', type=Path, help='write JSON report to this path')
    args = parser.parse_args()

    if not args.inventory.exists():
        print(f'inventory not found: {args.inventory}', file=sys.stderr)
        return 2

    report = reconcile(args.inventory)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json:
        args.json.write_text(text + '\n', encoding='utf-8')
    print(text)
    return 0 if report['adjudicated'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
