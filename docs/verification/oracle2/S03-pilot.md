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

## Not claimed

No production deploy, no employee messages, no public meeting joins. Company
process wording and answer keys stay in private storage only.
