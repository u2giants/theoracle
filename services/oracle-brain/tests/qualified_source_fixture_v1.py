"""Invented test source BEFORE full capture; never runtime/provider authority.

SQL callers first request sql_qualified_v3 (fresh workspace/parser) and use
prepared_qualified_model(...,assertion_factory=...) for the actual canonical
writer. Exactly two documents match the retained foundation fixture shape.
"""
import hashlib
from oracle_brain.operating_model.source_receipts import SourceReceipt,EvidenceRef
from oracle_brain.operating_model.observations import create_observation


def qualified_two_source_fixture_v1(monkeypatch,readings,*,original_bytes=None):
    import test_assembly_context as foundation
    from test_purpose_qualification_v3 import qualified_v3
    if (type(readings) is not tuple or len(readings)!=2
            or any(type(text) is not str or not text for text in readings)):
        raise ValueError('two actual invented reading texts required')
    originals=tuple(text.encode('utf8') for text in readings) if original_bytes is None else original_bytes
    if type(originals) is not tuple or len(originals)!=2 or any(type(body) is not bytes or not body for body in originals):
        raise ValueError('two independently retained actual original byte bodies required')
    prior=foundation.invented_inputs
    def actual_inputs():
        before,_=prior();observations=[]
        if len(before)!=2:raise ValueError('retained foundation source shape changed')
        for item,text,body in zip(before,readings,originals,strict=True):
            ref=item.ref.model_copy(update={'original_sha256':hashlib.sha256(body).hexdigest(),'reading_sha256':hashlib.sha256(text.encode('utf8')).hexdigest()})
            receipt=SourceReceipt(ref=ref,reading=text,display_revision='r1')
            observations.append(create_observation(receipt,item.occurrence_key,item.kind,item.scope,text,
                (EvidenceRef(ref=ref,start=0,end=len(text),quote=text),)))
        return tuple(observations),tuple({'source_refs':[o.ref.model_dump(mode='json')],
            'observations':[o.model_dump(mode='json')],'findings':[]} for o in observations)
    monkeypatch.setattr(foundation,'invented_inputs',actual_inputs)
    # This creates fresh actual wire/census/assessment/whole semantic fixtures
    # AFTER sources are fixed; callers cannot retrofit an already qualified body.
    return qualified_v3.__wrapped__(foundation.context.__wrapped__())
