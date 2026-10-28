# Design-question options analysis — Q1–Q6 for the writer-consistent cut

**Status: ANALYSIS ONLY — options and trade-offs for the root coordinator's decision. No decision is made here. Nothing is implemented. Nothing is authorized.**
**Parent:** #24 · **Closeout step:** §6.10 groundwork · **Date:** 2026-10-27 EDT
**Companions:** `source-owner-design-proposal.md` (§4 Q1–Q6, same directory) · `writer-inventory.md` (same directory) · `qualification-census-test-matrix.md` (same directory)
**Base:** main `3555dba4` (docs merged on main) · **Method:** read-only inspection of the cited writer sites plus the existing controls they build on

> The design decision belongs to the root coordinator. Each "RECOMMENDED" line below is a
> recommendation with reasoning, not a decision, not an approval, and not implementation
> authority. Every proof sketch is **invented/synthetic only**; no live or production claim is
> made anywhere in this document.

---

## 0. Standing constraints this analysis is checked against

These bind every option below. Section 7 at the end names any conflict explicitly.

| # | Constraint | Source |
|---|---|---|
| C-a | **W10 SAME budget/shape never weakened**: complete mandatory population, ten workers, unchanged 120-second ceiling, zero error/skip/timeout/launch/cleanup | `plan_oracle_consultant_overhaul.md` W10 rows; `qualification-census-test-matrix.md` Part C |
| C-b | **Sealed SQL 017/025 fail-closed unchanged**: `017_processing_model_history.sql` sealed identity (`:690-697`, `RAISE insufficient_privilege ... 'bounded sealed workflow identity required'`) and `025_recommendation_actions.sql` immutable-deny triggers (`:49-54`) + `_processing_immutable_artifact_metadata_v1` stay exactly as they are | task constraints; source inspection |
| C-c | **UNKNOWN is never drained/done**: no option may resolve an UNKNOWN by assumption | design §2 Stage 5/8; task constraints |
| C-d | **No assertion weakening / existing controls not replaced**: SQL004 stays serving-only; 014–027 local guards stay as-is; no advisory-only / GUC / self-stamp grant | design §2.2/§7; `writer-inventory.md` "Existing controls that do NOT constitute a global writer fence" |
| C-e | **No production writes; synthetic proofs only** | task constraints |
| C-f | **No POP shared-db; no company originals; no production RTO/RPO claims** (the 1.275s/0.0s/1.511s figures are test/exercise only and are not quoted here as anything else) | task constraints; `qualification-census-test-matrix.md` Part G |
| C-g | Any new SQL lives in the Oracle-owned legacy-source schema under its **applicable reviewed migration route** (no live-edit, no unreviewed DDL) | AGENTS.md §13; design §2.2 |

---

## Q1 — FalkorDB barrier: what mechanism fences graph writes for a writer-consistent cut?

### Evidence read

- `services/oracle-brain/oracle_brain/graph/falkor.py:28-55` — `project`/`withdraw` are pure projections of `(assertion_id, revision, payload)` onto `Assertion` nodes (docstring: "Confirmed graph projection, partitioned by workspace and revision").
- `services/oracle-brain/oracle_brain/graph/falkor.py:57-69` — `rebuild` does `MATCH (n) DETACH DELETE n` then re-projects an accepted list; a full rebuild path already exists.
- `services/oracle-brain/oracle_brain/graph/graphrag.py:327-351` — `build()` writes `Document`/`HolisticSnapshot` nodes (`SET d.original_hash…` at `:342`, `MERGE (s:HolisticSnapshot) SET s.finalized=true` at `:351`); "Published snapshots are immutable; partial attempts require a new config generation, preserving the failed graph as recovery evidence"; `verify_documents()` (`:365+`) checks graph content hashes against the complete corpus; `load_reviewed_snapshot()` (`:377-383`) requires a matching finalized snapshot.
- `services/oracle-brain/oracle_brain/graph/base.py:10-18` — the store interface already abstracts `project`/`rebuild`; `graph/projector_cli.py:26-28` drives projection from an event list, confirming the projection model.
- Inventory rows F8-30 (`graph/falkor.py:33-67`) and F8-31 (`graph/graphrag.py:342,351`) mark both "cannot be fenced by SQL barrier; need separate graph barrier".

### Options

**Q1-A — SQL-gated effect owner (route every graph write through one owner that checks the SQL barrier first).**
Mechanism: introduce a single Python effect owner (e.g. alongside `graph/base.py` or as an `operating_model/` module) that, for each graph mutation, (i) opens the same SQL transaction context the Stage 2 guard uses (`assert_admitted(tx, expected_generation)`), (ii) records an outbox intent row reusing the existing `oracle_brain/outbox.py` pattern (F8-4, 16 sites already write `outbox_events`), (iii) issues the FalkorDB query (`falkor.py:34` / `:52` / `:66`, `graphrag.py:342,351`), (iv) records a receipt. `projector_cli.py:26-28` and `graphrag.build()` call sites are rerouted through this owner.
Trade-offs: correctness — fences graph writes to the SQL generation with a two-phase intent/receipt, so a crash between (iii) and (iv) leaves an in-doubt write that must stay UNKNOWN (C-c); blast radius — all graph call sites, Python-only, no new SQL store; cost — medium; failure modes — in-doubt writes, double-apply on naive retry (mitigated by intent idempotency keys and the no-resend rule of R8).
Builds on: F8-4 `outbox.py`, inventory F8-30/F8-31 "cut fence" column, design Stage 3 effect-owner pattern.

**Q1-B — Graph-local generation key (check-and-set a cut epoch inside the graph).**
Mechanism: a `CutEpoch {generation}` node/property per `oracle2_<workspace>` graph; each mutation query matches `WHERE e.generation = $gen` and aborts otherwise; optional FalkorDB/Redis-side key.
Trade-offs: correctness — **weak**; `graph.query()` calls in `falkor.py`/`graphrag.py` are standalone queries with no cross-store atomicity against the PostgreSQL barrier, so the graph epoch can drift from the SQL generation (e.g. SQL generation bumps, epoch write fails). Blast radius — small code (inside `falkor.py`), large semantic risk; cost — low; failure modes — epoch drift, multi-query flows (a `graphrag.build()` ingest is dozens of queries) with no atomicity.
Conflicts: design §2.2 ("No advisory-only / GUC / self-stamp grant") and C-d — a self-checked graph key is the graph-side equivalent of a self-stamp. **Named conflict; see §7.**

**Q1-C — Reconstructible projection (fence SQL only; treat the graph as derived state rebuilt and digest-verified after the cut).**
Mechanism: the cut fences SQL writers only (Stage 2). Stage 6 reconciliation adds a **graph digest** = canonical sorted hash over `(assertion_id, revision, sha256(payload))` for `Assertion` nodes and `(node id, content_hash)` for GraphRAG nodes. The digest is compared against a rebuild output: `FalkorGraphStore.rebuild(workspace, accepted)` (`falkor.py:64-69`) fed from the SQL snapshot's accepted claims, and `load_reviewed_snapshot()` (`graphrag.py:377-383`) + `verify_documents()` for the GraphRAG half. Any graph write that occurred without a matching SQL row shows up as a digest difference and blocks the CAS (never "assumed fine").
Trade-offs: correctness — exact for the `Assertion` projection (payload originates in SQL claims; `projector_cli.py:26-28` replays from events). For the GraphRAG half, rebuild must not re-run extraction non-deterministically; the design already retains finalized immutable snapshots ("published snapshots are immutable", `graphrag.py:327`) and `verify_documents()` pins content hashes, so the retained snapshot is the rebuild source. Blast radius — zero runtime write-path changes; cost — low/medium (digest + determinism proof); failure modes — rebuild non-determinism (mitigated by retained snapshots, not re-extraction), and the semantic requirement that the graph is **never authoritative** (only a projection) — that must be an explicit adjudicated claim in the Stage 0 census.
Builds on: `falkor.py` `rebuild`, `graphrag.py` `verify_documents`/`load_reviewed_snapshot`, W03's "GraphRAG ingest/finalize/reload/rebuild" obligation.

**Q1-D — Hybrid: Q1-A as the operational fence during the window + Q1-C as the reconciliation authority.**
Mechanism: both of the above; the effect owner keeps mid-cut discipline and receipts, and the rebuild digest is what the Stage 6 comparison actually trusts.
Trade-offs: correctness — strongest; blast radius/cost — sum of A and C; failure modes — the same in-doubt UNKNOWN surface as A, plus C's determinism proof.

### RECOMMENDED (recommendation, not a decision)

**Q1-C**, with **Q1-D** as the upgrade path if a consumer proves it needs mid-cut graph consistency.
Reasoning: the code already models the graph as a projection (`falkor.py` docstring + `rebuild` + `verify_documents` + immutable retained snapshots), so C delivers a fenced, reconcilable cut without inventing a second barrier protocol or an in-doubt window; A is valuable but its intent/receipt machinery is only worth its UNKNOWN surface if the graph turns out to be read-authoritative mid-cut; B conflicts with C-d (see §7).

### Evidence that would confirm the choice (invented/synthetic only)

1. Synthetic determinism: seed N accepted claims in the owned test SQL store, project into graph W1, `rebuild` into graph W2 from the SQL snapshot's accepted list, compare canonical digests → equal.
2. Synthetic mid-cut stray write: inject a graph mutation with no SQL counterpart during synthetic `pausing`; after the cut the rebuild digest differs from the pre-stray digest and from the SQL-derived digest → the difference is reported and the CAS is denied (never silently accepted).
3. Synthetic GraphRAG reload: finalize a synthetic corpus snapshot → digest; `load_reviewed_snapshot` → same digest; `verify_documents` passes on the retained content hashes (no re-extraction).
All fixtures invented; no production graph is read or written.

---

## Q2 — Browser bypass: how is `typing_indicators` closed without breaking live chat UX?

### Evidence read

- `apps/web/app/channels/[channelId]/_components/channel-chat.tsx:169-195` — `broadcastTyping` (the inventory cites `:180,189`) upserts `typing_indicators` at `:180` and deletes at `:188-189` through the **browser Supabase client**; rows carry `expires_at = now + 5s`. The comment at `:169-171` states the rows exist "for server-side lull-interjection worker, which can't subscribe to a Realtime WebSocket" — i.e. the table is read by `apps/workers/src/trigger/lull-interjection.ts` (see `:27`, "Typing presence is live through short-lived `typing_indicators` heartbeats").
- The same component already routes the durable write (`sendMessage`) through `/api/messages` with the explicit comment "Route through the server API so the insert uses the service-role connection (DIRECT_URL) and server-side session validation" — a working precedent for server routing (`apps/web/app/api/messages/route.ts:76`, inventory F1-1).
- Supabase Realtime presence (`presenceChannel.track`) is not a database write and is out of scope for the SQL cut.
- Inventory: F1-3 (external bypass), F10-6 ("Must be routed through server or explicitly declared"), design R14 ("No silent bypass (typing_indicators!)"; invalidates the cut if bypass observed).

### Options

**Q2-A — Route typing writes through a server API endpoint.**
Mechanism: add `apps/web/app/api/typing/route.ts` mirroring the `/api/messages` pattern (`apps/web/app/api/messages/route.ts:76`); `broadcastTyping` calls `fetch('/api/typing', …)` instead of `supabase.from('typing_indicators')…` (`channel-chat.tsx:180,188`); the endpoint performs the upsert/delete under the normal Stage 2 same-tx guard. Debounce, 5-second expiry, and the Realtime presence channel are untouched.
Trade-offs: correctness — the write becomes an ordinary fenced SQL writer (F1-1 shape), closing R14 completely; blast radius — one component function + one new route; UX — unchanged semantics, one extra HTTP hop on a non-critical, debounced signal; cost — low; failure modes — if the route is unavailable, typing indicators stop (advisory signal degrades, chat itself unaffected).
Builds on: F1-1 server-route pattern, the component's own server-routing rationale.

**Q2-B — Declare `typing_indicators` ephemeral/non-authoritative and exclude it from the cut.**
Mechanism: Stage 0 census marks the table excluded (self-expiring 5s rows; heuristic consumer only), and the runbook claims no durable authority.
Trade-offs: correctness — **partial and risky**; exclusion is not fencing. If the browser keeps writing during `pausing`, R14's "no silent bypass" fails and `consistent_boundary_proven` must stay false. Additionally, lull-interjection reads the table and its decisions become durable (`oracleInterventions`, F6-4), so "no durable authority" is not strictly true — the table influences durable output. Blast radius — near zero code; cost — very low; failure modes — exactly the R14 invalidation mode.
Conflicts: C-d / design §2.2 ("Uncontrolled external writer = incomplete cut") if exclusion is claimed as closure without a hard stop. **Named conflict; see §7.**

**Q2-C — Supabase RLS policy that denies writes outside admitted phases (proposal option (c)).**
Mechanism: an RLS policy on `typing_indicators` (Oracle-owned Supabase `theoracle`) reads cut state through a `security definer` helper and denies browser-role writes whenever the phase is not an admitting phase; the browser client code can stay as-is and simply stop receiving writes during the window.
Trade-offs: correctness — enforced at the platform boundary (the browser cannot bypass RLS); blast radius — a managed-platform policy change on the Oracle-owned Supabase project (C-g applies: reviewed migration route), and it generalizes to any other direct-browser table (notably the open candidate `apps/web/app/admin/settings/model-pool/_components/model-pool-editor.tsx:2`, F5-9 "verify if server action or direct Supabase"); cost — medium; failure modes — a fail-open policy would be worse than none (must be fail-closed), and policy bugs only degrade typing (benign).
Builds on: F10-6 external-participant registration.

**Q2-D — Q2-A as the normal path + Q2-C as the fail-closed backstop.**
Mechanism: both; the route is how typing is written, RLS is what refuses anything else (including the F5-9-class client-component writes the census has not yet adjudicated).
Trade-offs: correctness — strongest; blast radius — A + C; cost — medium; failure modes — the union of both, none new.

### RECOMMENDED (recommendation, not a decision)

**Q2-A** now; add **Q2-C** in the same stage if the F5-9 adjudication confirms another direct-browser table exists (then Q2-D is the end state).
Reasoning: A is the smallest change that converts the bypass into a normal fenced writer using a pattern the file already uses, keeps the UX identical, and avoids a "non-authoritative" claim the lull-interjection consumer contradicts. C is the right backstop but is a managed-platform change and earns its cost best if it covers more than one table.

### Evidence that would confirm the choice (invented/synthetic only)

1. Synthetic browser fixture (this belongs in the absent cohort suite `apps/web/tests/oracle2/cohort.spec.ts`, R20's home): during a synthetic `pausing` phase, typing events reach `/api/typing` and are queued/refused with an arrival receipt or a refusal status — no direct row write occurs.
2. Synthetic direct-Supabase attempt (simulating an old client build): with Q2-C, the write is denied by RLS; with A alone, the census must show the client version that still writes directly is not in the cohort (otherwise the cut claim stays incomplete — honest, not silent).
3. UX non-regression: debounce + 5s expiry + presence tracking behave identically when the route is healthy; lull-interjection still reads heartbeats while the system is in an admitting phase.
All fixtures invented.

---

## Q3 — Cached Drizzle clients: how are they wrapped/invalidated across a generation fence?

### Evidence read

- `packages/db/src/client.ts:22-24` — module-level `directDb`/`pooledDb` singletons, lazily built and cached for the process lifetime (`:36` `getDirectDb`, `:49` `getPooledDb`); both `max: 1` connections; pure transport.
- Inventory F6-16: "Cached clients wrap all DB access; **barrier must be at each call site, not in the client**"; the existing-controls table: cached Drizzle clients "Must not be assumed to enforce barrier by wrapping alone".
- Design §2.2: the guard is `assert_admitted(tx, expected_generation)` **in the same transaction** as the mutation; stale generation aborts the transaction; role + generation both admitted (no self-stamp).

### Options

**Q3-A — Barrier at each mutation call site (the design's stated approach).**
Mechanism: at each of the 111 confirmed sites (F1–F6, F8 per Stage 2), the mutation transaction calls `assert_admitted(tx, gen)` which **re-reads the control row in-transaction** (`SELECT … FROM cut_control … FOR SHARE`, the same shape `operating_model/cutover.py:33-34` already uses with `pg_advisory_xact_lock` + `SELECT generation … FOR UPDATE`). Nothing about the generation is cached in `client.ts` or in process state; the cached client stays pure transport, so there is nothing to invalidate.
Trade-offs: correctness — strongest for C-d (same-tx, R3/R4/R19 satisfied by re-reading, not by cache invalidation); blast radius — 111 sites, large but mechanical and already enumerated with per-row fence notes in `writer-inventory.md`; cost — high (call-site audit + guard insertion + Stage 0 adjudication of the 7 candidates first); failure modes — a missed site is an unaccounted writer (R12) → mitigated by the Q3-C backstop below.
Builds on: the inventory's per-row "Same-tx barrier check" column; `cutover.py`'s existing CAS read pattern.

**Q3-B — Wrap the cached client itself with a barrier check (proposal option (b), analyzed and rejected upstream).**
Mechanism: `getDirectDb()`/`getPooledDb()` return a proxy whose query execution pre-checks generation.
Trade-offs: correctness — **weak**; the check runs outside the mutation's transaction (TOCTOU: check passes, fence moves, stale tx commits) and cannot reliably distinguish reads from mutations at the transport layer. Blast radius — small code, large semantic risk; cost — low; failure modes — false confidence, trivially bypassed by importing `postgres` directly (as `scripts/oracle2/*.py` already do via raw `psycopg`).
Conflicts: design §2.2 ("barrier must be at the mutation, not the transport") and C-d. **Named conflict; see §7.**

**Q3-C — PostgreSQL-side enforcement (session variable / trigger / RLS), proposal option (c).**
Mechanism: a `BEFORE INSERT OR UPDATE OR DELETE` trigger per writer table (installed in the reviewed SQL migration route, C-g) that reads the in-transaction control state and raises on stale generation or a fencing phase; alternatively RLS policies. This is the same enforcement family as the existing `deny_operating_model_mutation()` (`services/oracle-brain/sql/004_workflow_integrity.sql:42`, already installed across 004/008/017/020/021/025/026/027).
Trade-offs: correctness — strong against missed sites and against uncensused roles (R12), because the database refuses; blast radius — every writer table in the 131-site inventory, plus careful stacking with existing immutable-deny triggers (must not weaken them — C-b); cost — medium/high; failure modes — superuser/owner-role connections can bypass RLS but **not** ordinary triggers unless the role set is constrained (relevant to F9, Q4); trigger overhead must be measured under the unchanged W10 budget (C-a).
Builds on: `deny_operating_model_mutation()` trigger pattern; 014–027 local guards (additive, not replacing).

**Q3-D — Q3-A + Q3-C (call-site guards for same-tx semantics; DB-side backstop for the missed-site/unknown-role failure mode).**
Mechanism: both; and the explicit answer to "how are cached clients invalidated": **they are not — no generation value is ever cached outside the transaction**, so there is nothing to invalidate. The fence is re-read in-tx at the mutation (A) and enforced by the database if a site misses the guard (C).

### RECOMMENDED (recommendation, not a decision)

**Q3-D**, keeping the design's stated approach (A) as the primary mechanism and adding C as enforcement of last resort; explicitly **not** B.
Reasoning: A is the only shape that satisfies "barrier at the mutation in the same transaction"; C closes A's one real failure mode (missed/uncensused writer, R12) without weakening anything; B is forbidden by the design and the existing-controls table. The "cached client" question dissolves once the design rule "never cache generation outside the tx" is stated as an invariant.

### Evidence that would confirm the choice (invented/synthetic only)

1. Synthetic stale-writer (R3/R19): a process holds a cached `getDirectDb()` instance, reads generation 1, the control bumps to 2, the writer attempts a mutation presenting 1 → same-tx guard aborts, nothing publishes (including no partial multi-statement publish).
2. Synthetic missed-site backstop (R12): the same mutation with the call-site guard deliberately omitted → the DB-side trigger refuses; the census role set accounts for the role or the cut claim stays incomplete.
3. W10 non-regression (C-a): a synthetic W10-shaped run (complete mandatory population, ten workers, **unchanged** 120-second ceiling, zero error/skip/timeout/launch/cleanup) with guards and triggers enabled stays green; if it cannot, the option is not viable as-is and the budget is **not** widened to make it pass.
All fixtures invented.

---

## Q4 — Script/CLI writers (F9): how do they join the cut protocol?

### Evidence read

- `writer-inventory.md` F9-1…F9-13: 13 rows (8 confirmed, 5 candidates), plus F3-8 `scripts/oracle2/import_original_corpus.py:5 sites` (a CLI writer inside F3).
- Connection pattern is raw and out-of-band: `scripts/oracle2/seed_hosted_preview.py:88-99` does `psycopg.connect(admin_url)` and even `CREATE ROLE …` and applies whole SQL files (`:96-99`) — an owner/superuser-class connection outside service supervision (no Trigger.dev lease, no HTTP handler). `packages/db/src/seed.ts:4 sites` is Drizzle-based. Test-adjacent candidates: `holistic_browser_fixture.py`, `verify_workflow_*.py` (3 files, 29 sites), `resource_experiment.py`, `restore_experiment.py`, `measure-s11-setup-batch-01.py`.
- R12 (unknownrole): "Unadmitted DB role writes → write refused; census must account." R5 (reinstall): "No namespace reset; identities authoritative" — a seed script that re-applies SQL/reset namespaces is exactly this hazard.

### Options

**Q4-A — Register as participants with same-tx barrier checks.**
Mechanism: one shared helper (e.g. `scripts/oracle2/_cut_guard.py`) calling the same `assert_admitted(conn, gen)` in the script's transaction; the script's DB role joins the admitted-role set for the generation; a script run under an unadmitted role is refused (R12).
Trade-offs: correctness — complete fencing even if an operator runs a script during the window; blast radius — the confirmed F9 rows + F3-8; cost — low/medium (one helper, one call per script entrypoint); failure modes — a superuser connection (the `admin_url` pattern) bypasses role admission unless owner roles are explicitly excluded from admission or the Q3-C trigger refuses them; DDL statements (CREATE ROLE / applied SQL files) are not row writes and need the Q6 C4 treatment.

**Q4-B — Classify offline-only and exclude, with a proven no-run window.**
Mechanism: Stage 0 adjudicates F9 test-adjacent rows as test-only/excluded; the runbook asserts no script runs during the window.
Trade-offs: correctness — **discipline-only**, weakest; blast radius — none in code; cost — very low; failure modes — a mid-cut script run is an unaccounted writer (R12) and `seed_hosted_preview.py`-class re-seeding is an R5 namespace-reset risk.
Conflicts: C-d / gate standard ("no missing implementation/placeholder/unregistered case") if exclusion substitutes for enforcement. **Named conflict; see §7.**

**Q4-C — Explicit manual admission per run (run-scoped ticket).**
Mechanism: before a run, the cut controller CAS-records a run admission (run id, script content digest, generation, purpose, expiry) in the Stage 1 control schema; the script presents the admission in-tx (a run-admission row lookup alongside `assert_admitted`); absent/expired → refused.
Trade-offs: correctness — strong traceability, works for authorized maintenance outside cut windows too; blast radius — scripts + controller API; cost — medium; failure modes — replayed/stolen admission (mitigate: pin script digest + expiry + single-use run id).
Builds on: 014 reserve/finalize/withdraw CAS (local custody shape) and the Stage 1 controller-admission table.

**Q4-D — Tiered: Q4-A for confirmed production-adjacent writers; Q4-B only where test-only status is proven by role/schema binding; Q4-C wherever an excluded script can still reach production data.**
Mechanism: F9-1/2/3/12 + F3-8 get the guard (A). F9-4…F9-10 are excluded **only** on proof that their role cannot write production schemas; otherwise they take C. Every disposition is recorded per site in the Stage 0 census digest.

### RECOMMENDED (recommendation, not a decision)

**Q4-D.**
Reasoning: it satisfies Stage 0 ("every site classified") and R12 role accounting without a discipline-only exclusion, and its cost is bounded because all of F9 shares one connection pattern. B alone is not defensible against the gate standard.

### Evidence that would confirm the choice (invented/synthetic only)

1. Synthetic script run during `pausing` with the guard: refused or queued (arrival receipt), no row lands.
2. Synthetic stale-generation script run: transaction aborts; no partial multi-statement publish.
3. Synthetic test-only role attempting a production-schema write: refused (R12) if C is in play; if B is claimed for a site, the proof artifact is the role/schema binding showing the attempt is impossible — not an operator promise.
4. The census digest visibly contains each F9 site's disposition (participant / test-only-excluded / run-scoped).
All fixtures invented.

---

## Q5 — Snapshot overflow: what happens when snapshot/reconcile exceeds its budget or the working set is larger than expected?

### Evidence read

- Design Stage 6: "Bounded full snapshot and reconciliation… Record a **vector of local snapshot/commit and queue positions**, not a fabricated universal LSN"; exit: "Zero unexplained differences"; R10: overflow → "Completion denied; honest overflow report", **invalidates the cut**.
- Existing bounded pattern: `services/oracle-brain/sql/026_operational_recovery.sql:503-515` — "All declared policy tables are SHARE locked in the same bounded transaction" then `txid_current_snapshot()`; `:596` — per-row SHA-256 digest query with `LIMIT 100001 bounded` (an explicit over-limit detection shape); `:658` — "No policy payload/receipt is issued by completeness or snapshot metadata."
- The state machine already has `ABORTED / UNKNOWN / rolling-back ↺` (design §2.1).

### Options

**Q5-A — Deny completion and abort/rollback (the R10 literal).**
Mechanism: `record_snapshot` fails on overflow; the controller CASes `pausing → ABORTED` (or `→ rolling-back` where effects must be fenced first per Stage 8); writers return to the old generation via the same CAS discipline; the overflow report names plane, bound, observed count/digest. Stage 4 queue arrivals are replayed only under fresh per-arrival authorization.
Trade-offs: correctness — exactly R10, no partial success; blast radius — the cut attempt only; cost — low (policy already written); failure modes — repeated aborts if the working set keeps growing (a retry-without-capacity rule is needed), and the rollback itself must satisfy Q6.

**Q5-B — Extend bounds with explicit owner approval (proposal option (b)).**
Mechanism: a CAS admits a new bound + reason + approver; the snapshot resumes or restarts under the new bound.
Trade-offs: correctness — workable only if the new bound is still an explicit finite bound with its own digest; blast radius — pause duration (Stage 4 queue grows while `pausing`); cost — low; failure modes — "raise the limit until it passes" creep, which is a fail-open pattern adjacent to C-a's "budget never weakened" principle (different budget — see §7); a cut that was never sized simply succeeds later at a larger size.
Conflicts: C-a-adjacent if "extend" means unbounded or repeated automatic widening. **Named as a weakening pattern; see §7.**

**Q5-C — Partitioned per-plane bounded snapshot + pre-flight sizing.**
Mechanism: before `begin_pause`, a read-only sizing pass runs the 026-style `LIMIT n+1` count/digest per plane (rows, permissions, lineage, object manifests, pending events) and **refuses the cut before pausing** if any plane exceeds its bound. During Stage 6 each plane snapshots under its own bound using the 026 SHARE-lock plane closure (`:503-515`) and per-row digest (`:596`); a mid-snapshot overflow still denies completion for the whole cut (`consistent_boundary_proven=false`, no CAS) with a per-plane overflow report. Matches the design's "vector of local snapshot/commit and queue positions."
Trade-offs: correctness — preserves R10 exactly while making overflow a pre-pause refusal in the common case; drift between sizing and pause is caught by the hard in-snapshot bound (honest denial, not a silent pass); blast radius — snapshot machinery only; cost — medium; failure modes — estimate drift (mitigated as above), long pause if sizing is slow (sizing is read-only and can run before any pause).

**Q5-D — Incremental/streaming snapshot with rolling digest (implementation technique, not a policy).**
Mechanism: chunked per-plane iteration with a running SHA-256, never materializing the full set; cross-plane ordering still honors "close each SQL plane before crossing private/network boundaries."
Trade-offs: correctness — fine *within* a bound; alone it does not answer "working set larger than expected" (that becomes unbounded work, not a bounded snapshot); cost — medium/high; failure modes — long snapshot under `pausing` (queue growth), so it pairs with C's pre-flight sizing.

### RECOMMENDED (recommendation, not a decision)

**Q5-C as the policy, Q5-A as the mandatory failure behavior, Q5-D as an allowed implementation technique; not Q5-B's "keep widening."**
Reasoning: R10's "completion denied; honest overflow report" is preserved in every path; pre-flight sizing turns the common overflow into a cheap pre-pause refusal; the 026 bounded digest machinery is reused rather than replaced. If a working set legitimately needs a bigger bound, that is a **new finite bound with a digest and a named approver** before the next attempt — not a mid-cut relaxation.

### Evidence that would confirm the choice (invented/synthetic only)

1. Synthetic over-size: a plane sized at 1500 rows against a 1000 bound → cut refused **before** `begin_pause`; nothing enters `pausing`.
2. Synthetic drift: sizing passes at 900, synthetic growth to 1200 by snapshot time → `record_snapshot` denies; controller CASes to ABORTED/rolling-back; overflow report names plane + bound + observed; `drained`/`snapshot-reconciled` never claimed (C-c).
3. Synthetic in-bound: 999 rows → per-plane digest computed in the 026 row-hash shape; vector of per-plane positions recorded; no universal LSN fabricated.
All fixtures invented; no production data touched.

---

## Q6 — Rollback representability: can a CAS/rollback represent every write class in the 131-site inventory?

### Evidence read

- Stage 8: "Route only to an actually representable reviewed old state. No reverse-migration fiction." The brand-new ruling (design §1) means "old state" is the **pre-cut generation of the new system** (stop the cut, continue on the old generation) — there is no legacy Oracle state to return to.
- Write classes visible in the inventory and schema:
  - **C1 — mutable SQL rows** (the majority of F1–F8): generation revert + forward compensating rows.
  - **C2 — append-only / immutable SQL**: `deny_operating_model_mutation()` triggers (`004_workflow_integrity.sql:42` and installs at 004:47/72/102/149/160/187, 008:164, 017:61, 020:87/679/681, 021:81, 025:49-54, 026:65, 027:125) refuse UPDATE/DELETE outright; 017 sealed history (`:690-697` fail-closed insufficient_privilege) and 025 sealed artifact metadata are append-only by design (C-b).
  - **C3 — external effects** (F10): GCS deletes (`packages/ai/src/providers/vertex-cache-cleanup.ts:31,81`, `vertex-gemini-adapter.ts:656,658,702,750`), Recall dispatch (`apps/workers/src/lib/recall.ts:35,56`), Vertex model runs/cost, Supabase Auth/Storage — physically irreversible.
  - **C4 — DDL / role grants** (F9 `seed_hosted_preview.py:96-99` CREATE ROLE + applied SQL files): not data rows at all.
  - **C5 — self-expiring transient** (`typing_indicators`, 5s `expires_at`): expiry is its own rollback.

### Options

**Q6-A — Class-partitioned rollback contract (annotate the census, define rollback per class).**
Mechanism: Stage 0 gains a `rollback_class` column (C1–C5). Stage 8's "rollback complete" is defined as: (a) generation reverted via the control CAS; (b) every C1 mutation reverted or compensated by a new row (never an in-place history rewrite); (c) every C2/C3 post-cut effect has a retained receipt + quarantine record and stays UNKNOWN where unacknowledged; (d) no C4 DDL occurred in-window, else rollback is UNKNOWN; (e) C5 expires.
Trade-offs: correctness — honest and complete; blast radius — census schema + Stage 8 definition; cost — low/medium (mostly design + annotations); failure modes — mis-classified sites (mitigated by the same adjudication discipline Stage 0 already requires).

**Q6-B — Restrict each cut attempt to C1-representable writes only (defer C2/C3-heavy families).**
Mechanism: fence a subset of families per attempt; external dispatch and DDL are forbidden via run-scoped admission (Q4-C) for the window; then everything that happened is revertible.
Trade-offs: correctness — strong rollback story per attempt; blast radius — cut completeness suffers: unfenced families are exactly R11 "missingparticipant" (`consistent_boundary_proven=false`) unless their non-participation is itself adjudicated and digested; cost — multiple cut attempts; failure modes — the un-fenced families must be *proven* quiescent, not assumed (C-c).

**Q6-C — Rollback = "stop and continue on the old generation" only (behavioral rollback, no state revert).**
Mechanism: after `rolling-back`, the generation CAS re-admits old-generation writers; post-cut writes are **retained and quarantined**, never un-written; consumers see them as post-cut events requiring fresh authorization. "Representable reviewed old state" is redefined as "old generation + retained post-cut events, explicitly quarantined."
Trade-offs: correctness — fully representable (nothing is un-written), consistent with "no reverse-migration fiction" and R8/R13 ("never guesses rollback"); blast radius — consumer-facing semantics (quarantine must be visible); cost — low; failure modes — consumers confusing quarantined events with live state (needs an explicit quarantine marker).

**Q6-D — Q6-A as the definition + Q6-C as the mechanism for everything non-representable (C2/C3/C4), with C1 additionally supporting compensating rows where an in-place revert would be semantically wrong (e.g. approved claims — 017 immutable history already forces corrections to be new revisions).**

### RECOMMENDED (recommendation, not a decision)

**Q6-D.**
Reasoning: the honest answer to the question is **no — a CAS cannot represent every write class** (C3 external effects are physically irreversible; C2 immutable history is fail-closed against in-place revert; C4 DDL is outside the data plane). The gate standard needs that truth stated as a per-class contract, not a single "rollback" word. D preserves 017/025 fail-closed semantics (C-b), keeps every post-W event (Stage 8), and never invents reverse migrations. B is worth keeping in mind as a **phased rollout** tactic but is not a complete answer on its own (R11).

### Evidence that would confirm the choice (invented/synthetic only)

1. Synthetic per-class cut: write one row per class into the owned test store (C1 mutable insert; C2 append-only insert; C3 a synthetic external-delete receipt; C5 a typing row), then execute synthetic rollback.
2. Assert: C1 compensated by a new revision/withdraw row with the original retained; a C2 UPDATE attempt is refused by the immutable trigger and represented only by an appended compensation row; C3 keeps its receipt + quarantine record with UNKNOWN status and **no resend** (R8); C5 expired; zero history rows deleted anywhere.
3. Assert R13 posture: a synthetic crash before/after the CAS reconciles read-only and never guesses; rollback never replays a possibly delivered response.
All fixtures invented; no production store is touched.

---

## 7. Cross-check: conflicts with standing constraints

| Option | Constraint | Conflict? | Detail |
|---|---|---|---|
| Q1-B graph-local generation key | C-d (no advisory-only / self-stamp; design §2.2) | **Yes** | A graph-side self-checked epoch is the graph analogue of a self-stamp; it cannot fence against a SQL generation bump and would be advisory at best. Do not adopt unless bundled inside Q1-A's SQL-gated owner. |
| Q2-B "exclude typing_indicators" as closure | C-d / gate standard (no silent bypass, R14) | **Yes if claimed as fencing** | Acceptable only as a census classification paired with a hard stop (Q2-A or Q2-C). Alone it leaves a live bypass. |
| Q2-C RLS policy | C-g (reviewed migration route) | No, but flagged | Oracle-owned Supabase; still a managed-platform change needing its reviewed route. Not a POP shared-db action (C-f ok). |
| Q3-B transport wrapping | C-d (barrier at the mutation, not the transport; existing-controls table) | **Yes** | Explicitly forbidden upstream; TOCTOU; bypassable. |
| Q3-C trigger install | C-b (sealed 017/025 unchanged) | No if additive | Triggers may only be added to mutable writer tables and must not replace/alter 017/025's `deny_operating_model_mutation` installs or 017's sealed fail-closed. Any option that edits 017/025 semantics is a conflict — none recommended here does. |
| Q3-A/C, Q2-A, Q1-A overhead | C-a (W10 budget/shape never weakened) | No, but gating | Every option that adds per-write work must be validated in a W10-shaped run at the **unchanged** 120-second ceiling / ten workers / full population. If it cannot pass, the option is not viable as-is; the W10 budget is **not** widened to accommodate it. |
| Q4-B discipline-only exclusion | C-d / gate standard | **Yes if used alone** | Use only where role/schema binding proves impossibility (Q4-D). |
| Q5-B extend bounds | C-a-adjacent (budget weakening pattern) | **Pattern conflict** | Snapshot bounds are a different budget than W10, but "widen until it passes" is the same weakening pattern. Permitted only as a new finite bound + digest + named approver before the next attempt (Q5-C), never as mid-cut relaxation. |
| Q5-A abort path | C-c (UNKNOWN never drained) | No | Abort must not claim `drained`; UNKNOWN/queued arrivals stay unresolved until individually authorized. |
| Q6-C/D quarantine retention | C-c | No | Post-cut effects stay UNKNOWN/quarantined; never "assumed delivered" (R8). |
| All options | C-e (synthetic proofs only) | No | Every proof sketch above is invented/synthetic; no live proof is claimed. |
| All options | C-f | No | No POP shared-db, no company originals, no production RTO/RPO figures are used or quoted. |
| Q3-C / Q4-A SQL additions | C-g | No, but flagged | New SQL must travel the Oracle-owned reviewed migration path; nothing in this document authorizes DDL. |

---

## 8. Decision summary for the coordinator (no decision made here)

| Q | Options | Recommendation (not a decision) | One-line why |
|---|---|---|---|
| Q1 FalkorDB | A effect owner / B graph epoch / C reconstructible projection / D hybrid | **C** (D as upgrade path) | The graph is already a verified, rebuildable projection; B violates the no-self-stamp rule. |
| Q2 browser bypass | A server route / B declare ephemeral / C RLS phase gate / D A+C | **A** now (C/D if F5-9 confirms more direct-browser tables) | Smallest change that makes the write an ordinary fenced writer without touching UX. |
| Q3 cached clients | A call-site guard / B client wrap / C DB-side enforcement / D A+C | **D** (never B) | Same-tx guard is the design's rule; DB backstop catches missed sites; "invalidation" is a non-problem if generation is never cached. |
| Q4 F9 scripts | A participants / B offline-only exclusion / C run-scoped admission / D tiered | **D** | Every site gets a digested disposition; discipline-only exclusion fails the gate standard. |
| Q5 snapshot overflow | A deny+abort / B extend bounds / C per-plane bounds + pre-flight sizing / D streaming | **C with A as failure policy, D as technique** | R10 preserved; overflow becomes a pre-pause refusal in the common case; no budget creep. |
| Q6 rollback | A class contract / B C1-only cuts / C behavioral rollback / D A+C | **D** (honest answer: **not every class is CAS-representable**) | C2 immutable + C3 external + C4 DDL need forward-retention, not revert; 017/025 stay fail-closed. |

**Blockers these options do not remove** (unchanged from `source-owner-design-proposal.md` §6): no barrier is installed anywhere yet (missing items 1–5), the cohort suite is absent (item 8 / R20), and Stage 0 adjudication of the 6 candidate sites is a prerequisite to any of the above. This document authorizes nothing.

---

## 9. Source references

- `source-owner-design-proposal.md` §4 Q1–Q6, §5 R1–R20, §6 blockers, §7 existing controls (same directory)
- `writer-inventory.md` F1–F10 rows and "Existing controls that do NOT constitute a global writer fence" (same directory)
- `qualification-census-test-matrix.md` Part B (S14/S15), Part E matrix cases, Part F unregistered cases (same directory)
- `docs/verification/oracle2/s14-writer-cut/writer-cut-source-owner-design.md` (earlier draft, invariants 1–6, Stage 0–8)
- Code inspected read-only: `services/oracle-brain/oracle_brain/graph/falkor.py`, `graph/graphrag.py`, `graph/base.py`, `graph/projector_cli.py`, `operating_model/cutover.py`, `outbox.py`; `services/oracle-brain/sql/004_workflow_integrity.sql`, `017_processing_model_history.sql`, `025_recommendation_actions.sql`, `026_operational_recovery.sql`; `apps/web/app/channels/[channelId]/_components/channel-chat.tsx`, `apps/web/app/api/messages/route.ts`; `packages/db/src/client.ts`; `apps/workers/src/trigger/lull-interjection.ts`; `apps/workers/src/lib/recall.ts`; `packages/ai/src/providers/vertex-cache-cleanup.ts`, `vertex-gemini-adapter.ts`; `scripts/oracle2/seed_hosted_preview.py`
- Owner ruling (no company comparison): `plan_oracle_consultant_overhaul.md` STATUS, 2026-10-27
