"""Read-only retirement proof. Never deletes files or grants legacy activation."""
from .contracts import digest
from .release_manifest import ReleaseManifest

def validate_retirement_path(path: str):
    if (type(path) is not str or not path.strip() or path.startswith('/') or
            '\\' in path or ':' in path or
            any(ord(char) < 32 or ord(char) == 127 for char in path) or
            any(part in ('', '.', '..') for part in path.split('/'))):
        raise ValueError('retirement path must be canonical repository relative')

def verify_retirement(manifest: ReleaseManifest, census: dict, *, proposed_paths: tuple[str, ...],
                      preserved_capabilities: dict, accepted_release_hashes: frozenset[str],
                      admitted_census_hashes: frozenset[str], admitted_equivalence_hashes: frozenset[str]):
    if manifest.acceptance_state != 'admitted_hosted' or manifest.content_hash() not in accepted_release_hashes:
        raise PermissionError('W11 accepted hosted release required')
    if digest(census) not in admitted_census_hashes or census.get('release_hash') != manifest.content_hash():
        raise PermissionError('current exact release call census required')
    if digest(preserved_capabilities) not in admitted_equivalence_hashes:
        raise PermissionError('independently admitted capability equivalents required')
    if preserved_capabilities.get('release_hash') != manifest.content_hash():
        raise PermissionError('capability proofs do not bind accepted release')
    entries = census.get('files', {})
    if not proposed_paths:
        raise ValueError('nonempty unique retirement paths required')
    for path in proposed_paths:
        validate_retirement_path(path)
    if len(set(proposed_paths)) != len(proposed_paths):
        raise ValueError('nonempty unique retirement paths required')
    for path in proposed_paths:
        entry = entries.get(path)
        if not entry or entry.get('replaced') is not True or entry.get('references') != []:
            raise PermissionError('retirement target is not replaced and unreferenced')
        if entry.get('retention_required') is not False:
            raise PermissionError('source/audit/recovery retention forbids retirement')
        capabilities = entry.get('capabilities')
        if not isinstance(capabilities, list) or not capabilities:
            raise PermissionError('retirement target has no explicit capability census')
        for capability in capabilities:
            proof = preserved_capabilities.get('capabilities', {}).get(capability, {})
            seal = proof.get('evidence_hash', '')
            if proof.get('passed') is not True or not isinstance(seal, str) or len(seal) != 64 or any(c not in '0123456789abcdef' for c in seal) or proof.get('release_hash') != manifest.content_hash():
                raise PermissionError('old capability has no passed new equivalent')
    if census.get('new_legacy_writers') != [] or census.get('fallback_dispatches') != []:
        raise PermissionError('new legacy writers and fallback dispatch are prohibited')
    return {'release_hash': manifest.content_hash(), 'paths': list(proposed_paths),
            'census_hash': digest(census), 'equivalents_hash': digest(preserved_capabilities),
            'deletion_authorized': False, 'reviewed_retirement_pr_required': True}

def require_no_legacy_activation(*_args, **_kwargs):
    raise PermissionError('new legacy writer or fallback activation is prohibited')
