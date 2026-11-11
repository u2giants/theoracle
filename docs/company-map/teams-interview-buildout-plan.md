---
summary: "Plan from 2026-11-02 to let every tenant employee feed the Company Map through the Teams bot: inbound capture, follow-ups, weekly tick."
kind: plan
status: open
read-when: working on Teams interview intake or the outbound question tick
---

# Teams interview build-out — implementation plan

Written 2026-11-02 (EST). Owner direction (Albert, verbatim): "we have to build
out the functionality of this system talking directly to employees over Teams".
Tenant ruling (verbatim): "All empployees in our M365 tenant should be able to
access the oracle to feed information in."

## Goal

Employees feed the Company Map by talking to the Teams bot: they can volunteer
knowledge unprompted, the bot asks good follow-ups, and the weekly outbound
question tick runs for everyone in the tenant. Every contribution becomes a
cited `cmap.source` transcript that flows through the normal pipeline.

## What exists today (main at `eb8d0540`)

- Inbound chain: Teams route → `senderProfile` → brain
  `POST /interview/teams/inbound` → `brain/interview/inbound.py`
  `handle_inbound`: match/auto-register the @popcre.com sender, store the
  conversation reference, handle `stop`/`skip`, and turn a reply to an
  **asked** open question into a source. Anything else returns
  `handled: False` and falls through to the join-meeting helper.
- Outbound: `brain/interview/tick.py` hourly tick, gated by
  `BRAIN_INTERVIEW_ENABLED` (off), weekly cap `BRAIN_INTERVIEW_WEEKLY_CAP=2`,
  only to employees with a stored conversation reference.
- Two-way sends work (#325).

Gap: an employee who just tells the bot how something works gets the meeting
help text, and nothing is kept.

## Phases (each its own PR, brain tests + one live Teams proof)

1. **Volunteered knowledge intake.** In `handle_inbound`, when no question is
   pending and the text is not a command or a `join` request, treat a message
   of real content (≥ 12 words, or a reply within an open intake thread) as a
   contribution. Buffer messages per employee in a new
   `cmap.teams_intake(employee_id, started_at, last_at, turns jsonb, state)`
   row; close the thread after 20 minutes of silence or on "done", then ingest
   one transcript source `Teams contribution — <employee> — <date>` with
   speaker turns. Reply acknowledges ("Got it — keep going, or say done").
   Short greetings ("hi", "hello") get a one-line intro that says what the bot
   is for and invites a contribution. Done when: tests
   `test_volunteer_becomes_source`, `test_greeting_gets_intro`,
   `test_join_still_reaches_meeting_helper`; live proof a colleague's message
   appears as a source.
2. **Follow-up questions in the thread.** While a thread is open, the
   conversation model (`BRAIN_CHAT_MODEL`, env only) asks at most two short
   follow-ups grounded in the Map ("who do you hand that to?", "which system
   records it?") using the entity/relation context for names the employee
   mentioned. Bot turns are kept in the transcript so sources stay honest.
   Done when: `test_followups_capped_at_two`, follow-up text cites no
   invented names (judge check in the test with a stub model).
3. **Turn on the outbound tick tenant-wide.** Every auto-registered employee
   with a conversation reference is eligible; keep weekly cap 2, `stop`/`skip`
   as today, quiet hours 8 PM–8 AM EST and weekends. Set
   `BRAIN_INTERVIEW_ENABLED=true` on Coolify only after phases 1–2 are live.
   Done when: tick log shows sends within cap for ≥ 3 employees in a week and
   at least one answer became a source.
4. **Reach employees who never messaged the bot.** Proactive first contact
   needs a conversation reference; use Teams app proactive install for the
   tenant (Graph `installedApps` for users) so the bot can open a 1:1 chat.
   This needs a Microsoft Graph application permission
   (`TeamsAppInstallation.ReadWriteForUser.All`) — the one step that may
   need tenant-admin consent; report it `Blocked —` if the AI cannot grant it.
5. **Visibility.** Map admin page lists recent Teams contributions per
   employee with links to their sources; no new permission system (login +
   `is_admin` only, per plan).

## Constraints

- Model ids from env only (plan §11). No gates on reading. Public repo: no
  tenant ids, emails, or LAN details in docs.
- Never redeploy the brain while a pipeline job runs.
- Each contribution enqueues the normal `read_source` chain; watch the
  OpenRouter $25/day cap when the tick goes tenant-wide.
