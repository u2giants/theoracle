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
