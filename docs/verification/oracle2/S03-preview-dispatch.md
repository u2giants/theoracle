# S03 real-data preview dispatch — exact inputs for independent technical review

Status: **pending review** (revision 1, 2026-10-01 EDT). Nothing in this file
runs before a `VERDICT APPROVE` whose record names the reviewed commit and this
path. The operator executes **only** the steps below at that commit.

Purpose: the leftover-proof gate on [#58](https://github.com/u2giants/theoracle/issues/58)
/ [#27](https://github.com/u2giants/theoracle/issues/27) — one isolated,
explicitly authorized real-data preview journey, reviewed by its process owner
(Ilona, licensing workflow) using the S01 rubric. Synthetic offline proof is
already green (CI `36644212614`, 11/11). This dispatch does **not** authorize
production settings, production writes, public meeting joins, or employee
messages.

## Preconditions

- `ai-task-gates start --class code` recorded for this repository.
- Reviewed commit is the worktree HEAD (`git rev-parse HEAD`); re-request review
  if it changes after APPROVE.
- No new cloud account, paid tier, Trigger project, Supabase project, or vendor
  key is created or modified.
- Provider-policy note: the S03 thin journey (`oracle_brain/consultant/pilot.py`,
  `apps/web/lib/oracle2-client.ts`) answers from uploaded source spans and does
  not dispatch a vendor model. No `ProcessingApproval` outbound call is made.
  If a later step adds a model call, stop and open a new dispatch.

## Authorized real-data scope (settled; do not re-ask)

Albert (2026-09-28): all data can be shared with all AI providers; use Ilona for
the whole licensing workflow. Process owner for this journey: **Ilona
(licensing)**. Source class: POP licensing operational process text already
recorded in private company knowledge — specifically the Disney DCP Vault
artwork-withdrawal confirmation practice **settled from Ilona, 2026-09-25**
(relayed by Albert; durable rule in `popcre/shared-db`
`docs/business-rules/licensing-master-data.md`, provenance issue
`popcre/shared-db#3347`). Answer key for S01 scoring: that same settled
practice (no formal notice; UPDATED + manual removal; or creation-time sunset
date; portal absence ≠ confirmed withdrawal).

Do **not** copy private contract text, employee identity, or raw DCP asset
filenames into this public repository, issues, or model logs. Sanitized process
steps and the already-published operational rule only.

## Actions

1. **Approval record before any run** — post on #58 the reviewed commit SHA,
   this file's path, the approving review file path and `VERDICT` line, and the
   one journey scope (Ilona / licensing / DCP withdrawal confirmation). No
   step 2 before that comment exists.
2. **Isolated preview environment** — from the reviewed commit, start
   `@oracle/web` on `http://127.0.0.1` only (default port 3000, or the next
   free port). Bind loopback. No public hostname, no Vercel production project
   change, no `oracle.designflow.app`. The pilot store is in-process memory
   (`apps/web/lib/oracle2-client.ts`); no database migration or hosted store is
   provisioned. If a remote URL is later required for a human reviewer, that is
   a **new** dispatch (Vercel preview is out of scope here).
3. **Run one real-data journey** in the consultant UI (`/consultant`) using a
   sanitized process document composed only of the settled operational steps
   (upload → source-linked draft → correct one connection → scoped confirm →
   one connected question → cited answer + one explicitly hypothetical
   improvement). Suggested connected question (S01 improvement/exception shape):
   *When artwork disappears from the DCP Vault, what do we treat as confirmed
   withdrawal, and what must we not infer?*
4. **Capture private recording** outside the public repository (local
   non-committed path or approved private Oracle storage under verified admin
   access; no new account): screenshots or DOM text of draft, correction,
   confirmation, answer, citations, and the hypothetical block. Never paste raw
   private source text into GitHub.
5. **S01-rubric review package** — produce a blinded packet for the process
   owner: question, permitted source spans shown to the product, effective
   date/scope, and output (answer text, citations, hypothetical). Score fields
   per `evals/oracle2/acceptance-spec.md` (fact correctness, mandatory
   exceptions, citation support, temporal/customer scope, usefulness, clarity;
   improvement contract). Ilona is the named grader. The established answer key
   is her 2026-09-25 settled practice. A second reviewer resolves disputes
   before any aggregate score is published.
6. **Sanitized result artifact** — `docs/verification/oracle2/S03-pilot.md`
   (Markdown only): date (EST), reviewed commit, journey steps performed,
   pass/fail against the S01 rubric dimensions, citation resolution, whether
   the answer distinguished established fact from hypothetical improvement,
   process-owner outcome (accepted / rejected / pending), and the private
   evidence **location reference only**. No secrets, no raw private document,
   no employee names beyond the already-public process-owner name Ilona.
7. **Acceptance gate** — plan S03 row becomes ✅ only after the process owner
   accepts the cited answer. Then close #27 and #58, retire the predecessor
   S03 baton under the successor rule, and only then name S04 (#28) next on #24.

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

Stop the local server. Delete only this session’s non-committed private capture
if the owner directs. No cloud resource is created, so there is nothing to
unprovision. A failed journey is recorded as failed; the stop rule in plan S03
applies if the process map or answer is materially wrong — diagnose the
boundary before adding anything.

## Stop rules

- Do not send any company text to a model endpoint (thin journey needs none).
- Do not widen the document set beyond the one licensing journey.
- Do not tick plan S03 or close #27/#58 without process-owner acceptance.
- If the cited answer cannot support the settled operational facts, stop and
  record the failed boundary (source reading / retrieval / explanation).
