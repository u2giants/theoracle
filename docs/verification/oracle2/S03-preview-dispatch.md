# S03 real-data preview dispatch — exact inputs for independent technical review

Status: **pending review** (revision 4, 2026-10-04 EDT). Revisions 1–3 were
REJECTED (last: `20261001T182245-1505817-15927`) including a Critical on
publishing process/answer-key content (now private) and High on substituting
memory grants for S02 authority. This revision is at a head that uses
**store-backed** `oracle2.appointments` authority (`apps/web/lib/oracle2-authority.ts`,
merged in PR #61). Nothing here runs before a `VERDICT APPROVE` whose record
names **this** reviewed commit and this path.

Purpose: the leftover-proof gate on [#58](https://github.com/u2giants/theoracle/issues/58)
/ [#27](https://github.com/u2giants/theoracle/issues/27) — one isolated,
explicitly authorized real-data preview journey, reviewed by its process owner
(Ilona, licensing workflow) using the S01 rubric. Synthetic offline proof is
already green (CI `36644212614`, 11/11). This dispatch does **not** authorize
production settings, production writes, public meeting joins, or employee
messages.

## Preconditions

- Task class declared in the reviewed worktree.
- Reviewed commit is the worktree HEAD (`git rev-parse HEAD`); re-request
  review if it changes after APPROVE.
- No new cloud account, paid tier, Trigger project, Supabase project, or vendor
  key is created or modified.
- Representative source is a **process table** (allowed by plan S03
  “PDF/table or diagram”), not free-form essay text: `step_id | owner | action |
  handoff_to | exception` rows for one licensing process.

## Company-data processing admission (before any real-data step)

Plan `plan_oracle_consultant_overhaul.md` §Company-data processing admission
requires this **before** any real-data preview, even when no vendor model is
called.

1. **Organizational approval on record:** Albert Hazan, 2026-09-28 EDT
   (settled): “All data can be shared with all AI providers.” Process owner:
   Ilona. Purpose: `s03-real-data-preview`. Data class:
   `licensing-operational-process` (sanitized process-table rows only).
2. **Outbound calls in this dispatch:** none. Thin pilot answers from uploaded
   spans; `provider_policy.dispatch` is not invoked. Any model/extraction/
   embedding/OCR/tracing call requires a **new** dispatch with a full
   `ProcessingApproval` (`services/oracle-brain/oracle_brain/provider_policy.py`).
3. **Private processing register** (body never committed):
   `C:\Users\ahazan\.local\share\mimocode-private\oracle2\S03-processing-register.md`
   — record the approval quote, purpose, data class, retention (evidence
   deleted when plan S03 is accepted or owner directs), no training beyond the
   settled sharing authorization, no residency change. Publish on #58 only the
   reference path and SHA-256.
4. Re-check the register immediately before the real journey.

## Authorized real-data source and answer key (settled; do not re-ask)

Source: one sanitized **process table** for a licensing workflow process owned
by Ilona (process owner). Exact company process steps, private source text, and
the graded answer key live only in the private processing register / evidence
directory — never in this public repository (`plan…` public-repo rule;
`evals/oracle2/acceptance-spec.md` private-equivalent rule).

Answer-key **location only** (not contents): the private register named above,
section “S01 answer key”. Ilona’s dated operational practice is already on
record in a separate private/durable business-rule home and is used only as the
grading key.

Do **not** copy private contract text, employee identity, process-step wording,
answer keys, or raw asset filenames into this public repository, issues, or
model logs.

## Actions

1. **Approval record before any run** — post on #58: reviewed commit SHA, this
   path, approving review file + `VERDICT` line, processing-register path +
   SHA-256, journey scope (Ilona / licensing / DCP withdrawal / process table).
   No step 2 before that comment exists.
2. **Isolated preview environment** — from the reviewed commit, start
   `@oracle/web` on `http://127.0.0.1` only. Bind loopback. No public hostname,
   no Vercel production change. Set preview-only env:
   - `ORACLE2_DATABASE_URL` — isolated store as role `oracle2_pilot_web`
     (SELECT on `oracle2.appointments`, journey-row writes; **not** admin) from
     `dev/oracle2/compose.yaml` on CI/edge-dev3 Docker; local scoop Postgres is
     known-unstable and is **not** an accepted journey store
   - `ORACLE2_PILOT_WORKSPACE_ID` — fixed pilot workspace UUID
     `00000000-0000-4000-8000-000000000002`
   - `ORACLE2_PILOT_TOKEN` (random secret, not committed; private evidence dir)
   - `ORACLE2_PILOT_ACTOR=00000000-0000-4000-8000-000000000003` (UUID matching
     bootstrap `--actor`; body identities ignored)
   Bootstrap once on that store (not production) with
   `oracle_brain.bootstrap_pilot_authority` using an **admin** connection
   (`oracle2_admin`) — required inputs: `--workspace`, `--owner`,
   `--appointed-by` (≠ owner), `--appointment-id`, `--actor` (pilot UUID),
   `--owner-signature-hex`, `ORACLE2_OWNER_PUBLIC_KEY`, and admin
   `ORACLE2_DATABASE_URL`. All appointment writes are one transaction. The web
   app connects only as `oracle2_pilot_web` (SELECT appointments). Compose init
   scripts run on **first volume init only**; use a fresh volume or apply
   `init-postgres.sql` + `grant-postgres.sql` as admin on an existing store.
   The web app never uses an admin connection.
3. **Browser-test gate (required before real data)** — run
   `tests/oracle2/pilot.spec.ts` against that server (`ORACLE2_PREVIEW_URL`).
   All tests must pass, including 401 without session/token and fail-closed
   authority when the store is unreachable. Record the summary in the private
   evidence directory.
4. **Authority-backed journey** — process-owner UI uses S02-backed checks:
   - Actor comes only from server env allowlist. Body `actorId` fields are
     ignored.
   - Token missing/wrong → 401. Missing session → 401.
   - `correct` → 403 without store-backed `review`; `confirm` → 403 without
     store-backed `confirm` (`has_authority` SQL lineage on
     `oracle2.appointments`, same as `authz.py`).
   - Capture one 401 and one 403 in private evidence.
   - Companion: `test_authority.py` (forged actors, out-of-scope grants,
     revoked parents, expired delegates, revocation racing confirmation).
5. **Run one real-data journey** on the process table
   (upload → source-linked draft → **correct one connection** → scoped
   confirm → one **connected** question → cited answer + one explicitly
   hypothetical improvement). The corrected edge appears as
   “Process-map connections in scope”. Unrelated map neighbors are labeled
   “Process-map context only (not established answer evidence)” and are **not**
   cited as facts. Connected question wording lives in the private register.
6. **Private evidence controls** — only under
   `C:\Users\ahazan\.local\share\mimocode-private\oracle2\S03-evidence\`:
   - Owner: this session’s operator on this machine account.
   - Access: local user only; not in git; not on shared drives; not emailed.
   - Retention: delete when plan S03 is accepted or owner directs.
   - Contents: browser-gate summary, 401/403 negative, draft, correction,
     confirmation, answer, citations, hypothetical, connection line, token
     location reference (not the token in GitHub).
7. **S01-rubric review package** — blinded packet for the process owner
   (question, permitted spans, date/scope, output). Score **each** dimension in
   `evals/oracle2/acceptance-spec.md`: fact correctness, mandatory exceptions,
   citation support, temporal/customer scope, usefulness, clarity; improvement
   contract (observed vs hypothesis vs measure vs missing inputs). Ilona is the
   named grader. **Any failed dimension fails the journey.** Dispute reviewer
   (second reader before any aggregate score): the assigned independent AI
   reviewer already used for this dispatch, acting read-only on the blinded
   packet — not a new human hire and not an agent contact to Ilona.
8. **Sanitized result artifact** — `docs/verification/oracle2/S03-pilot.md`:
   date EST, commit, register ref + SHA-256, browser-gate result, authority
   negative, connection line, per-dimension pass/fail, citation resolution,
   fact vs hypothetical, process-owner outcome, private evidence directory
   reference only.
9. **Acceptance gate** — plan S03 ✅ only when every scored rubric dimension
   passes **and** the process owner accepts the cited answer. Then close #27
   and #58, retire the predecessor S03 baton under the successor rule, and only
   then name S04 (#28) next on #24.

## Out of scope

- Production deploy/writes, Trigger prod, Vercel prod, employee messages,
  public meeting joins.
- New Trigger projects; model evaluation; cheaper-model work; S04 lifecycle;
  OCR containers.
- Agent contact with Ilona or any person; grading uses the owner’s existing
  relay path.

## Rollback

Stop the local server. Delete private evidence/secret file if the owner
directs. No cloud resource is created. A failed journey is recorded as failed;
plan S03 stop-rule applies if the process map or answer is materially wrong.

## Stop rules

- No company text to any model endpoint.
- Do not widen beyond the one process-table journey.
- Do not tick plan S03 / close #27/#58 without full rubric pass and
  process-owner acceptance.
- If browser tests fail, fix and re-run before any real-data step.
- If token/authority gates do not refuse unauthorized callers, stop and fix
  the gate before claiming the journey.
