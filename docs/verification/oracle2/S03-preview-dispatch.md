# S03 real-data preview dispatch — exact inputs for independent technical review

Status: **pending review** (revision 3, 2026-10-01 EDT). Revision 1 was
REJECTED (`20261001T161933-1000779-31397`). A follow-up snapshot of the old
head was also REJECTED (`20261001T162959-1042914-14354`) for free-text stand-in
documents, corrections not affecting answers, caller-supplied identities, loose
evidence ownership, and no browser gate. This revision is at a new head that
includes connection-aware answers, pilot token + actor allowlist auth, a
process-table source, and an explicit browser-test gate. Nothing here runs
before a `VERDICT APPROVE` whose record names **this** reviewed commit and this
path.

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

Source: one sanitized **process table** for the Disney DCP Vault
artwork-withdrawal confirmation practice **settled from Ilona, 2026-09-25**
(relayed by Albert; durable rule in `popcre/shared-db`
`docs/business-rules/licensing-master-data.md`, provenance
`popcre/shared-db#3347`). Rows cover: monitor style-guide assets; identify
removal on UPDATED; manual POP removal as confirmation; creation-time sunset
date as alternate signal; explicit non-inference of legal rights from portal
absence.

Answer key (S01 fact correctness / mandatory exceptions): no formal notice in
the normal path; UPDATED + manual removal; **or** creation-time sunset date;
portal absence is **not** confirmed withdrawal and **not** legal entitlement.

Do **not** copy private contract text, employee identity, or raw DCP asset
filenames into this public repository, issues, or model logs.

## Actions

1. **Approval record before any run** — post on #58: reviewed commit SHA, this
   path, approving review file + `VERDICT` line, processing-register path +
   SHA-256, journey scope (Ilona / licensing / DCP withdrawal / process table).
   No step 2 before that comment exists.
2. **Isolated preview environment** — from the reviewed commit, start
   `@oracle/web` on `http://127.0.0.1` only. Bind loopback. No public hostname,
   no Vercel production change. Set preview-only env:
   - `ORACLE2_PILOT_TOKEN` (random secret, not committed; stored only in the
     private evidence directory)
   - `ORACLE2_PILOT_ACTOR=pilot-user` (single configured actor; body identities
     are ignored)
   - `ORACLE2_PILOT_SCOPES=review,confirm`
   The token is **not** browser-bundled. The UI takes it in a password field;
   `POST /api/consultant/session` checks token + allowlist and issues an
   httpOnly session cookie bound to that actor. Scopes `review`/`confirm` are
   granted only after that check. Body-supplied identities are ignored. GET
   runs and all mutating consultant APIs require the session. The pilot store
   remains in-process memory; no hosted store is provisioned.
3. **Browser-test gate (required before real data)** — run
   `tests/oracle2/pilot.spec.ts` against that server (`ORACLE2_PREVIEW_URL`).
   All tests must pass, including the negative test that mutating APIs return
   401 without a valid pilot token. Record the run summary in the private
   evidence directory. This gate has never been in offline CI; it must pass
   live before the real journey.
4. **Authority-backed journey** — process-owner UI must use the S03 authority
   path:
   - Actor comes from the authenticated request (`x-oracle2-actor-id` must be
     on `ORACLE2_PILOT_ACTORS`); body-supplied identities are ignored.
   - Token missing/wrong → 401; unknown actor → 403; `correct` without `review`
     scope → 403; `confirm` without `confirm` scope → 403.
   - Capture one rejected unauthenticated confirm (401/403) in private
     evidence.
   - Offline companion already green: `test_authority.py`.
5. **Run one real-data journey** on the process table
   (upload → source-linked draft → **correct one connection** → scoped
   confirm → one **connected** question → cited answer + one explicitly
   hypothetical improvement). The corrected connection must appear in the
   answer’s “Process-map connections in scope” line and a connected block must
   be among the citations (connection boost in retrieval).
   Connected question: *When artwork disappears from the DCP Vault, what do we
   treat as confirmed withdrawal, and what must we not infer?*
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
