# Teams two-way communication — what it took (2026-11-02)

The owner asked the bot "hi" from his own Teams account and asked for a reply
back through Teams to prove both directions work. Three stacked problems stood
in the way; each is fixed and merged. This file records what they were, what
changed, and the live proof.

## The three blockers

1. **The sender's identity did not match the employee record.** Teams
   identifies people by their work address (`albert@popcre.com`) while
   `public.employees.email` held a personal address, and the intake matched on
   that one column. The message reached the bot (it answered with the
   meeting-join helper) but the interview intake matched nobody and recorded
   nothing.
2. **A tenant employee with no row could never be recorded at all.** Most
   people in the company had no `employees` row, so their messages could not
   be stored even with perfect matching.
3. **The write-back path refused to run while interviews are off.** The
   conversation-reference lookup (what lets the system write into a Teams
   chat) raised 409 whenever the outbound interview switch was off — which it
   is, on purpose. That also blocked every direct reply, including tests.

Interviews (the bot asking employees questions) stay OFF per standing
direction. Nothing here turns them on; the ask tick still gates itself.

## What changed

| PR | Change |
|---|---|
| [#318](https://github.com/u2giants/theoracle/pull/318) | The intake now matches senders on `employees.email` **or** any linked `employee_identities.email` (the table already carries per-provider emails). |
| [#320](https://github.com/u2giants/theoracle/pull/320) | A first Teams message from an unknown **@popcre.com** sender auto-registers a minimal employee row (display name from the Teams profile) so the conversation is recorded. Non-tenant addresses never auto-register — identity hygiene, not a permission system (the plan allows login + `is_admin` only). |
| [#325](https://github.com/u2giants/theoracle/pull/325) | The conversation-reference lookup is ungated (404 only for an unknown employee). The outbound ask tick keeps gating itself on the interviews switch. |

Owner ruling implemented along the way (2026-11-02, verbatim): "all emails in
the system should be @popcre.com emails. All empployees in our M365 tenant
should be able to access the oracle to feed information in." The owner's own
employee email was normalized to the @popcre.com address.

## How the two directions work

**Inbound (employee → Oracle).** Microsoft Teams delivers the message to the
Bot Framework endpoint
[`apps/web/app/api/teams/bot/messages/route.ts`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/api/teams/bot/messages/route.ts):
the bot resolves the sender's profile (email + display name) and offers every
message to the brain's `POST /interview/teams/inbound`
([`apps/brain/brain/api/interview.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/interview.py)).
There
[`apps/brain/brain/interview/inbound.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/interview/inbound.py)
matches the sender (any linked identity email), auto-registers unknown
@popcre.com senders, and stores the conversation reference in
`cmap.teams_conversation` — the only way to write back later. It then handles
"stop" / "skip" / answers to asked questions (answers become `cmap.source`
transcripts that flow through the normal pipeline). Anything it does not
handle falls through to the meeting-join helper reply.

**Outbound (Oracle → employee).** `POST /api/teams/bot/proactive` on the web
app (same route file's sibling
[`apps/web/app/api/teams/bot/proactive/route.ts`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/api/teams/bot/proactive/route.ts))
takes `{employee_id, text}` with the shared service token, fetches the stored
conversation reference from the brain's
`GET /interview/teams/conversation/{employee_id}`, and sends through the Bot
Framework adapter (`continueConversationAsync`) into that same chat. When no
reference is stored (Teams never delivered a conversation update and the
employee never opened the chat — 11 install-wave employees were stuck this
way), the route opens the 1:1 chat itself (`createConversationAsync`), stores
the new reference with the brain, and sends. The
brain's interview tick
([`apps/brain/brain/interview/tick.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/interview/tick.py))
uses this route for its questions and refuses to send while the interviews
switch is off — that gate is unchanged.

## Live proof (2026-11-02)

- **Inbound:** the owner's "hi" from Teams produced
  `cmap.teams_conversation` row "Albert H. · albert@popcre.com · updated
  2026-11-02 19:58:44 UTC" — the message is recorded against the employee.
- **Outbound:** `POST /api/teams/bot/proactive` with the owner's employee id
  and the test text returned `{"sent": true}`; the message arrived in his
  Teams chat: "Two-way communication check: this is The Oracle writing back
  into your Teams chat. If you can read this message, the reply path is
  working end to end."

## Reproducing a send

Anyone with the shared service token can write into an employee's Teams chat
(messaged the bot before or not — without a stored reference the bot opens
the 1:1 chat itself):

```
POST https://oracle.designflow.app/api/teams/bot/proactive
x-brain-token: <BRAIN_SHARED_TOKEN>
{"employee_id": "<uuid from cmap.teams_conversation>", "text": "message"}
```

Returns `{"sent": true}` on success; `404 not_reachable` when no Teams chat
can be opened for the employee (no matching tenant user, or the account
cannot receive Teams).

## Constraints preserved

- Interview question-asking stays disabled (`BRAIN_INTERVIEW_ENABLED=false`
  and the admin page switch); only the reply path opened.
- No permission system beyond the plan's login + `is_admin`; tenant
  auto-registration is identity hygiene scoped to @popcre.com addresses.
- Regression tests: `tests/test_interview.py` (`test_work_email_matches_identity_row`,
  `test_tenant_sender_auto_registers`, `test_personal_sender_is_not_auto_registered`,
  `test_conversation_lookup_works_while_interviews_off`).
