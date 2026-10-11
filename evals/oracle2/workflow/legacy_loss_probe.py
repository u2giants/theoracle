import asyncio,importlib.util,json,os
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timedelta,timezone
import subprocess
from urllib.parse import urlparse
import pytest
from graphrag_sdk.core.models import LLMResponse
from oracle_brain.graph.graphrag import Corpus,HolisticGraphPilot,AdmittedLLM,AdmittedEmbedder,CallBudget
from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval
def checked_fixture():
    root = os.environ.get('BASELINE_ROOT', '')
    graph = urlparse(os.environ.get('ORACLE2_TEST_FALKORDB_URL', ''))
    name = os.environ.get('W01_OWNED_CONTAINER', '')
    if not root or not name.startswith('oracle-w01-') or graph.hostname != '127.0.0.1':
        raise RuntimeError('W01_INFRA_FAILURE: invalid baseline or owned loopback target')
    try:
        info = json.loads(subprocess.check_output(['docker','inspect',name]))[0]
        ports = info['NetworkSettings']['Ports']['6379/tcp']
        if (info['Config']['Labels'].get('oracle.w01.synthetic') != 'true'
            or not any(p['HostIp']=='127.0.0.1' and int(p['HostPort'])==graph.port for p in ports)
            or graph.port in {56379,56380}):
            raise ValueError('target not owned synthetic store')
        path = Path(root)/'services/oracle-brain/tests/test_holistic_graphrag_integration.py'
        spec=importlib.util.spec_from_file_location('fixed_baseline',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    except Exception as exc:
        raise RuntimeError('W01_INFRA_FAILURE: baseline/target qualification failed') from None
fixture=checked_fixture()
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
            print('W01_GRAPH_SCOPE: '+pilot.graph_name)
            rows=await pilot.rag._graph_store.query_raw("MATCH (n:ReportedFinding) RETURN count(n)")
            count = rows.result_set[0][0]
            if count == 0:
                print('W01_EXPECTED_LOSS: actual SDK finalize/reload findings=' + str(count))
                pytest.fail('W01_EXPECTED_LOSS: nonempty findings lost after finalize/reload')
            print('W01_UNEXPECTED_PASS: baseline preserves some or all findings')
            return
        except pytest.fail.Exception:
            raise
        except Exception:
            raise RuntimeError('W01_INFRA_FAILURE: SDK setup/build/reload failed') from None
        finally: await pilot.close()
    asyncio.run(run())
