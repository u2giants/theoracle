"""Real pinned SDK ingestion from sealed ledger records; never second extraction."""
import json,logging,hashlib,copy
from importlib.metadata import version
from uuid import UUID
from graphrag_sdk import GraphRAG,ConnectionConfig,FalkorDBConnection,Ontology,Entity,Relation,ChunkingStrategy,ExtractionStrategy,TextChunk,TextChunks
from graphrag_sdk.core.models import GraphData,GraphNode,GraphRelationship,EntityMention,ResolutionResult
from graphrag_sdk.ingestion.resolution_strategies.base import ResolutionStrategy
from .contracts import digest,canonical_bytes
from .workflows.process_model import WorkflowModel,canonical_workflow_items

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
    def validate_document_observation(self,chunk,observation):
        for evidence in observation['evidence']:
            if chunk.text[evidence['start']:evidence['end']]!=evidence['quote']:
                raise ValueError('ledger evidence does not match SDK source')

    async def extract(self,chunks,ontology,ctx):
        if len(chunks.chunks)!=1:raise ValueError('receipt must remain a complete source chunk')
        chunk=chunks.chunks[0];nodes=[];mentions=[]
        for observation in self.observations:
            self.validate_document_observation(chunk,observation)
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


class QualifiedLedgerExtraction(LedgerExtraction):
    """Ingest sealed derived evidence, never treat derived text as an original."""
    def __init__(self,*args,expected_text,**kwargs):
        super().__init__(*args,**kwargs)
        self.expected_text=expected_text

    def validate_document_observation(self,chunk,observation):
        body=json.loads(chunk.text)
        if (chunk.text!=self.expected_text or body.get('projection_schema')!='qualified-evidence-projection-v1'
                or observation not in body['observations']
                or any(e['ref']!=body['original_source_ref'] for e in observation['evidence'])):
            raise ValueError('qualified derived evidence differs from sealed projection')

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
    graph_prefix=PREFIX
    consolidation_records=False
    ontology_labels=('ReportedObservation','WorkflowStep','DecisionGateway','BusinessArtifact','BusinessRole','BusinessProcess','WorkflowTransition','BusinessInterface','WorkflowCondition','BusinessObjective','MetricDefinition','DecisionVariant')

    def __init__(self,graph_url:str,*,workspace_id:UUID,artifact_id:UUID,artifact_version:int,generation:UUID,llm,embedder,dimensions:int,read_only:bool=False,qualification_guard=None,_paid_connection_config=None):
        if version('graphrag-sdk')!='1.4.0':raise RuntimeError('exact qualified SDK required')
        self.graph_name=f'{self.graph_prefix}{workspace_id.hex}_{artifact_id.hex}_{artifact_version}_{generation.hex}'
        if _paid_connection_config is None:
            config=ConnectionConfig.from_url(graph_url,graph_name=self.graph_name,query_timeout_ms=30_000)
        else:
            if type(self) not in (PaidProcessingSDKProjectionV3,PaidConsolidationSDKProjectionV1,PaidMetadataSDKProjectionV3,ConsolidatedMetadataSDKProjectionV1,NativeInventedTLSProjectionV1,NativeInventedTLSProjectionV2):raise PermissionError('TLS override is restricted to explicit paid SDK profile')
            config=paid_tls_connection_config_v3(graph_url,self.graph_name,_paid_connection_config)
        self.connection=FalkorDBConnection(config)
        if read_only:self.connection=_FencedConsolidatedReadConnectionV1(self.connection) if type(self) is ConsolidatedMetadataSDKProjectionV1 else ReadOnlyConnection(self.connection)
        self.rag=GraphRAG(self.connection,llm=llm,embedder=embedder,embedding_dimension=dimensions,
          ontology=Ontology() if read_only else Ontology(entities=[Entity(label=k) for k in self.ontology_labels],relations=[Relation(label='RELATED_TO')]))
        self.qualification_guard=qualification_guard
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
            typed=WorkflowModel.model_validate_json(canonical_bytes(w))
            for kind,key,item in canonical_workflow_items(typed):
                add(w['workflow_id']+':'+key,kind,item.model_dump(mode='json'))
        for model in payload.get('operating_models',[]):add(str(model['model_id']),'operating_model',model)
        if 'consolidation_core' in payload:
            from .consolidation_contracts_v1 import ConsolidationCoreV1
            core=ConsolidationCoreV1.model_validate_json(canonical_bytes(payload['consolidation_core']))
            for assertion in core.assertions:add('assertion:'+str(assertion.assertion_id)+':'+str(assertion.revision),'temporal_assertion',assertion.model_dump(mode='json'))
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
        if 'consolidation_core' in payload:
            from .consolidation_contracts_v1 import ConsolidationCoreV1
            core=ConsolidationCoreV1.model_validate_json(canonical_bytes(payload['consolidation_core']))
            if core.model.model_dump(mode='json')!=payload['operating_models'][0]:raise PermissionError('qualified temporal graph body differs')
            for assertion in core.assertions:
                raw=assertion.model_dump(mode='json')
                identifier='assertion:'+str(assertion.assertion_id)+':'+str(assertion.revision)
                support=tuple(sorted(set(assertion.supporting_observations)|set(assertion.opposing_observations)|set(assertion.temporal_observations)|set(assertion.unknown_finding_ids)))
                # Entire exact assertion, including opposition/unknown/time/scope,
                # participates in actual SDK entity-name embedding inventory.
                add(identifier,'ReportedAssertion',canonical_bytes(raw).decode(),raw,support)
        return nodes,relations

    def source_texts(self,ledger,workspace_id,payload):
        return {r['source_id']:ledger.current_source(workspace_id,UUID(r['source_id'])).reading for r in payload['source_refs']}

    def document_id(self,ref,payload):return ref['source_id']

    def document_hashes(self,payload):
        return {r['source_id']:r['reading_sha256'] for r in payload['source_refs']}

    def extractor(self,observations,nodes,relations,chunks,text):
        return LedgerExtraction(observations,nodes,relations,chunks)

    async def annotate_document(self,ref,payload):pass

    async def build(self,ledger,workspace_id:UUID,artifact_id:UUID,artifact_version:int):
        if self.read_only:raise PermissionError('read-only projection cannot build')
        if workspace_id!=self.workspace_id:raise PermissionError('projection workspace mismatch')
        from .assembly_qualification import read_documentary_artifact
        payload=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,qualification_guard=self.qualification_guard)
        records,finalized=await self._build_graph_payload(ledger,workspace_id,payload)
        await self.verify(payload)
        # Exact sources and current access are checked again after all asynchronous work.
        if read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,qualification_guard=self.qualification_guard)!=payload:raise PermissionError('input changed during projection')
        await self.connection.query('CREATE (:OperatingModelSnapshot {content_hash:$seal,record_digest:$records,sdk:$sdk,finalized:true})',params={'seal':digest(payload),'records':digest({'records':records}),'sdk':'1.4.0'})
        return {'graph_name':self.graph_name,'content_hash':digest(payload),'record_digest':digest({'records':records}),'sdk_version':'1.4.0','finalized':finalized.model_dump(mode='json')}

    async def _build_graph_payload(self,ledger,workspace_id,payload):
        # Graph writes only. Public callers must establish their own complete
        # before/after authority; this private helper never supplies a grant.
        records=self.records(payload)
        count=await self.connection.query('MATCH (n) RETURN count(n)')
        if count.result_set[0][0]:raise ValueError('projection generation is already occupied; reload or rebuild separately')
        semantic_nodes,semantic_relations=self.semantic_projection(payload)
        texts=self.source_texts(ledger,workspace_id,payload)
        observation_chunks={o['observation_id']:digest({'text':texts[o['ref']['source_id']]}) for o in payload.get('observations',[])}
        support_chunks={key:{value} for key,value in observation_chunks.items()}
        if 'consolidation_core' in payload:
            if not self.consolidation_records:raise PermissionError('explicit qualified consolidation SDK profile required')
            for finding in payload.get('findings',[]):
                support_chunks[finding['finding_id']]={self.document_id(e['ref'],payload) for e in finding['evidence_refs']}
        semantic_chunks={identifier:sorted({chunk for oid in values[3] for chunk in support_chunks[oid]}) for identifier,values in semantic_nodes.items()}
        for ref in payload['source_refs']:
            text=texts[ref['source_id']]
            observations=[o for o in payload.get('observations',[]) if o['ref']==ref]
            source_observations={o['observation_id'] for o in observations}
            if 'consolidation_core' in payload:
                source_observations|={f['finding_id'] for f in payload.get('findings',[]) if any(e['ref']==ref for e in f['evidence_refs'])}
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
            result=await self.rag.ingest(text=text,document_id=self.document_id(ref,payload),chunker=ReceiptChunks(),extractor=self.extractor(observations,source_nodes,source_relations,semantic_chunks,text),resolver=PreserveIds())
            if result.chunks_indexed!=1:raise RuntimeError('SDK source/chunk ingestion incomplete')
            await self.annotate_document(ref,payload)
        finalized=await self.rag.finalize()
        if not finalized.indexes or not all(finalized.indexes.values()):raise RuntimeError('SDK finalization incomplete')
        # Artifact/finding/control records stay outside SDK entity name deduplication.
        for identifier,(kind,seal) in records.items():
            label='ReportedFinding' if kind=='finding' else ('AnalysisArtifact' if kind=='analysis' else ('ReportedAssertionRecord' if kind=='temporal_assertion' else 'WorkflowArtifact'))
            await self.connection.query(f'CREATE (n:OperatingModelRecord:{label} {{id:$id,kind:$kind,payload_hash:$seal}})',params={'id':identifier,'kind':kind,'seal':seal})
        for o in payload.get('observations',[]):
            await self.connection.query('MATCH (r:OperatingModelRecord {id:$id}),(e:__Entity__ {id:$id}) CREATE (r)-[:PROJECTS]->(e)',params={'id':o['observation_id']})
        for f in payload.get('findings',[]):
            for evidence in f['evidence_refs']:
                await self.connection.query('MATCH (f:OperatingModelRecord {id:$fid}),(d:Document {id:$sid}) CREATE (f)-[:SUPPORTED_BY {payload_hash:$seal}]->(d)',params={'fid':f['finding_id'],'sid':self.document_id(evidence['ref'],payload),'seal':digest(evidence)})
        if 'consolidation_core' in payload:
            from .consolidation_contracts_v1 import ConsolidationCoreV1
            core=ConsolidationCoreV1.model_validate_json(canonical_bytes(payload['consolidation_core']))
            observations={o['observation_id']:o for o in payload.get('observations',[])}
            findings={f['finding_id']:f for f in payload.get('findings',[])}
            for assertion in core.assertions:
                identifier='assertion:'+str(assertion.assertion_id)+':'+str(assertion.revision)
                groups=(('supporting',assertion.supporting_observations),('opposing',assertion.opposing_observations),('valid-time',assertion.temporal_observations),('unknown',assertion.unknown_finding_ids))
                for polarity,ids in groups:
                    for item in ids:
                        evidence=findings[item]['evidence_refs'] if polarity=='unknown' else observations[item]['evidence']
                        for quote in evidence:
                            await self.connection.query('MATCH (r:OperatingModelRecord {id:$id}),(d:Document {id:$document}) CREATE (r)-[:SUPPORTED_BY {polarity:$polarity,payload_hash:$seal,reading_start:$start,reading_end:$end,original_source_ref:$ref}]->(d)',params={'id':identifier,'document':self.document_id(quote['ref'],payload),'polarity':polarity,'seal':digest(quote),'start':quote['start'],'end':quote['end'],'ref':canonical_bytes(quote['ref']).decode()})
        return records,finalized

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
        supports=(await self.connection.query('MATCH (f:OperatingModelRecord)-[r:SUPPORTED_BY]->(d:Document) RETURN f.id,d.id,r.payload_hash,r.polarity,r.reading_start,r.reading_end,r.original_source_ref')).result_set
        expected_supports={(f['finding_id'],self.document_id(e['ref'],payload),digest(e),None,None,None,None) for f in payload.get('findings',[]) for e in f['evidence_refs']}
        if 'consolidation_core' in payload:
            from .consolidation_contracts_v1 import ConsolidationCoreV1
            core=ConsolidationCoreV1.model_validate_json(canonical_bytes(payload['consolidation_core']))
            observations={o['observation_id']:o for o in payload.get('observations',[])}
            findings={f['finding_id']:f for f in payload.get('findings',[])}
            for assertion in core.assertions:
                identifier='assertion:'+str(assertion.assertion_id)+':'+str(assertion.revision)
                for polarity,ids in (('supporting',assertion.supporting_observations),('opposing',assertion.opposing_observations),('valid-time',assertion.temporal_observations),('unknown',assertion.unknown_finding_ids)):
                    for item in ids:
                        evidence=findings[item]['evidence_refs'] if polarity=='unknown' else observations[item]['evidence']
                        for quote in evidence:
                            expected_supports.add((identifier,self.document_id(quote['ref'],payload),digest(quote),polarity,quote['start'],quote['end'],canonical_bytes(quote['ref']).decode()))
        # The complete edge census stays closed: no ignored extra edge, changed
        # polarity, source revision or quote offsets can pass graph verification.
        if len(supports)!=len(expected_supports) or {tuple(r) for r in supports}!=expected_supports:raise ValueError('projection lost finding lineage edges or assertion evidence')
        documents=(await self.connection.query('MATCH (d:Document) RETURN d.id,d.content_hash')).result_set
        expected_docs=self.document_hashes(payload)
        if {r[0]:r[1] for r in documents}!=expected_docs:raise ValueError('SDK source manifest mismatch')

    async def load(self,ledger,workspace_id:UUID,artifact_id:UUID,artifact_version:int):
        from .assembly_qualification import read_documentary_artifact
        payload=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,qualification_guard=self.qualification_guard)
        await self._check_graph_snapshot(payload)
        await self.verify(payload)
        return payload

    async def _check_graph_snapshot(self,payload):
        # Graph integrity only. This private helper never proves read authority.
        rows=(await self.connection.query('MATCH (s:OperatingModelSnapshot) RETURN s.content_hash,s.record_digest,s.sdk,s.finalized')).result_set
        expected=[digest(payload),digest({'records':self.records(payload)}),'1.4.0',True]
        if len(rows)!=1 or list(rows[0])!=expected:raise ValueError('current sealed finalized snapshot required')

    async def close(self):await self.connection.close()


class ProcessingSDKProjection(SDKProjection):
    """Explicit qualified processing namespace; no legacy graph reuse."""
    graph_prefix='oracle_processing_v1_'

    def __init__(self,*args,qualification_guard,**kwargs):
        from .assembly_qualification import QualifiedAssemblyReadGuard
        if not isinstance(qualification_guard,QualifiedAssemblyReadGuard):
            raise PermissionError('trusted current processing qualification verifier required')
        super().__init__(*args,qualification_guard=qualification_guard,**kwargs)

    projection_schema='qualified-evidence-projection-v1'

    @staticmethod
    def projection_view(payload):
        qualification=payload['qualified_lineage']
        model=payload['operating_models'][0]
        documents=[]
        for ref in payload['source_refs']:
            observations=[o for o in payload.get('observations',[]) if o['ref']==ref]
            findings=[]
            for finding in payload.get('findings',[]):
                excerpts=[e for e in finding['evidence_refs'] if e['ref']==ref]
                if excerpts:
                    findings.append({'finding_id':finding['finding_id'],'kind':finding['kind'],
                        'text':finding['text'],'status':finding['status'],'evidence_refs':excerpts})
            content={'projection_schema':'qualified-evidence-projection-v1',
                'original_source_ref':ref,'qualified_model':model,
                'observations':observations,'findings':findings}
            if 'consolidation_core' in payload:content['qualified_consolidation_core']=payload['consolidation_core']
            text=json.dumps(content,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
            content_hash=hashlib.sha256(text.encode()).hexdigest()
            identifier='qualified_doc_'+digest({'model_hash':digest(model),'candidate_hash':qualification['candidate_hash'],
                'source_ref':ref,'derived_content_hash':content_hash})
            documents.append({'document_id':identifier,'source_ref':ref,'content_hash':content_hash,'text':text})
        return {'schema_version':1,'schema':'qualified-evidence-projection-v1',
            'candidate_hash':qualification['candidate_hash'],'qualified_model_hash':digest(model),
            'source_refs':payload['source_refs'],'documents':documents}

    @classmethod
    def processing_projection_digest(cls,payload):return digest(cls.projection_view(payload))

    def source_texts(self,ledger,workspace_id,payload):
        return {d['source_ref']['source_id']:d['text'] for d in self.projection_view(payload)['documents']}

    def document_id(self,ref,payload):
        return next(d['document_id'] for d in self.projection_view(payload)['documents'] if d['source_ref']==ref)

    def document_hashes(self,payload):
        return {d['document_id']:d['content_hash'] for d in self.projection_view(payload)['documents']}

    def extractor(self,observations,nodes,relations,chunks,text):
        return QualifiedLedgerExtraction(observations,nodes,relations,chunks,expected_text=text)

    async def annotate_document(self,ref,payload):
        await self.connection.query('MATCH (d:Document {id:$id}) SET d.original_source_ref=$ref,d.original_reading_hash=$original,d.projection_schema=$schema,d.projection_digest=$projection',
            params={'id':self.document_id(ref,payload),'ref':json.dumps(ref,sort_keys=True),
                'original':ref['reading_sha256'],'schema':self.projection_schema,
                'projection':self.processing_projection_digest(payload)})

    async def build(self,ledger,workspace_id,artifact_id,artifact_version):
        result=await super().build(ledger,workspace_id,artifact_id,artifact_version)
        from .assembly_qualification import read_documentary_artifact
        payload=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,qualification_guard=self.qualification_guard)
        await self.connection.query('MATCH (s:OperatingModelSnapshot) SET s.projection_schema=$schema,s.projection_digest=$projection',
            params={'schema':self.projection_schema,'projection':self.processing_projection_digest(payload)})
        await self.verify(payload)
        return {**result,'projection_schema':self.projection_schema,'projection_digest':self.processing_projection_digest(payload)}

    async def verify(self,payload):
        await super().verify(payload)
        await _verify_processing_provenance_v1(self,payload)


async def _verify_processing_provenance_v1(adapter,payload):
    projection=adapter.processing_projection_digest(payload)
    rows=(await adapter.connection.query('MATCH (d:Document) RETURN d.id,d.original_source_ref,d.original_reading_hash,d.projection_schema,d.projection_digest')).result_set
    expected={adapter.document_id(r,payload):(json.dumps(r,sort_keys=True),r['reading_sha256'],adapter.projection_schema,projection) for r in payload['source_refs']}
    if len(rows)!=len(expected) or {r[0]:tuple(r[1:]) for r in rows}!=expected:
        raise ValueError('derived projection provenance differs from qualified model')
    rows=(await adapter.connection.query('MATCH (s:OperatingModelSnapshot) RETURN s.projection_schema,s.projection_digest')).result_set
    if rows and (len(rows)!=1 or list(rows[0])!=[adapter.projection_schema,projection]):
        raise ValueError('qualified projection snapshot differs')


def paid_tls_connection_config_v3(graph_url,graph_name,config):
    """Preserve every explicitly supported SDK TLS setting; never downgrade.

    Protected hosting settings authenticate the files/pins/current capability.
    This adapter validates transport equality and copies the supported config;
    it grants no target, graph, credential or private-file permission itself.
    """
    from urllib.parse import urlsplit,unquote
    import math
    if type(config) is not ConnectionConfig:raise PermissionError('exact pinned SDK ConnectionConfig required')
    url=urlsplit(graph_url)
    if (url.scheme!='rediss' or not url.hostname or not url.username or not url.password
            or url.path not in ('','/','/0') or url.query or url.fragment
            or (config.host,config.port,config.username,config.password)!=(url.hostname,url.port or 6379,unquote(url.username),unquote(url.password))
            or config.graph_name!=graph_name or config.ssl is not True or config.ssl_check_hostname is not True
            or config.ssl_cert_reqs!='required' or any(not isinstance(v,str) or not v for v in (config.ssl_ca_certs,config.ssl_certfile,config.ssl_keyfile))
            or type(config.query_timeout_ms) is not int or not 1<=config.query_timeout_ms<=30000 or type(config.retry_count) is not int or not 1<=config.retry_count<=3
            or not isinstance(config.pool_timeout,(int,float)) or not math.isfinite(config.pool_timeout) or not 0<config.pool_timeout<=30):
        raise PermissionError('exact admitted paid graph TLS target, mutual credentials and finite SDK bounds required')
    return copy.deepcopy(config)


class PaidProcessingSDKProjectionV3(ProcessingSDKProjection):
    """Explicit exact-paid-vector build/load; legacy projections stay unchanged."""
    def __init__(self,graph_url,*,workspace_id,artifact_id,artifact_version,generation,embedder,qualification_guard,read_only=False,signed_receipt=None,receipt_secret=None,connection_config=None):
        from .paid_sdk_embeddings_v3 import PaidProjectionEmbedderV3
        from graphrag_sdk.core.providers import LLMInterface
        if type(embedder) is not PaidProjectionEmbedderV3:
            raise PermissionError('exact authenticated paid SDK embedder required')
        witness=embedder.data.witness
        if (witness.workspace_id,witness.qualified_artifact_id,witness.qualified_artifact_version)!=(workspace_id,artifact_id,artifact_version):
            raise PermissionError('paid SDK vector artifact identity differs')
        class NoGeneration(LLMInterface):
            model_name='sealed-projection-no-generation'
            def __init__(self):super().__init__(self.model_name)
            def invoke(self,prompt,**kwargs):raise PermissionError('sealed SDK projection cannot generate or extract again')
        self.paid_embedder=embedder;self._paid_building=False;self._paid_proof=None;self._paid_built_here=False
        self._paid_signed_receipt=copy.deepcopy(signed_receipt);self._paid_receipt_secret=receipt_secret
        super().__init__(graph_url,workspace_id=workspace_id,artifact_id=artifact_id,artifact_version=artifact_version,
            generation=generation,llm=NoGeneration(),embedder=embedder,dimensions=256,read_only=read_only,
            qualification_guard=qualification_guard,_paid_connection_config=connection_config)

    def _paid_payload(self,payload):
        from .paid_sdk_embeddings_v3 import processing_embedding_inventory_v3
        if processing_embedding_inventory_v3(payload)!=self.paid_embedder.data.inventory:
            raise PermissionError('current qualified SDK input differs from exact paid inventory')
        self.paid_embedder.assert_no_denials()
        return self.paid_embedder.data.inventory

    async def _verify_paid_vectors(self,payload):
        inventory=self._paid_payload(payload)
        return await self._verify_paid_vectors_inventory(inventory)

    async def _verify_paid_vectors_inventory(self,inventory):
        # One operation-local immutable inventory, never cached authority.
        from .paid_sdk_embeddings_v3 import PaidSDKProjectionProofV3
        self.paid_embedder.assert_no_denials()
        w=self.paid_embedder.data.witness
        from .paid_sdk_embeddings_v3 import graph_vector_coverage_v3
        chunks=(await self.connection.query('MATCH (c:Chunk) RETURN c.text,c.embedding')).result_set
        entities=(await self.connection.query('MATCH (e:__Entity__) RETURN e.id,e.name,e.embedding')).result_set
        relations=(await self.connection.query('MATCH ()-[r:RELATES]->() RETURN r.transition_key,r.fact,r.embedding')).result_set
        coverage,keys=graph_vector_coverage_v3(inventory,chunks=chunks,entities=entities,relations=relations,
            paid_data=self.paid_embedder.data)
        if self._paid_building:self.paid_embedder.assert_observed(keys)
        proof=PaidSDKProjectionProofV3(embedding_inventory_hash=w.inventory_hash,embedding_context_hash=w.context_hash,
            embedding_native_receipt_hash=w.native_receipt_hash,embedding_wire_hash=w.raw_response_hash,
            embedding_commit_hash=w.phase_commit_hash,embedding_vectors_hash=w.vectors_hash,embedding_coverage_hash=coverage)
        if not self._paid_building:
            rows=(await self.connection.query('MATCH (s:PaidSDKEmbeddingSnapshotV3) RETURN s.proof_hash')).result_set
            if rows!=[[digest(proof.model_dump(mode='json'))]]:
                raise PermissionError('missing exact completed paid SDK build marker; partial graph cannot be adopted')
        if not self._paid_building and not self._paid_built_here and proof!=self._paid_expected_receipt_proof:
            raise PermissionError('actual graph vector coverage differs from signed delivery receipt')
        self._paid_proof=proof
        return proof

    async def verify(self,payload):
        if not self._paid_building and not self._paid_built_here:self._verify_paid_receipt(payload)
        await super().verify(payload)
        await self._verify_paid_vectors(payload)

    async def build(self,ledger,workspace_id,artifact_id,artifact_version):
        if type(self) not in (PaidProcessingSDKProjectionV3,PaidConsolidationSDKProjectionV1) or self.read_only or workspace_id!=self.workspace_id:
            raise PermissionError('exact writable paid projection identity required')
        from .assembly_qualification import read_documentary_artifact
        self._paid_built_here=False
        self._paid_building=True
        try:
            # BOTH actual ledger authority and independent SDK scope precede
            # the first graph query and are freshly checked after ALL graph work.
            manifest,payload=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,
                qualification_guard=self.qualification_guard,with_manifest=True)
            payload=copy.deepcopy(payload);inventory=self._paid_payload(payload)
            records,finalized=await self._build_graph_payload(ledger,workspace_id,payload)
            projection=self.processing_projection_digest(payload)
            await self.connection.query('CREATE (:OperatingModelSnapshot {content_hash:$seal,record_digest:$records,sdk:$sdk,finalized:true,projection_schema:$schema,projection_digest:$projection})',
                params={'seal':digest(payload),'records':digest({'records':records}),'sdk':'1.4.0','schema':self.projection_schema,'projection':projection})
            # Full structural/provenance proof plus actual paid float32 vectors.
            # Public verify remains independently complete for other operations.
            await ProcessingSDKProjection.verify(self,payload)
            proof=await self._verify_paid_vectors_inventory(inventory)
            await self.connection.query('CREATE (:PaidSDKEmbeddingSnapshotV3 {proof_hash:$proof})',params={'proof':digest(proof.model_dump(mode='json'))})
            rows=(await self.connection.query('MATCH (s:OperatingModelSnapshot) RETURN s.content_hash,s.record_digest,s.sdk,s.finalized,s.projection_schema,s.projection_digest')).result_set
            expected=[digest(payload),digest({'records':records}),'1.4.0',True,self.projection_schema,projection]
            if len(rows)!=1 or list(rows[0])!=expected:raise PermissionError('paid build actual finalized snapshot differs')
            markers=(await self.connection.query('MATCH (s:PaidSDKEmbeddingSnapshotV3) RETURN s.proof_hash')).result_set
            if markers!=[[digest(proof.model_dump(mode='json'))]]:raise PermissionError('paid build actual completion marker differs')
            self.paid_embedder.assert_no_denials()
            latest,body=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,
                qualification_guard=self.qualification_guard,with_manifest=True)
            if latest!=manifest or canonical_bytes(body)!=canonical_bytes(payload):raise PermissionError('input changed during paid projection')
        finally:self._paid_building=False
        self._paid_built_here=True
        return {'graph_name':self.graph_name,'content_hash':digest(payload),'record_digest':digest({'records':records}),
            'sdk_version':'1.4.0','finalized':finalized.model_dump(mode='json'),'projection_schema':self.projection_schema,
            'projection_digest':projection,'paid_embedding':proof.model_dump(mode='json')}

    async def load(self,ledger,workspace_id,artifact_id,artifact_version):
        # Only the current real compiler SQL getter may supply prior ACK data.
        # Caller/cache/HMAC alone is not proof that an ACK actually committed.
        from .authority_adapter import ProcessingArtifactResolver
        from .contracts import ProcessingProjectionReceiptV3
        from datetime import datetime,timezone
        if type(self._paid_receipt_secret) is not bytes or len(self._paid_receipt_secret)<32:
            raise PermissionError('fresh paid SDK load requires authenticated prior committed V3 delivery receipt')
        source=ledger.processing_sources
        if (type(source) is not ProcessingArtifactResolver or source.binding.profile!='candidate-compiler'
                or ledger.principal!=source.binding.principal):
            raise PermissionError('actual compiler receipt read capability required')
        from .assembly_qualification import read_documentary_artifact
        from contextlib import nullcontext
        shared=getattr(source,'shared_connection',None)
        with (shared() if shared is not None else nullcontext()):
            manifest,payload=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,qualification_guard=self.qualification_guard,with_manifest=True)
            sealed=canonical_bytes(payload)
            payload=json.loads(sealed)
            current=source.projection_receipt_v3(workspace_id,artifact_id,artifact_version)
            if type(current) is not ProcessingProjectionReceiptV3:raise PermissionError('actual current compiler ACK required')
            receipt={**current.receipt.model_dump(mode='json'),'signature':current.signature}
            if self._paid_signed_receipt is not None and self._paid_signed_receipt!=receipt:
                raise PermissionError('cached paid SDK receipt differs from actual current ACK')
            self._paid_signed_receipt=receipt
            self._verify_paid_receipt(payload)
            if (receipt['source_digest'],receipt['permission_digest'])!=(manifest.source_digest,manifest.permission_digest):
                raise PermissionError('paid SDK ACK source/compiler manifest seal differs')
            await self._check_graph_snapshot(payload)
            await self.verify(payload)
            result=payload
            again=source.projection_receipt_v3(workspace_id,artifact_id,artifact_version)
            latest,body=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,qualification_guard=self.qualification_guard,with_manifest=True)
            if (again.receipt!=current.receipt or again.signature!=current.signature or again.source_refs!=current.source_refs
                    or datetime.now(timezone.utc)>=min(current.valid_until,again.valid_until)
                    or latest!=manifest or canonical_bytes(body)!=sealed or canonical_bytes(payload)!=sealed):
                raise PermissionError('paid SDK ACK or current authority changed during graph load')
            self._verify_paid_receipt(body)
        return result

    async def paid_projection_proof(self,payload):
        # ALWAYS query again immediately before the handler signs/ACKs; cached
        # proof alone does not authenticate current graph/source/semantic state.
        await self.verify(payload)
        return self._paid_proof

    def _verify_paid_receipt(self,payload):
        import hmac
        from .projection_delivery import signature
        from .paid_sdk_embeddings_v3 import PaidSDKProjectionProofV3
        receipt=self._paid_signed_receipt;secret=self._paid_receipt_secret
        fields={'schema_version','event_id','workspace_id','artifact_id','version','content_hash','source_digest','permission_digest',
            'graph_name','record_digest','projection_schema','projection_digest','sdk_version','projector_id','lease_role',
            'lease_token','lease_attempt','lease_until'}
        paid_fields=set(PaidSDKProjectionProofV3.model_fields)-{'schema_version'}
        if (type(receipt) is not dict or set(receipt)!=fields|paid_fields|{'signature'}
                or type(secret) is not bytes or len(secret)<32 or type(receipt['signature']) is not str):
            raise PermissionError('fresh paid SDK load requires authenticated prior committed V3 delivery receipt')
        body={k:v for k,v in receipt.items() if k!='signature'}
        if not hmac.compare_digest(signature(secret,body),receipt['signature']):raise PermissionError('paid SDK receipt signature differs')
        proof=PaidSDKProjectionProofV3.model_validate({k:v for k,v in body.items() if k in PaidSDKProjectionProofV3.model_fields})
        w=self.paid_embedder.data.witness
        expected={'embedding_inventory_hash':w.inventory_hash,'embedding_context_hash':w.context_hash,
            'embedding_native_receipt_hash':w.native_receipt_hash,'embedding_wire_hash':w.raw_response_hash,
            'embedding_commit_hash':w.phase_commit_hash,'embedding_vectors_hash':w.vectors_hash}
        if (body['schema_version']!=3 or body['workspace_id']!=str(self.workspace_id)
                or body['artifact_id']!=str(w.qualified_artifact_id) or body['version']!=w.qualified_artifact_version
                or body['content_hash']!=digest(payload) or body['graph_name']!=self.graph_name
                or body['record_digest']!=digest({'records':self.records(payload)})
                or body['projection_schema']!=self.projection_schema or body['projection_digest']!=self.processing_projection_digest(payload)
                or body['sdk_version']!='1.4.0' or any(getattr(proof,k)!=v for k,v in expected.items())):
            raise PermissionError('signed paid SDK receipt does not bind current graph/model/vectors')
        self._paid_expected_receipt_proof=proof


class PaidMetadataSDKProjectionV3(ProcessingSDKProjection):
    """Executor-only verified ACK metadata/graph read; no wire, key or provider."""
    def __init__(self,graph_url,*,workspace_id,artifact_id,artifact_version,generation,resolver,
                 qualification_guard,connection_config):
        from .purpose_qualification_v3 import PurposeQualifiedAssemblyReadGuardV3
        from .authority_adapter import ProcessingArtifactResolver
        from .contracts import ProcessingProjectionDeliverySealV3
        from graphrag_sdk.core.providers import LLMInterface,Embedder
        if type(qualification_guard) is not PurposeQualifiedAssemblyReadGuardV3:
            raise PermissionError('actual current schema3 semantic verifier required before graph access')
        if (type(resolver) is not ProcessingArtifactResolver or resolver.binding.profile!='documentary-executor'
                or connection_config is None):raise PermissionError('actual metadata-only executor and explicit TLS graph profile required')
        seal=resolver.projection_delivery_seal(workspace_id,artifact_id,artifact_version)
        if type(seal) is not ProcessingProjectionDeliverySealV3:raise PermissionError('actual current executor delivery metadata required')
        expected=f'oracle_processing_v1_{workspace_id.hex}_{artifact_id.hex}_{artifact_version}_{generation.hex}'
        if seal.graph_name!=expected:raise PermissionError('configured graph differs from current SQL delivery')
        class NoGeneration(LLMInterface):
            def __init__(self):super().__init__('sealed-executor-no-generation')
            def invoke(self,*args,**kwargs):raise PermissionError('executor cannot generate')
        class NoEmbedding(Embedder):
            model_name='no-query-embedding-authority'
            def embed_query(self,*args,**kwargs):raise PermissionError('executor has no paid query embedding authority')
        self.delivery_resolver=resolver;self._executor_manifest=None;self._executor_ledger=None
        super().__init__(graph_url,workspace_id=workspace_id,artifact_id=artifact_id,artifact_version=artifact_version,
            generation=generation,llm=NoGeneration(),embedder=NoEmbedding(),dimensions=256,read_only=True,
            qualification_guard=qualification_guard,_paid_connection_config=connection_config)
        self._delivery_target=(workspace_id,artifact_id,artifact_version)

    async def build(self,*args,**kwargs):raise PermissionError('metadata-only executor cannot build')

    def _delivery(self,payload):
        from .purpose_qualification_v3 import PurposeAssemblyQualificationV3,PurposeFinalLineageV3
        PurposeAssemblyQualificationV3.model_validate_json(canonical_bytes(payload.get('assembly_qualification')))
        PurposeFinalLineageV3.model_validate_json(canonical_bytes(payload.get('qualified_lineage')))
        from .paid_sdk_embeddings_v3 import processing_embedding_inventory_v3
        return self._delivery_inventory(payload,processing_embedding_inventory_v3(payload))

    def _delivery_inventory(self,payload,inventory):
        from .contracts import ProcessingProjectionDeliverySealV3
        from .paid_sdk_embeddings_v3 import processing_embedding_inventory_v3
        from datetime import datetime,timezone
        from .purpose_qualification_v3 import PurposeAssemblyQualificationV3,PurposeFinalLineageV3
        if self._executor_manifest is None:raise PermissionError('actual authorized executor load context required')
        # No reinterpretation of a legacy qualification as new V3 authority.
        PurposeAssemblyQualificationV3.model_validate_json(canonical_bytes(payload.get('assembly_qualification')))
        PurposeFinalLineageV3.model_validate_json(canonical_bytes(payload.get('qualified_lineage')))
        seal=self.delivery_resolver.projection_delivery_seal(*self._delivery_target)
        m=self._executor_manifest
        if (type(seal) is not ProcessingProjectionDeliverySealV3 or datetime.now(timezone.utc)>=seal.valid_until
                or seal.graph_name!=self.graph_name or seal.content_hash!=digest(payload)
                or (seal.content_hash,seal.source_digest,seal.permission_digest)!=(m.content_hash,m.source_digest,m.permission_digest)
                or len(seal.source_refs)!=len(inventory.source_refs) or set(seal.source_refs)!=set(inventory.source_refs) or seal.record_digest!=digest({'records':self.records(payload)})
                or seal.projection_schema!=self.projection_schema or seal.projection_digest!=self.processing_projection_digest(payload)
                or seal.embedding_inventory_hash!=digest(inventory.model_dump(mode='json'))):
            raise PermissionError('current executor delivery does not bind this graph/model/projection')
        return seal,inventory

    async def _verify_metadata_graph(self,payload,inventory,before):
        await super().verify(payload)
        await _verify_metadata_vectors_v1(self,payload,inventory,before)

    async def verify(self,payload):
        # Public verification independently retains both current SDK scopes.
        if self._executor_ledger is None or self._executor_manifest is None:raise PermissionError('actual authorized executor load context required')
        from .assembly_qualification import read_documentary_artifact
        shared=getattr(self._executor_ledger.processing_sources,'shared_connection',None)
        from contextlib import nullcontext
        with (shared() if shared is not None else nullcontext()):
            manifest,actual=read_documentary_artifact(self._executor_ledger,*self._delivery_target,qualification_guard=self.qualification_guard,with_manifest=True)
            sealed=canonical_bytes(actual)
            if manifest!=self._executor_manifest or canonical_bytes(payload)!=sealed:raise PermissionError('executor verification input differs')
            before,inventory=self._delivery(payload)
            await self._verify_metadata_graph(payload,inventory,before)
            after,_=self._delivery_inventory(payload,inventory)
            self._same_delivery(before,after)
            latest,body=read_documentary_artifact(self._executor_ledger,*self._delivery_target,qualification_guard=self.qualification_guard,with_manifest=True)
            if latest!=manifest or canonical_bytes(body)!=sealed or canonical_bytes(payload)!=sealed:raise PermissionError('qualified executor input changed during verification')

    @staticmethod
    def _same_delivery(before,after):
        from datetime import datetime,timezone
        if (datetime.now(timezone.utc)>=min(before.valid_until,after.valid_until)
                or before.model_dump(exclude={'checked_at','valid_until'})!=after.model_dump(exclude={'checked_at','valid_until'})):
            raise PermissionError('current executor delivery changed during graph verification')

    async def load(self,ledger,workspace_id,artifact_id,artifact_version):
        if ((workspace_id,artifact_id,artifact_version)!=self._delivery_target or ledger.processing_sources is not self.delivery_resolver
                or ledger.principal!=self.delivery_resolver.binding.principal):
            raise PermissionError('exact current executor ledger/profile required')
        from .assembly_qualification import read_documentary_artifact
        shared=getattr(ledger.processing_sources,'shared_connection',None)
        from contextlib import nullcontext
        with (shared() if shared is not None else nullcontext()):
            manifest,payload=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,qualification_guard=self.qualification_guard,with_manifest=True)
            sealed=canonical_bytes(payload);payload=json.loads(sealed)
            self._executor_manifest=manifest;self._executor_ledger=ledger
            before,inventory=self._delivery(payload)
            await self._check_graph_snapshot(payload)
            await self._verify_metadata_graph(payload,inventory,before)
            after,_=self._delivery_inventory(payload,inventory)
            self._same_delivery(before,after)
            again,body=read_documentary_artifact(ledger,workspace_id,artifact_id,artifact_version,qualification_guard=self.qualification_guard,with_manifest=True)
            if again!=manifest or canonical_bytes(body)!=sealed or canonical_bytes(payload)!=sealed:raise PermissionError('qualified executor input changed during graph load')
        return payload


class NativeInventedTLSProjectionV1(SDKProjection):
    """Exact new invented proof graph; no private projection or old-job reuse."""
    def __init__(self,graph_url,*,connection_config,read_only=True):
        from urllib.parse import urlsplit
        from .runtime import NoGeneration,SyntheticEmbedding
        parsed=urlsplit(graph_url)
        expected_user='oracle_native_proof_executor_v1' if read_only else 'oracle_native_proof_projector_v1'
        if (type(read_only) is not bool or parsed.hostname!='oracle-graph.designflow.app'
                or parsed.port!=16391 or parsed.username!=expected_user):
            raise PermissionError('exact separately admitted invented graph role and endpoint required')
        # Transport admission is fixed to this new invented graph. Keep the core
        # independent of hosting fixtures; the adapter test binds these IDs to it.
        super().__init__(graph_url,workspace_id=UUID('6426980e-6287-4f58-9e94-d1cb49b5cd5d'),
            artifact_id=UUID('992fa7e3-138e-443a-99fd-a466205b2fde'),artifact_version=1,
            generation=UUID('b30a0da3-5a5b-4a97-9c51-733e383aa21e'),llm=NoGeneration(),embedder=SyntheticEmbedding(),
            dimensions=8,read_only=read_only,_paid_connection_config=connection_config)


class NativeInventedTLSProjectionV2(SDKProjection):
    """Exact fresh v2 graph; pure identity dependency, no hosting import."""
    def __init__(self,graph_url,*,connection_config,read_only=True):
        from urllib.parse import urlsplit
        from .native_proof_v2_identity import IDENTITY as i
        from .runtime import NoGeneration,SyntheticEmbedding
        parsed=urlsplit(graph_url)
        expected=i['graph_executor'] if read_only else i['graph_projector']
        if (type(read_only) is not bool or parsed.scheme!='rediss'
                or parsed.hostname!='oracle-graph.designflow.app' or parsed.port!=16391
                or parsed.username!=expected or not parsed.password
                or parsed.path not in ('','/','/0') or parsed.query or parsed.fragment):
            raise PermissionError('exact separately admitted v2 graph role and endpoint required')
        super().__init__(graph_url,workspace_id=UUID(i['workspace']),artifact_id=UUID(i['artifact']),
            artifact_version=1,generation=UUID(i['generation']),llm=NoGeneration(),embedder=SyntheticEmbedding(),
            dimensions=8,read_only=read_only,_paid_connection_config=connection_config)


class PaidConsolidationSDKProjectionV1(PaidProcessingSDKProjectionV3):
    """Only fresh admitted temporal captures; no historic graph serving."""
    consolidation_records=True
    ontology_labels=SDKProjection.ontology_labels+('ReportedAssertion',)

    def _paid_payload(self,payload):
        if 'consolidation_core' not in payload:raise PermissionError('explicit fresh consolidation projection required')
        return super()._paid_payload(payload)


async def _verify_metadata_vectors_v1(projection,payload,inventory,before):
    from .paid_sdk_embeddings_v3 import graph_vector_coverage_v3,PaidSDKProjectionProofV3
    chunks=(await projection.connection.query('MATCH (c:Chunk) RETURN c.text,c.embedding')).result_set
    entities=(await projection.connection.query('MATCH (e:__Entity__) RETURN e.id,e.name,e.embedding')).result_set
    relations=(await projection.connection.query('MATCH ()-[r:RELATES]->() RETURN r.transition_key,r.fact,r.embedding')).result_set
    coverage,_=graph_vector_coverage_v3(inventory,chunks=chunks,entities=entities,relations=relations)
    if coverage!=before.embedding_coverage_hash:raise PermissionError('executor graph vectors differ from authenticated ACK coverage')
    proof=PaidSDKProjectionProofV3.model_validate({k:getattr(before,k) for k in PaidSDKProjectionProofV3.model_fields})
    marker=(await projection.connection.query('MATCH (s:PaidSDKEmbeddingSnapshotV3) RETURN s.proof_hash')).result_set
    if marker!=[[digest(proof.model_dump(mode='json'))]]:raise PermissionError('executor completed graph marker differs')


def _consolidated_query_timeout_v1(timeout):
    from .request_deadline_v1 import request_remaining_v1
    remaining=request_remaining_v1()
    if timeout is not None and (type(timeout) is not int or timeout<=0):raise PermissionError('strict bounded readonly query timeout required')
    return max(1,min(30000,int(remaining*1000),timeout if timeout is not None else 30000))

class _FencedConsolidatedReadGraphV1(ReadOnlyGraph):
    async def query(self,cypher,params=None,*,timeout=None):
        from .request_deadline_v1 import request_remaining_v1
        result=await self._graph.ro_query(cypher,params=params,timeout=_consolidated_query_timeout_v1(timeout))
        request_remaining_v1();return result
    ro_query=query

class _FencedConsolidatedReadDriverV1(ReadOnlyDriver):
    def select_graph(self,name):return _FencedConsolidatedReadGraphV1(self._driver.select_graph(name))

class _FencedConsolidatedReadConnectionV1(ReadOnlyConnection):
    @property
    def graph(self):return _FencedConsolidatedReadGraphV1(self._connection.graph)
    @property
    def _driver(self):
        driver=self._connection._driver
        return _FencedConsolidatedReadDriverV1(driver) if driver is not None else None
    async def query(self,cypher,params=None,*,timeout=None):
        return await self.graph.query(cypher,params=params,timeout=timeout)


class ConsolidatedMetadataSDKProjectionV1(SDKProjection):
    """Actual own-history metadata/accepted-ACK read; no provider or graph writes.

    Retained original receipt timestamps are never renewed. Each operation uses
    the same actual own SQL022 consumer and complete current source permissions.
    No callback, caller seal, fake current-source resolver or paid embedder.
    """
    graph_prefix='oracle_processing_v1_'
    consolidation_records=True
    ontology_labels=PaidConsolidationSDKProjectionV1.ontology_labels
    projection_schema=ProcessingSDKProjection.projection_schema
    projection_view=staticmethod(ProcessingSDKProjection.projection_view)
    processing_projection_digest=classmethod(ProcessingSDKProjection.processing_projection_digest.__func__)
    document_id=ProcessingSDKProjection.document_id
    document_hashes=ProcessingSDKProjection.document_hashes

    def __init__(self,graph_url,*,authority,blobs,model_id,version,generation,connection_config,
                 deadline,valid_at=None,known_at=None):
        from .consolidation_authority_v1 import ConsolidationAuthorityV1
        from .artifact_storage import FileBlobStore
        from .request_deadline_v1 import request_remaining_v1
        from graphrag_sdk.core.providers import LLMInterface,Embedder
        request_remaining_v1()
        if (type(authority) is not ConsolidationAuthorityV1 or authority.binding.operation!='history-read'
                or type(blobs) is not FileBlobStore or model_id!=authority.binding.model_id
                or type(version) is not int or version<1 or type(generation) is not UUID):
            raise PermissionError('actual exact own history consumer and immutable private owner required')
        self.authority=authority;self.blobs=blobs;self.model_id=model_id;self.model_version=version
        self.deadline=deadline;self.valid_at=valid_at;self.known_at=known_at;self._loaded_bytes=None
        packet=self._fresh_packet_v1();receipt=packet[3].retained_receipt
        expected=f'oracle_processing_v1_{authority.binding.workspace_id.hex}_{model_id.hex}_{version}_{generation.hex}'
        if receipt.graph_name!=expected:raise PermissionError('actual selected retained ACK graph differs')
        class NoGeneration(LLMInterface):
            def __init__(self):super().__init__('retained-consolidation-no-generation')
            def invoke(self,*args,**kwargs):raise PermissionError('readonly consolidation cannot generate')
        class NoEmbedding(Embedder):
            model_name='no-query-embedding-authority'
            def embed_query(self,*args,**kwargs):raise PermissionError('readonly consolidation has no query embedding authority')
        super().__init__(graph_url,workspace_id=authority.binding.workspace_id,artifact_id=model_id,
            artifact_version=version,generation=generation,llm=NoGeneration(),embedder=NoEmbedding(),dimensions=256,
            read_only=True,qualification_guard=None,_paid_connection_config=connection_config)
        self._require_receipt_v1(packet[2],packet[3])
        request_remaining_v1()

    def _fresh_packet_v1(self):
        from .request_deadline_v1 import request_remaining_v1
        request_remaining_v1()
        packet=self.authority.read_serving_packet_v1(self.model_id,blobs=self.blobs,deadline=self.deadline,
            valid_at=self.valid_at,known_at=self.known_at)
        if packet[0].model.version!=self.model_version:raise PermissionError('selected retained model version changed')
        request_remaining_v1()
        return packet

    def _require_receipt_v1(self,payload,delivery):
        from .paid_sdk_embeddings_v3 import processing_embedding_inventory_v3
        from .consolidated_delivery_v1 import ConsolidatedReadDeliveryV1
        if type(delivery) is not ConsolidatedReadDeliveryV1:raise PermissionError('actual retained delivery read required')
        receipt=delivery.retained_receipt
        inventory=processing_embedding_inventory_v3(payload)
        if (receipt.graph_name!=self.graph_name or receipt.content_hash!=digest(payload)):
            raise PermissionError('retained graph/model differs')
        # Complete SourceRef equality is proved by the actual SQL/private owner;
        # independently bind every graph digest to that exact immutable body.
        from .source_receipts import SourceRef
        refs=tuple(SourceRef.model_validate_json(canonical_bytes(r)) for r in payload['source_refs'])
        if (len(refs)!=len(delivery.source_refs) or set(refs)!=set(delivery.source_refs)
                or receipt.record_digest!=digest({'records':self.records(payload)})
                or receipt.projection_digest!=self.processing_projection_digest(payload)
                or receipt.embedding_inventory_hash!=digest(inventory.model_dump(mode='json'))):
            raise PermissionError('complete retained graph record/projection/vector inventory differs')
        return inventory

    @staticmethod
    def _same_packet_v1(before,after):
        from .request_deadline_v1 import request_remaining_v1
        request_remaining_v1()
        strip=lambda d:d.model_dump(mode='json',exclude={'checked_at','valid_until'})
        if (canonical_bytes(before[2])!=canonical_bytes(after[2]) or before[1]!=after[1]
                or strip(before[3])!=strip(after[3])):
            raise PermissionError('current complete recipient model/delivery scope changed')

    async def build(self,*args,**kwargs):raise PermissionError('readonly consolidation cannot build or acknowledge')

    async def _verify_actual_graph_v1(self,payload,delivery):
        inventory=self._require_receipt_v1(payload,delivery)
        await SDKProjection.verify(self,payload)
        await _verify_processing_provenance_v1(self,payload)
        await _verify_metadata_vectors_v1(self,payload,inventory,delivery.retained_receipt)

    async def load(self):
        before=self._fresh_packet_v1()
        await self._check_graph_snapshot(before[2])
        await self._verify_actual_graph_v1(before[2],before[3])
        after=self._fresh_packet_v1();self._same_packet_v1(before,after)
        self._loaded_bytes=canonical_bytes(after[2])
        return after

    async def verify(self,payload):
        if self._loaded_bytes is None or canonical_bytes(payload)!=self._loaded_bytes:
            raise PermissionError('actual authorized retained SDK load required')
        before=self._fresh_packet_v1()
        if canonical_bytes(before[2])!=self._loaded_bytes:raise PermissionError('retained SDK input changed')
        await self._check_graph_snapshot(before[2])
        await self._verify_actual_graph_v1(before[2],before[3])
        after=self._fresh_packet_v1();self._same_packet_v1(before,after)
        return after
