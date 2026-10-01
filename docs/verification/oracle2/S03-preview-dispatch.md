# S03 real-data preview dispatch — exact inputs for independent technical review

Status: **pending review** (revision 2, 2026-10-01 EDT). Revision 1 was
REJECTED (run `20261001T161933-1000779-31397`) for missing the processing
register, unproven connected understanding, unauthenticated confirmation,
weak acceptance, and loose evidence storage. This revision fixes those
findings. Nothing here runs before a `VERDICT APPROVE` whose record names the
reviewed commit and this path. The operator executes **only** the steps below
at that commit.

Purpose: the leftover-proof gate on [#58](https://github.com/u2giants/theoracle/issues/58)
/ [#27](https://github.com/u2giants/theoracle/issues/27) — one isolated,
explicitly authorized real-data preview journey, reviewed by its process owner
(Ilona, licensing workflow) using the S01 rubric. Synthetic offline proof is
already green (CI `36644212614`, 11/11). This dispatch does **not** authorize
production settings, production writes, public meeting joins, or employee
messages.

## Preconditions

- `ai-task-gates start --class code` or `prose` recorded for this repository.
- Reviewed commit is the worktree HEAD (`git rev-parse HEAD`); re-request review
  if it changes after APPROVE.
- No new cloud account, paid tier, Trigger project, Supabase project, or vendor
  key is created or modified.
- Journey surface is the merged S03 thin stack:
  - `services/oracle-brain/oracle_brain/workflows/pilot.py` (Postgres +
    `knowledge/authority.py` transactional correct/confirm)
  - `apps/web/lib/oracle2-client.ts` + `/api/consultant/*` (process-owner UI)
  - Both paths now pass draft `connections` into retrieval and answer text so
    a corrected process link is visible in the cited answer.

## Company-data processing admission (before any real-data step)

Plan `plan_oracle_consultant_overhaul.md` §Company-data processing admission
requires this **before** any real-data preview, even when no vendor model is
called. Do it first and record it; do not skip because the thin answer path is
offline.

1. **Organizational approval on record:** Albert Hazan, 2026-09-28 EDT
   (settled): “All data can be shared with all AI providers.” Process owner
   for the licensing journey: Ilona. Purpose: S03 real-data pilot journey
   acceptance. Data class: POP licensing operational process text (sanitized
   steps), not contracts, not employee messages.
2. **Outbound calls in this dispatch:** none. `oracle_brain/consultant/pilot.py`
   and `apps/web` answer from uploaded source spans only. `provider_policy.dispatch`
   is not invoked. If any step would add a model call, extraction, embedding,
   OCR, or tracing processor, **stop** and open a new dispatch with a
   `ProcessingApproval` covering provider, account, endpoint, data classes,
   purpose, terms hash, expiry, and register ref (`oracle_brain/provider_policy.py`).
3. **Private processing register** (never commit raw register contents):
   write `C:\Users\ahazan\.local\share\mimocode-private\oracle2\S03-processing-register.md`
   (or the approved private Oracle storage object if that path is unavailable)
   with: date/time EST, the quote of Albert’s sharing settlement, purpose
   `s03-real-data-preview`, data class `licensing-operational-process`,
   retention = session evidence only until plan S03 is accepted then delete
   captures; training use = not used for training beyond the provider policy
   already authorized; no residency change. Publish on #58 only this file’s
   **reference path and SHA-256**, never its body.
4. Re-check the register immediately before step “Run one real-data journey.”

## Authorized real-data scope (settled; do not re-ask)

Source class: POP licensing operational process text already recorded in
private company knowledge — specifically the Disney DCP Vault
artwork-withdrawal confirmation practice **settled from Ilona, 2026-09-25**
(relayed by Albert; durable rule in `popcre/shared-db`
`docs/business-rules/licensing-master-data.md`, provenance
`popcre/shared-db#3347`). Answer key for S01 scoring: that same settled
practice (no formal notice; UPDATED + manual removal; or creation-time sunset
date; portal absence ≠ confirmed withdrawal).

Do **not** copy private contract text, employee identity, or raw DCP asset
filenames into this public repository, issues, or model logs. Sanitized
process steps and the already-published operational rule only.

## Actions

1. **Approval record before any run** — post on #58 the reviewed commit SHA,
   this file’s path, the approving review file path and `VERDICT` line,
   processing-register reference path + SHA-256, and the one journey scope
   (Ilona / licensing / DCP withdrawal confirmation). No step 2 before that
   comment exists.
2. **Isolated preview environment** — from the reviewed commit, start
   `@oracle/web` on `http://127.0.0.1` only (default port 3000, or the next
   free port). Bind loopback. No public hostname, no Vercel production project
   change, no `oracle.designflow.app`. The pilot store is in-process memory
   (`apps/web/lib/oracle2-client.ts`); no database migration or hosted store is
   provisioned. If a remote URL is later required for a human reviewer, that is
   a **new** dispatch (Vercel preview is out of scope here).
3. **Authority-backed journey (required)** — the process-owner UI must run
   through the S03 authority path, not an unauthenticated shortcut:
   - Uploader actor is granted `review` + `confirm` on upload
     (`grantAuthority` in `oracle2-client.ts`, mirroring S02
     `has_authority` scopes).
   - `POST /api/consultant/reviews/[id]` **refuses** `correct` without
     `review` and **refuses** `confirm` without `confirm` (HTTP 403).
   - Record one rejected unauthenticated confirm attempt in the private
     capture (status 403) as proof the gate is live.
   - Companion offline proof already green: `test_authority.py` (forged
     actors, out-of-scope grants, revoked parents, expired delegates,
     revocation racing confirmation).
4. **Run one real-data journey** in `/consultant` using a **sanitized**
   process document composed only of the settled operational steps
   (upload → source-linked draft → **correct one connection** → scoped
   confirm → one **connected** question → cited answer + one explicitly
   hypothetical improvement). The corrected connection must appear in the
   answer’s “Process-map connections in scope” line and the cited spans must
   include a connected block (connection boost in retrieval). Suggested
   connected question: *When artwork disappears from the DCP Vault, what do we
   treat as confirmed withdrawal, and what must we not infer?*
5. **Capture private evidence** only under the controlled path from the
   processing register (same directory):
   - `C:\Users\ahazan\.local\share\mimocode-private\oracle2\S03-evidence\`
   - Access: this machine’s user account only; not in any git repo; not
     synced to shared drives; deleted when plan S03 is accepted or at the
     register’s retention end, whichever the owner directs.
   - Record: draft, correction, confirmation (incl. the 403 negative),
     answer, citations, hypothetical, and the process-map connection line.
   - Never paste raw private source text into GitHub.
6. **S01-rubric review package** — blinded packet for the process owner:
   question, permitted source spans shown to the product, effective
   date/scope, and output. Score **each** dimension per
   `evals/oracle2/acceptance-spec.md`: fact correctness, mandatory exceptions,
   citation support, temporal/customer scope, usefulness, clarity; improvement
   contract (observed evidence vs hypothesis vs measure vs missing inputs).
   Ilona is the named grader. Answer key = her 2026-09-25 settled practice.
   **Any failed dimension is a failed journey** — do not average it away. A
   second reviewer resolves disputes before any aggregate score is published.
7. **Sanitized result artifact** — `docs/verification/oracle2/S03-pilot.md`
   (Markdown only): date (EST), reviewed commit, processing-register ref +
   SHA-256, journey steps, authority negative test, connection line, per-
   dimension pass/fail, citation resolution, fact vs hypothetical split,
   process-owner outcome (accepted / rejected / pending), private evidence
   **directory reference only**. No secrets, no raw private document, no
   employee names beyond the already-public process-owner name Ilona.
8. **Acceptance gate** — plan S03 row becomes ✅ only when **every** S01
   dimension the rubric scores for this journey is pass **and** the process
   owner accepts the cited answer. Partial rubric success leaves the row
   open. Then close #27 and #58, retire the predecessor S03 baton under the
   successor rule, and only then name S04 (#28) next on #24.

## Out of scope

- Production deploy, production database writes, Trigger prod, Vercel prod
  settings, employee messages, public meeting joins.
- New Trigger preview projects (S02 synthetic projects are a prior closed
  workstream and are not reused for real data).
- Model evaluation or cheaper-model work (separate child under #24).
- Expanding connectors, OCR containers, or S04 source lifecycle.
- Contacting Ilona or any person directly from an agent; process-owner grading
  is delivered through the owner’s existing relay path. No agent outreach.

## Rollback

Stop the local server. Delete the private evidence directory contents if the
owner directs. No cloud resource is created, so there is nothing to
unprovision. A failed journey is recorded as failed; the stop rule in plan S03
applies if the process map or answer is materially wrong — diagnose the
boundary before adding anything.

## Stop rules

- Do not send any company text to a model endpoint (thin journey needs none).
- Do not widen the document set beyond the one licensing journey.
- Do not tick plan S03 or close #27/#58 without full rubric pass and
  process-owner acceptance.
- If the cited answer cannot support the settled operational facts, stop and
  record the failed boundary (source reading / retrieval / explanation).
- If authority gates do not 403 an unauthorized confirm, stop and fix the
  gate before claiming the journey.
