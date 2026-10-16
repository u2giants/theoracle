"""Different invented phase principals preserve actual historical extraction seals."""
from uuid import uuid4
import pytest
from test_assembly_context import context
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.purpose_assembly_v2 import AssemblyJobContextV2,CompilerExtractionHandoffV2
from oracle_brain.operating_model.semantic_acceptance import sealed


def make_v2(context):
    old,model,now=context
    handoff=CompilerExtractionHandoffV2(workspace_id=old.job.workspace_id,compiler_actor=uuid4(),
        compiler_login='compiler_fixture',compiler_runtime_hash='a'*64,compiler_authority_receipt_hash='b'*64,
        source_registry_hash=old.source_registry_hash,source_refs=tuple(r.ref for r in old.receipts),
        extractions=old.extractions,issued_at=now,expires_at=old.expires_at)
    # A DIFFERENT current assembly permission; immutable extraction seals retained.
    job=old.job.model_copy(update={'permission_hash':'9'*64})
    new=AssemblyJobContextV2(actor_id=old.actor_id,provider_login='assembly_fixture',
        runtime_hash=old.runtime_hash,source_registry_hash=old.source_registry_hash,
        compiler_digest=old.compiler_digest,parent_registry_hash=old.parent_registry_hash,
        expected_handoff_hash=sealed(handoff),job=job,receipts=old.receipts,handoff=handoff,
        census=old.census,reviewed_inventories={},model_id=old.model_id,model_version=1,expires_at=old.expires_at)
    return new,model,now


def test_v2_assembly_uses_own_permission_and_keeps_historical_extraction_seals(context):
    new,model,now=make_v2(context)
    historical=[e.manifest.permission_digest for e in new.extractions]
    assert all(p!=new.job.permission_hash for p in historical)
    payload,_=new.validate_candidate(model.model_dump_json(),now=now)
    assert payload['operating_models'][0]['model_id']==str(model.model_id)
    assert [e.manifest.permission_digest for e in new.extractions]==historical


@pytest.mark.parametrize('damage',('handoff','omitted','reordered','historical-permission','payload','new-permission','model-id'))
def test_v2_separation_never_weakens_exact_historical_handoff_binding(context,damage):
    new,model,now=make_v2(context)
    if damage=='handoff':new=new.model_copy(update={'expected_handoff_hash':'f'*64})
    elif damage=='omitted':new=new.model_copy(update={'receipts':new.receipts[:-1]})
    elif damage=='reordered':new=new.model_copy(update={'receipts':tuple(reversed(new.receipts))})
    elif damage=='historical-permission':
        e=new.handoff.extractions[0]
        changed=e.model_copy(update={'manifest':e.manifest.model_copy(update={'permission_digest':'f'*64})})
        new=new.model_copy(update={'handoff':new.handoff.model_copy(update={'extractions':(changed,*new.extractions[1:])})})
    elif damage=='payload':new.extractions[0].payload['findings'].append({'text':'unsealed'})
    elif damage=='new-permission':
        # Current permission is qualified externally in the purpose descriptor;
        # it cannot overwrite a historical extraction's seal to make them equal.
        e=new.handoff.extractions[0]
        new=new.model_copy(update={'handoff':new.handoff.model_copy(update={'extractions':(
            e.model_copy(update={'manifest':e.manifest.model_copy(update={'permission_digest':new.job.permission_hash})}),
            *new.extractions[1:])})})
    elif damage=='model-id':new=new.model_copy(update={'model_id':uuid4()})
    with pytest.raises((PermissionError,ValueError)):
        new.validate_candidate(model.model_dump_json(),now=now)
