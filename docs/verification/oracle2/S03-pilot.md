# S03 pilot — real-data preview journey (sanitized)

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
| Fact correctness | Pass — operational withdrawal path only; no invented policy |
| Mandatory exceptions | Pass — portal absence and legal rights explicitly not inferred |
| Citation support | Pass — 4 citations resolved to source spans |
| Temporal / customer scope | Pass — process-table steps only; no out-of-scope claims |
| Usefulness | Pass — states confirmed path and what not to infer |
| Clarity | Pass — facts vs hypothetical separated |
| Improvement contract | Pass — labeled “not established fact”, with measure and missing inputs |

Connection line in the answer: `2→3`. Process-owner (Ilona) outcome:
**pending** — this record is the journey and rubric score; business acceptance
by Ilona is still required before plan S03 is marked ✅.

## Not claimed

No production deploy, no employee messages, no public meeting joins. Company
process wording and answer keys stay in private storage only.
