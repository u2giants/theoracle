# Oracle overhaul: technology and strategy research

Research checked 2026-09-27 EDT. This is a decision record, not a vendor benchmark.
Companion: [implementation plan](../../plan_oracle_consultant_overhaul.md), whose STATUS table is authoritative for execution.

## Recommendation

Build an evidence-backed operating model and a consulting workflow. Use **FalkorDB as the replaceable graph projection**, **Graphiti behind a candidate-generation adapter**, **Python LangGraph for the state machines**, **Docling for document structure**, and **Postgres plus object storage for durable evidence, approvals, identity, and workflow state**. Retain the existing Next.js interface shell and Trigger.dev transport where they pass the new contracts. This is a replacement of the knowledge/consulting core, not another prompt patch.

These are engineering recommendations from source inspection. No candidate was installed, benchmarked with company data, or granted access during this planning session. S02/S03 must establish actual fitness. The plan fixes a small shortlist and failure criteria; it does not authorize an endless framework comparison.

## Research method and reproducibility

Reviewed primary maintainers' repositories and documentation, actual license files for ambiguous licenses, current repository metadata through GitHub's authenticated API, and Oracle source at `b3f2377f9b1fd13e1b9abf07cc8f342c180f076e`. Repository activity, licensing and release labels below are observations, not promises of reliability. Stars were deliberately excluded as an adoption criterion. Vendor performance claims were not used to set acceptance thresholds. Some documentation describes newer behavior than a selected release: verify features at the installed version.

The following snapshot was obtained from `gh api repos/OWNER/REPO`, `/commits?per_page=1`, and `/releases/latest`. A latest-release response is **not** always the current package version: monorepos, development CLI tags, and historical release entries can mislead. Specifically, do not install LangGraph's CLI development tag as the LangGraph library, Neo4j's historical GitHub release, Mem0's TypeScript tag for Python, or AGE's release candidate by inference. The inspected LangGraph library manifest reported 1.2.12; re-resolve a stable, compatible release in S02 and record the lockfile/digest. No floating `latest` in deployed environments.

| Repository / immutable source | Observed release label | License indication | Archived? | Use in this design |
|---|---|---|---|---|
| [getzep/graphiti](https://github.com/getzep/graphiti/tree/6b4b56ff6f4b1e4e69c3c3c5487cf1b8762c483a) | [v0.30.2](https://github.com/getzep/graphiti/releases/tag/v0.30.2) | Apache-2.0 | No | Candidate temporal extraction and retrieval; prove approval isolation. |
| [FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB/tree/a4fec0a60d6d73f27681c0918762728b803d350d) | [v4.20.7](https://github.com/FalkorDB/FalkorDB/releases/tag/v4.20.7) | SSPL (server LICENSE) | No | Preferred graph store; SSPL source-available server, not Apache/MIT. |
| [FalkorDB/GraphRAG-SDK](https://github.com/FalkorDB/GraphRAG-SDK/tree/b80b908025e28b73dbba7f3747a624c831ce2e5c) | [v1.4.0](https://github.com/FalkorDB/GraphRAG-SDK/releases/tag/v1.4.0) | Apache-2.0 | No | Bounded fallback comparison, not a second production ingestion engine. |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph/tree/07b33185eab893be2ed031eedae52f09314bf77c) | [cli==0.4.32.dev0](https://github.com/langchain-ai/langgraph/releases/tag/cli%3D%3D0.4.32.dev0) | MIT | No | Business workflow state machine; use stable library release. |
| [docling-project/docling](https://github.com/docling-project/docling/tree/2d5c590c34b6378fd8a47c65b534b280aa40c93c) | [v2.130.0](https://github.com/docling-project/docling/releases/tag/v2.130.0) | MIT | No | Primary structured document parsing. |
| [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG/tree/453dce83d6d0354a06e46c8d4029a0895c4e054b) | [v1.5.7](https://github.com/HKUDS/LightRAG/releases/tag/v1.5.7) | MIT | No | Retrieval baseline and alternative, not a parallel canonical memory. |
| [microsoft/graphrag](https://github.com/microsoft/graphrag/tree/769542fbf1d8e5b4c6a8677fefc34621c87894c5) | [v3.2.0](https://github.com/microsoft/graphrag/releases/tag/v3.2.0) | MIT | No | Global summary/search design reference; optional measured offline module. |
| [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy/tree/9c900c7de0a3cc3114c23fe8202ebe48e2206ce1) | [3.4.0](https://github.com/stanfordnlp/dspy/releases/tag/3.4.0) | MIT | No | Later offline prompt optimization on development data only. |
| [langfuse/langfuse](https://github.com/langfuse/langfuse/tree/2ed0d25befdaceba736c08d7e855f3bc4135851e) | [v4.46.0](https://github.com/langfuse/langfuse/releases/tag/v4.46.0) | MIT core; separate enterprise terms | No | Optional observability exporter; no new mandatory platform for first proof. |
| [vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas/tree/298b68274234c060deacab3cf5fb52aa3a20e885) | [v0.4.3](https://github.com/vibrantlabsai/ragas/releases/tag/v0.4.3) | Apache-2.0 | No | Supplementary retrieval evaluation, not the release judge. |
| [process-intelligence-solutions/pm4py](https://github.com/process-intelligence-solutions/pm4py/tree/24a3bf610aea6ecc4938b1864b3ad71fcfb82084) | [2.7.22](https://github.com/process-intelligence-solutions/pm4py/releases/tag/2.7.22) | AGPL-3.0 | No | Optional event-log analysis after event-data and license gates. |
| [Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured/tree/ddf4453692ae034e09ab6dadf2fafb2ab3425c08) | [0.27.10](https://github.com/Unstructured-IO/unstructured/releases/tag/0.27.10) | Apache-2.0 | No | Fallback parser only for documented Docling failures. |
| [mem0ai/mem0](https://github.com/mem0ai/mem0/tree/94c3fe9f238f3dbf29c9ce98643bd71eb13077cd) | [ts-v3.3.1](https://github.com/mem0ai/mem0/releases/tag/ts-v3.3.1) | Apache-2.0 | No | Not the canonical corporate fact engine. |
| [topoteretes/cognee](https://github.com/topoteretes/cognee/tree/c4cd8ceb9509dff6bddfabdadbeab7cc040bc32b) | [v1.6.1](https://github.com/topoteretes/cognee/releases/tag/v1.6.1) | Apache-2.0 | No | Strong packaged alternative; deferred to avoid competing memory owners. |
| [onyx-dot-app/onyx](https://github.com/onyx-dot-app/onyx/tree/65912e1bf4bcc56ac5d04fb776fc262c58f4b55d) | [v4.8.1](https://github.com/onyx-dot-app/onyx/releases/tag/v4.8.1) | MIT core; separate enterprise terms | No | Enterprise-search/UI comparison; not a consulting replacement out of the box. |
| [infiniflow/ragflow](https://github.com/infiniflow/ragflow/tree/313ca90f6abd7682fe8523e16fd67b3653a3fa84) | [v0.27.2](https://github.com/infiniflow/ragflow/releases/tag/v0.27.2) | Apache-2.0 | No | Document-RAG alternative; not a second production engine. |
| [neo4j/neo4j](https://github.com/neo4j/neo4j/tree/54a7dcf7c2501b31866199143364c5332da8936f) | [3.2.0-alpha08](https://github.com/neo4j/neo4j/releases/tag/3.2.0-alpha08) | GPL-3.0 | No | Only graph fallback if FalkorDB fails mandatory tests. |
| [apache/age](https://github.com/apache/age/tree/fa109ef1ddb1c7a945a1c340195d650000e49713) | [PG18/v1.8.0-rc0](https://github.com/apache/age/releases/tag/PG18/v1.8.0-rc0) | Apache-2.0 | No | Not selected; SQL extension operations add an adoption dependency. |
| [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research/tree/1b7d2e80db9faa586165c60e09096dbbfd483a64) | No latest release returned | MIT | Yes | Archived; study patterns only, do not adopt as maintained base. |
| [stanford-oval/storm](https://github.com/stanford-oval/storm/tree/fb951af7744dab086e34962e9bc6fe878e145f83) | [v1.1.0](https://github.com/stanford-oval/storm/releases/tag/v1.1.0) | MIT | No | Research-question and cited-report patterns. |
| [py-why/dowhy](https://github.com/py-why/dowhy/tree/cc23521127ba21ade40514539ae7b91db27ca54a) | [v0.14](https://github.com/py-why/dowhy/releases/tag/v0.14) | MIT | No | Optional quantitative analysis after causal assumptions are reviewed. |

## Why FalkorDB, and what it cannot decide

FalkorDB supports property graphs, Cypher, full-text and vector indexes. That suits questions about connected approvals, vendors, roles, handoffs, exceptions and downstream consequences. This capability is documented in the [database overview](https://docs.falkordb.com/) and [index documentation](https://docs.falkordb.com/cypher/indexing). Its graph representation does not establish that extracted relationships are correct, complete, authorized or causal. That is Oracle's responsibility.

The [server license](https://github.com/FalkorDB/FalkorDB/blob/main/LICENSE) is SSPL. Its [GraphRAG SDK](https://github.com/FalkorDB/GraphRAG-SDK) is Apache-2.0; these are different licenses. Record a deployment-specific license review before production adoption or redistribution; this document makes no legal conclusion. Do not describe the entire stack as permissively licensed open source. [Persistence documentation](https://docs.falkordb.com/operations/durability/persistence) covers persistent volumes and RDB/AOF configuration. A working restart demo does not prove restoration, bounded data loss, concurrency, or an upgrade recovery path.

| Choice | Fit | Decision criteria |
|---|---|---|
| FalkorDB | Native relationship navigation and semantic/text search; Graphiti driver exists | First choice, conditional on isolation, temporal correctness, recovery, resource usage and license fit |
| Neo4j | Alternative property graph store; documented fine-grained enterprise permissions | Fallback if a mandatory FalkorDB condition fails; edition and operating cost must be explicit |
| Existing Postgres/pgvector | Strong transaction/evidence record and credible simpler retrieval baseline | Keep as durable authority; compare question quality to prove graph benefit |
| Apache AGE | Adds Cypher to Postgres | Not selected: requires a supported extension/deployment path and does not remove extraction/approval work |

Neo4j [RBAC documentation](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/) distinguishes Enterprise/Aura tiers. Do not assume free Community has every production security feature. A database swap is allowed only through the small `GraphStore` interface and the same acceptance suite; never restart the application plan over database preference.

**FalkorDB acceptance experiment (S02):** use 10,000 synthetic assertions and 100,000 synthetic relations plus a separate 10x stress set; include three access partitions, duplicates, historical corrections, high-degree nodes and source withdrawal. Run 20 concurrent readers and a serial writer. Test restore on a new instance, loss/replay of graph writes after durable acceptance, bounded traversal and memory under the proposed host's limit. Target warm retrieval p95 <= 2 seconds at pilot size, zero forbidden records, no missing acknowledged facts after replay, and restore <= 60 minutes. These are proposed product gates, not measured vendor claims. Record hardware, versions, volume, errors, p50/p95 and peak resident memory. Memory exhaustion or missing access guarantees is a failing result, not a reason to weaken the tests.

## Selected foundations and explicit boundaries

### Graphiti: temporal candidates, not unquestioned truth

[Graphiti](https://github.com/getzep/graphiti) offers incremental episodes, entity/relationship extraction, temporal facts and hybrid search, with a FalkorDB driver. Its documented model is a better starting point than rebuilding temporal memory from scratch. It is a library, not a complete enterprise consulting application. Oracle still needs source-span receipts, employee review, access decisions, correction propagation and recommendations.

Inspect [edge fields](https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py) and the [FalkorDB driver](https://github.com/getzep/graphiti/blob/main/graphiti_core/driver/falkordb_driver.py) at the snapshot commit before integration. Oracle's test must prove that extracted invalidations in a **candidate** partition cannot change a confirmed fact. A `group_id` is a partition identifier, not proof that the caller may access it. Add explicit checks on all search, episode, node, edge, summary and deletion paths. If preserving exact evidence requires unsupported internals, use the bounded fallback in S02 rather than forking the whole library. Anonymous telemetry must be disabled in company-data environments and verified for the pinned package.

### LangGraph plus the existing job transport

[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) distinguishes conversation checkpoints from cross-conversation stores. Use Postgres checkpoints for business-workflow state and the evidence ledger for accepted knowledge. A saved transcript is not an approved procedure. Resume must recheck current permissions and schema versions.

The [FalkorDB integration article](https://www.falkordb.com/blog/graphrag-langchain-langgrap/) demonstrates a Python checkpointer and a separate JavaScript graph wrapper. The earlier proposal conflated these. Language compatibility is not the deciding issue: the proposed Python core removes that constraint, while independent checkpoints keep conversation recovery available when the graph is rebuilt.

The repository already pins Trigger.dev 4.5.15, despite older prose calling it v3. Its [Python extension](https://trigger.dev/docs/config/extensions/pythonExtension) can package and run scripts. Prove the pinned combination with Docling, Graphiti and LangGraph before choosing another host. Trigger owns job delivery/retry/concurrency; LangGraph owns business stages and pauses. Externally visible effects get durable idempotency keys. Persist interruption and exit; do not leave a paid worker waiting for an employee. A separate container service is a fallback only if the measured bundle or execution limits demand it. [Cloud Run](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run) is a possible host, not a provisioned resource or authorization to create one.

### Docling and layout-aware evidence

[Docling](https://github.com/docling-project/docling) handles document formats and structural parsing; [DoclingDocument](https://docling-project.github.io/docling/concepts/docling_document/) represents hierarchy, tables, layout and provenance. Retain that structure and original bytes. Do not flatten a responsibility table into text and expect the model to reconstruct cell ownership. For a diagram, cite the source image region and require review where OCR/layout is ambiguous. Spreadsheet values and formulas need separate treatment. [Unstructured](https://github.com/Unstructured-IO/unstructured) is a fallback candidate for a demonstrated format failure, not a second parser for every file. Parser/model dependencies have their own licenses and resource requirements.

### Retrieval strategies: local, connected and company-wide

[Microsoft GraphRAG's query overview](https://microsoft.github.io/graphrag/query/overview/) separates local, global and DRIFT search. Its [global search design](https://microsoft.github.io/graphrag/query/global_search/) uses community summaries for broad questions. We adopt the distinction, not the entire batch pipeline. Oracle will initially build versioned summaries for explicit process/department groups. A global answer expands relevant summary claims back to allowed original evidence. Rebuild only affected groups after a source update. Evaluate community detection later if explicit groups miss useful connections.

[LightRAG](https://github.com/HKUDS/LightRAG) provides an attractive lighter retrieval baseline with document deletion and reranking in its current documentation. It is useful for a bounded comparison if the selected stack underperforms. Running it alongside Graphiti as another owner of accepted knowledge would create conflicting update semantics.

Use exact names/IDs, keyword and vector candidates, bounded graph traversal, reranking and query-specific evidence packing. A single nearest vector node is too fragile for names, exceptions and broad questions. No model-generated unrestricted Cypher in employee serving. Use typed query plans mapped to parameterized, read-only templates with fixed hop/row/time caps. Numerical aggregation must state the population covered, not treat top-k retrieval as a company census.

### Evaluation and improvement

[Ragas](https://github.com/vibrantlabsai/ragas) supplies useful evaluation components; [DSPy](https://github.com/stanfordnlp/dspy) supplies optimization methods. Use automated graders as diagnostics, with deterministic source/permission checks and blinded human business grading as release gates. Optimize on development examples only; never tune against the held-out acceptance answers. Learning from uploads means updating evidence and derived knowledge, not silently fine-tuning a foundation model.

[Langfuse](https://github.com/langfuse/langfuse) can trace runs and evaluations. Its [license](https://github.com/langfuse/langfuse/blob/main/LICENSE) separates MIT portions from enterprise directories. Start with existing Oracle run records plus redacted structured traces; add an exporter only if it resolves a demonstrated support gap. No raw employee conversations in public telemetry.

## Other frameworks examined, and why they are not the base

| Project | What it offers | Recommendation for Oracle |
|---|---|---|
| [Cognee](https://github.com/topoteretes/cognee) | Graph-based memory and domain models; current docs explicitly target a company brain | Credible alternative, not dismissed. Prefer the narrower temporal library under an Oracle-owned acceptance ledger; revisit only if S02 shows that boundary costs more than a packaged core |
| [Mem0](https://github.com/mem0ai/mem0) | Persistent assistant/user memory | Useful for preferences, not selected as the authority for disputed corporate procedures; its published managed-platform scores are not OSS or Oracle acceptance scores |
| [Onyx](https://github.com/onyx-dot-app/onyx) | Enterprise search, chat and deep-research experiences | Compare usability and connector practices; replacing the shell with Onyx would still leave procedure confirmation and consulting outcomes to build; inspect enterprise license boundaries |
| [RAGFlow](https://github.com/infiniflow/ragflow) | Document parsing, retrieval and agent workflows | Credible document-Q&A alternative; not an automatic model of this business or a reason to deploy two RAG systems |
| [STORM](https://github.com/stanford-oval/storm) | Perspective-driven research and cited reports | Reuse question-diversity/report evaluation ideas; avoid treating generated reports as company evidence |
| [Open Deep Research](https://github.com/langchain-ai/open_deep_research) | Reference research workflow | Repository was archived when checked; patterns only, no maintained-runtime dependency |
| [PM4Py](https://github.com/process-intelligence-solutions/pm4py) | Event-log process analysis | Optional after real case/activity/timestamp data exists; AGPL/commercial suitability review before deployment |
| [DoWhy](https://github.com/py-why/dowhy) | Modeling/testing causal assumptions | Optional analyst tool with sufficient data; a knowledge-graph edge is not a causal estimate |

## Learning from invited Teams meetings

[Microsoft's transcript overview](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/meeting-transcripts/overview-transcripts) describes post-meeting transcript access and resource-specific consent. [Notification documentation](https://learn.microsoft.com/en-us/graph/teams-changenotifications-callrecording-and-calltranscript) describes subscription timing and lifecycle. [Tenant controls](https://learn.microsoft.com/en-us/microsoftteams/meeting-transcript-api-access) can independently block access or speaker attribution. Availability must be checked for the exact scheduled/channel/ad-hoc scenario. Missing speaker attribution becomes unknown, never an inferred employee identity.

[Recall real-time transcription](https://docs.recall.ai/docs/bot-real-time-transcription) documents signed utterance events, asynchronous processing and separate failure notifications. Retain Recall for an explicitly invited participant; use Graph as an available post-meeting reconciliation source. No recording a meeting merely because a URL was found. Partial utterances are not durable facts; completed transcript revisions supersede prior observations with lineage. Deduplicate the same meeting captured by both providers. A question asked by Oracle and its answer must not re-ingest Oracle's own text as an employee claim.

## Industry expertise and consulting method

The repository describes a home-decor business; licensing, overseas sourcing and retail workflows appear in existing evidence fixtures. This is a **starting hypothesis**, not a complete private company profile. The first business interviews establish product categories, business model, customers/channels, geography, value chain, operational systems and constraints. Domain vocabulary must include licensed and unlicensed products, approval variants, supplier responsibilities, artwork/version identity, samples, packaging, orders, shipping windows and retailer requirements without asserting a particular company's policy.

Primary-source starting points:

- [APQC Consumer Products PCF](https://www.apqc.org/resource-library/resource-listing/apqc-process-classification-framework-pcf-consumer-products-pdf-0): a vocabulary for process classification. The downloadable framework has specific license/attribution terms. Link and map concepts; do not copy the complete taxonomy into a public repository.
- [ASCM SCOR Digital Standard](https://www.ascm.org/corporate-solutions/standards-tools/scor-ds/): structure supply-chain diagnosis and metrics. Check [current access guidance](https://www.ascm.org/corporate-solutions/standards-tools/scor-ds/open-access-guidance/) before reuse. Published metrics are definitions, not POP performance figures.
- [GS1 US general merchandise guidance](https://www.gs1us.org/industries-and-insights/apparel-and-general-merchandise): product identity, shared attributes and retail data exchange. Confirm applicability to the specific channel.
- [Licensing International data](https://licensinginternational.org/data/): licensing-sector research; distinguish public information from licensed/member reports. No unauthorized purchases or republication.
- Applicable retailer manuals, licensor agreements and supplier documents **provided by the business** outrank generic best practice for that relationship. They remain private and scoped.

The consultant workflow is our design: define the business problem; map supporting and opposing evidence; locate affected processes; generate competing explanations; calculate only from sourced measurements; propose alternatives; assess feasibility and tradeoffs; draft a reversible experiment; record the owner's decision; compare subsequent observations with the baseline. Unknowns become a measurement/interview request. A confident paragraph or a polished report is not an improvement outcome.

[Anthropic's workflow guidance](https://www.anthropic.com/engineering/building-effective-agents) supports starting with bounded, composable workflows. Its publication is older than this research date and explicitly points to newer hosted offerings; it is used as a design principle, not proof that 2024 model recommendations are current. [Tool-design guidance](https://www.anthropic.com/engineering/writing-tools-for-agents) supports measured tool contracts. The older [Lost in the Middle study](https://arxiv.org/abs/2307.03172) motivates a context-position test; it does not establish the performance of today's models. Compare the new graph path to a current long-context baseline on the same corpus.

## Contribution opportunities with bounded ownership

No upstream issue or PR was posted during planning. The implementation lead owns each contribution only after a reproducible defect appears; sharing company data is excluded.

| Target | Useful contribution if confirmed | Upstream acceptance evidence | Local limit / retirement |
|---|---|---|---|
| Graphiti | Synthetic test for temporal correction, FalkorDB parity, or duplicate-episode behavior | Failing test on pinned upstream commit, small patch and passing maintainer suite | Adapter workaround with linked issue and removal condition; no permanent product fork |
| Docling | Synthetic table/diagram provenance regression fixture | Reproducible source document with redistribution rights and expected structural output | Retain bounded fallback for that format until upstream release passes |
| FalkorDB integration | Checkpoint/replay or query-isolation test if a real deficiency is found | Minimal synthetic crash/recovery or filtered-query reproduction | Do not switch checkpoint storage merely to generate a contribution |
| Ragas/LightRAG | Evaluation fixture for scope, negative evidence and source withdrawal | Synthetic benchmark with clear license and reproducible results | Optional; never a prerequisite to shipping the first usable Oracle workflow |

## Limits of this research

No live production audit, database benchmark, authenticated employee session, customer dataset evaluation, license opinion, supplier contract review, or cost quotation was performed. The plan names the proof needed for each. Documentation URLs can move; use the immutable repository snapshots where available. New versions must be assessed against the same product gates rather than adopted because they are newer. Keep private source material out of this public repository and its issues.
