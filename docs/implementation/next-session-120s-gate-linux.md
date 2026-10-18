# Next-session prompt — speed the slow stage and re-prove the 120-second gate

Copy everything below the line into a fresh session on **Linux (edge-dev3)**. Do not run this on Windows — the suite needs `fcntl` and the full dependency tree.

---

Resume u2giants/theoracle on main. Read first:

1. https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-16T1558Z-edge-dev3-claude-s03-s16-offline-coordination.md
2. https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-10-16T0101Z-edge-dev3-codex-replacement-coordination.md (§3 timing facts, §6 step 4)
3. https://github.com/u2giants/theoracle/blob/main/plan_oracle_replacement_documentary_journey.md STATUS

**Goal:** make one admitted fresh coherent native fixture run finish **within 120 seconds** with every control terminal, then prove it. That is the only outcome.

**Where:** isolated worktree from https://github.com/u2giants/theoracle/tree/claude/step4-combined-integration (head `1ce38d6` or newer). Never edit the canonical checkout. Local commits only until the gate passes; then normal PR — never push to protected main.

**Known timing (do not repeat unchanged attempts):**
- Complete run was **123.12s** (FAIL). ACK alone ~102s; executor answer ~113s; compiler reload ~115s; missing-wire ~122s; withdrawal ~122s.
- Later candidate **128.29s** incomplete (test-interface failure on `blob.get` vs `blobs.read` — already fixed in Phase B holdNoBlob).
- Catalogue batching already helped once. The remaining overrun is the confirmation/completion stage, not the product wall clock.

**Do only:**
1. Profile the ACK/completion path in the fixture (paid embedding wire, graph ACK, compiler reload). Name the dominant cost with evidence.
2. Speed that stage without weakening currentness, cost, identity, or the 180/60/30 horizons. No new authority, no cache that skips a real check.
3. Optional if profiling says so: the approved three-lane C/D/E concurrent fixture at `96bb55f` (compiler restart + direct executor + result RPC), 32-handler cap and 8-socket TLS bridge unchanged. Cleanup service stays ours — do not take 96bb's result service.
4. Fresh 001..014 target. Keep every original 10 control plus `protected_result_mtls_*` and `held_result_mtls_denied_before_private_bytes` (`blobs.read`, not `blob.get`).
5. ONE admitted run under 120s with all resources retired or honestly UNKNOWN.

**Do not:** predict a pass; retry an unchanged full; relax the 120s number; renew authority; ship SQL014; deploy; resume company/staff/grading pauses; claim live proof outside the same issues.

**Done when:** one clean run reports terminal ALL controls in **≤120s** on the exact head, with a receipt on the existing #27 live-proof checklist (same issue — never a leftover-proof issue). If the stage cannot be made fast enough without weakening a check, say so with numbers — that is a real result.

Sign GitHub comments: `Posted by Claude chat <id> on edge-dev3`.
