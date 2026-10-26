# S14 writer-cut structural implementation — disposition

**Parent:** #24 · **Branch:** `codex/parent24-writercut-tool1988-20261026` · **Date:** 2026-10-26 EDT  
**Class:** code (offline structural only; no production, no POP shared-db, no company comparison, no live cutover)

## Summary

Offline structural implementation of the S14 global writer consistent cut, as far
as offline allows. Cohort acceptance suite, inventory/reconciliation, and
consistent-cut participation modules for the named writer families are in place
with 25 passing offline race-matrix tests. Company comparison and live cutover
remain HELD.

## What is proven (offline)

| Deliverable | Path | Proof |
|---|---|---|
| Writer census adjudication + digest | `services/oracle-brain/oracle_brain/operating_model/writer_census.py` | 80 sites adjudicated: 60 confirmed, 15 excluded, 5 external, 0 unknown. Census digest `7bdbfc00a0a82d259711f964adcd896e904454439d960c3e60b5cbcaae78e923` |
| Inventory reconciliation tool | `scripts/writer-cut-reconcile.py` | Emits per-family counts + digest + blocking reasons; report at `docs/verification/oracle2/s14-writer-cut/writer-cut-reconciliation.json` |
| Durable cut-control state machine | `services/oracle-brain/oracle_brain/operating_model/cut_control.py` | Phases legacy-active→pausing→drained→snapshot-reconciled→replacement-active + ABORTED/UNKNOWN/rolling-back; CAS on transition_count; stale controller refused |
| Local barrier + generation guard | `services/oracle-brain/oracle_brain/operating_model/writer_barrier.py` | `assert_admitted` in same-tx contract; stale generation refused; role not admitted refused; pausing/closed refuse; fixed effect owner with UNKNOWN/no-resend |
| Race matrix R1–R20 | `services/oracle-brain/tests/test_writer_cut_race_matrix.py` | **25 tests passed** in 0.19s (offline invented fixtures) |
| Cohort acceptance suite (R20) | `apps/web/tests/oracle2/cohort.spec.ts` | Required suite present with 9 structural cases; real browser proof against installed runtime remains HELD |
| Ownership correction preserved | inventory + design docs | Legacy Oracle Supabase `theoracle` is Oracle-owned; **no POP shared-db claim** |
| Tool1988 disposition | `docs/verification/oracle2/s14-writer-cut/tool1988-doc-safety-disposition.md` | Candidate `2634e51f` matcher path proved locally; exact CI blocker is StepFun `paces_before_call` pacing, documented with evidence |

## Named writer families with consistent-cut participation

| Family | Confirmed files | Barrier hook |
|---|---|---|
| F1 chat/messages/modelusage/contextpacks/typing | 6 | messages.insert, contextPacks, modelRuns, typing_indicators (browser path needs installed fence) |
| F2 storage bytes/SQL metadata/orphans | 3 | Storage upload/remove + SQL inserts; in-flight upload receipt |
| F3 imports/Teams/discovery/transcripts | 8 | row writers + ingress receipts; late webhook drain inventory |
| F4 extraction/paid batches/late-drain | 8 | generation at source claim, publication, provider submission |
| F5 admin approvals/corrections/taxonomy/gaps/identity/auth | 12 | every admin mutation + auth-link writes |
| F6 synthesis/translation/contradiction/lull/outbound/cached | 19 | schedules, started jobs, outbound operations |
| F8 Python oracle-brain legacy | 3 | separate processes; independent fencing |
| F9 external uncontrolled | 5 classes | incompleteness declarations; `consistent_boundary_proven` stays false until controlled |

## Race matrix coverage (offline)

R1 race · R2 pause-arrival · R3 stale-writer · R4 restart · R5 reinstall · R6 latebatch · R7 orphan · R8 lostACK · R9 privacy · R10 overflow · R11 missingparticipant · R12 unknownrole · R13 crashrollback · R14 cohort-bypass · R15 stop · R16 security-denial · R17 rollingback · R18 concurrent-pause-CAS · R19 generation-mismatch-restart · R20 cohort-acceptance-suite

All 25 offline tests pass. Cases that require real browser, installed runtime, or
company stores assert structural refusal/hold rather than live behavior.

## What is HELD (not claimed)

1. **Company comparison** — business-acceptance hold remains.
2. **Live cutover / adoption / non-use / retention / removal** — separate authority required.
3. **Real browser cohort proof against installed runtime** — suite exists; live run not executed.
4. **SQL barrier installation at each confirmed writer** — guard contract and tests exist; physical same-tx hooks in each mutator not yet patched into operational source.
5. **Storage/external fixed effect owners in production** — offline owner model proved; installation held.
6. **Provider/graph fully-drained evidence** — UNKNOWN blocks drained; real drain inventory not executed.
7. **Actual installed writer/schedule/directSQL/bypass-role census** — F9 remains incompleteness declaration.
8. **Tool1988 landing** — candidate `2634e51f` preserved; CI blocker is StepFun pacing (`paces_before_call`); no green CI invented.

## Census digest

```
7bdbfc00a0a82d259711f964adcd896e904454439d960c3e60b5cbcaae78e923
```

Confirmed writers: 60 · Excluded lexical: 15 · External classes: 5 · Unknown: 0

## Boundaries preserved

- No POP shared-db claim. Legacy Oracle Supabase `theoracle` is Oracle-owned.
- No production, no deployment, no database effects.
- No company comparison or live cutover.
- No toolkit/reviewer repair (Tool1988 blocker documented only).
- Existing SQL004 serving-selector fence is not treated as an ingestion pause.
- `retirement.require_no_legacy_activation` has no operational call sites (unchanged).
