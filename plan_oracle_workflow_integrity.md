# Oracle workflow integrity and measured process analysis

Written October 11, 2026 EDT. Planning publication only; no application change,
company-data generation, installation, migration or production action is delivered
by this document. Track this work on [S03 issue #27](https://github.com/u2giants/theoracle/issues/27)
under [parent #24](https://github.com/u2giants/theoracle/issues/24); retain live proof
on [the existing proof card #58](https://github.com/u2giants/theoracle/issues/58).
Implementation owner: the session explicitly adopting this plan on #27. Until
adoption, implementation is not started; this planning session owns publication.

## STATUS — read first

Every implementation row is open as of October 11, 2026 EDT. A completed row must
link an immutable verification artifact and deployed revision where relevant.
Keep source merged, synthetic verified, privately audited, hosted verified and
business accepted as separate states. Never close #24/#27/#58 from this plan alone.

| Step | Outcome | State | Dependency | Required acceptance artifact |
|---|---|---|---|---|
| W01 | Adopt current recovery and freeze reproduction | Open | Current recovery ownership reconciliation | `docs/verification/oracle2/workflow/W01-baseline.md` |
| W02 | Persist conflicts and missing-information observations | Open | W01 | `W02-findings.md` in the same verification directory |
| W03 | Model explicit process execution and scope | Open | W02 | `W03-workflow-contract.md` |
| W04 | Qualify and integrate PM4Py structural checks | Open | W03 | `W04-pm4py-qualification.md` |
| W05 | Preserve source lineage and invalidate derived artifacts | Open | W02; W03 for workflow lineage | `W05-lineage.md` |
| W06 | Expose the connected workflow and unresolved findings | Open | W04, W05 | `W06-browser.md` |
| W07 | Import actual event records with honest completeness | Open | W03, W05 | `W07-operational-import.md` |
| W08 | Discover observed behavior and compare it to documented flow | Open | W04, W07 | `W08-process-analysis.md` |
| W09 | Add bounded planning, calculation and challenge roles | Open | W06, W08 | `W09-consulting.md` |
| W10 | Run full regressions and independent source audits | Open | W02–W09 | `W10-acceptance.md` |
| W11 | Reviewed release, restricted hosting and recovery proof | Open | W10; existing H7/H8 hosting gates | `W11-live-proof.md` |
| W12 | Reconcile downstream plans and close accepted outcomes | Open | W11 | `W12-closeout.md` |

**Fresh-session start:** W01. Read this STATUS, then the immutable
[recovery handoff](https://github.com/u2giants/theoracle/blob/36e91038ee6b1126f9d9c27adce7583a6b74c654/HANDOFF.d/2026-10-11T2032Z-edge-dev3-codex-holistic-recovery-cutover.md).
It describes unfinished source auditing and restricted hosting, not a working
production consultant. Re-read current #27 activity and current remote heads;
do not take over its stores/jobs or replay paid generations without reconciliation.
The recovery handoff/code are not files in the planning/main checkout. Fetch
`codex/oracle-readiness-recovery` and inspect the pinned commit, or retrieve the
immutable GitHub blob at that exact commit via the GitHub contents API. If the
branch moves or disappears, the pinned commit is still the required reference;
do not substitute main. If neither Git nor GitHub can supply the exact object,
W01 records a recovery-owner source-availability blocker on #27. This document
already carries the relevant scope, failed paths, environment and stop conditions;
source unavailability blocks integration, not permission to recreate private state.
Planning-session registration: [this session's handoff](HANDOFF.d/2026-10-11T2059Z-edge-dev3-codex-workflow-integrity-plan.md).

## 1. Ultimate goal

Oracle should explain how work moves through POP Creations, including who owns
each handoff, which decisions create different paths, what happens when work is
returned, and which instructions disagree or remain incomplete. It should compare
the documented process with actual recorded activity and propose improvements
whose evidence and measurements can be checked. An unanswered question must stay
visible; a confident explanation must not erase it.

**If a step conflicts with this goal, the goal wins — stop and flag it.**
Keep evidence, privacy and recoverability intact. Neither a formally valid flow
nor a fluent report establishes that it represents company practice or policy.

## 2. What this application is

Oracle is the employee and owner-facing company knowledge/consultant application
in [u2giants/theoracle](https://github.com/u2giants/theoracle). The existing site is
[oracle.designflow.app](https://oracle.designflow.app), hosted by Vercel. Next.js
provides the interface and authenticated API, Trigger.dev runs Python jobs, and
the isolated `services/oracle-brain` Python package implements the new learning
path. Oracle-owned Postgres and private source files are durable authority;
FalkorDB is a rebuildable reported-source graph, accessed through pinned GraphRAG
SDK 1.4.0. Candidate and confirmed identities remain separate.

`main` is the long-lived integration branch; implement on an isolated short-lived
current-upstream worktree and land through PR. The reviewed recovery baseline is
[36e91038ee6b1126f9d9c27adce7583a6b74c654](https://github.com/u2giants/theoracle/commit/36e91038ee6b1126f9d9c27adce7583a6b74c654)
on `codex/oracle-readiness-recovery`. The remote main observed for this plan is
[687d9e92da6c4fc1ec0a47206c0e82b4176f863f](https://github.com/u2giants/theoracle/commit/687d9e92da6c4fc1ec0a47206c0e82b4176f863f).
The local canonical checkout had older, divergent history; it was not used as
the implementation base. This plan's documentation branch starts at current
remote main and does not transplant or merge recovery code.

Existing web/legacy worker deployment is not proof of the dedicated holistic
worker's deployment. Private hosted FalkorDB connectivity remains subject to
the recovery handoff's separate restrictions. Ansible owns host/OS changes;
Coolify, if qualified, owns the new application containers.

## 3. Trigger and reproduction

Albert requested: “write an implementation plan to fix the lost conflicts and
missing information, add explicit workflow modeling with PM4Py, and integrate
the useful parts of the other projects while keeping FalkorDB and GraphRAG.”
This authorizes this plan's publication; it does not start implementation.

The defect is established in the recovery source, not by a fresh production
company-answer run. At the pinned baseline, `ProcessModel` declares
`missing_information` and `conflicts` in
`services/oracle-brain/oracle_brain/graph/graphrag.py:158–162`; extraction returns
only nodes, relationships and mentions at `:454`. Only objects and links are
materialized. The in-memory `_readings` cache at `:283` does not provide durable
findings or a retrieval path. A conflict separately represented by a `CONTRADICTS`
edge can survive; the two free-standing lists do not. Do not claim all conflicts
are lost or that this is the sole cause of every unsuccessful answer.

Reproduce without provider calls: extend the fixed-response extraction fixture
in `services/oracle-brain/tests/test_holistic_graphrag.py:255–279` with one missing
owner and two conflicting requirements. Extract, write through the actual pinned
SDK, finalize, reopen in a new process, retrieve and render. Before the fix, the
lists have no persisted representation. The new regression must fail on that
baseline and pass after W02. Use public invented examples only.

## 4. Scope

In scope: structured source findings; immutable persisted extraction artifacts;
explicit workflow contracts and source-backed gateways/loops; deterministic
workflow compilation and PM4Py checks; source ownership/revision/dependency
lineage; permission-filtered rendering; actual CSV/XES event import; measured
process discovery/conformance; bounded evidence-based consulting; qualification,
tests, release and retained live-proof conditions for these changes.

Useful outside ideas are integrated into Oracle, not as five new applications:
ProMoAI text-to-formal-model and engineer/analyst separation; agency-agents clear
role deliverables and challenge criteria; ODD source/owner/dependency lineage;
CrewAI consultant's planner/analyst/writer sequence. PM4Py is the sole proposed
new analytical runtime dependency. No code is copied from the other projects by
default; independently implement these patterns using existing Oracle contracts.

**NOT in this plan:** replacing FalkorDB or GraphRAG; a second knowledge authority;
installing CrewAI, ODD or ProMoAI services; autonomous arbitrary code execution;
inventing event logs from SOPs; changing approved company policy; employee
messages; resumed company-answer/Ilona/Jessica grading; provider/account/key changes;
reopening the closed credential incident; new cloud purchases; live ERP writes;
the entire S04–S16 overhaul; repairing unrelated historical R2 experiments.

The Tailscale credential incident is CLOSED. Albert explicitly ruled
“Yes—close the credential incident” on October 11, 2026 EDT; the
[closure receipt](https://github.com/u2giants/theoracle/issues/27#issuecomment-6111823232)
supersedes the older October 11 1641Z handoff’s OPEN status. Preserve the accepted
private external transcript copy and the no-rotation boundary; do not reopen it.

## 5. Current code and delivery state

**Recovery inventory only:** every line reference in the following table uses
recovery commit `36e91038ee6b1126f9d9c27adce7583a6b74c654`, not planning/main HEAD.
New files named later are implementation targets, not existing capabilities.
Use `rg` to relocate symbols after integrating a newer accepted recovery revision.
In particular `graph/retrieval.py` and the occurrence/observation hardening are
recovery-only prerequisites. W02 must not attempt edits to these nonexistent-on-main
surfaces before W01 establishes the accepted recovery integration base.

| Existing component | Exact anchor | Established behavior and limit |
|---|---|---|
| Process extraction contract | `graph/graphrag.py:143–162` under `services/oracle-brain/oracle_brain` | Flat objects/links; free-text findings; no typed branch/parallel-join contract |
| Preserved claims/observations | same file `:204–260` | Distinct quoted relationships and per-original observations are retained |
| Repeated execution positions | same file `:263–273`, `:425–433` | Step/Decision/Exception/Rule occurrence identities survive SDK reconciliation |
| Whole-document reading | same file `:332–355` | Evidence windows are losslessly assembled for extraction |
| Source-bound conversion | same file `:398–454` | Quote/type/endpoint checks; findings are not projected |
| Snapshot seal | same file `:572–599`, `:620–640` | Finalization/reload check claim and observation identifiers; new artifacts are not covered |
| Answer/review | same file `:642–692` | Graph context plus all distinct original texts; source-grounding review; no formal workflow or metric input contract |
| Original diversity | `graph/retrieval.py:14–89` | Stock SDK paths retained, structured keywords plus balanced original observations; no new findings path |
| Runtime inventory | `holistic_runtime.py:165–195` | Admitted current confirmed source readings with provenance; not an operational event ledger |
| Delivery | `holistic_runtime.py:221` onward; `apps/workers/src/trigger/oracle2-holistic.ts` | Preview-only configuration and dedicated Python transport; source and hosted release are separate |
| Durable stores | `services/oracle-brain/sql/001_foundation.sql`, `002_pilot.sql:13–24`; `oracle_brain/storage.py` | Source evidence, reviews, outbox/checkpoints; no workflow/metric artifact tables |
| Dependencies | `services/oracle-brain/pyproject.toml:6–22` | Python 3.12 core, pinned GraphRAG SDK; PM4Py absent |
| Existing verification | `scripts/oracle2/verify_phase.py:24–29`; `.github/workflows/oracle2-contracts.yml` | S03 required test list, real isolated stores, synthetic browser proof |

**Planning observation, not a completed W01 baseline:** 32 focused tests ran at
the pinned recovery commit, using its qualified Python environment and
`python -m pytest services/oracle-brain/tests/test_holistic_graphrag.py -q -p no:cacheprovider`
([sanitized planning receipt](docs/verification/oracle2/workflow/planning-baseline.md)).
This count is not asserted for main, which has a different test inventory. Re-run
at W01 and save its exact head, dependency digest and sanitized result in
W01-baseline.md. This is not business acceptance, full-store verification or a
deployed outcome.

**Current main separately:** at `687d9e92da6c4fc1ec0a47206c0e82b4176f863f`,
`apps/web/app/api/consultant/questions/route.ts:43–58` explicitly requires dedicated
holistic settings and dispatches `oracle2-holistic-answer`; unavailable readiness
fails visibly. `apps/web/lib/oracle2-client.ts` manages pilot UI/run state.
`oracle_brain/retrieval/pilot.py` and `consultant/pilot.py` remain older pilot
components, not an authorized fallback for this question route. Main has an
earlier `graph/graphrag.py` and lacks `graph/retrieval.py`; its ProcessModel list
loss also exists but its line offsets and regression inventory differ. Source
preparation at main may freeze fixtures/contracts only. Integration W02–W11
targets the accepted recovery graph/runtime and this same dedicated web/worker
route, never an accidental switch back to the old passage reader.

The linked recovery handoff reports 26 upload identities/eight original hashes,
781 reported relationships and 543 observations; these are historical receipt
counts, not this plan's new acceptance evidence. Its independent source audit
stopped on output truncation after two completed originals; five were unstarted,
and the cross-document audit was prepared but unrun. Adopt newer receipts before
doing work. Recovery branch publication is not recovery merge/hosting acceptance.

## 6. Findings and root cause

1. **Findings are requested but not transported.** Prompts put caveats in
   `missing_information`/`conflicts` (`graphrag.py:367–373`), but conversion has no
   destination for them (`:419–454`). A schema field and exact quote guards do not
   guarantee end-to-end preservation.
2. **An evidence graph is not an execution model.** `ENTITY_TYPES`/`RELATION_TYPES`
   at `graphrag.py:29–31` express steps, responsibilities and relations. They do
   not encode gateway type, joins, start/end, branch conditions or enabled-state
   execution. Descriptions may carry this meaning, but cannot be compiled reliably
   without a separate explicit contract. Do not feed every `DEPENDS_ON` or
   `RESPONSIBLE_FOR` relation into a control-flow edge.
3. **The complete-source answer can mask graph omissions.** `answer()` still
   supplies every distinct original (`graphrag.py:650–680`). Good output alone
   cannot prove the graph retained a conflict. Verify ledger → graph → retrieval
   → rendered artifact separately, alongside the current complete-source path.
4. **Snapshot integrity is incomplete for the proposed work.** Existing seals
   check identifier sets, not every new finding/model/metric payload. W02/W05
   must seal canonical payload digests, detect edits with an unchanged ID, and
   invalidate dependent artifacts on source or permission changes.
5. **PM4Py serves two different purposes.** Formal-model structural analysis
   needs a specified process, not event timestamps. Observed process discovery
   and performance analysis need real cases/activities/time. Structural soundness
   does not prove completeness, business truth, feasible conditions or causation.

## 7. Rejected approaches and recorded failures

| Approach | Why it is rejected | Required alternative |
|---|---|---|
| Add more prompts/agents without retained artifacts | The current lists already exist in prompts; another prompt cannot repair a missing storage/retrieval path | Persist and prove each artifact end to end |
| Turn a generic graph into an executable flow by guesswork | Responsibility, dependencies, sequence and parallel branches are different meanings | Explicit evidence-backed workflow contract; partial status when unknown |
| Fabricate timestamps or cases from SOP order | Described practice is not observed activity | Separate documented model from real event import |
| Declare a sound net complete or correct | A compiler can create a valid net while omitting a mandatory approval | Independent source inventory plus trace expectations |
| Collapse repeated step labels or endpoint-only relationships | Recovery reproduced lost routes/claims through SDK finalize | Retain occurrence IDs and quoted claim IDs |
| Let later source descriptions overwrite earlier ones | Shared names do not give a source authority over another | Source-specific observations and unresolved disagreements |
| Count duplicate uploads as independent corroboration | Same original bytes are one source, even with several upload IDs | Original-hash deduplication and alias supports |
| Normalize a bad quote or borrow another original's quote | Changes provenance; past delimiter/type failures showed this boundary | Exact current-source spans; bounded quote-only repair, otherwise fail |
| Repeat whole-corpus generation after a bounded failure | Prior audits truncated; unchanged qualified readings and captured generations already exist | Diagnose exact failed response; one bounded affected-artifact correction |
| Copy PMAx generated-code execution | Oracle does not need arbitrary model code, credentials or unconstrained retries to calculate a known metric | Allowlisted typed operations implemented and tested by Oracle |
| Import all of agency-agents/CrewAI as another orchestrator | Roles do not supply source ownership, evidence admission or measurements | Existing LangGraph with bounded named contracts |
| Install ODD to obtain company meaning automatically | Metadata lineage identifies assets and dependencies; business meaning remains source/model work | Small Oracle lineage records with ownership and invalidation |
| Use ungraded company questions as acceptance | Owner stopped that methodology | Synthetic engineering tests and separately admitted source audits; questions remain paused |

## 8. Decisions and build contracts

All decisions below are dated October 11, 2026 EDT. “Locked” fixes the design for
this plan; it never overrides permissions, a failed test or current owner limits.

### 8.1 Locked architecture and source attribution

Postgres + private object storage remain durable authority; FalkorDB remains a
derived reported-source projection; GraphRAG retains its stock retrieval paths
and current safeguards. Add small typed Oracle adapters, not vendor patches.
Use current LangGraph state/checkpoint ownership for the consulting sequence.
No direct provider fallback, telemetry, policy self-approval or unrestricted query
generation. PM4Py must run within bounded CPU/memory/time and dependency limits.

Sources checked October 11, 2026 EDT:

| Project | Pattern adopted | Integration and primary source |
|---|---|---|
| PM4Py | Formal process validation and measured log analysis | Oracle-owned adapter to [PM4Py](https://github.com/process-intelligence-solutions/pm4py); [formal-model analysis API](https://github.com/process-intelligence-solutions/pm4py/blob/24a3bf610aea6ecc4938b1864b3ad71fcfb82084/pm4py/analysis.py) |
| ProMoAI/PMAx | Text-to-formal-model refinement; engineer/analyst separation; calculation artifacts | Extend Oracle extraction/compiler and calculation→interpretation contracts; [README](https://github.com/fit-process-mining/ProMoAI), [agent implementation](https://github.com/fit-process-mining/ProMoAI/blob/main/promoai/agents/agents.py) |
| agency-agents | Explicit role deliverables, evidence checks and bounded challenge | Encode planner/analyst/challenger result schemas in Oracle; [orchestrator role](https://github.com/msitarzewski/agency-agents/blob/main/specialized/agents-orchestrator.md) |
| ODD | Source ownership, versions and derived-asset dependency lineage | Small Oracle asset/dependency registry, not the whole platform; [ODD](https://github.com/opendatadiscovery/odd-platform) |
| CrewAI consultant | Planner → analyst → writer separation | Use existing Oracle workflow engine; [actual implementation](https://github.com/hanantabak2/crewai_ai_business_consultant_on_streamlit/blob/main/main.py) accepts topic/stakeholder strings and has no supplied operational-data or citation contract |

These are selective design patterns, not claims the external projects solve
Oracle's problem. The PM4Py source link is the prior research's immutable
2.7.22 candidate; W04 re-qualifies its supported APIs or records a newer exact
stable compatible version, rather than installing branch documentation. W04 records exact upstream commits/licenses and the chosen
stable PM4Py version before dependency admission. PM4Py/ProMoAI advertise AGPL;
do not copy code or deploy until the assigned technical reviewer records exact
license/deployment fit. No purchase is implied. An incompatible license stops
the affected deployment; it is not permission to remove requested functionality.

### 8.2 Finding and workflow contracts

Add `oracle_brain/knowledge/findings.py` and
`oracle_brain/workflows/process_model.py`. Use strict, versioned Pydantic models
with flat collections and ID references, no deeply nested generated schemas.

**Finding:** `finding_id`, `kind` (`missing_information`, `source_conflict`,
`model_incomplete`), `workspace_id`, `source_refs`, `affected_object_ids`,
`process_id`, `scope`, `text`, `status`, `origin`, `evidence_refs`, `coverage_ref`,
`supersedes`, `schema_version`. Source refs include original byte hash, admitted
reading hash, integer source revision, source ID and parser identity. Adapt the
current string display revision (`rN`) through the authoritative source record;
do not guess a revision by parsing arbitrary text. Evidence refs use validated
SourceSpan-like start/end/quote against the exact admitted reading.

A reported conflict cites at least two opposed assertions/spans. If only one
source reports that a conflict exists, keep it `reported_conflict_unverified`,
not two invented sides. A missing-information finding may cite an explicit
“not specified” statement. Otherwise it is a derived coverage gap: reference the
complete reviewed inventory and required slot, with `origin=coverage_inference`;
do not fabricate a quotation proving absence or claim nobody owns the work.
Do not require a string-list finding to become a company fact to preserve it.

Statuses distinguish `unresolved`, `resolved_by_authorized_review`,
`superseded`, `withdrawn`, `needs_evidence`. Resolution retains old evidence,
scoped review event and reviewer authority. Rejection/withdrawal never erases the
history. Missing evidence remains visible and cannot be used as confirmed policy.

**WorkflowModel:** header ID/version/workspace/process/scope/source manifest,
reported-vs-confirmed status and `complete|partial|ambiguous|conflicted`; flat
steps, gateways, transitions, role assignments, artifacts, findings and handoffs.
Step occurrences have unique IDs even when labels repeat. Gateways specify
`exclusive_split|exclusive_join|parallel_split|parallel_join`; transitions carry
source/target, condition reference, loop/rework flag and support. Starts/ends,
termination/rejection, optional paths and cross-process call/return boundaries are
explicit. Conditions retain quoted source wording plus typed known/unknown
applicability; no arbitrary expression execution. Inclusive OR/event gateways or
unstructured cycles are preserved as unsupported partial semantics in the first
compiler, never coerced into XOR/AND. Synthesize a sole formal start/end only as
clearly marked compiler plumbing, never as a reported company step.

Cross-document joins require explicit shared process/scope or accepted identity
mapping, not similar labels. Preserve versions, customers, departments and dates.
Every source-backed step/transition/gateway keeps supporting spans or existing
claim IDs with current-source resolution. Structural diagnostics are derived
analysis; they do not require fake source quotes. Formal completeness requires
independent source-obligation coverage, not merely the number of mapped items.

### 8.3 Persistence, projection and invalidation

Add reviewed additive Oracle-only migration
`services/oracle-brain/sql/004_workflow_integrity.sql` plus the retained repository
bootstrap/migration route. Tables: `artifact_manifests` (workspace, artifact ID,
kind/version, input/source/permission/compiler/dependency digests, content hash,
private object key, state), `finding_events` (append-only scoped finding/review
events), `artifact_dependencies` (exact upstream revision → downstream artifact),
`operational_imports` (mapping/window/quality/count/hash receipt). Enforce unique
workspace+ID/version keys and write-once payloads; only authority-scoped events
change current status. Use existing transactional outbox to project artifacts.
Keep large model/log payloads in private object storage, not giant graph strings.

All artifact readers recompute payload hash and recheck current access. No
mutable “latest” pointer may confer authority or bypass input-hash checks. Include
canonical sorted payload digests in snapshots; reloading verifies content, not
only IDs. Project `ReportedFinding`, `WorkflowArtifact`, `AnalysisArtifact` and
their support/dependency edges outside SDK entity deduplication; extend store,
retrieval and snapshot seals to retain them. Distinguish source conflicts from
derived model diagnostics. The ledger can rebuild every graph projection.

Source revision/withdrawal, permission removal, corrected identity, model version,
event-window change or compiler/dependency update invalidates dependent summaries,
maps, metrics and recommendations. Invalidation denies stale serving first;
recomputation is a separately admitted bounded job. Permission snapshots are
inputs, not immutable grants. Recheck membership/source access on every read.

### 8.4 PM4Py and measured data

Compile only a qualified complete WorkflowModel to BPMN/Petri net with reversible
Oracle step/transition ID maps. Keep documentary model, compiled formal model and
observed discovered model as separate artifacts. Check deadlocks, unreachable
steps, completion and rework paths. A partial/ambiguous model may be displayed but
returns `not_analyzable` with findings; never a green soundness badge. Soundness
checks structure, not business conditions or approval authority. Add typed
scenario traversal to test source-supported branch conditions independently.

Initial operational import supports validated CSV and XES with explicit mapping:
event ID, case ID, activity, timestamp + zone, optional lifecycle start/complete,
resource/role, system, object refs, process/scope and source row. Never infer an
actor from a label. Validate time zones, tie ordering, duplicate IDs, cancellation,
ongoing/right-censored cases, missing events and dataset coverage. Retain rejected
rows privately with reason; expose quality denominator and exclusions. Distinguish
elapsed throughput, inter-event delay and actual work duration; start/complete
records are required for work duration. Business calendars are explicitly supplied,
not guessed; otherwise report elapsed wall-clock time. A case spanning an order,
SKU and approval cycle needs explicit correlation; many-to-many object records
must not be flattened into a false case. Preserve them and return unsupported
mapping until an object-centric OCEL extension is separately qualified.

Metrics include cases/window/coverage, median/p90 elapsed time, observed path
variants, rework counts and alignment deviations. Every number links to input
event hashes/row IDs, method/version, exclusions and mapping/model version.
Discovery describes observed records. Conformance is deviation from the selected
documentary model, not automatic wrongdoing. No causation/savings claim without
an independently measured intervention. An incomplete log cannot prove a task
never happens. No real operational export is asserted available by this plan;
synthetic adapter proof and actual operational usefulness remain separate.

### 8.5 Bounded consultant roles

Planner selects approved tool operations and relevant model/findings; calculation
worker executes typed operations; analyst explains measured results; challenger
checks support, alternatives, omitted exceptions, scope and unknowns; writer
renders only admitted outputs. Use no more than four generation calls per report
(planner, analyst, challenger, writer), one challenger revision at most within
the same budget, no automatic retries, and the existing funded/admitted route.
Calculations are code, not model guesses. Failed challenge returns an explicit
limited result, not a polished unsupported report. Existing whole-source
grounding remains; no stage resolves a conflict or writes confirmed policy.

**Open technical choices with criteria:** stable PM4Py release/API compatibility
and applicable license (W04); bounded formal-check execution limits measured on
fixtures; exact rendering library already present in the web app; whether a real
event mapping has sufficient identity/time/coverage (W07). Record resolved choices
in this plan and verification artifacts. Do not ask Albert technical permission.
No unresolved business decision is required to begin the scoped engineering work.

### 8.6 Relationship to the existing H and S stages

This is the execution detail for the newly requested integrity/analysis scope,
not a competing replay of the H recovery plan. Existing H records retain their
evidence and owner; the new W rows start open. The following mapping is binding
from W01, not deferred until closeout:

| Existing obligation | W responsibility and retained gate |
|---|---|
| H1 ownership/paused grading | W01 adopts exact scope; no question or grading restart |
| H2 SDK/provider admission | Retained prerequisite for W02/W04; do not reinstall or change providers merely to start |
| H3 original reading | Reuse qualified complete readings; W01/W10 adopt coverage receipts, not reread originals unnecessarily |
| H4 process graph | W02 fixes finding loss; W03 adds explicit execution contract; retain occurrence/quote/scope guards |
| H5 retrieval/explanation | W02/W06 extend its same SDK/web path; preserve stock retrieval and whole-source grounding |
| H6 lifecycle/permission/grounding | W05/W06/W10 extend its invariants across new artifacts; prior passes are not new-artifact proof |
| H7 technical review/hosting | W10/W11 retain exact review, current checks, restricted topology and restore gates |
| H8 original/cross-source readiness | Existing recovery owner finishes/adopts its audits; W10 adds workflow/finding coverage with compatible receipts |
| H9 company questions | Remains deferred; no W step restarts it |
| S04/S05/S09 | Only findings/model lineage and integrity intersections are specified here; broader lifecycle/policy/company-answer scope stays open |
| S11/S13–S16 | W07–W09 supply scoped analytical components; W11–W12 retain release/restore/retirement obligations without closing those stages |

A receipt may satisfy both H and W only when exact source, code, schema, graph and
permission inputs and the tested behavior match; both rows link the same immutable
artifact. Otherwise extend the relevant proof once and link it from both. Do not
replay a prior accepted H step or count synthetic evidence as H8 acceptance.

## 9. Ordered implementation

Before every phase, re-read this STATUS and all downstream steps through W12,
plus affected S04–S16 obligations in the parent plan. Record discovered drift.
Natural context cut points are after W03, W06 and W10; apply `fresh-session` at a
cut only when useful and transfer all remaining obligations. A phase completion
is never authority to stop remaining authorized work. The plan names no model
tier implementer; apply the standing mechanical-work delegation policy at execution.
Every stage gate also requires all §10 matrix tests for that stage's input classes;
short gate lists below are highlights, never permission to omit a binding test.

### W01 — Freeze the real baseline and reproduce losses

Inspect current remote main/recovery refs, #27/#58 ownership, accepted receipts and
the exact recovery handoff. Start a dedicated worktree at accepted current upstream.
Do not edit or cherry-pick another owner's pending recovery. If recovery is still
unmerged, its owner retains recovery landing/audits; this owner can prepare isolated
fixtures/contracts, but integration waits for the accepted recovery base.

Create `services/oracle-brain/tests/test_workflow_findings.py` and
`tests/fixtures/workflow_integrity/` with a two-source synthetic conflict, missing
owner, same-label repeated approval, alias upload and cancelled branch. Freeze
source-obligation inventory independently of extractor output. Record exact version,
source hashes and the red findings round-trip test in W01-baseline.md.

Gate: `test_unresolved_findings_survive_finalize_reload` fails against the pinned
baseline for the missing list projection; existing focused graph tests still pass.
Zero paid provider calls, zero company questions, no reused mutable snapshot.

### W02 — Persist and serve conflicts and missing information

Implement `knowledge/findings.py`, `artifact_storage.py` and the additive SQL
described in §8.3. Do not create a `storage/` package that shadows existing
`storage.py` imports. Add `scripts/oracle2/migrate_workflow_integrity.py` as an
idempotent, transaction-bound dedicated Oracle migration runner with schema-version
and target-identity assertions; wire the isolated bootstrap in
`scripts/oracle2/init_local_stores.py`, `dev/oracle2/init-postgres.sql` and
`dev/oracle2/grant-postgres.sql`. Fresh and preexisting isolated stores must apply
the same reviewed migration; extraction identities receive only required
artifact/outbox permissions, never owner-review authority. Hosted application of
this runner is a separately reviewed W11 action, not local bootstrap against
production. Extend `graph/graphrag.py` ProcessModel and
ProcessExtraction with typed findings, preservation of legacy lists as
`needs_evidence`, scope/span validation, durable extraction receipt and findings
projection. Update snapshot build/reload payload seals and `graph/retrieval.py`
to include scoped unresolved findings and their source supports.

Adapt existing `_readings` only when source/model/schema/prompt/provider identity
hashes match; legacy payloads become unverified imported findings, never disappear
or acquire invented spans. Store new artifact revision, retain old graph. Update
`holistic_runtime.py` serialization and graph retrieval to expose findings without
requiring a new company-answer call. Gate: new nonempty findings survive actual SDK
finalize/restart/retrieval; same-ID tampering fails; unresolved and incomplete
evidence survive; cross-workspace/withdrawn sources cannot be served. Require
`test_legacy_findings_import_keeps_needs_evidence` in `test_workflow_findings.py`
and the §10 `test_artifact_storage.py` checks explicitly at this gate. Save W02.

### W03 — Build source-backed executable workflow contracts

Add `workflows/process_model.py`, `workflows/process_extract.py`,
`workflows/process_validate.py`; extend extraction through the existing admitted
LLM and bounded cache. Transform evidenced objects/links into explicit flat
execution records, preserving separate responsibility and dependency relations.
Use independent obligation inventory for starts/ends, role handoffs, decision
branches, join semantics, rework and rejection. Missing semantics create findings
and a partial model; they do not trigger endless inference calls. Add
`tests/test_process_model.py` and `tests/test_process_coverage.py`.

Gate: source fixtures for exclusive choice, parallel join, repeated approval,
rework loop, partial workflow and cross-document version conflict retain exact
scoped supports. A graph with a mandatory approval omitted fails semantic
coverage even if structurally well formed. Save W03.

### W04 — Qualify PM4Py and compile explicit models

Add `process_analysis/pm4py_adapter.py`, `process_analysis/compiler.py`,
`process_analysis/scenarios.py`, and dependency/qualification tests. Resolve
stable PM4Py on Python 3.12 with SDK 1.4.0; record exact version/commit/license,
dependency tree and bundle resource behavior. Update `pyproject.toml`, `uv.lock`,
and regenerate `apps/workers/oracle2-requirements.txt` with the retained frozen
export. Do not float `latest` or copy ProMoAI code.

Compile only supported explicit semantics to BPMN/Petri nets. Keep reversible
transition IDs and marked plumbing. Run the pinned equivalent of `check_is_sound`
in a cancellable subprocess: initial bounds 30 seconds, 512 MiB, 500 activities,
2,000 transitions, 10,000 explored states for owned scenario traversal. Budget
exhaustion is `analysis_incomplete`; retain diagnostics and original model.
Tune only with recorded fixture evidence. Do not call deprecated API names by
memory; qualify the installed public API.

Gate: `test_pm4py_detects_deadlock`, `test_xor_and_parallel_language`,
`test_rework_preserves_occurrences`, `test_unknown_gateway_not_coerced`,
`test_compiled_model_round_trip_ids`, `test_formal_check_timeout_keeps_model`
and `test_structural_soundness_does_not_accept_omitted_approval` pass. Worker
dependency export/SDK regression and bundle checks stay green. Save W04.

### W05 — Integrate the useful ODD lineage pattern

Implement `knowledge/lineage.py`, extend `artifact_storage.py`, `outbox.py` and
`graph/graphrag.py`. Register source steward, authority scope, revision/reading
hash, aliases, model/findings/analysis dependencies and recomputation health.
Steward is a supplied responsible party, not an LLM-assigned owner. Index dependent
artifacts for invalidation; source deletion/revision and current permission denial
must prevent stale display before recompute. Extend existing revision/withdrawal
paths only enough for these artifacts; carry broader S04 obligations forward.

Gate: `test_revision_invalidates_findings_workflow_metrics_and_advice`,
`test_revoked_permission_denies_cached_artifact`, `test_alias_is_not_second_source`,
`test_lineage_cycle_rejected`, `test_steward_requires_authority`, and
`test_rebuild_from_ledger_without_graph` pass.
Ledger/graph restart proof uses isolated stores. Save W05.

### W06 — Deliver workflow and uncertainty views

Add `apps/web/components/consultant/workflow-view.tsx`,
`workflow-findings.tsx`, `process-analysis-panel.tsx`, and
`apps/web/app/api/consultant/processes/[id]/route.ts`. Extend existing
`apps/web/components/consultant/pilot-workspace.tsx`, `apps/web/lib/oracle2-client.ts`
and transport contracts. Display process steps, handoffs, gateways, source-backed
paths, partial/conflicted status and formal diagnostics. Findings link to current
permitted evidence; do not bury them in a tooltip. Distinguish reported instructions,
confirmed policy, derived structural checks and measured activity. Add scoped
finding/model review events via `api/consultant/reviews/[id]/route.ts` only with
explicit existing role authority; source confirmation alone does not grant workflow
policy authority. Include loading, empty, stale, blocked and denied states.

Gate: `apps/web/tests/oracle2/workflow-integrity.spec.ts` proves upload/import →
SDK → finding/workflow store → restarted retrieval → UI on invented data. Visually
inspect conflict evidence, partial branches and denied access in the browser.
Require the §10 `test_workflow_authorization.py` checks at this gate.
No company questions or employee messages. Save W06 with sanitized screenshots.

### W07 — Import real operational records through a separate path

Add `ingest/operational_export.py`, `process_analysis/event_contracts.py`,
`process_analysis/event_store.py`, and
`apps/web/app/api/consultant/processes/[id]/events/route.ts`. Accept authorized
read-only CSV/XES uploads; do not connect/write ERP systems. Set initial limits:
25 MiB upload, 100,000 events, 100 columns, 100,000-character cell; quarantine
oversize or incompatible content before parsing. Disable XML external entities
and network resolution. Enforce configured source/window/process mapping and
private raw-object retention. Normalize event times to UTC internally and show
EDT/EST in human reports; retain original zone/offset and reject ambiguous local
times. Equal-time events without a supplied tie order remain unordered, not a
fabricated sequence. Do not use direct-SOP record dates as event times.

Gate: `tests/test_operational_export.py` covers §10 rows. A valid synthetic fixture
imports exactly once with input/mapping hashes and row provenance; rejected rows
and censored cases are visible. Actual private export acceptance needs separate
current processing admission and data evidence; absence remains unavailable.
Save W07 with synthetic and actual-data state explicitly separated.

### W08 — Discover measured behavior and compare it to documented flow

Implement `process_analysis/discovery.py`, `conformance.py`, `metrics.py` and
`tests/test_process_analysis.py`. Use allowlisted PM4Py discovery/alignment calls
on validated logs. Keep discovered process distinct from documentary model;
stable activity mapping is scoped/versioned, never fuzzy automatic equivalence.
Cap alignment at 60 seconds/512 MiB per batch, 1,000 cases per cancellable batch;
unfinished batches report incomplete denominators, never sample silently.

Return variants, repeat/rework counts, elapsed median/p90 and deviations with
complete provenance. For start/complete lifecycle use actual duration; otherwise
do not report work time. Comparisons use model version applicable to event dates;
missing applicability means unavailable conformance. Exclude cancelled/ongoing
cases only under explicit receipt rules and show their counts. No ROI or causal
claims. Gate: independent hand-calculated fixture values match PM4Py/owned metrics;
parallel paths are not misreported as violations, incomplete logs cannot prove
skipped work, and event-row drill-down explains every reported number. Save W08.

### W09 — Integrate bounded consulting roles and artifacts

Add `consultant/process_analysis.py`, `consultant/challenge.py` and
`workflows/process_consult.py`; extend holistic runtime/worker dispatch behind an
explicit new operation, not free-form code or generated Cypher. Use existing
LangGraph and scoped checkpoints with the roles in §8.5. Extend UI panels to
render evidence, findings, measured numbers, alternatives and hypothetical
experiments. Calculations are fixed typed functions; analyst/writer cannot
rewrite metric values or erase unresolved source disagreement.

Gate: `test_report_cites_model_and_event_artifacts`,
`test_challenger_rejects_invented_savings`, `test_report_preserves_unresolved_conflict`,
`test_writer_cannot_change_metric_value`, `test_role_cannot_promote_policy`,
`test_consulting_call_ceiling`, and
`test_failed_challenge_returns_limited_result` pass. Preview shows one measured
synthetic bottleneck plus a stated uncertainty and a hypothetical measurement
experiment. Real company-report generations remain paused. Save W09.

### W10 — Prove the whole path and independent coverage

Extend `scripts/oracle2/verify_phase.py` required S03 tests, add
`scripts/oracle2/verify_workflow_integrity.py` for staged W contracts and
`scripts/oracle2/verify_workflow_browser.py`; update
`.github/workflows/oracle2-contracts.yml` with deterministic synthetic verification.
Record exact command/test inventory, skipped tests, versions and artifact hashes;
no gate passes with a required test skipped. Run retained legacy/web/worker guards.

After admitted recovery ownership/budget/source checks, independently compare
current complete original readings with workflow/findings inventory. Reuse captured
valid extractions only with exact compatible schema/input identity; diagnose the
failed third-original audit's truncation before bounded retry. Original and
cross-document audits remain source audits, not resumed business Q&A. Flag
all detail ambiguities and unknowns. Freeze accepted synthetic trace expectations
before extraction; never derive the answer key from generated models.

Gate: no essential source obligation is omitted, no unsupported scope/causation,
conflict retained, coverage independent of model self-review. Current protected
source audits and all actual SDK/store/browser paths pass at exact head. Real
event usefulness is unavailable until an admitted export exists; retain its open
acceptance row rather than claiming a measurement from synthetic data. Save W10.

### W11 — Land, deploy and prove recovery without collateral changes

Use assigned non-Codex rotation reviewer through `ai-review`, exact frozen head,
tests and release inputs. Recheck task gates before review/ship/pr-wait/database/
deployment/infrastructure actions. Make recovery backups including all new ledger,
private blobs and graph artifacts. Serialize stores/CI ports with the existing
recovery owner; never stop another session or drop its volumes. Open normal PR,
attach it to the chat, use bounded `bin/ai-pr-wait`, merge required checks, and
verify merged-main checks. Docs-only planning publication does not wait for CI;
implementation with code/config does.

Deploy only dedicated admitted worker and reviewed private hosted resources.
Restricted worker connectivity/backup restore and current FalkorDB license fit
must be proven; broad wildcard tailnet access is not sufficient. No new provider
purchase or manual host edit. Recoverable rollout selects a versioned artifact
manifest and previous compatible runtime; older snapshots remain intact but
cannot be served as current knowledge. Roll back code via normal platform/repo
path, not destructive schema rollback. Verify browser → worker → SDK/private
graph → ledger/evidence, permissions, withdrawal, restore and actual web/worker
revisions with synthetic scenarios first. No company questions are resumed.

Gate: exact hosted revisions match reviewed input; fresh-instance recovery
reproduces content seals and findings/models/metrics; original capability survives.
Require the §10 `test_workflow_recovery.py` checks at this gate.
Keep `- [ ] live proof` on #27/#58 until done. Missing policy-management authority
is a named external technical blocker owned by the recovery implementation session,
not a request for Albert to do setup. Save W11.

### W12 — Close only verified outcomes and preserve downstream truth

Update this STATUS and parent plan's affected S03/S04/S05/S09/S11/S13–S16 entries,
router/research/env/deployment documentation and #24/#27/#58 from actual artifacts.
Register any remaining business-acceptance/data/hosting gap on the same cards with
named owner and evidence. Retire this plan's handoff only after all obligations
are accepted or carried to the successor under the three-part successor rule.
Do not retire the existing recovery baton simply because this plan is published.

Gate: every requested outcome has source/test/merge/hosted/acceptance status and
an openable artifact; no undocumented outstanding obligation; no synthetic/live
or reported/confirmed conflation. Record exact head, deployment and rollback
manifest in W12. Whole-project S04–S16 closure remains outside this plan.

## 10. Required tests and adversarial inputs

All named files below are future additions unless §5 identifies them as existing.
Test names in §9 and this table are binding behavioral specifications.

| External input | Hostile or ambiguous case | Required test |
|---|---|---|
| Model finding output | Nonempty lists silently dropped at graph conversion | `test_unresolved_findings_survive_finalize_reload` in `test_workflow_findings.py` |
| Legacy cached findings | Lists imported without valid quote support | `test_legacy_findings_import_keeps_needs_evidence` in `test_workflow_findings.py` |
| Finding evidence | Quote borrowed across source/version; forged span | `test_finding_support_is_exact_current_original` in the same file |
| Missing-information output | Absence presented as quoted policy or invented owner | `test_absence_is_coverage_inference_not_company_fact` in the same file |
| Conflict output | One side invented; old/new scope merged | `test_conflict_needs_two_supported_sides_or_unverified_status` in the same file |
| Source text | Prompt instructions ask to resolve or hide conflicts | `test_source_instructions_do_not_change_finding_authority` in the same file |
| Artifact ledger/blob | Payload edited without ID change; hash/path traversal | `test_payload_tamper_and_object_key_escape_rejected` in `test_artifact_storage.py` |
| Workflow output | Orphan/duplicate IDs; unknown condition; wrong scope join | `test_invalid_workflow_references_and_scope_rejected` in `test_process_model.py` |
| Workflow topology | AND treated as XOR; repeated step collapsed; unknown OR coerced | `test_xor_and_parallel_language`, `test_rework_preserves_occurrences`, `test_unknown_gateway_not_coerced` in `test_pm4py_adapter.py` |
| Workflow coverage | Sound net omits mandatory approval | `test_structural_soundness_does_not_accept_omitted_approval` in `test_process_coverage.py` |
| Formal analyzer | Exponential net, memory/time/cancellation exhaustion | `test_formal_check_timeout_keeps_model` in `test_pm4py_adapter.py` |
| Lineage | Cyclic dependency; forged owner; stale alias | `test_lineage_cycle_rejected`, `test_steward_requires_authority`, `test_alias_is_not_second_source` in `test_lineage.py` |
| CSV/XES upload | Oversize; external XML entity; compressed bomb; malformed encoding | `test_operational_upload_limits_and_xml_entities` in `test_operational_export.py` |
| Event identity | Duplicate replay; conflicting ID; many-to-many false case | `test_event_idempotency_and_conflicting_duplicate`, `test_object_correlation_not_flattened` in the same file |
| Event time | Missing zone, ambiguous DST, negative duration, tied unordered timestamps | `test_ambiguous_times_and_negative_duration_rejected`, `test_tied_events_not_fabricated_sequence` in the same file |
| Event coverage | Cancelled/open cases, missing events, biased denominator | `test_censoring_and_exclusions_are_reported` in `test_process_analysis.py` |
| Metric output | Elapsed delay called work duration; synthetic called observed | `test_elapsed_time_is_not_work_duration`, `test_synthetic_metrics_not_reported_as_company_measurements` in the same file |
| Consultant output | Unsupported saving, concealed conflict, metric rewritten | `test_challenger_rejects_invented_savings`, `test_report_preserves_unresolved_conflict`, `test_writer_cannot_change_metric_value` in `test_process_consult.py` |
| API actor/request | Forged workspace/process/source permission; stale cache | `test_cross_workspace_workflow_access_denied`, `test_revoked_permission_denies_cached_artifact` in `test_workflow_authorization.py` |
| Review action | Unprivileged model/policy confirmation, race/double review | `test_role_cannot_promote_policy`, `test_review_race_keeps_append_only_history` in the same file |
| UI evidence/export | Hidden conflict, stored script/HTML, spreadsheet formula | `workflow-integrity.spec.ts` cases `conflicts stay visible`, `evidence is escaped`, `export formulas are neutralized`, `withdrawn evidence denied` |
| Release/restore | Corrupted backup or stale model/current-source mismatch | `test_restore_requires_current_manifest_and_payload_seals` in `test_workflow_recovery.py` |

Retained required gates: `python3 scripts/oracle2/verify_phase.py S02 --mode offline`,
`python3 scripts/oracle2/verify_phase.py S03 --mode offline`, existing
`scripts/oracle2/verify_holistic_browser.py`, worker typecheck/bundle guard and web
build/guards from the current repository workflow. Run only on approved isolated
stores. New targeted unit invocation after dependencies are frozen:
`services/oracle-brain/.venv/bin/python -m pytest services/oracle-brain/tests/test_workflow_findings.py services/oracle-brain/tests/test_process_model.py services/oracle-brain/tests/test_process_coverage.py services/oracle-brain/tests/test_pm4py_adapter.py services/oracle-brain/tests/test_lineage.py services/oracle-brain/tests/test_operational_export.py services/oracle-brain/tests/test_process_analysis.py services/oracle-brain/tests/test_process_consult.py -q`.
The extended required S03 gate must also include artifact/authz/recovery suites;
the short targeted invocation is not a substitute for it.

Public verification documents contain synthetic evidence, version/hash receipts
and sanitized results only. Company source text, private event rows, answer keys,
business names in evidence and provider raw output stay in approved private storage.

## 11. Standing rules and gotchas

Read `AGENTS.md`, the task router, affected deployment/incident rules and current
recovery handoff. Start the correct task class; this planning publication is
`reviewer-safety` because plans/handoffs are protected. Implementation includes
code, dependencies, deployment surfaces and Oracle-only SQL: re-declare the
stronger observed class and apply every required gate. Never invent a class/action
or work around a refusal. Worktrees are isolated; canonical checkout is landing-only.

**Database boundary:** Oracle's dedicated `oracle2` store is not POP's shared
application database. The generic shared-db template instruction does not route
these dedicated Oracle tables to `popcre/shared-db`. Use the Oracle canonical
reviewed migration path, isolated migration proof and before-dependent-release
gates. No `popcre/shared-db` structure/curated data change is in scope. If that
boundary changes, stop and obtain its separate claim-first workflow; no ad-hoc SQL.

No private originals in public repo/review packet; no secrets in arguments/output.
Use 1Password `vibe_coding`, protected injection and existing admission. Retain
closed credential/no-rotation rulings. No framework/vendor edits, new generated
code executor, automatic aliases, automatic policy confirmation or hidden failures.
Review scopes may use public synthetic fixtures only. Human-readable times use
America/New_York EDT/EST; machine ISO identifiers may stay UTC.

Current recovery and CI compose projects share fixed ports 55432/56379/56380/54566.
Never assume CI stores are disposable while recovery stores are running. Take
fresh scoped backups, coordinate exact process ownership, and stop only an owned
project preserving volumes. Never broad Docker cleanup. Snapshot/config changes
invalidate earlier graph proofs and exact-head review. Freeze before independent
review; do not change a plan during its review and reuse a stale approval.

Keep each result on the existing issue. No one-phase stopping rule. Host changes
belong to Ansible; app releases belong to their normal platforms. Do not claim
source merge, deployment, private coverage and business acceptance are equivalent.
New background monitor, employee messages or real company Q&A is not authorized.

## 12. Access and environment

Git remote reads and `gh issue view` succeeded during planning; this establishes
repository read access, not production or secret authority. Resolve current
credentials and reviewers at execution. Authenticated restricted Tailscale policy
management was unavailable in the recovery snapshot; inspect fresh state but do
not infer permission from broad wildcard connectivity.

Read the protected **Holistic recovery evidence index - The Oracle (edge-dev3,
2026-10-11)** in 1Password vault **vibe_coding** for exact same-machine recovery
paths, worktree/store/process identity, receipts, admission and backup locations.
Only access locations are in this plan, never secret values. Relevant runtime
entry: **OpenRouter API Key - The Oracle (local .env.local)**. Other existing
access locations and approved login references are in `docs/1password.md` and
the pinned recovery handoff. Do not load the key for planning or code review.
There is no established company QA login for this new scope; synthetic local
browser identity comes from the existing browser verifier. Real employee access
or company questions remain paused and cannot be a made-up acceptance requirement.

Re-read processing register scope/expiry/provider/model, remaining daily budget
and exact input hashes before any private engineering dispatch. Existing $25/day
limit and no direct-provider retry remain; no plan estimate authorizes spend.
Preserve approved OpenRouter/OpenAI route, no fallback, data collection denied,
store false, no automatic retries. Technical access repairs remain AI-owned with
assigned review, never instructions for Albert to perform setup.

Synthetic local setup: from the accepted implementation worktree run
`uv sync --project services/oracle-brain --frozen --extra test`; inspect
`dev/oracle2/compose.yaml` and current owners before `docker compose -f dev/oracle2/compose.yaml up -d --wait`;
run `scripts/oracle2/init_local_stores.py` with that environment's interpreter.
Test URLs/variables and browser startup are defined in
`.github/workflows/oracle2-contracts.yml` and `scripts/oracle2/verify_holistic_browser.py`;
reuse their synthetic-only configuration without production keys. New stage
verifier takes `--stage WNN --mode synthetic --result <owned-output>`; `private-audit`
is a separate admitted mode, never the CI default. Add these flags in W10.

Current holistic runtime is preview-only and forbids confirmed/projection/admin
credentials. Extend only through reviewed dedicated identities. No hosted live
proof may be asserted until the actual restricted topology and runtime revisions
are verified. Preserved private state adoption requires the original machine;
another machine may draft/test synthetic contracts but must not recreate company
state or duplicate a running audit.

## 13. Definition of done, risks and decisions

### Completion checklist

- All W rows have reproducible artifacts and true status; findings, workflow,
  lineage, event mapping, calculations and consulting results survive actual
  SDK finalize/reload and permission/revision changes.
- Source-supported branches/joins/rework/hand-offs are explicit; partial models
  stay partial; every original obligation is independently accounted for.
- PM4Py exact dependency/license fit is recorded; resource bounds/cancellation,
  formal checks and independently calculated event fixtures pass.
- Useful external patterns exist as small owned Oracle components; FalkorDB,
  GraphRAG, original retrieval capability, evidence authority and access remain.
- New and retained unit/store/browser/build gates pass with required tests
  unskipped; exact-head independent review APPROVE is current.
- Owned files committed/pushed, PR merged normally, required merged-main checks
  verified; dedicated web/worker/graph/ledger deployment revisions and restricted
  restore proof recorded. Offline passing code is not hosted acceptance.
- Actual event analysis remains unaccepted until a current admitted export is
  measured. Company-answer/process-owner acceptance remains paused until an
  authorized business evaluation exists; never mark it complete from this work.
- Docs/router/parent drift/status/issues updated. Remaining gaps stay on existing
  cards with owner; successor handoff links carry every obligation. Rollback
  and source/private-evidence retention work. No unrelated handoff deleted.

### Risks and resolution criteria

| Risk/uncertainty | Owner | Criterion and safe response |
|---|---|---|
| Recovery head moves/unmerged fixes collide | Implementation lead plus existing recovery owner | Freeze accepted base and exact ownership before editing; source prep may continue independently |
| Missing-info strings lack evidence | Implementation lead | Preserve needs-evidence/coverage-inference records; never manufacture proof |
| Documentary flow underspecifies gateways | Implementation lead | Partial model plus explicit finding; no guessed executable meaning |
| PM4Py API/license/dependency incompatibility | Implementation lead and assigned technical reviewer | Stable pinned bundle and exact reviewed deployment fit; affected release blocked if unqualified |
| Formal soundness creates false confidence | Implementation lead | Independent source coverage and documented semantic scenarios are separate required gates |
| Actual event export unavailable/incomplete | Implementation lead | Synthetic integration accepted only as such; real analysis stays unavailable on same issue |
| Restricted hosting authority remains missing | Existing recovery implementation owner | Exact topology gate remains blocked; no bypass/purchase/credential substitution |
| Whole-corpus audit exceeds model output budget | Implementation lead | Preserve prior raw response; bounded affected-artifact repair with complete obligation inventory |
| Review/extraction resolves policy conflict silently | Implementation lead | Append-only findings and explicit scoped authority review; fail on automatic promotion |

Rollback selects previous compatible runtime and artifact manifest after restoring
access-appropriate source state; no data erasure or reuse of stale evidence as
current. Keep new immutable artifacts for investigation and provide compensating
Oracle migrations if necessary. Restored graphs must match ledger and payload
seals. Runtime forward-redeploy follows Trigger's existing rollback constraints.

### Final self-audit

All 13 required sections and STATUS are present. Checklist mapping: goal §1;
application/trigger/current state §§2–6; rejected paths §7; locked/open contracts
§8; every executable step/files/dependency/gate §9; hostile input × named test
matrix §10; safety and database boundary §11; access/setup/secret locations §12;
completion/risks/rollback §13; reciprocal handoff links in STATUS and the registered
handoff. Every implementation row remains open; publication proves no runtime outcome.

1. **Can a brand-new session execute without this chat? Yes, within the stated
   gates.** §§2–6 fix the source baseline and distinguish pending recovery from
   main; §§8–10 specify contracts/files/scenarios/tests; §§11–13 specify admission,
   ownership, private-state adoption, release and blocked-state handling. Missing
   live authority/data are documented constraints, not invitations to guess.
2. **Is all relevant background and reasoning preserved? Yes.** §§3/6 identify
   the actual list-loss and graph/formal-model boundary; §7 records finalize,
   overwriting, alias, truncation and false-acceptance failures; §8 states selected
   patterns and rejected full-platform integrations; §§11–12 retain the stopped
   questions, closed incident, budget and hosting limits.
3. **Can the goal guide a correct deviation? Yes.** §1 explicitly gives it
   precedence; §§8/13 require partial/unknown states over invented structure,
   distinguish measured behavior from policy, and retain evidence/rollback.

Self-audit found and fixed three traps before publication: generic shared-db
routing was corrected for Oracle's separate store (§11); conflict strings without
opposed spans get unverified status rather than invented support (§8.2); proposed
`storage/` package shadowing was removed in favor of `artifact_storage.py` (W02).

Posted by Codex chat 01a12b2c-9fa9-72c0-a132-341a402873d8 on edge-dev3
