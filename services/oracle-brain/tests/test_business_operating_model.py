from uuid import UUID
import hashlib
import pytest
from oracle_brain.operating_model.model import BusinessOperatingModel,ProcessRecord,BusinessRecord,Interface,AssemblyDecision
from oracle_brain.operating_model.assembly import validate_assembly
from oracle_brain.operating_model.observations import create_observation
from oracle_brain.operating_model.source_receipts import SourceRef,SourceReceipt,EvidenceRef
from oracle_brain.operating_model.workflows.process_model import Support
W=UUID(int=1)

def observation(source,text,scope='scope-a',kind='handoff'):
    seal=hashlib.sha256(text.encode()).hexdigest()
    ref=SourceRef(workspace_id=W,source_id=UUID(int=source),revision=1,original_sha256=seal,reading_sha256=seal,parser_id='synthetic')
    receipt=SourceReceipt(ref=ref,reading=text,display_revision='r1')
    return create_observation(receipt,'occurrence',kind,scope,text,(EvidenceRef(ref=ref,start=0,end=len(text),quote=text),))

def model(observations,*,interfaces=(),decisions=(),cross_source=False):
    a,b=observations
    return BusinessOperatingModel(model_id=UUID(int=3),version=1,workspace_id=W,source_refs=tuple(dict.fromkeys(o.ref for o in observations)),declared_population='Two invented processes',processes=(ProcessRecord(process_id='p1',label='Design',scope=a.scope,source_ids=tuple(dict.fromkeys(o.ref.source_id for o in observations)) if cross_source else (a.ref.source_id,),observation_ids=tuple(o.observation_id for o in observations) if cross_source else (a.observation_id,),completeness='partial'),ProcessRecord(process_id='p2',label='Supplier',scope=b.scope,source_ids=(b.ref.source_id,),observation_ids=(b.observation_id,),completeness='partial')),objects=(BusinessRecord(object_id='artifact',kind='artifact',label='ART',scope=a.scope,support=Support(observation_ids=(a.observation_id,))),),interfaces=interfaces,assembly_decisions=decisions,workflows=(),finding_ids=(),completeness='partial')

def interface(o):return Interface(interface_id='i',from_process='p1',to_process='p2',artifact_id='artifact',scope=o.scope,support=Support(observation_ids=(o.observation_id,)),status='supported')

def test_same_reviewer_labels_with_different_scopes_cannot_join():
    a=observation(4,'Reviewer sends ART','scope-a');b=observation(5,'Reviewer sends ART','scope-b')
    with pytest.raises(ValueError,match='cross-scope'):validate_assembly(model((a,b),cross_source=True),{o.observation_id:o for o in (a,b)})

def test_cross_source_join_without_decision_rejected():
    a=observation(4,'Design sends ART to Supplier');b=observation(5,'Design sends ART to Supplier')
    with pytest.raises(ValueError,match='explicit admitted identity'):validate_assembly(model((a,b),cross_source=True),{o.observation_id:o for o in (a,b)})

def test_unsupported_cross_process_artifact_interface_rejected():
    a=observation(4,'Reviewer sends ART');b=observation(5,'Supplier receives packet')
    with pytest.raises(ValueError,match='explicit artifact handoff'):validate_assembly(model((a,b),interfaces=(interface(a),)),{o.observation_id:o for o in (a,b)})

def test_supported_handoff_links_artifact_and_both_endpoints():
    a=observation(4,'Design sends ART to Supplier');b=observation(5,'Supplier receives packet')
    m=model((a,b),interfaces=(interface(a),))
    assert validate_assembly(m,{o.observation_id:o for o in (a,b)})==m
