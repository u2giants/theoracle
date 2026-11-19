# Plan: the interview bot understands replies and acts on them (agent reply step)

Written 2026-11-18 (EST) by the #604 delivery session (Claude, edge-dev). Issue:
https://github.com/u2giants/theoracle/issues/604. Registering handoff:
[HANDOFF.d/2026-11-19T0200Z-edge-dev-claude-interview-agent.md](HANDOFF.d/2026-11-19T0200Z-edge-dev-claude-interview-agent.md).
Parent plan (the serial conversation this builds on, built and live):
[plan_interview_conversation_rebuild.md](plan_interview_conversation_rebuild.md).

## STATUS

**A fresh session starts at the first ⬜ row.** Update a row when its step lands, citing a
commit, test path or run id.

| Step | What | State | Evidence |
|---|---|---|---|
| 1 | Directory lookup (`find_person`) | ✅ done 2026-11-18 | `apps/brain/tests/test_interview_agent.py::test_find_person_returns_both_duplicate_names` (prefix match, Teams-reachable first) |
| 2 | Agent loop in the composer (tool calls, then one decision) | ✅ done 2026-11-18 | `apps/brain/tests/test_interview_agent.py::test_agent_looks_up_then_refers`; live model check on Albert's chat returned refer to Jennifer Chaffier |
| 3 | `refer` decision: hand the question to the named colleague | ✅ done 2026-11-18 | `apps/brain/tests/test_interview_agent.py::test_agent_looks_up_then_refers`, `::test_refer_to_unlooked_up_id_is_rejected` |
| 4 | "I don't know" replies go through the agent too | ✅ done 2026-11-18 | `apps/brain/tests/test_interview_agent.py::test_dont_know_naming_a_colleague_refers`, `::test_dont_know_without_a_name_still_asks_who_would_know` |
| 5 | Referred question opens with who sent it | ✅ done 2026-11-18 | `apps/brain/tests/test_interview_agent.py::test_referred_question_opens_with_referrer` |
| 6 | Tests, PR, merge, deploy, live proof in Albert's chat | ⬜ open | — |

## 1. The ultimate goal

Albert (owner, POP Creations) is interviewing staff through the Oracle's Teams bot so the
Company Map learns how the business really works. Today the bot's AI reads each reply but can
only pick one of a few fixed moves (follow up, next question, reword, close). When Albert wrote
"ask Jen", the bot had no way to act on it: it saved the words as an answer. Albert's words:
"we're not at a place of intelligence and understanding. how do we go one level deeper".

When this is done, the bot behaves like a sensible human interviewer: it works out what a
reply means and acts on it with real abilities — look a colleague up in the staff directory,
hand the question to them (saying who suggested them), ask which person when a name is
ambiguous, follow up, move on, reword, or close. The only fixed rules are safety rules:
never invent a person, never message someone outside the directory, never send twice, respect
the weekly cap and pauses. **If a step conflicts with this goal, the goal wins — stop and flag it.**

## 2. What this application is

`u2giants/theoracle` monorepo. `apps/brain` is a Python 3 (uv, FastAPI, psycopg) worker that
runs jobs from `cmap.job`; it is deployed on Coolify (`https://coolify.designflow.app`,
application uuid `uge6pfm4qapktivto4981mtg`, image tag env `BRAIN_IMAGE_TAG` = merge SHA, image
built by the "Brain image" GitHub workflow on main). Database: Supabase Postgres (schemas
`cmap`, `public`). The Teams bot web side lives in the Next.js app and is not touched here.
The interview code is `apps/brain/brain/interview/`, prompts in `apps/brain/brain/prompts/`.

## 3. What triggered this

Albert's live chat (conversation `dcb04ba8-f347-4e81-97c6-e0c184527f82`, 2026-11-18). He asked
whether telling the bot "go ask someone else" makes it find and ask that person. It does not:
`inbound._conversation_message` classifies the reply (`answer`/`dont_know`/…); an answer is
ingested and `converse.compose_next` can only return `followup`, `next_question` or `close`
(`converse.py` `ACTIONS`). A `dont_know` reply gets the fixed "Who would know?" and whatever the
employee says next is treated as another answer.

## 4. Scope

In: directory lookup tool, a small tool-call loop in the composer, a `refer` decision that
re-targets the current question to a directory employee, routing `dont_know` replies through the
agent, a referral intro on the colleague's opening message, en + zh-CN strings, tests.

NOT in this plan: changing the reply classifier (`inbound.classify_reply`); free-text questions
written by the model to a colleague (the colleague only ever gets the stored question); referring
to people outside `public.employees`; merging the duplicate "Jen Chaffier"/"Jennifer Chaffier"
directory rows (data fix, reported on #604); Teams web changes; scheduling ("ask me tomorrow").

## 5. Current state

Live (merge `cd269a67`, deployed 2026-11-18): serial conversation, send-once key in `_send`,
clarify with retry, sentence-start name fix. `tick.select_target` (tick.py ~228) already honours
`open_question.target_employee_id` as a manual pick and skips `skipped_by`; `tick.reachable_employees`
applies pause + weekly cap. `conversation.release_question` puts an asked question back to `open`.
Nothing of this plan exists yet.

## 6. Key findings

- Directory: `public.employees(id, email, name, role, department, departments, locale, disabled_at)`.
  Names repeat (two Chaffier rows), so lookup must return ids and let the agent disambiguate.
- A question whose `target_employee_id` is set is routed only to that employee by the next tick,
  if reachable (tick.py `select_target`, "manual" branch). So "refer" = release the question
  from the current employee (skipped) and set `target_employee_id` to the colleague.
- `release_question` clears `target_employee_id`; refer must set it after releasing.
- `followup.invented_names` guards names; lookup results must be added to the allowed text.

## 7. Rejected approaches

- **Keyword rules ("ask X" → refer):** exactly the static-rules trap Albert rejected.
- **Provider-native tool calling:** `post_chat_with_rescue` handles model rescue/fallback across
  OpenRouter models; native tool schemas vary per model. A JSON protocol (`{"tool": ...}` or a
  final decision) works with every model and the existing `_call`/`parse_model_json`.
- **Letting the model write the question for the colleague:** an unchecked model message to a
  third person; the stored question is sent instead.
- **Pre-matching directory names in code and handing a list to the model:** still a script; the
  model should decide when to look someone up.

## 8. Decisions

Locked (2026-11-18, this plan): JSON tool protocol, at most 3 tool calls then a forced decision;
refer only to an employee id returned by `find_person` in the same run, never the current
employee; refer only the current question; colleague gets the stored question with a fixed
localized intro naming the referrer; cap/pause respected by the existing tick (a referral can
wait). Open: wording of the reply to the referrer (model writes it, name-checked).

## 9. Steps

1. **`find_person`** — `converse.find_person(conn, query) -> list[dict]` (new): case-insensitive
   match on any word of `employees.name` (and full name), `disabled_at IS NULL`, max 5, each
   `{employee_id, name, role, department, in_teams: bool}` (`in_teams` = a `cmap.teams_conversation`
   row exists). Gate: `test_find_person_returns_both_duplicate_names`. `helper-ok` (fully named);
   stop-and-ask if the SQL needs a new index or table.
2. **Agent loop** — in `compose_next`: prompt gets a TOOLS section; model returns either
   `{"tool":"find_person","query":"..."}` or the final decision. Loop ≤3 tool calls, appending
   `TOOL RESULT` blocks to the prompt; results' names join `allowed_names`. Existing retry and
   fallback remain. Gate: `test_agent_looks_up_then_refers`. `lead-only` (decides production
   messages).
3. **`refer`** — new action in `ACTIONS`/`_check`: requires `employee_id` from this run's lookup
   results and ≠ current employee, and a current `question_id`. `run_interview_reply` then:
   `release_question(skipped=True)`, `UPDATE open_question SET target_employee_id=%s,
   why = why || ' [referred by <name>]'`, record `meta.referred_to`, send ONE message: the
   model's text (e.g. "Thanks — I'll ask Jen Chaffier.") followed by the next queued question
   (kind `question`, that question's id) or, with nothing queued, the close string (kind `close`). Ambiguous lookup → the model asks which one
   (followup; names allowed). Gate: `test_refer_retargets_question_and_moves_on`,
   `test_refer_to_unlooked_up_id_is_rejected`. `lead-only`.
4. **dont_know through the agent** — the `dont_know` branch calls the agent first; a `refer`
   is executed, anything else keeps today's behaviour (fixed "who would know", then move on).
   Gate: `test_dont_know_naming_a_colleague_refers`. `lead-only`.
5. **Referral intro** — tick opening: if `why` contains `[referred by X]`, prefix
   `strings.referred_intro` ("{name} suggested you'd know this.") — en + zh-CN. Gate:
   `test_referred_question_opens_with_referrer`. `helper-ok`; stop-and-ask if the opening send
   code differs from tick.py ~650.
6. **Land** — interview suites green, PR, merge, image, deploy, live: Albert writes "ask Carlos"
   style reply; DB shows question `target_employee_id` = colleague and the reply turn. `lead-only`.

## 10. Tests

New in `apps/brain/tests/test_interview_agent.py` (names above). Must stay green:
`tests/test_interview*.py tests/test_inbound_zh.py tests/test_replay_interview.py`, run with
`DATABASE_URL=postgresql://oracle:oracle@localhost:5433/brain_test`.

## 11. Constraints and gotchas

Branch + PR, never push main; no hard-coded model names; every new user string in en and zh-CN
(`strings.py`); files mix CRLF/LF — preserve endings, never `ruff format` the tree; prompt text
is data-fenced (`<<< >>>`); do not touch the reply classifier; production is read-only except the
deploy.

## 12. Access

Secrets by 1Password location only: vault `vibe_coding`, item `qcuyabwseaptvuzvtjejffi2ou`
field `oracle_session_pooler` (DB), item `u3aqw63jqnkmnziip3gp5hwb5m` (Coolify token), via
`op_run`. `gh` authenticated as u2giants.

## 13. Done, risks

Done = rows 1–6 ✅ with evidence, deployed SHA verified, live referral visible in the DB, #604
evidence comment. Risks: model refers on a vague mention (guard: lookup id required; colleague
still gets only the stored question); referral to a capped person waits — acceptable. Rollback:
redeploy previous `BRAIN_IMAGE_TAG` (`cd269a6781aabf2774fa0377ebc6d7a44a0f1cee`).

## Self-audit

1. A fresh session can execute it: goal §1, files/functions and gates §9, access §12. Yes.
2. Background and dead ends carried: §3, §6, §7. Yes.
3. Goal clear enough to steer: §1 states the human-interviewer standard and safety-only rules. Yes.

## Lead launch prompt

```
Read plan_interview_agent.md STATUS, then §1 and §9. You are the lead. Do steps 2, 3, 4, 6
yourself; hand steps 1 and 5 to your helper. Your helper is your own tool's smaller model —
Haiku (high effort) for Claude Opus, Luna (high) for Sol, GLM Flash for GLM MAX, Mimo Flash for
Mimo Pro. Never a full-strength model. Rules: https://github.com/popcre/ai-devops/blob/main/templates/system/model-tier-delegation.md
The helper returns finished work or an evidenced blocker, makes no design decisions, merges and
posts nothing, asks you when a stop-and-ask trigger fires, and is taken back after 30 minutes
stuck. You run every gate in §10 yourself.
```
