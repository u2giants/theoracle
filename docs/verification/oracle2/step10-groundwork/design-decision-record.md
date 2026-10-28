# Write-fencing design decision — root decision record (closeout §6 step 10)

**Status: DECIDED — binding root decision record. Supersedes the PENDING ROOT DECISION marker in `source-owner-design-proposal.md`.**
**Parent:** #24 · **Closeout step:** §6.10 · **Decided by:** parent24 coordinator, 2026-10-28 · **Landed by:** MiMo subagent, 2026-10-28 EDT
**Analysis:** `design-question-options.md` (PR #237, merged `5984e4ee`) · **Companion:** `source-owner-design-proposal.md` (same directory)

> This record carries the coordinator's decision content verbatim. It authorizes design direction only; implementation, schema changes, and any production action remain separate, gated work.

---

Decided by the parent24 coordinator, 2026-10-28. Analysis: design-question-options.md (PR #237). This record supersedes the PENDING ROOT DECISION marker in source-owner-design-proposal.md.

- Q1 FalkorDB barrier: DECIDED = C (reconstructible projection). Fence the SQL plane; the graph is rebuilt and digest-verified after the cut (falkor.py:57-69 rebuild; graphrag.py:327-383 immutable verified snapshots). D (hybrid) is the measured upgrade path ONLY if rebuild cannot hold the budget — measured, never assumed. Option B (graph-local epoch) is FORBIDDEN (self-stamp conflict).
- Q2 browser bypass: DECIDED = A (server /api/typing route mirroring /api/messages precedent at api/messages/route.ts:76), turning channel-chat.tsx:180,188 into an ordinary fenced writer; UX unchanged. Add C (Supabase RLS phase gate) ONLY if F5–F9 adjudication finds more direct-browser tables. Option B alone is FORBIDDEN (silent bypass invalidates the cut, R14).
- Q3 cached clients: DECIDED = D (A+C). Per-site same-tx guard (generation re-read in-tx, never cached) PLUS DB-side trigger/RLS backstop catching missed sites (R12). Option B (transport/client wrap) is FORBIDDEN (TOCTOU). If the trigger backstop cannot pass a W10-shaped run at the UNCHANGED 120s/ten-worker budget, retain A plus a mandatory missed-site audit and record the gap — the budget is never weakened to make C fit.
- Q4 script writers: DECIDED = D (tiered). F9 sites become registered participants with the shared guard; test-adjacent rows are excluded ONLY on proven role/schema binding. seed_hosted_preview.py:88-99 is an admin-role writer (R12/R5) — discipline-only exclusion (B alone) is FORBIDDEN.
- Q5 snapshot overflow: DECIDED = C with A as the failure policy. Per-plane bounds + pre-flight sizing reusing the 026_operational_recovery.sql:503-596 pattern (SHARE-lock plane closure + txid_current_snapshot() + per-row SHA-256 + LIMIT 100001 overflow detection); D (streaming) is an internal technique. Overflow becomes a pre-pause REFUSAL (R10 preserved). Option B (widen-until-fits) is FORBIDDEN (budget creep).
- Q6 rollback: DECIDED = A+C. A CAS cannot represent every write class — the class-partitioned rollback contract is binding: (C1) mutable rows = compensatable; (C2) immutable/append-only (deny_operating_model_mutation across 004/017/020/021/025/026/027) = forward compensation only; (C3) external effects (object deletes, Recall, provider cost) = NEVER reversible — receipts + quarantine + typed UNKNOWN; (C4) DDL = outside the data plane; (C5) self-expiring rows. Behavioral rollback = generation revert + retained/quarantined post-cut events. "Old state" = the pre-cut generation of the NEW system (owner ruling 2026-10-27: brand new, no legacy comparison).

Cross-cutting conditions (binding on every implementation):
1. Every option is gated on a W10-shaped run at the UNCHANGED shared 120s / ten workers / per-request <=30s / full mandatory population / 0 F/E/S/timeout/launch/cleanup. If an option cannot pass it, the option fails — the budget never moves.
2. Sealed SQL 017 and 025 stay unchanged; fail-closed for genuine integrity failures is never weakened.
3. All proofs are synthetic/invented only. No production writes, no POP shared-db, no company originals. Synthetic RTO/RPO figures (1.275s / 0.0s / 1.511s) are never quoted as production.
4. UNKNOWN is never drained or done; uncertain writes are never resent; strict framing/currentness is never suppressed.
