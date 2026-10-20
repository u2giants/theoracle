#!/usr/bin/env python3
"""Verify a reviewed retirement packet without mutating files or infrastructure."""
import argparse
import json
from pathlib import Path
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.retirement import verify_retirement

REQUIRED_CENSUS_KEYS = (
    'legacy_core_modules', 'imports_of_legacy_core',
    'trigger_jobs_touching_legacy', 'web_routes_legacy_auth',
    'legacy_writers', 'new_legacy_writers', 'fallback_dispatches',
)

def validate_census_completeness(census: dict) -> None:
    """Every import/job/route/writer population must be present and explicit."""
    for key in REQUIRED_CENSUS_KEYS:
        if key not in census:
            raise ValueError(f'census missing required population: {key}')
    if census.get('new_legacy_writers') != []:
        raise PermissionError('new legacy writers are prohibited')
    if census.get('fallback_dispatches') != []:
        raise PermissionError('fallback dispatch is prohibited')
    if census.get('deletion_authorized') is not False:
        raise PermissionError('census must record deletion_authorized=false')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--admission', type=Path, required=True,
                        help='Independent trusted admission registry, separate from proposed packet')
    parser.add_argument('--census-file', type=Path, default=None,
                        help='Optional import/job/route/writer census JSON to validate completeness')
    args = parser.parse_args()
    raw = args.packet.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError('retirement packet exceeds bound')
    packet = json.loads(raw)
    admission_raw = args.admission.read_bytes()
    if len(admission_raw) > 1024 * 1024:
        raise ValueError('admission registry exceeds bound')
    admission = json.loads(admission_raw)
    if args.census_file:
        census_raw = args.census_file.read_bytes()
        if len(census_raw) > 1024 * 1024:
            raise ValueError('census file exceeds bound')
        census_doc = json.loads(census_raw)
        validate_census_completeness(census_doc)
    manifest = ReleaseManifest.model_validate_json(json.dumps(packet['manifest']))
    proof = verify_retirement(manifest, packet['census'],
                              proposed_paths=tuple(packet['proposed_paths']),
                              preserved_capabilities=packet['preserved_capabilities'],
                              accepted_release_hashes=frozenset(admission['accepted_release_hashes']),
                              admitted_census_hashes=frozenset(admission['admitted_census_hashes']),
                              admitted_equivalence_hashes=frozenset(admission['admitted_equivalence_hashes']))
    if args.census_file:
        proof['census_file_validated'] = True
    print(json.dumps(proof, sort_keys=True))

if __name__ == '__main__':
    main()
