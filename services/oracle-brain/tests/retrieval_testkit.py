"""Independent invented source/access registry for offline retrieval proofs."""
import time
from uuid import UUID
from oracle_brain.retrieval.packing import (
    CurrentSourceAccess, SOURCE_ACCESS_PURPOSE, dependency_for, current_source_payload,
)
from seal_testkit import sign_seal

ACTOR = UUID('00000000-0000-4000-8000-0000000000a1')


def host_reader(known_spans, *, denied_sources=(), actor_id=ACTOR):
    registry = {(s.source_id, s.revision, s.span_id): s for s in known_spans}
    def read(dependency, access, challenge):
        actual = registry.get((dependency.source_id, dependency.revision, dependency.span_id))
        if actual is None:
            raise PermissionError('source missing or superseded')
        proof = CurrentSourceAccess(
            dependency=dependency_for(actual), actor_id=actor_id, role=access.role,
            permitted=(access.actor_id == actor_id and access.role in actual.roles
                       and actual.source_id not in denied_sources),
            challenge=challenge, valid_until=time.time() + 30, mac='')
        return proof.model_copy(update={'mac': sign_seal(SOURCE_ACCESS_PURPOSE, current_source_payload(proof))})
    return read
