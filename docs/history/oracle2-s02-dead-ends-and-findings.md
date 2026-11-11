---
summary: Dead ends and key findings from the Oracle 2 S02 foundation work (September 2026), kept verbatim from a retired handoff; Oracle 2 was removed in #398.
kind: archive
status: done
read-when: reconsidering Trigger.dev Python workers, Graphiti, FalkorDB or local real-store testing on edge-dev3
---

# Oracle 2 S02 — dead ends and key findings (September 2026)

Sections 4 and 5 of `HANDOFF.d/2026-09-28T1122Z-edge-dev3-codex-oracle-s02-coordination.md`, copied verbatim when that handoff was retired on 2026-11-11 under the successor rule (issue #26 closed; S02 merged as `e7f861a`; Oracle 2 itself removed in #398). The full handoff is in git history.

## 4. Everything tried that did not work

- `edge-dev3` has no Docker, Podman, Postgres, Redis server or passwordless sudo. Local real-store testing was unavailable. GitHub's isolated Ubuntu Actions runner supplied the real stores and recovery test instead; local static/import tests alone were insufficient.
- The first unconstrained Python install occupied about 6.0 GB because of CUDA wheels. The pinned CPU-only Linux bundle measured about 1.6 GB and imported required packages; that is local disk size, **not** measured Trigger package size or cold start.
- The existing Trigger project shares credential-bearing environment variables with legacy workers. Trigger's Python extension injects project environment variables into scripts, so it cannot safely serve both extraction and confirmed projection identities. Separate scoped preview projects or a qualified container host are required; no preview project was created.
- Graphiti did not expose exact source-start/source-end offsets in its supported edge contract. An intentionally shifted span failed the fixture. The bounded Pydantic `CandidateBundle` fallback preserves the admission contract without granting Graphiti confirmed-write authority.
- A first attempt to register the coordinator's timed wait against parent #24 failed because that issue lacked a `parked` label. A dedicated parked issue #44 succeeded, then Albert invoked wrap-up; the timed wait was cancelled and #44 closed. Do not rely on #44 to wake a future session.

## 5. Root causes and key findings

`docs/verification/oracle2/S02-dependencies.md` in PR #45 contains exact dependency/image hashes, test references, resource measurements and the preview isolation proposal. `dev/oracle2/runtime-identities.yaml`, split Trigger configs and the contract tests implement distinct extractor, projector and checkpoint identities. The CI workflow uses full Git history for S01's validator and real isolated stores for S02, correcting the S01 handoff's shallow-history warning. The preview host remains the decisive missing proof. Synthetic test passwords are loopback fixtures only; the sub-agent reported no real credential read or exposure. Oracle's Supabase migration target remains unclassified, and PR #45's SQL applies only to local/CI stores.

