"""Real pinned SDK ingestion from sealed ledger records; never second extraction."""
import json,logging
from importlib.metadata import version
from uuid import UUID
from graphrag_sdk import GraphRAG,ConnectionConfig,FalkorDBConnection,Ontology,Entity,Relation,ChunkingStrategy,ExtractionStrategy,TextChunk,TextChunks
from graphrag_sdk.core.models import GraphData,GraphNode,GraphRelationship,EntityMention,ResolutionResult
from graphrag_sdk.ingestion.resolution_strategies.base import ResolutionStrategy
from .contracts import digest

PREFIX='oracle_operating_model_v1_'

class ReceiptChunks(ChunkingStrategy):
    async def chunk(self,text,ctx):
        return TextChunks(chunks=[TextChunk(text=text,index=0,uid=digest({'text':text}))])

class PreserveIds(ResolutionStrategy):
    async def resolve(self,graph_data,ctx):
        return ResolutionResult(nodes=graph_data.nodes,relationships=graph_data.relationships,merged_count=0,remap={})

class LedgerExtraction(ExtractionStrategy):
    def __init__(self,observations,semantic_nodes=(),semantic_relations=(),semantic_chunks=None):
        self.observations,self.semantic_nodes,self.semantic_relations=observations,semantic_nodes,semantic_relations
        self.semantic_chunks=semantic_chunks or {}
    async def extract(self,chunks,ontology,ctx):
        if len(chunks.chunks)!=1:raise ValueError('receipt must remain a complete source chunk')
        chunk=chunks.chunks[0];nodes=[];mentions=[]
        for observation in self.observations:
            for evidence in observation['evidence']:
                if chunk.text[evidence['start']:evidence['end']]!=evidence['quote']:
                    raise ValueError('ledger evidence does not match SDK source')
            oid=observation['observation_id']
            nodes.append(GraphNode(id=oid,label='ReportedObservation',properties={
             'name':observation['value']+' ['+oid+']','display_name':observation['value'],
             'description':observation['value'],'scope':observation['scope'],
             'payload_hash':digest(observation),'source_chunk_ids':[chunk.uid]}))
            mentions.append(EntityMention(entity_id=oid,chunk_id=chunk.uid))
        for identifier,label,title,seal in self.semantic_nodes:
            source_chunks=self.semantic_chunks.get(identifier,[chunk.uid])
            nodes.append(GraphNode(id=identifier,label=label,properties={'name':title+' ['+identifier+']','display_name':title,'description':title,'payload_hash':seal,'source_chunk_ids':source_chunks}))
            if chunk.uid in source_chunks:mentions.append(EntityMention(entity_id=identifier,chunk_id=chunk.uid))
        relationships=[GraphRelationship(start_node_id=a,end_node_id=b,type='RELATES',properties={'transition_key':key,'payload_hash':seal,'fact':fact,'description':fact,'source_chunk_ids':[chunk.uid],'status':'reported','rel_type':'RELATED_TO'}) for a,b,key,seal,fact in self.semantic_relations]
        return GraphData(nodes=nodes,relationships=relationships,mentions=mentions)

class ReadOnlyGraph:
    """Route SDK data and ontology reads through the native read-only decoder."""
    def __init__(self,graph):self._graph=graph
    def __getattr__(self,name):return getattr(self._graph,name)
    async def query(self,cypher,params=None,**kwargs):
        return await self._graph.ro_query(cypher,params=params,**kwargs)

class ReadOnlyDriver:
    def __init__(self,driver):self._driver=driver
    def __getattr__(self,name):return getattr(self._driver,name)
    def select_graph(self,name):return ReadOnlyGraph(self._driver.select_graph(name))

class ReadOnlyConnection:
    """App boundary for SDK 1.4.0 AsyncGraph.ro_query; no vendor patch.

    SDK readback calls query(), which otherwise selects GRAPH.QUERY. Delegate
    native decoding to the driver's read-only command and keep all other
    connection behavior (including close/config) on the qualified SDK object.
    """
    def __init__(self,connection):self._connection=connection
    def __getattr__(self,name):return getattr(self._connection,name)
    @property
    def graph(self):return ReadOnlyGraph(self._connection.graph)
    @property
    def _driver(self):
        driver=self._connection._driver
        return ReadOnlyDriver(driver) if driver is not None else None
    async def query(self,cypher,params=None,*,timeout=None):
        return await self._connection.graph.ro_query(cypher,params=params,
            timeout=timeout if timeout is not None else self._connection.config.query_timeout_ms)

class SDKProjection:
    def __init__(self,graph_url:str,*,workspace_id:UUID,artifact_id:UUID,artifact_version:int,generation:UUID,llm,embedder,dimensions:int,read_only:bool=False):
        if version('graphrag-sdk')!='1.4.0':raise RuntimeError('exact qualified SDK required')
        self.graph_name=f'{PREFIX}{workspace_id.hex}_{artifact_id.hex}_{artifact_version}_{generation.hex}'
        self.connection=FalkorDBConnection(ConnectionConfig.from_url(graph_url,graph_name=self.graph_name,query_timeout_ms=30_000))
        if read_only:self.connection=ReadOnlyConnection(self.connection)
        self.rag=GraphRAG(self.connection,llm=llm,embedder=embedder,embedding_dimension=dimensions,
          ontology=Ontology() if read_only else Ontology(entities=[Entity(label=k) for k in ('ReportedObservation','WorkflowStep','DecisionGateway','BusinessArtifact','BusinessRole','BusinessProcess','WorkflowTransition','BusinessInterface','WorkflowCondition','BusinessObjective','MetricDefinition','DecisionVariant')],relations=[Relation(label='RELATED_TO')]))
        self.read_only=read_only
        self.workspace_id=workspace_id
        logging.getLogger('graphrag_sdk').setLevel(logging.CRITICAL)

    @staticmethod
    def records(payload:dict) -> dict[str,tuple[str,str]]:
        records={}
        def add(identifier,kind,raw):
            if identifier in records:raise ValueError('duplicate projected identity')
            records[identifier]=(kind,digest(raw))
        for o in payload.get('observations',[]):add(o['observation_id'],'observation',o)
        for f in payload.get('findings',[]):add(f['finding_id'],'finding',f)
        for w in payload.get('workflows',[]):
            add(w['workflow_id'],'workflow',w)
            for kind,key in [('steps','step_id'),('gateways','gateway_id'),('transitions','transition_id'),('roles','assignment_id'),('artifacts','artifact_id'),('handoffs','handoff_id'),('conditions','condition_id')]:
                for obj in w.get(kind,[]):add(w['workflow_id']+':'+obj[key],kind,obj)
        for model in payload.get('operating_models',[]):add(str(model['model_id']),'operating_model',model)
        add('artifact:'+digest(payload),'artifact',payload)
        return records

    @staticmethod
    def semantic_projection(payload):
        nodes={}; relations={}
        def add(identifier,label,title,raw,support):
            value=(label,title,digest(raw),tuple(support))
            if identifier in nodes and nodes[identifier]!=value:raise ValueError('incompatible semantic projection identity')
            nodes[identifier]=value
        for w in payload.get('workflows',[]):
            prefix=w['workflow_id']+':'
            for collection,key,label in [('steps','step_id','WorkflowStep'),('gateways','gateway_id','DecisionGateway'),('artifacts','artifact_id','BusinessArtifact'),('conditions','condition_id','WorkflowCondition')]:
                for obj in w.get(collection,[]):add(prefix+obj[key],label,obj.get('label',obj.get('wording',obj.get('kind',obj[key]))),obj,obj['support']['observation_ids'])
            for edge in w['transitions']:
                identifier=prefix+edge['transition_id']
                support=edge['support']['observation_ids']
                add(identifier,'WorkflowTransition',edge['transition_id'],edge,support)
                for suffix,a,b in [('from',prefix+edge['from_id'],identifier),('to',identifier,prefix+edge['to_id'])]:
                    relations[identifier+':'+suffix]=(a,b,digest(edge),'Reported transition '+edge['from_id']+' → '+edge['to_id'],tuple(support))
        for model in payload.get('operating_models',[]):
            for process in model['processes']:add(process['process_id'],'BusinessProcess',process['label'],process,process['observation_ids'])
            for obj in model['objects']:add(obj['object_id'],{'role':'BusinessRole','artifact':'BusinessArtifact','objective':'BusinessObjective','metric_definition':'MetricDefinition','decision_variant':'DecisionVariant'}[obj['kind']],obj['label'],obj,obj['support']['observation_ids'])
            for interface in model['interfaces']:
                if interface['status']=='supported':
                    identifier=interface['interface_id'];support=interface['support']['observation_ids']
                    add(identifier,'BusinessInterface',identifier,interface,support)
                    for suffix,a,b in [('from',interface['from_process'],identifier),('to',identifier,interface['to_process'])]:
                        relations[identifier+':'+suffix]=(a,b,digest(interface),'Reported handoff '+interface['artifact_id'],tuple(support))
        return nodes,relations

    async def build(self,ledger,workspace_id:UUID,artifact_id:UUID,artifact_version:int):
        if self.read_only:raise PermissionError('read-only projection cannot build')
        if workspace_id!=self.workspace_id:raise PermissionError('projection workspace mismatch')
        payload=ledger.read(workspace_id,artifact_id,artifact_version)
        records=self.records(payload)
        count=await self.connection.query('MATCH (n) RETURN count(n)')
        if count.result_set[0][0]:raise ValueError('projection generation is already occupied; reload or rebuild separately')
        semantic_nodes,semantic_relations=self.semantic_projection(payload)
        receipts={ref['source_id']:ledger.current_source(workspace_id,UUID(ref['source_id'])) for ref in payload['source_refs']}
        observation_chunks={o['observation_id']:digest({'text':receipts[o['ref']['source_id']].reading}) for o in payload.get('observations',[])}
        semantic_chunks={identifier:sorted({observation_chunks[oid] for oid in values[3]}) for identifier,values in semantic_nodes.items()}
        for ref in payload['source_refs']:
            receipt=receipts[ref['source_id']]
            observations=[o for o in payload.get('observations',[]) if o['ref']==ref]
            source_observations={o['observation_id'] for o in observations}
            source_nodes=[(identifier,label,title,seal) for identifier,(label,title,seal,support) in semantic_nodes.items() if source_observations.intersection(support)]
            source_relations=[(a,b,key,seal,fact) for key,(a,b,seal,fact,support) in semantic_relations.items() if source_observations.intersection(support)]
            # Stock SDK prunes relations whose endpoints are absent from this batch.
            # Include sealed endpoints while retaining their actual source chunk IDs
            # and adding mentions only for this receipt's documentary support.
            required={identifier for a,b,*_ in source_relations for identifier in (a,b)}
            present={node[0] for node in source_nodes}
            for identifier in sorted(required-present):
                label,title,seal,_=semantic_nodes[identifier]
                source_nodes.append((identifier,label,title,seal))
            result=await self.rag.ingest(text=receipt.reading,document_id=ref['source_id'],chunker=ReceiptChunks(),extractor=LedgerExtraction(observations,source_nodes,source_relations,semantic_chunks),resolver=PreserveIds())
            if result.chunks_indexed!=1:raise RuntimeError('SDK source/chunk ingestion incomplete')
        finalized=await self.rag.finalize()
        if not finalized.indexes or not all(finalized.indexes.values()):raise RuntimeError('SDK finalization incomplete')
        # Artifact/finding/control records stay outside SDK entity name deduplication.
        for identifier,(kind,seal) in records.items():
            label='ReportedFinding' if kind=='finding' else ('AnalysisArtifact' if kind=='analysis' else 'WorkflowArtifact')
            await self.connection.query(f'CREATE (n:OperatingModelRecord:{label} {{id:$id,kind:$kind,payload_hash:$seal}})',params={'id':identifier,'kind':kind,'seal':seal})
        for o in payload.get('observations',[]):
            await self.connection.query('MATCH (r:OperatingModelRecord {id:$id}),(e:__Entity__ {id:$id}) CREATE (r)-[:PROJECTS]->(e)',params={'id':o['observation_id']})
        for f in payload.get('findings',[]):
            for evidence in f['evidence_refs']:
                await self.connection.query('MATCH (f:OperatingModelRecord {id:$fid}),(d:Document {id:$sid}) CREATE (f)-[:SUPPORTED_BY {payload_hash:$seal}]->(d)',params={'fid':f['finding_id'],'sid':evidence['ref']['source_id'],'seal':digest(evidence)})
        await self.verify(payload)
        # Exact sources and current access are checked again after all asynchronous work.
        if ledger.read(workspace_id,artifact_id,artifact_version)!=payload:raise PermissionError('input changed during projection')
        await self.connection.query('CREATE (:OperatingModelSnapshot {content_hash:$seal,record_digest:$records,sdk:$sdk,finalized:true})',params={'seal':digest(payload),'records':digest({'records':records}),'sdk':'1.4.0'})
        return {'graph_name':self.graph_name,'content_hash':digest(payload),'record_digest':digest({'records':records}),'sdk_version':'1.4.0','finalized':finalized.model_dump(mode='json')}

    async def verify(self,payload):
        expected=self.records(payload)
        rows=(await self.connection.query('MATCH (n:OperatingModelRecord) RETURN n.id,n.kind,n.payload_hash')).result_set
        if len(rows)!=len(expected) or {r[0]:(r[1],r[2]) for r in rows}!=expected:raise ValueError('projection lost or changed authoritative records')
        obs={o['observation_id']:digest(o) for o in payload.get('observations',[])}
        semantic_nodes,semantic_relations=self.semantic_projection(payload)
        obs.update({identifier:values[2] for identifier,values in semantic_nodes.items()})
        rows=(await self.connection.query('MATCH (n:__Entity__) RETURN n.id,n.payload_hash')).result_set
        if len(rows)!=len(obs) or {r[0]:r[1] for r in rows}!=obs:raise ValueError('SDK finalize lost occurrence/observation support')
        relation_rows=(await self.connection.query('MATCH ()-[r:RELATES]->() RETURN r.transition_key,r.payload_hash')).result_set
        expected_relations={key:value[2] for key,value in semantic_relations.items()}
        if len(relation_rows)!=len(expected_relations) or {r[0]:r[1] for r in relation_rows}!=expected_relations:raise ValueError('SDK lost supported control/interface edges')
        projects=(await self.connection.query('MATCH (r:OperatingModelRecord)-[:PROJECTS]->(e:__Entity__) RETURN r.id,e.id')).result_set
        expected_projects={(o['observation_id'],o['observation_id']) for o in payload.get('observations',[])}
        if len(projects)!=len(expected_projects) or {tuple(r) for r in projects}!=expected_projects:raise ValueError('projection lost observation lineage edges')
        supports=(await self.connection.query('MATCH (f:OperatingModelRecord)-[r:SUPPORTED_BY]->(d:Document) RETURN f.id,d.id,r.payload_hash')).result_set
        expected_supports={(f['finding_id'],e['ref']['source_id'],digest(e)) for f in payload.get('findings',[]) for e in f['evidence_refs']}
        if len(supports)!=len(expected_supports) or {tuple(r) for r in supports}!=expected_supports:raise ValueError('projection lost finding lineage edges')
        documents=(await self.connection.query('MATCH (d:Document) RETURN d.id,d.content_hash')).result_set
        expected_docs={r['source_id']:r['reading_sha256'] for r in payload['source_refs']}
        if {r[0]:r[1] for r in documents}!=expected_docs:raise ValueError('SDK source manifest mismatch')

    async def load(self,ledger,workspace_id:UUID,artifact_id:UUID,artifact_version:int):
        payload=ledger.read(workspace_id,artifact_id,artifact_version)
        rows=(await self.connection.query('MATCH (s:OperatingModelSnapshot) RETURN s.content_hash,s.record_digest,s.sdk,s.finalized')).result_set
        expected=[digest(payload),digest({'records':self.records(payload)}),'1.4.0',True]
        if len(rows)!=1 or list(rows[0])!=expected:raise ValueError('current sealed finalized snapshot required')
        await self.verify(payload)
        return payload

    async def close(self):await self.connection.close()
