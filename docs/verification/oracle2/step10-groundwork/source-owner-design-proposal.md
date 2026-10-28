# Canonical Source-Owner Design Proposal — writer-consistent cut

**Status: PENDING ROOT DECISION — draft proposal only, not implemented, not approved**
**Parent:** #24 · **Closeout step:** §6.10 groundwork · **Date:** 2026-10-27 EDT
**Companion:** `writer-inventory.md` (same directory) · `s14-writer-cut/writer-cut-source-owner-design.md` (PR #199, earlier draft)

> **This document is a design proposal awaiting root coordinator decision. It authorizes nothing. No implementation, no schema change, no production action, no business acceptance is granted by this document.** The design decision belongs to the coordinator (root). This document produces evidence and a draft proposal only.

## 1. Problem statement

The current operating model has 131 identified write sites across 10 families (see `writer-inventory.md`). No global writer-consistent cut exists. The closeout (§3.11) identifies the required capability: "real local SQL barriers + external participants/queue/drain/reconcile/CAS/rollback." The gate standard is "no missing implementation/placeholder/unregistered case or unexplained reconciliation difference."

**Owner ruling 2026-10-27:** The S14 legacy-vs-Oracle company comparison is CANCELLED ("we don't need to compare to the old one. we know that one didn't work. We need to treat this as brand new"). What remains are the technical structural obligations only. This design does NOT propose any comparison against the old Oracle.

## 2. Core design: single durable cut-control owner

Extend the **SAME durable release-selector CAS** (existing `operating_model/cutover.py` selector infrastructure) with a cut-control state machine.

### 2.1 Control state machine

```
legacy-active → pausing → drained → snapshot-reconciled → replacement-active
                    ↘ ABORTED / UNKNOWN / rolling-back ↺
```

Each transition is CAS on exact prior generation. Fields:

| Field | Purpose |
|---|---|
| release manifest / workspace | Pins the cut to a specific release |
| current controller admission | Only the admitted controller drives transitions |
| old ingestion generation | Generation every legacy writer must present |
| new ingestion generation | Generation replacement writers will use |
| writer-census digest | Immutable SHA-256 of the adjudicated writer list |
| phase | Current state-machine position |
| pause-start evidence | Monotonic + wall timestamps |
| queue coverage | Which ingress families are covered |
| snapshot/canonical digests | For reconciliation comparison |

### 2.2 Enforcement model

**Local barrier, not advisory lock.** Every confirmed SQL writer checks barrier+generation **in the same transaction** as its mutation. A stale generation aborts the transaction. Independent role admission: the writer's DB role and generation must both be admitted (prevents self-stamp). No advisory-only / GUC / self-stamp grant.

**FalkorDB writes** (`graph/falkor.py`, `graph/graphrag.py`) cannot be fenced by a PostgreSQL barrier. They need a separate graph-generation check or must be routed through an effect owner that participates in the cut.

**External writers** (Supabase Auth, Storage, GCS, Recall, Vertex) require explicit participant registration. Uncontrolled external writer = incomplete cut.

## 3. Stages

### Stage 0 — Writer census adjudication (prerequisite)

Convert the inventory into an adjudicated confirmed/candidate/excluded census with a stable digest. Unknown sites block the census digest. Produce `writer-census-digest` = SHA-256 of canonical sorted confirmed-writer list.

**Exit:** Every site classified; digest stable; zero unknown writers.

### Stage 1 — Single durable cut-control owner

One control row per (release, workspace). API: `begin_pause`, `mark_drained`, `record_snapshot`, `activate_replacement`, `begin_rollback`, `abort`. Each is CAS on exact prior generation. Controller admission in a separate table.

**Exit:** Control row exists; CAS transitions tested; stale-generation controller refused.

### Stage 2 — Local barrier + generation at every confirmed SQL writer

Install `assert_admitted(tx, expected_generation)` guard at each confirmed writer from the inventory. Cover F1–F6, F8. F7 replacement/pilot routes are inventoried but not activated.

**Exit:** Synthetic stale-generation writer cannot publish; correct-generation writer can.

### Stage 3 — Storage and external effect owners

Storage upload/remove: wrap in effect owner (a) checks barrier+generation before object op, (b) records in-flight upload receipt, (c) commits SQL metadata only after object success, (d) records orphan removal. External dispatch (Recall, Vertex, GCS): outbound intent before call, receipt after. LostACK stays UNKNOWN; no resend. FalkorDB writes: separate graph-generation check or effect owner.

**Exit:** Upload during `pausing` is durably accepted as opaque arrival; no orphan object without receipt.

### Stage 4 — Durable pause arrival queue

One queue per ingress family (documents, messages, Teams/live, import, extraction). Arrival record: original arrival id, body hash, family, received-at, status. Resume requires fresh permissions and one globally retained ownership decision per arrival. No hash/idempotency namespace reset across reinstall/generation/rollback.

**Exit:** Concurrent arrivals during pause retained exactly once; replay individually authorized.

### Stage 5 — Drain started writers

Inventory of started process/task/lease/provider operation IDs. Wait for each to reach terminal state or mark UNKNOWN. UNKNOWN blocks `drained`. Queue depth alone is insufficient.

**Exit:** Every started writer terminal or UNKNOWN; zero UNKNOWN to claim drained.

### Stage 6 — Bounded full snapshot and reconciliation

Snapshot rows, permissions, approval/translation lineage, object bodies, pending events. Close each SQL plane before crossing private/network boundaries. Record a **vector of local snapshot/commit and queue positions**, not a fabricated universal LSN.

**Exit:** Zero unexplained differences between snapshot and canonical digests.

### Stage 7 — Atomic selector/ownership-generation CAS

Only zero unexplained differences allows the CAS. Intake resumes through fresh new-generation owners. Crash before/after CAS reconciles read-only; never guesses rollback.

**Exit:** CAS succeeds exactly once; replacement writers publish with new generation.

### Stage 8 — Rollback path

Fence new effects. Retain every post-W accepted event / UNKNOWN / provider receipt. Recheck current permissions. Route only to representable reviewed old state. No reverse-migration fiction.

**Exit:** Rollback preserves post-W events; no lostACK replayed.

## 4. Open questions and trade-offs (for root decision)

### Q1: FalkorDB barrier mechanism

**Trade-off:** PostgreSQL advisory locks cannot fence FalkorDB writes. Options: (a) route all FalkorDB writes through an effect owner that checks the SQL barrier first, (b) install a separate FalkorDB generation key checked at each graph mutation, (c) accept FalkorDB as reconstructible (rebuild from SQL snapshot) and fence only SQL. Option (c) is simplest but requires proving rebuildability. **Root decision needed.**

### Q2: Browser Supabase client (typing_indicators)

**Trade-off:** `channel-chat.tsx:180,189` writes `typing_indicators` directly from the browser via Supabase client. This bypasses any server-side barrier. Options: (a) route through a server API endpoint, (b) declare typing_indicators as ephemeral/non-authoritative and exclude from the cut, (c) install a Supabase RLS policy that checks a generation column. Option (b) is simplest if typing indicators have no durable authority. **Root decision needed.**

### Q3: Cached Drizzle client wrapping

**Trade-off:** `packages/db/src/client.ts` exports cached clients used everywhere. Options: (a) install barrier at each call site (131 sites), (b) wrap the cached client itself with a barrier check (but this violates "barrier must be at the mutation, not the transport"), (c) use PostgreSQL row-level security or a session variable checked by a trigger. Option (a) is the design's stated approach but is invasive. **Root decision needed on whether (c) is acceptable as an alternative.**

### Q4: Script/CLI writers (F9)

**Trade-off:** Scripts like `seed_hosted_preview.py`, `migrate_workflow_integrity.py`, `resource_experiment.py` write to SQL but are not part of the online serving path. Options: (a) register them as participants and require barrier checks, (b) classify them as offline-only and exclude from the cut (but then they must be proven to not run during the cut window), (c) require explicit manual admission per run. **Root decision needed.**

### Q5: Snapshot overflow policy

**Trade-off:** If snapshot volume exceeds bounded limits, the design says "snapshot completion is denied." But the cut is already in `pausing` at that point. Options: (a) abort and rollback, (b) extend bounds with explicit owner approval, (c) partition the snapshot. **Root decision needed.**

### Q6: Rollback representability

**Trade-off:** "Route only to an actually representable reviewed old state." But the brand-new ruling means there is no old Oracle state to roll back to. Rollback within the new system means: fence new effects, retain accepted events, return to `legacy-active` generation. But if the new system has no pre-cut state (brand new), rollback means "stop the cut and continue with old generation." **Root decision needed on what "old state" means for a brand-new system.**

## 5. Invented race / proof matrix (to execute later)

Each case requires a real test in the owned test database or a separately authorized exact-owned store. Provider/storage/Auth observations remain invented fixtures where the real platform cannot be driven.

| # | Case | Scenario | Required behavior | Invalidates cut? | Status |
|---|---|---|---|---|---|
| R1 | race | Pre-pause tx overlaps pause transition | Serialize on barrier row; no torn state | No if handled | not-started |
| R2 | pause-arrival | New write during `pausing` | Durable opaque arrival receipt, exactly-once | No if retained | not-started |
| R3 | stale-writer | Old-gen worker publishes after gen bump | Same-tx barrier refuses; abort | No if refused | not-started |
| R4 | restart | Writer restarts mid-cut | Re-reads barrier+gen before write | No if rechecked | not-started |
| R5 | reinstall | Service reinstalled mid-cut | No namespace reset; identities authoritative | **Yes if reset** | not-started |
| R6 | latebatch | Provider batch completes after pause | Opaque late arrival or UNKNOWN | No if UNKNOWN | not-started |
| R7 | orphan | Upload succeeds, SQL fails (or vice versa) | In-flight receipt; orphan removal recorded | No if accounted | not-started |
| R8 | lostACK | External dispatch ACK lost | Status UNKNOWN; no resend | No if UNKNOWN | not-started |
| R9 | privacy | Privacy withdrawal during pause/cut | Must execute; invalidates candidate cut | **Yes** | not-started |
| R10 | overflow | Snapshot exceeds bounded limits | Completion denied; honest overflow report | **Yes** | not-started |
| R11 | missingparticipant | Family has no active barrier participant | `consistent_boundary_proven=false` | **Yes** | not-started |
| R12 | unknownrole | Unadmitted DB role writes | Write refused; census must account | **Yes if unaccounted** | not-started |
| R13 | crashrollback | Controller crashes before/after CAS | Read-only reconcile; no replay | No if reconciled | not-started |
| R14 | cohort | Browser cohort routing during cut | No silent bypass (typing_indicators!) | **Yes if bypass** | not-started |
| R15 | stop | Safety STOP during any phase | STOP executes; cut invalidated | **Yes** | not-started |
| R16 | security-denial | Security denial during any phase | Denial executes; cut invalidated | **Yes** | not-started |
| R17 | rollingback-phase | Rollback begins, new write arrives | New effects fenced; arrival queued | No if fenced | not-started |
| R18 | concurrent-pause-CAS | Two controllers attempt CAS | Exactly one winner | No if single winner | not-started |
| R19 | generation-mismatch-restart | Worker restarts with changed gen | Must re-admit | No if re-admitted | not-started |
| R20 | cohort-acceptance | Required cohort suite (absent) | Must exist and pass before S15 | **Yes — suite absent** | not-started |

## 6. Missing implementation (blockers)

1. No local legacy-source write barrier (same-tx generation check) at any confirmed writer.
2. No object/all-credential fence for Storage/external effects.
3. No actual installed writer/schedule/directSQL/bypass-role census (incomplete F9/F10 classes).
4. No common durable pause arrival queue across legacy paths.
5. No global generation guard in 020–027 or legacy mutators.
6. No provider/graph fully-drained evidence.
7. No full-source current canonical union proof.
8. No S15 cohort flow (`apps/web/tests/oracle2/cohort.spec.ts` is absent).
9. No FalkorDB barrier mechanism (Q1 unresolved).
10. No browser-client bypass resolution (Q2 unresolved).
11. `retirement.require_no_legacy_activation` has no operational call sites.

## 7. Relationship to existing controls (do not weaken)

See `writer-inventory.md` "Existing controls that do NOT constitute a global writer fence" table. The design extends, not replaces, the existing release-selector CAS. SQL004 continues to fence serving selector only. The 014–027 local guards remain as-is.

## 8. What this design does NOT do

- Does NOT implement anything.
- Does NOT authorize company comparison, cutover, adoption, non-use, retirement, or removal.
- Does NOT propose comparison against the old Oracle (cancelled per owner ruling 2026-10-27).
- Does NOT invent business metrics. The prior test/exercise figures (1.275s / 0.0s / 1.511s RTO/RPO) are **test/exercise only** and must never be presented as production figures.
- Does NOT create a POP shared-db claim. Legacy Oracle Supabase "theoracle" is Oracle-owned.
- Does NOT ask Albert any question. All open questions are technical decisions for the root coordinator.

## 9. Source references

- Writer inventory: `writer-inventory.md` (same directory)
- Closeout §3.11: `HANDOFF.d/2026-10-22T1211Z-edge-dev3-codex-parent24-closeout.md`
- Closeout §6.10: same file, step 10 gate
- Earlier design draft: `s14-writer-cut/writer-cut-source-owner-design.md` (PR #199)
- Earlier inventory JSON: `s14-writer-cut/writer-cut-complete-inventory.json` (PR #199)
- Owner ruling: `plan_oracle_consultant_overhaul.md` STATUS, 2026-10-27
- Prior audit: `writer-cut-audit-v2.md` (closeout tree `d0242524`)
