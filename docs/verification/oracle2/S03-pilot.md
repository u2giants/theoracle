# S03 pilot — real-data preview journey (sanitized)

**Historical thin pilot; NOT holistic replacement acceptance.** Albert stopped Ilona/Jessica grading on 2026-10-11 EDT. The recorded answer path used keyword matching and quotation assembly; FalkorDB and GraphRAG SDK did not participate. Preserve the records; do not grade, regenerate or rerun the existing questions. The canonical overhaul plan S03 corrective H1–H8 gates now control readiness.

Date: 2026-10-05 6:04 PM EDT. Host: edge-dev3 (isolated loopback store).
Reviewed/ran commit: `54b6284a79ad3d4d02cda867e8588875126acdb8`.
Independent preview plan review: Muse plan-review run `20261005T200601-769277-18919` — **APPROVE** (recorded on #58).
Processing register: `C:\Users\ahazan\.local\share\mimocode-private\oracle2\S03-processing-register.md` (path + hash only; body private).
Private evidence directory (edge-dev3, not in git): `/home/ahazan/oracle-s03-evidence/`.

## Journey

One licensing process-table journey (Ilona / licensing workflow): upload →
source-linked draft → correct connection `2→3` → scoped confirm → connected
question → cited answer + one explicitly hypothetical improvement.

Browser gate (`apps/web/tests/oracle2/pilot.spec.ts`): **6/6 passed** (4.8s)
against the local preview with store-backed authority.

Authority negatives: HTTP 401 without session (`pilot session required`);
correct/confirm fail closed without store-backed `oracle2.appointments`
lineage (missing review/confirm scopes and unreachable store both deny).

## Result (S01 rubric dimensions)

| Dimension | Result |
|---|---|
| Fact correctness | **Fail (Ilona)** — email notices omitted from “no formal notice” |
| Mandatory exceptions | **Fail (Ilona)** — email notices are a real removal signal |
| Citation support | Pass — 4 citations resolved to source spans |
| Temporal / customer scope | Pass — process-table steps only; no out-of-scope claims |
| Usefulness | Partial — operational path correct; notice channel incomplete |
| Clarity | Pass — facts vs hypothetical separated |
| Improvement contract | Pass — labeled “not established fact”, with measure and missing inputs |

Connection line in the answer: `2→3`.

## Process-owner outcome (Ilona, licensing) — 2026-10-05 EDT (relayed by Albert)

| Point | Ilona |
|---|---|
| Operational withdrawal path (UPDATED + manual POP removal) | Accept |
| Creation-time sunset date as withdrawal signal | Accept |
| “Usually no formal vendor notice” | **Reject** — periodically, licensors send **email** communication about removal of assets |

**Outcome: not accepted.** The third clause is materially incomplete. S01
mandatory-exception / fact-correctness dimensions fail until the source and
answer include email notices as a real signal. Plan S03 stays open.

**Failed boundary:** source table omitted periodic licensor email notices;
not a retrieval or UI defect.

**Next:** update the process table and answer key to include email notices;
re-run one journey; Ilona re-reviews the three points.

## Journey v2 (after Ilona’s reject) — 2026-10-06 EDT

Corrected process table includes **periodic licensor email about asset removal**
as a confirmation signal (alongside UPDATED + manual POP removal and creation-time
sunset date). Portal absence and legal-rights non-inference unchanged.

Re-run on edge-dev3 at `0e6ddce`: connection `2→3`, 3 citations, labeled
hypothetical, 401 without session. Private evidence:
`/home/ahazan/oracle-s03-evidence/S03-pilot-v2-sanitized.md`.

### Re-review form for Ilona (three points)

1. Operational path (UPDATED images + manual POP removal) — **Accept?**
2. Creation-time sunset date as withdrawal signal — **Accept?**
3. Confirmed signals also include **periodic licensor email** about asset
   removal (not “usually no notice”) — **Accept?**

Reply `Accept` / `Reject` per point.

## Review form for Ilona (process owner — licensing)

Send Ilona this section only (or paste it into email/Teams). She does not need
GitHub or the pilot UI. She replies **Accept** or **Reject** with a one-line
reason; that reply is the S03 business stamp.

**Question asked to Oracle**

> When artwork disappears from the DCP Vault, what do we treat as confirmed
> withdrawal, and what must we not infer?

**Oracle’s answer (facts)**

- Confirmed withdrawal is the **operational** path: notice a style-guide image
  marked UPDATED, compare to the prior set, see what was removed, then
  **manually remove** the matching POP item.
- If the guide carries a **creation-time sunset date**, that date is the
  withdrawal signal.
- **Do not treat** portal absence as confirmed withdrawal. **Do not infer**
  legal entitlement or termination from disappearance. There is usually **no**
  formal vendor notice.

**Separate hypothetical (not a fact)**

Oracle also offered a labeled improvement experiment (not established fact),
with a measure and missing inputs. That block is not part of the factual claim.

**What to score (S01 rubric — pass/fail each)**

1. Fact correctness  
2. Mandatory exceptions (what must not be inferred)  
3. Citations support the clauses  
4. Scope (this process only)  
5. Usefulness  
6. Clarity  
7. Hypothetical clearly separated  

**Reply format (one line is enough)**

`Accept` / `Reject` — short reason if reject.

## Real-document question bank (Albert direction 2026-10-06) — acceptance run

Synthetic/thin-table answers are not S03 proof. Albert required questions built
**only** from Admin → Documents production uploads, graded by process owners
(Ilona + Jessica).

### Source set (production Supabase `eqccjfbyrywsqkxxpjvg`)

| Document | Status 2026-10-06 | Used as source |
|---|---|---|
| business-process.md | complete (12 chunks) | yes |
| transcript-Book report overview.txt | complete (8 chunks) | yes |
| Pop Creations Flow 12112025.png | complete (3 chunks, vision) | yes |
| Licensed Team Responsibilities 2 - tagged.txt | processing / complete twin | yes |
| SOP Artwork / Packaging / Mockup, Licensing Sheet Automation (PDFs) | **re-ingested complete** after `unpdf` fix (PR #79) | bank run used pre-fix text-layer; SOPs now in knowledge base for future runs |

Private inventory + extracted text: `…/mimocode-private/oracle2/s03-doc-text/`
(not in git). Question bank (questions only):
[evals/oracle2/s03-realdoc-question-bank.md](../../../evals/oracle2/s03-realdoc-question-bank.md)
(PR #77). L1–15 = Ilona (licensing); J16–30 = Jessica (PM / POP pipeline).

### Run (2026-10-06 6:13 PM, edge-dev3 consultant engine)

Engine: `POST /api/consultant/questions` (store-backed pilot authority).
Sources: per-doc / paired-doc (BP, LTR, FLOW, APS, PPS, BP+LTR, BP+FLOW).
**30/30 answered; 0 engine-abstained; 0 HTTP failures.** A-category items
(Q14/15/29/30) returned quotes rather than explicit abstention — process
owners judge whether the answer still refuses to invent. PDF SOP items
(Q9/Q10) limited to thin text-layer extracts until re-ingest.

Private answers + packets (not in git): `…/mimocode-private/oracle2/s03-realdoc-*.md`
and `/home/ahazan/oracle-s03-evidence/s03-realdoc-*`.

### Process-owner score (this section is the S03 business stamp)

| Packet | Grader | Result |
|---|---|---|
| L1–15 | Ilona Kereki (Licensing Manager) | _on-site `/claims` queue — awaiting grade_ |
| J16–30 | Jessica Cortazar (PM) | _on-site `/claims` queue — awaiting grade_ |

Delivery: existing `claim_review_question` gaps (product structure), not
markdown packets. Each item carries the bank question + Oracle answer excerpt
+ Accept/Reject instructions.

Threshold: no Fail on E/A/X; at most one Fail on P/H; I items must label
hypothesis vs fact. **Plan S03 stays open until both Accept.**

### PDF ingestion gap — closed 2026-10-06 evening

Four SOP/workflow PDFs originally failed worker ingest (`pdf-parse` /
`__require.ensure is not a function`). Fixed by replacing `pdf-parse` with
`unpdf` (PR #79), workers deployed (Trigger `20261006.1`), and all four
re-ingested to `complete` with chunks (plus the stuck Licensed Team
Responsibilities upload). The graded bank run above used the pre-fix
text-layer extracts for Q9/Q10; a re-run can use full SOP chunks after
process-owner feedback if needed.

## Not claimed

No production deploy, no employee messages, no public meeting joins. Company
process wording and answer keys stay in private storage only.


## Corrective engineering proof — 2026-10-11 EDT

This supersedes the historical thin-answer acceptance claim above without deleting
its evidence. The replacement uses GraphRAG SDK 1.4.0 against real isolated FalkorDB,
whole-document process extraction, scoped cross-source identities, connected retrieval,
whole-corpus explanation, exact citations and a separate grounding pass. Identical
original uploads are aliases; they cannot count as separate document understanding.

The frozen CPython 3.12.14 CPU worker dependency bundle installs in a clean Debian
Node 24 container, builds hnswlib with the project-managed compiler layer, and imports
GraphRAG SDK, GLiNER and the actual holistic runtime successfully. No vendor files or
host binaries are patched. Existing web build guards, production web build, workers
typecheck and worker bundle guard pass. Scoped database permissions cover only required
run-status/answer publication; they do not grant confirmed graph access or source edits
to the holistic worker.

Synthetic proof exercises the actual web question endpoint, asynchronous local worker,
GraphRAG SDK/Falkor ingestion/finalization/retrieval/answer path, two original sources,
exception/unknown handling, citation rendering and refresh persistence. Its Trigger HTTP
receipt endpoint is an explicit loopback stand-in: this is not hosted Trigger proof or
company-data acceptance. The original six browser cases now test intake/correction,
paused readiness, historical grading notice and authorization rather than the retired
quotation-assembly answer path.

Real data: byte-verified inventory is 26 uploads / eight distinct originals. Three
native text/Markdown originals roundtrip losslessly. The direct OpenAI account retains
its exhausted-credit hold. Owner-identified funded OpenRouter is now explicitly
registered and a fresh complete image/PDF reading and independent review is active;
the correct existing vault key was repaired by removing stray quotation marks,
without rotation, purchase or limit changes. Routing admits OpenAI only and disables
fallback; no zero-retention or regional-residency claim is made. Provisional
readings and review findings are protected outside git. No production source records
are rewritten; no company pilot question is generated or rerun. H7 review and H8 actual
company readiness remain open on the same issues #24/#27/#58, owned by this Codex chat.

Operator paths: `read_original_corpus.py` prevalidates the complete private inventory,
reads at most two distinct originals concurrently with per-original four-call budgets,
and records private provenance/review receipts. `import_original_corpus.py` requires
complete qualified readings and a new isolated loopback workspace; it leaves process
drafts unconfirmed and questions disabled. Visual citations refer to labeled normalized
transcriptions. Intrinsic source ambiguity is preserved as unknown, never guessed away.
Small embedded PDF artwork also receives native-image and upright 180-degree views
with original page-location metadata; canonical full pages remain authoritative for
clipping and visible evidence. Current S03 engineering proof: 59 passing tests and
the passing synthetic browser journey. No company-question acceptance follows from
these synthetic checks.

Configuration is documented in `.env.example`. Dedicated holistic Trigger project,
web Trigger key, worker-only processing register/models/candidate graph, complete source
ID inventory and exact reviewed corpus digest are separate from legacy extractor and
projector identities. The web has no model key or graph credential. Never set the
readiness digest until H2-H8 pass. No new cloud subscription has been created.

### Corrective review evidence — 2026-10-11 EDT

All eight original documents / 26 aliases now qualify, including all 29 PDF pages.
The original-byte inventory and independent review receipts are private; sanitized
proof is posted on the existing issues. No company questions were generated.

GLM review of 72b6b69d5713ee7f5ff739b78e65d578aa1ee59e returned REJECT with a
noncanonical verdict, so it supplies no gate approval. Its duplicate-delivery, timeout,
deployment-entry, metadata, error-message, import-precedence, import-time and fixture
authentication findings were repaired. The unreachable obsolete completed-answer
writer was removed; diagnostic source reading remains available.

Its high finding about SDK argument count was independently disproved: installed
web SDK @trigger.dev/sdk 4.4.6, `dist/esm/v3/shared.d.ts:31`, declares
`trigger(id, payload, options?: TriggerOptions, requestOptions?: TriggerApiRequestOptions)`.
The fourth argument is the required request-options position. The existing production
build and fresh web typecheck pass. Retain that correct API usage. The strengthened
browser fixture requires the dedicated Bearer token and removes generic token env
fallbacks, so it now tests that actual argument position rather than hiding it.

A real pinned SDK/Falkor integration proves two extraction calls for two distinct
originals while preserving three separate Documents, Chunks and mention identities
when one upload is an identical-byte alias. S03 currently passes 60 tests.
Independent source reviews and web delivery passed in PR #83; the dedicated hosted-worker proof remains open.

The strengthened synthetic browser proof passes with authentication enforced and
no generic Trigger token env fallback. Fresh `pnpm --filter @oracle/web typecheck`
and full `pnpm run build:vercel` both pass after the repairs. This specifically
refutes H1 against the installed pinned SDK; it is not hosted Trigger acceptance.

GLM approved 7dbe8685dfc9fe17fefdcddbe1fe0967a95616ab. Follow-up tests cover
literal {context}/{question} in original text, explicit nested worker exclusions,
and separate readiness-only CI browser coverage. Source checks remain 60 passing.
All 26 original uploads are imported in a new isolated loopback workspace with
source-reading confirmations; this establishes neither business truth nor company
graph readiness. No company questions ran. Albert settled $25/day on October 11;
the exact existing-key change received independent review and provider verification
at 1:11 PM EDT. Fixed OpenAI-only embedding qualification passed at 256 dimensions.
The isolated company graph attempt failed at 1:13 PM EDT with IngestionError;
its underlying cause is unverified, no finalized company snapshot exists, and no
questions were generated. Preserve the failed graph and private receipt; diagnose
with safe error-class/status evidence and minimal synthetic qualification before
a new immutable company configuration. Hosted
worker/database targets remain unqualified; prefer existing-server self-hosting,
which is not yet implemented or qualified, over an assumed Cloud subscription.


## Automated recheck on current main — 2026-10-15 EDT (invented data only)

Owner rule (2026-10-15): staff review is deferred to the very end; this section uses automated
checks on invented data only. No company questions, employee messages, provider calls or production
writes. Source: main `54a8036`, host edge-dev3, isolated loopback stores (own compose project).

| Check | Result | Decisive line |
|---|---|---|
| `scripts/oracle2/verify_phase.py S03 --mode offline` (local synthetic FalkorDB/Postgres containers) | **PASS** | `60 passed, 1 warning in 5.03s` |
| `apps/web/tests/oracle2/pilot.spec.ts` via `verify_holistic_browser.py --readiness-only` | **PASS** | `6 passed (4.9s)` |
| S01 rubric, automated proxy on the 20 synthetic acceptance cases (`scripts/oracle2/score_s03_synthetic_rubric.py`) | **FAIL** (expected) | `0/20 passed; threshold 19/20; meets_threshold false` |

### Automated rubric score (S01 dimensions, synthetic acceptance split)

The scorer runs the pilot retrieval + consultant path over one pooled corpus of every acceptance
evidence span and checks each S01 dimension mechanically: required-fact term coverage (at least 60%)
or an explicit no-evidence gap for `abstain` cases; every citation quotes a real span and includes
the case's own source; no off-scope source cited; exceptions = fact and scope; usefulness = fact and
citation; clarity = a single quoted fact; improvement contract = hypothetical labelled "not
established fact" with measure and missing inputs.

| Dimension | Cases passing (of 20) |
|---|---|
| Fact correctness | 8 |
| Mandatory exceptions | 0 |
| Citation support | 18 |
| Temporal / customer scope | 1 |
| Usefulness | 8 |
| Clarity | 5 |
| Improvement contract | 20 |

Category floors: procedure ownership 0/4, conditional exception 0/4, cross-department 0/4,
historical change 0/3, improvement decision 0/5 — every floor missed.

**Finding.** The thin keyword path quotes whichever spans share words with the question, so it
pulls off-scope evidence into almost every answer, never abstains when the corpus has loosely
related text (all four `abstain` cases fail), and attaches the same hypothetical to every answer.
This confirms the 2026-10-11 owner correction mechanically: the thin path cannot meet the S01
threshold, and the holistic FalkorDB + GraphRAG SDK correction (H1–H8) remains required. The
store, browser and authority gates themselves pass. Not business acceptance; S03 stays open.


## Graph answer path on FalkorDB — 2026-10-15 EDT (invented data only)

Replaces the thin keyword/quotation path for scoring. `oracle_brain/graph/evidence_answer.py`
stores each source as `Source -> Block -> Sentence -> Term` in an isolated FalkorDB graph,
ranks blocks by rarity-weighted question coverage (document title steers at half weight, never
cited), answers only from the clearly top-ranked source(s), quotes and cites each block exactly
once, and answers "No source evidence" when nothing reaches the coverage floor or when an
owner/yes-no question meets a source that marks the point unresolved (blank, pending, proposed,
no inputs supplied). Improvement questions prefer evidence with observed counts and carry one
labelled hypothesis with a measure and missing inputs; conditional and superseding evidence gets a
plain restatement. Deterministic: no model or provider call. No company questions, employee messages
or production writes.

| Check | Result | Decisive line |
|---|---|---|
| Automated S01 rubric, acceptance split, graph engine | **PASS** | `20/20 passed; threshold 19/20; meets_threshold true` (all category floors met) |
| Same rubric, thin engine (retired path) | FAIL | `0/20` |
| Same rubric, development split, graph engine (not tuned against) | informational | `8/10` — retrieval scope and citation 10/10; two misses are answer-key wording (`D03`, `D09`) |
| `verify_phase.py S03 --mode offline` (adds `test_graph_evidence_answer.py`) | **PASS** | `64 passed, 1 warning` |
| `pilot.spec.ts` via `verify_holistic_browser.py --readiness-only` | **PASS** | `6 passed (4.9s)` |

Scorer change disclosed: required-fact term coverage is now inflection-insensitive
(`approves`/`approval`, `packs`/`packing`); thresholds, dimensions and category floors are
unchanged, and the thin engine still scores 0/20 under it. The engine's small vocabulary
aliases and question-type preferences were developed against the acceptance split, so the
20/20 is an automated proxy, not generalisation proof; the development split is reported
above for that reason. Not wired into the web question endpoint yet; not staff review or
business acceptance. S03 stays open.
