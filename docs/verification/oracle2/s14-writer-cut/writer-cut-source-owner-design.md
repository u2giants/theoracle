# S14 global writer consistent cut — source-owner design and race matrix

**Parent:** #24 · **Class:** code (design-only; no implementation, no production, no POP shared-db writes)  
**Companion inventory:** `writer-cut-complete-inventory.json` (same directory)  
**Ownership:** Legacy Oracle Supabase `theoracle` is Oracle-owned. No POP shared-db claim. No structural change authorized by this document.

---

## 1. Purpose and boundary

This document is the concrete source-owner design for the global writer consistent cut that S14 requires. It expands the root architectural direction into implementable stages and defines the invented race matrix to execute later. It is **not** implementation, not production action, not business acceptance, and not authority for comparison/cutover/adoption/non-use/retention/removal — those stay held behind a separate business-acceptance gate.

**Explicit invariants that every stage must preserve:**

1. **Pause is finite opaque original arrival/body-hash custody only.** During `pausing`, new effect claims are rejected and finite opaque arrival receipts/bytes are durably accepted into the existing actual ingress/custody owners, keyed by stable original arrival identity and unchanged body hash. Queueing is not source qualification, viewer permission, or an automatic right to replay.
2. **UNKNOWN never equals drained.** UNKNOWN blocks a positive `drained` claim. Read-only receipt and financial/forensic observation may continue under independently current narrow authority without reopening dispatch.
3. **STOP / privacy-withdrawal / security denial must remain operational** and invalidate the candidate cut. Any such source/permission change forces fresh reconciliation; its immutable fact is retained. These operations are never suppressed by the pause.
4. **Uncontrolled Auth/Storage/provider/unknown writer means incomplete.** If an external owner remains uncontrolled or its writer list is incomplete, `consistent_boundary_proven` stays `false`/`UNKNOWN`.
5. **No advisory-only / GUC / self-stamp grant.** PostgreSQL advisory locks alone only serialize callers that voluntarily participate. Enforcement is local at each actual write owner, coordinated by ONE control.
6. **No POP shared-db writes.** The retained Oracle legacy-source DB is Oracle-owned. A source-local barrier requires the actual Oracle legacy-source schema owner and its applicable reviewed migration route.

---

## 2. Root architectural direction (restated for implementability)

Extend the **SAME durable release-selector CAS** with:

| Field | Meaning |
|---|---|
| exact release manifest / workspace | Pins the release and workspace the cut belongs to |
| current installed controller admission | Only the admitted controller may drive transitions |
| old ingestion generation | Generation every legacy writer must present |
| new ingestion generation | Generation replacement writers will use |
| complete writer-census digest | Immutable digest of the adjudicated writer inventory |
| phase | `legacy-active → pausing → drained → snapshot-reconciled → replacement-active`, with `ABORTED`, `UNKNOWN`, `rolling-back` |

Every transition is CAS on exact prior generation and pins: census digest, release/runtime/config, pause-start monotonic/wall evidence, queue coverage, snapshot/canonical comparison digests, and current authority horizon.

**Enforcement is local at each actual write owner.** Each owned SQL mutation must lock/check its actual local barrier row/generation **in the same transaction** as the mutation, with a stale generation unable to publish. Independent role/generation admission: the writer's DB role and generation must both be admitted. Object upload/delete and external dispatch require their own installed fixed effect owner to participate in the same logical cut. Never hold SQL connections across private bytes or provider IO.

---

## 3. Implementable stages

### Stage 0 — Writer census adjudication (prerequisite)

**Goal:** Convert the candidate inventory into an adjudicated confirmed/candidate/excluded census with a stable digest.

- Walk every site in `writer-cut-complete-inventory.json`.
- For each `candidate`, decide: confirmed writer, excluded (hash/crypto/in-memory/comment/DTO), or unknown.
- Unknown sites block the census digest — the cut cannot start with an unknown writer.
- Produce `writer-census-digest` = SHA-256 of the canonical sorted confirmed-writer list (file + line-range + family + owner module).
- Record the external classes (F9) as **incompleteness declarations**, not as fenced writers.

**Exit criterion:** Every site is classified; digest is stable; zero unknown writers in the confirmed list.

### Stage 1 — Single durable cut-control owner

**Goal:** One control state machine tied to the existing release-selector owner.

- Schema: one control row per (release, workspace) with phase, generations, census digest, controller admission, timestamps, digests.
- API (internal, controller-only): `begin_pause`, `mark_drained`, `record_snapshot`, `activate_replacement`, `begin_rollback`, `abort`.
- Each API is CAS on exact prior generation; a concurrent call loses and must re-read.
- Controller admission is a separate table with role + generation; only admitted controller may call transitions.
- Reuse 027 inventory/binding/reconciliation and 026 deny/once/custody evidence as dependencies. Do **not** create a parallel fact/permission/receipt ledger.

**Exit criterion:** Control row exists; CAS transitions are tested in isolation; stale-generation controller is refused.

### Stage 2 — Local barrier + generation at every confirmed SQL writer

**Goal:** Every confirmed writer from the inventory checks barrier+generation in the SAME transaction.

- Install a local barrier row (or table) that the control owner transitions.
- Each writer module gets a guard function: `assert_admitted(tx, expected_generation)`.
- The guard runs **inside** the same transaction as the mutation. A stale generation causes the transaction to abort/raise.
- Independent role admission: the DB role the writer connects as must be admitted for that generation. A role that is not admitted cannot write even if it presents a correct generation number (prevents self-stamp).
- Cover all families F1–F6 and F8. F7 replacement/pilot routes are inventoried but not activated.

**Exit criterion:** A synthetic stale-generation writer cannot publish; a correct-generation writer can; both are proven in the owned test database.

### Stage 3 — Storage and external effect owners

**Goal:** Object and external writers participate in the same logical cut.

- Storage upload/remove: wrap in a fixed effect owner that (a) checks barrier+generation before the object op, (b) records an in-flight upload receipt, (c) commits the SQL metadata only after object success, (d) records orphan removal.
- External provider dispatch (Recall, Vertex batch/caches, GCS): fixed effect owner records an outbound intent before the call, and a receipt after. Lost ACK stays UNKNOWN; no resend.
- Supabase Auth: treat as external. Record identity-link writes (F5 `packages/auth/src/link.ts`) under the SQL barrier; Auth platform events remain external declarations.

**Exit criterion:** An upload arriving during `pausing` is durably accepted as an opaque arrival; no orphan object exists without a recorded receipt.

### Stage 4 — Durable pause arrival queue

**Goal:** Finite opaque arrivals during `pausing` are retained once, keyed by stable original arrival identity and unchanged body hash.

- One queue per ingress family (documents, messages, Teams/live, import, extraction submissions).
- Arrival record: original arrival id, body hash, family, received-at, status (`accepted-opaque`, `replayed`, `dropped-unknown`).
- Resume requires fresh current permissions and one globally retained ownership decision per arrival. No hash/idempotency namespace reset across reinstall/generation/rollback.

**Exit criterion:** Concurrent arrivals during pause are each retained exactly once; replay after resume is individually authorized.

### Stage 5 — Drain started writers and queue depth

**Goal:** Prove `drained` honestly.

- Inventory of started process/task/lease/provider operation IDs.
- Wait for each to reach a terminal state or explicitly mark UNKNOWN.
- UNKNOWN blocks `drained`. Queue depth alone is insufficient.
- Provider 200 is not visible delivery/stop proof; an already-sent request cannot be revoked by incrementing a database generation.

**Exit criterion:** Every started writer is terminal or UNKNOWN; zero UNKNOWN to claim drained.

### Stage 6 — Bounded full snapshot and reconciliation

**Goal:** Produce an honest vector of local snapshot/commit and queue positions.

- Snapshot source rows, permissions, approval/relationships/translation lineage, object body/custody, and all pending/accepted event owners.
- Close each SQL plane before crossing private/network boundaries; recheck original rights afterward.
- Record a **vector of actual local snapshot/commit and queue positions**, not a fabricated universal LSN or SQL004 sequence.
- These observations become a consistent cut only because all relevant writers are fenced and every exception/change is accounted for.

**Exit criterion:** Zero unexplained differences between snapshot and canonical comparison digests.

### Stage 7 — Atomic selector/ownership-generation CAS

**Goal:** One atomic transfer of ownership.

- Only zero unexplained differences allows the CAS.
- Intake resumes through fresh installed new-generation owners, not through an old queued worker's stale role.
- Crash before/after the CAS reconciles actual control receipts read-only; never guesses rollback or replays an uncertain operation.

**Exit criterion:** CAS succeeds exactly once; replacement writers publish with new generation; legacy writers cannot.

### Stage 8 — Rollback path (always available until retirement)

**Goal:** Rollback preserves every post-W accepted event and never blindly replays possibly delivered responses.

- First fence new effects.
- Retain every post-W accepted event / UNKNOWN / provider receipt.
- Recheck current source/privacy permissions.
- Route only to an actually representable reviewed old state.
- Unsupported new facts remain explicitly unavailable/quarantined; no reverse-migration fiction or evidence deletion.

**Exit criterion:** Rollback is proven to preserve post-W events; no lost ACK is replayed.

---

## 4. Invented race matrix (to execute later)

Each row is a named case. The cut is not accepted until every case has a real test in the owned test database or a separately authorized exact-owned store. Provider/storage/Auth observations remain invented fixtures where the real platform cannot be driven.

| # | Case | Scenario | Required behavior | Invalidates cut? |
|---|---|---|---|---|
| R1 | **race** | Pre-pause transaction overlaps pause transition | Transactions serialize on the barrier row. Either both commit under old generation or the later one is refused. No torn state. | No if handled |
| R2 | **pause-arrival** | New write arrives during `pausing` | Durable opaque arrival receipt with stable original arrival id and body hash. Effect claim rejected. Exactly-once retention. | No if retained |
| R3 | **stale-writer** | Old-generation worker tries to publish after generation bump | Same-tx barrier check refuses the write. Transaction aborts. No partial publish. | No if refused |
| R4 | **restart** | Writer process restarts mid-cut | On restart it re-reads barrier+generation before any write. Stale role/generation cannot recover by itself. | No if rechecked |
| R5 | **reinstall** | Whole service reinstalled mid-cut | No hash/idempotency namespace reset. Existing arrival identities and body hashes remain authoritative. New install must read the control row first. | Yes if namespace reset occurs |
| R6 | **latebatch** | Provider batch completes after pause | Result is accepted as an opaque late arrival or recorded UNKNOWN. No automatic replay into new generation. | No if UNKNOWN/queued |
| R7 | **orphan** | Storage upload succeeds but SQL insert fails (or vice versa) | In-flight upload receipt is recorded; orphan removal is attempted and recorded. No object exists without a receipt; no receipt without eventual disposition. | No if accounted |
| R8 | **lostACK** | External dispatch ACK is lost | Status stays UNKNOWN. No resend. Financial/forensic observation may continue read-only. | No if UNKNOWN held |
| R9 | **privacy** | Privacy withdrawal / deletion request during pause or cut | Must remain operational. Executes. Invalidates the candidate comparison boundary. Forces fresh reconciliation. Immutable fact retained. | **Yes — invalidates candidate cut** |
| R10 | **overflow** | Snapshot volume exceeds bounded limits | Snapshot completion is denied. Cut cannot claim `snapshot-reconciled`. Honest overflow report. | **Yes — denies completion** |
| R11 | **missingparticipant** | A family from the census has no active barrier participant | Cut cannot claim completeness. `consistent_boundary_proven=false`. | **Yes — denies completion** |
| R12 | **unknownrole** | A DB role writes that is not in the admitted role set | Write refused. Census must account for the role or the cut is incomplete. | **Yes if unaccounted** |
| R13 | **crashrollback** | Controller crashes after catch-up before CAS, or CAS succeeds but ACK is lost | Reconcile actual control receipts read-only. Never guess. No replay of uncertain operation. Manual/owner decision required if state is ambiguous. | No if reconciled honestly |
| R14 | **cohort** | Browser cohort routing during cut (real browser proof required for S15) | Each cohort member's writes either land in the queue or are refused. No silent bypass via direct browser Supabase client (typing indicators!). | Yes if bypass observed |
| R15 | **stop** | Independently bounded safety STOP during any phase | STOP executes. Cut is invalidated. Fresh reconciliation required. | **Yes — invalidates candidate cut** |
| R16 | **security-denial** | Security denial during any phase | Denial executes. Cut is invalidated. Fresh reconciliation required. | **Yes — invalidates candidate cut** |
| R17 | **rollingback-phase** | Rollback begins and a new write arrives | New effects fenced. Arrival goes to queue or is refused. Post-W accepted events retained. | No if fenced |
| R18 | **concurrent-pause-CAS** | Two controllers attempt pause or CAS simultaneously | Exactly one winner. Loser observes CAS failure and must re-read. | No if single winner |
| R19 | **generation-mismatch-restart** | Worker restarts and reads a generation that changed during downtime | Worker must re-admit; cannot continue on cached generation. | No if re-admitted |
| R20 | **cohort-acceptance** | Required cohort acceptance suite (currently absent) | Must exist and pass before S15. Proves real browser routing, not API-only. | **Yes — suite absent today** |

---

## 5. Relationship to existing controls (do not weaken)

| Existing control | Role in this design | Must not |
|---|---|---|
| SQL004 `004_workflow_integrity.sql:75` | Fences **serving selector only**. Explicitly: "Fence the serving selector, never source ingestion. Existing writes remain enabled." | Be treated as an ingestion pause |
| `operating_model/cutover.py` selector CAS / watermark replay refusal | Serving compatibility control | Be treated as source-writer freeze (line 39 says no source writer is frozen) |
| `retirement.require_no_legacy_activation` | Always denies proposed new legacy activation | Be assumed to have operational call sites (none found) |
| 014 reserve/finalize/withdraw source revision CAS | Local source custody and idempotency | Be replaced by an adoption guard |
| 020 capture/normalization/queue claim/receipt | Local durable guards | Be assumed to provide a global writer fence |
| 021 participation host generation | Participation host control only | Be assumed to cover legacy or corpus ownership |
| 024 question-effect advisory lock | Local semantic identity | Be assumed to provide a cut epoch |
| 025 compiler registration / personal CAS | Local command identity | Be assumed to be a company action or adoption authority |
| 026 recovery census SHARE locks | Bounded metadata transaction | Be assumed to span the later snapshot/native phase |
| 027 migration reader readonly snapshot | Finite technical source reader | Be assumed to be an all-writer watermark |
| `packages/db/src/client.ts` cached clients | Shared transport | Be assumed to enforce a barrier by wrapping alone |
| `maxAttempts:1` on workers | Local policy | Be assumed to prove a different queued job cannot act |

---

## 6. Concrete missing implementation (blockers for the real cut)

1. No local legacy-source write barrier (same-tx generation check) at any confirmed writer.
2. No object/all-credential fence for Storage/external effects.
3. No actual installed writer/schedule/directSQL/bypass-role census (the incomplete F9 class).
4. No common durable pause arrival queue across legacy paths.
5. No global generation guard in 020–027 or legacy mutators.
6. No provider/graph fully-drained evidence.
7. No full-source current canonical union proof.
8. No S15 cohort flow (`apps/web/tests/oracle2/cohort.spec.ts` is absent).
9. No actual company cutover/release/employee/business authority.
10. `retirement.require_no_legacy_activation` has no operational call sites.

---

## 7. Invented proof requirements (for later execution)

Invented proof must use genuine full current source/review/gates and separately authorized exact-owned stores only. It must show:

- Writes arriving at pause are retained once.
- Pre-pause transaction races serialize or refuse publication.
- Cached clients / old workers / restarts / reinstalls cannot publish with old generation.
- Concurrent pause/CAS has one winner.
- Each scheduled/webhook/batch completion family participates.
- Interrupted upload/object orphan and private-byte hash remains exact.
- Provider lostACK stays UNKNOWN / no resend.
- Custody / current permission / deletion / review change invalidates the comparison.
- Snapshot overflow / missingparticipant / unknownrole denies completion.
- Crash after catch-up before transfer and lost transferACK reconcile read-only.
- Rollback preserves all post-W accepted events and privacy denials.
- Real owned SQL role denial / trigger coverage.
- Actual queue/process descendants and fixed mTLS/HTTP effects.
- Provider/storage/Auth observations remain invented fixtures.

Source-only invented success, if later proved, still cannot authorize company shadow, cutover, adoption observation, or parent completion.

---

## 8. Remaining gate

**Business-acceptance hold remains.** Real comparison/cutover/adoption/non-use/retention/removal stays held. This design and inventory are technical prerequisites for S14; they are not acceptance. Only after every race-matrix case is proved and every missing implementation above is closed may the precise separate business permission question be consolidated. No deletion or parent closure before every required outcome is really proved.

---

## 9. Source references

- Handoff: `HANDOFF.d/2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md` §3.11, §6.10
- Prior audit: `writer-cut-audit-v2.md` (on closeout tree `d02425248e9e033a79a3b80d3b2f8fd0091cd725`) — 123 candidate files / 662 lexical sites
- Ownership correction: `writer-cut-ownership-correction-manifest.json` (same tree)
- Task router: `docs/agents/07-task-to-file-navigation.md`
- Data model: `docs/agents/08-data-model-and-external-identifiers.md`
- Deployment/release: `docs/agents/13-deployment.md`
