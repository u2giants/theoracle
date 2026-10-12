#!/usr/bin/env python3
"""Verify a reviewed retirement packet without mutating files or infrastructure."""
import argparse
import json
from pathlib import Path
from oracle_brain.operating_model.release_manifest import ReleaseManifest
from oracle_brain.operating_model.retirement import verify_retirement

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet',type=Path)
    parser.add_argument('--admission',type=Path,required=True,help='Independent trusted admission registry, separate from proposed packet')
    args=parser.parse_args()
    raw=args.packet.read_bytes()
    if len(raw)>4*1024*1024:raise ValueError('retirement packet exceeds bound')
    packet=json.loads(raw)
    admission_raw=args.admission.read_bytes()
    if len(admission_raw)>1024*1024:raise ValueError('admission registry exceeds bound')
    admission=json.loads(admission_raw)
    manifest=ReleaseManifest.model_validate_json(json.dumps(packet['manifest']))
    proof=verify_retirement(manifest,packet['census'],proposed_paths=tuple(packet['proposed_paths']),
        preserved_capabilities=packet['preserved_capabilities'],
        accepted_release_hashes=frozenset(admission['accepted_release_hashes']),
        admitted_census_hashes=frozenset(admission['admitted_census_hashes']),
        admitted_equivalence_hashes=frozenset(admission['admitted_equivalence_hashes']))
    print(json.dumps(proof,sort_keys=True))

if __name__=='__main__':main()
