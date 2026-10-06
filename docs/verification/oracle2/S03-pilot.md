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

## Not claimed

No production deploy, no employee messages, no public meeting joins. Company
process wording and answer keys stay in private storage only.
