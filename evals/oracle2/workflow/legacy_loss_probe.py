import asyncio,importlib.util,json,os
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from graphrag_sdk.core.models import LLMResponse
from oracle_brain.graph.graphrag import Corpus,HolisticGraphPilot,AdmittedLLM,AdmittedEmbedder,CallBudget
from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval
spec=importlib.util.spec_from_file_location("fixed_baseline",Path(os.environ["BASELINE_ROOT"])/"services/oracle-brain/tests/test_holistic_graphrag_integration.py")
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
class FindingsLLM(fixture.DeterministicLLM):
    def invoke(self,prompt,**kwargs):
        result=super().invoke(prompt,**kwargs)
        if "DOCUMENT DATA" in prompt:
            payload=json.loads(result.content)
            payload["missing_information"]=["Approval owner unspecified."]
            payload["conflicts"]=["Opposed approval reports require review."]
            return LLMResponse(content=json.dumps(payload))
        return result
def test_unresolved_findings_survive_finalize_reload():
    graph_url=os.environ["ORACLE2_TEST_FALKORDB_URL"]
    a,b=fixture._source(fixture.DOC_ONE,"a.txt"),fixture._source(fixture.DOC_TWO,"b.txt")
    corpus=Corpus(workspace_id=uuid4(),sources=(a,b),expected_source_ids=frozenset((a.source_id,b.source_id)))
    req=ProcessingRequest(provider="local-synthetic",account="loopback",endpoint=graph_url,data_classes=frozenset({"synthetic"}),purpose="holistic-integration",terms_hash="a"*64)
    approval=ProcessingApproval(**req.model_dump(),register_ref="W01-loss-baseline",expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    pilot=HolisticGraphPilot(corpus,graph_url,AdmittedLLM(FindingsLLM(str(a.source_id),str(b.source_id),a.text,b.text),req,[approval],CallBudget(64)),AdmittedEmbedder(fixture.DeterministicEmbedder(),req,[approval],CallBudget(64)),config_id="W01-nonempty-findings-v1",dimensions=4)
    async def run():
        try:
            await pilot.build()
            await pilot.load_reviewed_snapshot()
            rows=await pilot.rag._graph_store.query_raw("MATCH (n:ReportedFinding) RETURN count(n)")
            assert rows.result_set[0][0] >= 2, "nonempty missing_information/conflicts lost after actual SDK finalize/reload"
        finally: await pilot.close()
    asyncio.run(run())
