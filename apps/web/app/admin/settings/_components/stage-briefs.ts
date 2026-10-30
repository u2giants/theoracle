// Company Map stage metadata + clipboard job briefs (from
// docs/company-map/model-stage-job-brief.md §4.1–4.9). The brief texts are
// what "Copy job brief" puts on the clipboard; keep them verbatim.

export type StageId =
  | 'vision'
  | 'embed'
  | 'flat'
  | 'relations'
  | 'resolve'
  | 'reports'
  | 'answer'
  | 'recommend'
  | 'grade';

export type SeatChip = 'incumbent' | 'assigned' | 'bakeoff' | 'frozen';

/** Payload shape of GET /models on the brain service. */
export interface CompanyMapModels {
  vision: string | null;
  embed: string | null;
  embed_dims: number | null;
  flat_fallback: string | null;
  relations: string | null;
  resolve: string | null;
  reports: string | null;
  answer: string | null;
  recommend: string | null;
  grade: string | null;
  scaledown_enabled: boolean;
}

export interface CompanyMapStage {
  id: StageId;
  /** Pipeline position, 1-based. */
  order: number;
  title: string;
  /** One-line role, condensed from the brief's PURPOSE. */
  role: string;
  /** Env var the seat value comes from (set in Coolify app oracle-brain). */
  envVar: string;
  /** Extra env note shown under the model id (e.g. dims, fallback). */
  envNote?: string;
  chip: SeatChip;
  /** Key into the GET /models payload for the live model id. */
  modelKey: 'vision' | 'embed' | 'flat_fallback' | 'relations' | 'resolve' | 'reports' | 'answer' | 'recommend' | 'grade';
  brief: string;
}

const BRIEFS: Record<StageId, string> = {
  vision: "THE ORACLE \u2014 \"Vision Transcription\" role brief (Company Map)\n(Paste this into a model-evaluation assistant or vendor comparison to judge\nwhether a given model is the right pick for this setting.)\n\nPURPOSE\nConvert one page image \u2014 a diagram, flowchart, or a text-poor PDF page \u2014 into a\nfaithful text rendering plus structured diagram topology. The output feeds text\nstages that quote it verbatim; every omission here silently shrinks the graph.\n\nWHERE IT SITS IN THE PIPELINE\nSource intake -> reading (brain/read/) -> this call for images and pages with\nunder 200 native characters -> the returned page_text/diagram is merged into the\nchunk stream -> flat extraction and relations quote it exactly.\n\nWHAT IT IS FED (input)\n- prompts/read_visual.md: transcribe the page, the image is DATA, copy labels\n  exactly, do not infer missing arrows; return JSON.\n- Exactly one base64 PNG/JPEG per call.\n\nWHAT IS EXPECTED (output)\nA JSON object {\"page_text\", \"diagram\": {kind,nodes,edges,swimlanes}|null,\n\"unreadable_regions\"} \u2014 verbatim labels, topology as nodes/edges (rendered to\n\"->\" edge lines for text stages), honest unreadable flags. Parser tolerates a\ncode fence only.\n\nPROCESS IT USES\nOne stateless vision chat call, temperature 0, 120s timeout, no JSON-mode flag.\n\nWHAT MAKES A MODEL PERFECTLY SUITED\nOCR-grade text capture on messy labels and handwriting; diagram topology\nunderstanding (swimlanes, conditional arrows, dashed exceptions); strict\n\"copy, don't invent\" discipline; long enough output for dense pages.\n\nCAPABILITIES IT NEEDS (hard requirements)\nImage input. Reliable JSON-shaped answers from a plain prompt (no schema mode).\n\nCAPABILITIES IT DOES NOT NEED\nTool calling, reasoning budgets, streaming, long context, PDF input (pages are\nrendered to PNG before the call).\n\nMEASURED BENCHMARK\nOn the flowchart fixture (tests/fixtures/recorded/vision_flowchart.json): every\nvisible node label and edge condition present exactly once; zero invented arrows;\nunlabelled shapes flagged, not guessed. A model that returns clean prose instead\nof nodes/edges has failed the stage even if it reads the text well.\n\nHOW TO EVALUATE A CANDIDATE\nFeed the fixture flowchart and one dense scanned page under the production prompt\n(read_visual.md). Check in order: (a) valid JSON object; (b) node/edge recall vs\nthe gold fixture; (c) verbatim labels (substring match); (d) no invented edges;\n(e) then cost/latency. One call per candidate is enough to rank.\n\nKNOWN PITFALLS\n1. Prose summarization instead of transcription \u2014 the graph then cannot quote\n   labels.\n2. Image-generation or \"image editing\" models presented as vision readers.\n3. Truncated output on dense pages (cut-off JSON is discarded by the parser).\n\nBOTTOM LINE\nPick the cheapest vision model with the best dense-diagram transcription and\nverbatim discipline. Current seat: openai/gpt-4.1. Compete it against current\nvision tiers (including cheaper flash/lite vision models) on the two-fixture\ntest above; the winner must be no worse on node/edge recall.",
  embed: "THE ORACLE \u2014 \"Embeddings\" role brief (Company Map)\n\nPURPOSE\nTurn chunk texts, mention strings, entity descriptions and questions into\nvectors for retrieval, dedupe and the cosine bands that gate entity resolution.\n\nWHERE IT SITS IN THE PIPELINE\nEvery stage that compares text: local answering (top-8 entity retrieval, passage\nselection), resolve rule 5 (cosine \u22650.92 merge / 0.80\u20130.92 judge band), open-\nquestion dedupe, recommendation dedupe, global citation resolution.\n\nWHAT IT IS FED (input)\nBatches of 64 raw texts. Vectors requested at exactly 1024 dims\n(BRAIN_EMBED_DIMS \u2014 text-embedding-3-large defaults to 3072 and is explicitly\ndownsized).\n\nWHAT IS EXPECTED (output)\nOne float vector per input, exactly `dims` floats, order preserved. Anything\nelse raises and is retried 3\u00d7.\n\nPROCESS IT USES\nPOST /embeddings on OpenRouter, batched, counted as embedding_tokens.\n\nWHAT MAKES A MODEL PERFECTLY SUITED\nDeterministic vectors; strong short-business-text similarity (titles, roles,\nsystem names); stable dimensionality support; cheap per token (this is the\nhighest-call-count stage).\n\nCAPABILITIES IT NEEDS (hard)\nCustom output dimensions (or exactly 1024 native); batch endpoint; exact\ndimensionality contract.\n\nCAPABILITIES IT DOES NOT NEED\nEverything else \u2014 reasoning, JSON, tools, vision.\n\nMEASURED BENCHMARK\nThe resolve banding is the real test: on the fixture corpora the same-entity\npairs must sit \u22650.92 (auto-merge band) and the judged pairs inside 0.80\u20130.92;\ndifferent-entity pairs under 0.80. Also: per-chunk embedding cost under the\ncurrent seat's.\n\nHOW TO EVALUATE A CANDIDATE\nRe-embed the fixture mention set with the candidate; recompute the cosine\nmatrix; measure band placement against the entity labels in the fixture gold\n(tests/test_resolve.py scenarios). Then compare $/1M tokens. This stage is\npurely measurable \u2014 no judgment call.\n\nKNOWN PITFALLS\n1. Dimensionality drift (3072 vs 1024) silently breaking stored vectors \u2014\n   re-embed the whole corpus when switching, never mix.\n2. Models whose similarity collapses on short name strings (\"Jessica\",\n   \"Artwork Log\") even when document similarity looks fine.\n\nBOTTOM LINE\nThis is the most commoditized stage: pick on band accuracy + price. Current\nseat: openai/text-embedding-3-large @1024. Compete it against current cheap\nembedding tiers (and any new provider offerings); switch only with a full\nre-embed plan. Low priority in the bake-off \u2014 measurable, cheap, and a switch\ncosts a corpus rebuild.",
  flat: "THE ORACLE \u2014 \"Flat Extraction\" role brief (Company Map)\n\nPURPOSE\nClassify each chunk into one of 7 passage kinds (process, responsibility, rule,\nreference, complaint, decision, chatter) and lift flat entities (16 types) with\nexact character spans. This is the cheap bulk pass; by call count it is the\nmajority of all model work.\n\nWHERE IT SITS IN THE PIPELINE\nReading/chunking (\u2248400-token windows) -> this pass per chunk -> mentions feed\nrelations and entity resolution. Chunks classified \"chatter\" at score \u22650.8 are\nskipped by later stages \u2014 a misclassification here drops knowledge silently.\n\nWHAT IT IS FED (input)\nPrimary path: ScaleDown /classify (7 label rubrics) and /extract (16 entity\nrubrics) with the chunk text. Fallback path: prompts/flat_extract.md asking a\nfrontier model for the same rubrics in one JSON answer (both stages cached in\none call).\n\nWHAT IS EXPECTED (output)\nclassify {\"top_label\",\"scores\"}; extract entities[] {text,type,confidence,\nstart,end}. Mentions survive only with valid type, confidence \u22650.5 and a\nlocatable span (exact offsets \u2192 substring \u2192 casefold repair); the quote is the\ncontaining sentence.\n\nPROCESS IT USES\nScaleDown HTTP API (x-api-key), 3 attempts then frontier fallback\n(BRAIN_SCALEDOWN_ENABLED=false forces the fallback). 8 threads per source.\n\nWHAT MAKES A MODEL PERFECTLY SUITED\nHigh recall on entities in noisy business text (people, roles, systems,\ndocuments, metrics); calibrated confidence (the 0.5 cut is meaningless if the\nmodel is miscalibrated); exact span copying; honest classification (chatter\ndetection is load-bearing).\n\nCAPABILITIES IT NEEDS (hard)\nJSON answers; span-exact copying; cheap per call (this is the volume).\n\nCAPABILITIES IT DOES NOT NEED\nReasoning, long context (one chunk at a time), tools, conversation.\n\nMEASURED BENCHMARK\nOn the fixture set (transcript + procedure PDF + flowchart text, gold in\ntests/fixtures/recorded/scaledown/*.json): mention recall \u226595% of gold spans;\nchatter precision: no process/rule chunk ever classified chatter \u22650.8;\nconfidence calibration: accepted mentions dominate rejected ones in gold\nprecision.\n\nHOW TO EVALUATE A CANDIDATE\nRun the three fixture chunks through the candidate with the production rubrics.\nCheck in order: (a) valid JSON both passes; (b) mention recall vs gold; (c)\nspan exactness (substring of chunk); (d) chatter false-skips; (e) then price.\nThe frontier-fallback candidate must be evaluated with prompts/flat_extract.md\nexactly as production runs it.\n\nKNOWN PITFALLS\n1. High-confidence shallow extraction (few entities, all obvious) \u2014 recall is\n   the headline, same trap as the old extraction brief.\n2. Paraphrased spans \u2014 the quote-sentence logic needs locatable text.\n3. Note the ScaleDown fallback is a different shape (one call vs two) \u2014 a\n   cheap frontier model here also serves the fallback when ScaleDown is off.\n\nBOTTOM LINE\nScaleDown already owns the primary path; this stage's bake-off is really about\nthe frontier fallback model (which must not be worse than the old\nclaude-sonnet-4.5 fallback on recall) and about keeping chatter detection\nhonest. Cheap non-Claude candidates belong here.",
  relations: "THE ORACLE \u2014 \"Relationship Extraction\" role brief (Company Map)\n(Read \"#1 CRITERION\" and \"HOW TO EVALUATE\" before forming an opinion.)\n\nPURPOSE\nLink the mentions step 3 found in a chunk into typed relationships \u2014 what hands\noff to what, what depends on what, what is an exception \u2014 plus pick up mentions\nstep 3 missed. This is the highest-volume reasoning stage (~1 call per chunk;\nplan \u00a711 budgets ~100k calls on the full corpus) and the backbone of the graph.\n\nWHERE IT SITS IN THE PIPELINE\nFlat extraction -> this call per chunk (mentions keyed m1..mN, previous chunk's\nlast 2 sentences as context) -> relations + new mentions -> entity resolution ->\ngraph projection. Whatever it fails to emit is missing from the map.\n\nWHAT IT IS FED (input)\nprompts/relations.md with {{mentions_json}}, {{previous_context}},\n{{chunk_text}}. Ontology: 14 relation types, 4 stances.\n\nWHAT IS EXPECTED (output)\n{\"relations\":[{from,to,type,description,stance,confidence,quote}],\n\"new_mentions\":[{key,type,name,quote}]} \u2014 every quote an EXACT substring of the\nchunk (validator drops otherwise), types/stances in ontology, keys resolvable;\ninferred links capped at confidence 0.6.\n\nPROCESS IT USES\nOpenRouter chat, temperature 0, JSON mode, max_tokens 2000, 180s timeout,\n3 attempts/chunk, 8 threads, per-job frontier cap, resumable per chunk.\nTruncation is salvaged item-wise (_complete_items) but every dropped relation is\nlost graph.\n\nWHAT MAKES A MODEL PERFECTLY SUITED (priority order)\n1. RELATION RECALL on dense process chunks (the extraction brief's lesson, one\n   level up: a \"valid JSON + 3 relations\" model is under-extracting).\n2. Type discipline \u2014 conditional/exception/stance fidelity, not everything\n   flattened to \"depends_on\".\n3. Verbatim quote copying (validator-enforced).\n4. Strict JSON reliability at 2000 tokens; a truncating model silently loses\n   tail relations.\n5. THEN cost \u2014 this stage alone can dominate the run's token bill.\n\nCAPABILITIES IT NEEDS (hard)\nJSON mode (or equivalent strict JSON); exact-quote copying; enough output\nbudget to emit every relation in a dense chunk.\n\nCAPABILITIES IT DOES NOT NEED\nVision (chunks carry text), tools, streaming, long context (one chunk + hints).\n\nMEASURED BENCHMARK\nOn the fixture chunk set (gold = tests/fixtures/recorded/frontier/relations.json\nand the smoke's 546-edge corpus): relation recall \u226590% of gold edges; zero\ninvalid-type rows; \u226595% quotes exact substrings; type variety (at least the\nconditional/exception kinds appear when the source has them); truncation rate\n<2% of chunks.\n\nHOW TO EVALUATE A CANDIDATE\nFeed the fixture chunks with gold mentions under prompts/relations.md. Check in\norder: (a) valid JSON; (b) relation RECALL vs gold (headline); (c) type/stance\nfidelity; (d) quote exactness; (e) truncation frequency; (f) only then $/1M and\ntokens per chunk. Then run the end-to-end step-11 eval with the graph the\ncandidate built (bake-off protocol \u00a75).\n\nKNOWN PITFALLS\n1. The extraction trap one level up: schema-valid, quote-valid, and shallow.\n   Output-token volume on a dense chunk is a red-flag detector \u2014 ~1-2k tokens\n   means it gave up early.\n2. Loose \"tool-call\" JSON from providers without true JSON mode \u2014 malformed\n   fields fail validation and the chunk yields nothing.\n3. Fabricated quotes (the validator drops them \u2014 the relation vanishes).\n\nBOTTOM LINE\nThis is where the cheap non-Claude seat is most valuable and most risky: the\nbake-off must PROVE recall parity on real chunks before the switch. Current\nseat: anthropic/claude-sonnet-4.5. Compete current-generation non-Claude\ncandidates (and cheap Claude) on the recipe; winner goes to production only if\nits fixture recall passes and its step-11 end-to-end mean holds.",
  resolve: "THE ORACLE \u2014 \"Entity Resolution\" role brief (Company Map)\n\nPURPOSE\nTwo judgment calls: (1) judge whether a mention is the same real-world thing as\na candidate entity (\"Jessica\" vs \"Jessica Martinez\" \u2014 but NOT two different\nprocess steps with similar names); (2) write a factual canonical description\nfrom quotes for entities with \u22653 mentions.\n\nWHERE IT SITS IN THE PIPELINE\nAfter relations. Deterministic rules 1-4 (alias, exact, name-part, cosine\n\u22650.92) absorb the easy merges; the judge runs ONLY on the ambiguous cosine band\n[0.80, 0.92) and first-name collisions, on up to 5 candidates with sample\nquotes. Verdicts persist (cmap.resolve_decision); describes feed community\nreports and answering.\n\nWHAT IT IS FED (input)\nJudge: prompts/resolve_judge.md \u2014 mention {name,type,quote,source_title} + 5\ncandidates (canonical name, description, 2 quotes). Describe:\nprompts/entity_describe.md \u2014 type, all names, up to 12 distinct quotes.\n\nWHAT IS EXPECTED (output)\nJudge: {\"same_as\": id|null,\"confidence\",\"reason\"} \u2014 applied only at confidence\n\u22650.7; \"if unsure, null\" is the prompt rule. Describe:\n{\"canonical_name\",\"description\"} \u2014 \"using only the quotes\"; truncated JSON is\nsalvaged field-wise.\n\nPROCESS IT USES\nJSON mode, temperature 0, max_tokens 4000, 3 attempts; job frontier cap.\n\nWHAT MAKES A MODEL PERFECTLY SUITED\nConservative identity judgment (over-merging is the worst failure \u2014 it fuses\ntwo process steps into one entity and corrupts every downstream report);\ncautious null returns; quote-grounded description writing; strict JSON.\n\nCAPABILITIES IT NEEDS (hard)\nJSON mode; careful comparative judgment across short texts.\n\nCAPABILITIES IT DOES NOT NEED\nLong context (candidates are compact), tools, streaming.\n\nMEASURED BENCHMARK\nFrom the resolve fixtures (tests/test_resolve.py scenarios + recorded smoke):\nsame-entity pairs accepted at \u226595% recall in the judge band; different-entity\npairs merged in <2% of cases (precision is the headline); descriptions cite no\nfact absent from the quotes (spot-check 100% on fixture).\n\nHOW TO EVALUATE A CANDIDATE\nReplay the fixture mention/candidate pairs (the judge-band cases especially)\nunder prompts/resolve_judge.md. Check in order: (a) valid JSON; (b) merge\nPRECISION (no false merges \u2014 this ranks before recall); (c) recall on true\npairs; (d) description faithfulness; (e) then cost. A model that confidently\nmerges near-miss names is disqualified regardless of everything else.\n\nKNOWN PITFALLS\n1. Over-merging similar names (two \"Mike\"s, two \"approval\" steps).\n2. Chatty verdicts that break the JSON contract (truncation on long reasons).\n3. Descriptions that read the quotes too freely and invent roles/dates.\n\nBOTTOM LINE\nLower volume than relations but higher blast radius per error. Candidate cheap\nnon-Claude models must PROVE merge precision; if none do, this stage stays on\na stronger model even if relations moves. Current seat:\nanthropic/claude-sonnet-4.5.",
  reports: "THE ORACLE \u2014 \"Community Reports\" role brief (Company Map)\n\nPURPOSE\nWrite the map itself: per Leiden community a briefing (title, 120-200 word\nsummary, 5-12 findings with source_ids, open questions), rolled up L1 -> the\ncompany report with \"Top 10 cross-department issues\". These texts ARE what\nAlbert and Ilona read, and what global answers are built on.\n\nWHERE IT SITS IN THE PIPELINE\nGraph projection -> Leiden (seed=0, deterministic) -> one call per community ->\nstored reports reused on rerun (keyed level+entity set) -> answering (global),\nrecommendations, the /map UI.\n\nWHAT IT IS FED (input)\nprompts/community_report.md with a fitted context (12k-token budget): L0 =\nentity list + top 40 edges + \u226425 quotes with source ids; L1/L2 = child reports'\nsummaries+findings.\n\nWHAT IS EXPECTED (output)\n{\"title\",\"summary\",\"findings\":[{text,kind,stance,entity_ids,source_ids}],\n\"open_questions\":[str]}; findings with no real source_id are dropped. The\nprompt rule: \"Do not invent numbers. Every finding must list at least one\nsource_id.\"\n\nPROCESS IT USES\nJSON mode, temperature 0, max_tokens 4000, 6 parallel workers, one retry then\nskip (never kill the pass), job cap.\n\nWHAT MAKES A MODEL PERFECTLY SUITED\nGrounded synthesis (findings traceable to source_ids \u2014 enforced, but weak\nmodels cite decoratively); compression of noisy cross-department evidence into\nclear prose; policy-vs-practice judgment; no invented metrics; decent writing\n(Albert reads this).\n\nCAPABILITIES IT NEEDS (hard)\nJSON mode at 4000 tokens; long-context synthesis within 12k tokens.\n\nCAPABILITIES IT DOES NOT NEED\nTools, streaming, vision.\n\nMEASURED BENCHMARK\nOn the fixture corpus (smoke's 230-report run) and the real corpus run of\n2026-10-30 (330 L0 communities): \u226595% findings carry valid source_ids;\nzero invented numbers when inputs contain none; summary length in band; and\nthe step-11 global questions score at parity with the incumbent\n(mean \u2265 incumbent \u2212 0.05). Coverage check: the top-5 fixture themes (licensing\nstall, artwork hand-off, ...) each appear in some finding.\n\nHOW TO EVALUATE A CANDIDATE\nTwo steps. (a) Report-quality: give the candidate the same fitted context the\nproduction call uses for 3 representative communities (one clean, one noisy,\none cross-department); grade with a fixed strong grader on: source_id validity,\ntheme coverage, invented-number absence, summary clarity (the grader rubric\nlives in the bake-off harness, not the grade.md eval prompt). (b) End-to-end:\nbuild the reports with the candidate and run the step-11 global questions.\nThe candidate passes only if both hold.\n\nKNOWN PITFALLS\n1. Decorative citations \u2014 findings that name source_ids loosely or fabricate\n   them (the filter drops some, but not all).\n2. Beautiful empty prose \u2014 well-written summaries that miss the themes; read\n   3 reports against the fixture gold before believing a score.\n3. Cost blowups: this is the cost center (up to 12k-token contexts, hundreds\n   of calls). A mid-quality model at 1/5 the price can be the right pick ONLY\n   if (a) and (b) hold.\n\nBOTTOM LINE\nThe hardest slot to price-optimize because it is both the volume center and\nthe reading surface. Albert's rule: the step-11 eval decides. If a cheap\ncandidate holds end-to-end parity, take it; if it lands between cheap-heavy\nand premium-conversation in quality, this stage can take the conversation\nmodel (Claude Haiku 5.5) as a middle seat. Current seat:\nanthropic/claude-sonnet-4.5 (provisional until this bake-off).",
  answer: "THE ORACLE \u2014 \"Question Answering\" role brief (Company Map)\n\nPURPOSE\nAnswer employee/admin questions against the map \u2014 the voice of The Oracle.\nLocal mode: graph neighbourhood + retrieved passages with verbatim quote\ncitations. Global mode: synthesis over community reports. This is\nhuman-facing conversation; tone and honesty matter alongside grounding.\n\nWHERE IT SITS IN THE PIPELINE\nThe /map/ask UI and Teams interviews -> routing (ScaleDown classify) -> local\nanswer (top-8 entities, depth-2 neighbourhood, \u226430 chunks, quotes JSON) and/or\nglobal answer (reports, map-reduce in batches of 10 when >60k tokens) ->\ncitation validation (quotes must be exact substrings; invalid citations dropped\nand sentences marked \"(uncited)\") -> the answer + citations back to the UI.\n\nWHAT IT IS FED (input)\nprompts/answer_local.md / answer_global.md / answer_map.md with history (6\nturns), the question, graph context, passages (ScaleDown-compressed when >6k\ntokens) and a QUOTES list with chunk_ids. The persona: \"Operations Oracle\" \u2014\ninvestigative, cites, flags unknowns.\n\nWHAT IS EXPECTED (output)\n{\"answer_md\" (every factual sentence ends [n]), \"citations\":[...],\n\"unknowns\":[]} \u2014 quotes copied EXACTLY from the QUOTES list. Invalid JSON is\nfence/comma/salvage tolerant.\n\nPROCESS IT USES\nJSON mode, temperature 0, max_tokens 4000, 3 attempts. The user is waiting \u2014\nthis is the one stage where latency is felt.\n\nWHAT MAKES A MODEL PERFECTLY SUITED\nVerbatim quote copying (citation validation is unforgiving); grounding honesty\n(\"unknowns\" over invention); stance/nuance reading (policy vs practice);\nnatural concise prose (Albert and Ilona read these); reliable JSON at 4000\ntokens; decent latency.\n\nCAPABILITIES IT NEEDS (hard)\nJSON mode; strong instruction-following on citation markers; 12k+ context.\n\nCAPABILITIES IT DOES NOT NEED\nVision (text contexts), tools, giant output caps.\n\nMEASURED BENCHMARK\nThe step-11 eval IS this stage's benchmark: mean score over the eval questions\n(currently 5 fixture seeds; the 20 real questions when Albert and Ilona write\nthem), citation validity rate (drop rate), and the cross-source questions\n(\"Where does licensing approval stall and why?\") answered with sources. Also:\nmedian latency per question.\n\nHOW TO EVALUATE A CANDIDATE\nRun the step-11 eval on the same graph with the candidate as answer model and\na FIXED grader (see \u00a72). Check in order: (a) valid JSON + citation drop rate;\n(b) eval mean (parity or better than incumbent \u2212 0.05); (c) the stall question\nreads correctly; (d) latency; (e) price. This is Albert's designated\nconversation seat: Claude Haiku 5.5 is the standing assignment \u2014 the eval\nproves or revises it.\n\nKNOWN PITFALLS\n1. Paraphrased quotes \u2014 citations vanish, sentences become \"(uncited)\", score\n   collapses. Fastest quality test there is.\n2. Confidently merged stances (the \"policy vs practice\" distinction is the\n   product).\n3. Long-windedness \u2014 answer length past the marker discipline.\n\nBOTTOM LINE\nAssigned seat: Claude Haiku 5.5 (Albert's direction, 2026-10-30). Prove it on\nthe step-11 eval against 1-2 challengers; if it lands materially below the\nincumbent on citation validity or mean, report back before switching. Cost\nmarginal (low volume); quality is the whole game.",
  recommend: "THE ORACLE \u2014 \"Recommendations\" role brief (Company Map)\n\nPURPOSE\nFor each bottleneck/complaint/contradiction finding with \u22652 sources: one\nstructured recommendation \u2014 the problem, 2-4 COMPETING explanations (one must\nbe \"the data is incomplete\"), 3-5 options (one must be \"No change\"), and a\nreversible experiment with a metric. Quantified claims are scrubbed in code\nwhen the evidence has no numbers.\n\nWHERE IT SITS IN THE PIPELINE\nAfter communities. Finding + quotes + area report (12k fitted) -> this call ->\ncmap.recommendation rows -> the /map/recommendations page (Accept/Reject/\nRunning/Measured).\n\nWHAT IT IS FED (input)\nprompts/recommend.md with finding, \u226420 quotes, source list, community report.\n\nWHAT IS EXPECTED (output)\n{\"problem\",\"explanations\",\"options\",\"experiment\"} \u2014 code enforces shape,\ninjects the missing \"incomplete data\" / \"No change\" items, scrubs\npercentage/money patterns to \"an unmeasured amount\".\n\nPROCESS IT USES\nJSON mode, temperature 0, max_tokens 4000, 1 call per qualifying finding.\n\nWHAT MAKES A MODEL PERFECTLY SUITED\nGenuine competing-hypothesis thinking (the product's signature); restraint on\nnumbers; practical reversible-experiment design; tight problem statements\n(they feed embedding dedupe).\n\nCAPABILITIES IT NEEDS (hard)\nJSON mode; judgment quality in hypothesis/experiment generation.\n\nCAPABILITIES IT DOES NOT NEED\nLong context, tools, streaming.\n\nMEASURED BENCHMARK\nFixture gate (tests/test_recommend.py): the licensing-stall fixture yields a\nrecommendation with \u22652 explanations incl. \"incomplete data\", a \"No change\"\noption, no digit-percent pattern when inputs have numbers. Plus human read of\n3 real-corpus recommendations for plausibility (this output goes to Albert).\n\nHOW TO EVALUATE A CANDIDATE\nRun the fixture finding + 2 real-corpus findings through the candidate under\nprompts/recommend.md. Check: (a) valid JSON with the mandated items; (b) no\ninvented numbers; (c) explanation quality (mutually distinct, evidence-linked);\n(d) experiment sanity (reversible, measurable, has an owner role); (e) price.\n\nKNOWN PITFALLS\n1. Invented savings (\"reduce cycle time by 30%\") \u2014 code scrubs some patterns\n   but the model should not generate them.\n2. One-sided advocacy \u2014 the competing-explanations structure is the point.\n3. Dedupe-hostile problem statements (near-duplicate recommendations).\n\nBOTTOM LINE\nLow volume, high visibility. This can ride the conversation seat (Claude\nHaiku 5.5) if it passes (c)/(d); it must NOT ride a candidate that writes\nconfident invented numbers. Current seat: anthropic/claude-sonnet-4.5.",
  grade: "THE ORACLE \u2014 \"Eval Grading\" role brief (Company Map)\n\nPURPOSE\nScore an answer against the question's expected points: {\"covered\",\"missing\",\n\"contradicted\"} indexes. Score = covered/total \u2212 0.2 per contradiction. This\nmodel is the BAKE-OFF INSTRUMENT \u2014 its consistency is what makes every other\ncomparison meaningful.\n\nWHERE IT SITS IN THE PIPELINE\nStep-11 eval: per question, after answering. prompts/grade.md carries the\nquestion, numbered expected points, and the answer.\n\nWHAT IT IS FED (input)\nQuestion + 3-6 expected points + the answer markdown.\n\nWHAT IS EXPECTED (output)\nIndex lists only; contradicted wins over covered; every unlisted point counts\nmissing. \"Covered\" requires a citation marker in the sentence.\n\nPROCESS IT USES\nJSON mode, temperature 0, max_tokens 800, 3 attempts.\n\nWHAT MAKES A MODEL PERFECTLY SUITED\nSemantic equivalence judgment (paraphrase counts); consistency across runs\n(temperature 0 is not a guarantee); strict index discipline; no generosity\nbias (an answer that says something different is NOT covered).\n\nCAPABILITIES IT NEEDS (hard)\nJSON mode; careful reading; consistency.\n\nCAPABILITIES IT DOES NOT NEED\nLong context (answers are short), creativity, speed.\n\nMEASURED BENCHMARK\nAgreement with the keyword-grader fixture expectations\n(tests/test_eval_fixture.py) \u22650.8 mean on the seed set; self-consistency:\ntwo runs of the same input give identical indexes.\n\nHOW TO EVALUATE A CANDIDATE\nGrade the same 5 fixture answers twice with the candidate; require identical\nindexes both runs and agreement with the fixture expectations. Then \u2014 and only\nthen \u2014 it may replace the incumbent grader, AFTER a bake-off cycle completes\n(never mid-cycle).\n\nKNOWN PITFALLS\n1. Generosity drift \u2014 score inflation that makes every candidate look equal.\n2. Mid-cycle grader swaps \u2014 invalidates every comparison in flight.\n\nBOTTOM LINE\nDuring the whole bake-off the grader is FROZEN on anthropic/claude-sonnet-4.5\n(current seat). Grader candidates are evaluated at the very end and switched\nonly between cycles. This stage is about trust, not cost (1 call/question)."
};

export const SEAT_CHIP_LABELS: Record<SeatChip, string> = {
  incumbent: 'Incumbent',
  assigned: 'Assigned: claude-haiku-5.5 (pending proof)',
  bakeoff: 'Bake-off pending',
  frozen: 'Frozen grader',
};

/** Page-level legend wording for each seat chip (shown once, not per card). */
export const SEAT_CHIP_NOTES: Record<SeatChip, string> = {
  incumbent: 'seated today; competed at low priority',
  assigned: 'Albert’s conversation seat — prove on the step-11 eval',
  bakeoff: 'will be competed under its job brief',
  frozen: 'held fixed during the bake-off',
};

export const SEAT_CHIP_STYLES: Record<SeatChip, string> = {
  incumbent: 'bg-muted text-foreground',
  assigned: 'bg-primary/15 text-primary',
  bakeoff: 'bg-amber-100 text-amber-900 dark:bg-amber-950/50 dark:text-amber-200',
  frozen: 'bg-sky-100 text-sky-900 dark:bg-sky-950/50 dark:text-sky-200',
};

export const COMPANY_MAP_STAGES: CompanyMapStage[] = [
  {
    id: 'vision',
    order: 1,
    title: 'Vision transcription',
    role: 'One page image — diagram, flowchart, text-poor PDF — into faithful text and diagram topology.',
    envVar: 'BRAIN_VISION_MODEL',
    chip: 'incumbent',
    modelKey: 'vision',
    brief: BRIEFS.vision,
  },
  {
    id: 'embed',
    order: 2,
    title: 'Embeddings',
    role: 'Vectors for retrieval, dedupe, and the cosine bands that gate entity resolution.',
    envVar: 'BRAIN_EMBED_MODEL',
    chip: 'incumbent',
    modelKey: 'embed',
    brief: BRIEFS.embed,
  },
  {
    id: 'flat',
    order: 3,
    title: 'Flat extraction',
    role: 'Cheap bulk pass — classify each chunk into 7 passage kinds and lift flat entities with exact spans.',
    envVar: 'BRAIN_SCALEDOWN_ENABLED + BRAIN_FRONTIER_MODEL (fallback)',
    envNote: 'primary path: ScaleDown (SCALEDOWN_API_KEY)',
    chip: 'bakeoff',
    modelKey: 'flat_fallback',
    brief: BRIEFS.flat,
  },
  {
    id: 'relations',
    order: 4,
    title: 'Relationship extraction',
    role: 'Link a chunk’s mentions into typed relationships — the highest-volume reasoning stage and the graph’s backbone.',
    envVar: 'BRAIN_FRONTIER_MODEL',
    chip: 'bakeoff',
    modelKey: 'relations',
    brief: BRIEFS.relations,
  },
  {
    id: 'resolve',
    order: 5,
    title: 'Entity resolution',
    role: 'Judge ambiguous identity merges (precision first) and write factual canonical descriptions from quotes.',
    envVar: 'BRAIN_FRONTIER_MODEL',
    chip: 'bakeoff',
    modelKey: 'resolve',
    brief: BRIEFS.resolve,
  },
  {
    id: 'reports',
    order: 6,
    title: 'Community reports',
    role: 'Write the map itself — per-community briefings rolled up to the company report Albert reads.',
    envVar: 'BRAIN_FRONTIER_MODEL',
    chip: 'bakeoff',
    modelKey: 'reports',
    brief: BRIEFS.reports,
  },
  {
    id: 'answer',
    order: 7,
    title: 'Question answering',
    role: 'Answer employee questions against the map with verbatim quote citations — the Oracle’s voice.',
    envVar: 'BRAIN_CHAT_MODEL',
    envNote: 'fallback: BRAIN_FRONTIER_MODEL',
    chip: 'assigned',
    modelKey: 'answer',
    brief: BRIEFS.answer,
  },
  {
    id: 'recommend',
    order: 8,
    title: 'Recommendations',
    role: 'One structured recommendation per finding — competing explanations, options, a reversible experiment.',
    envVar: 'BRAIN_FRONTIER_MODEL',
    chip: 'bakeoff',
    modelKey: 'recommend',
    brief: BRIEFS.recommend,
  },
  {
    id: 'grade',
    order: 9,
    title: 'Eval grading',
    role: 'Score answers against expected points — the bake-off instrument itself.',
    envVar: 'BRAIN_EVAL_MODEL',
    envNote: 'fallback: BRAIN_FRONTIER_MODEL',
    chip: 'frozen',
    modelKey: 'grade',
    brief: BRIEFS.grade,
  },
];
