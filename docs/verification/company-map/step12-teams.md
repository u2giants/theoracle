# Step 12 verification — open-question queue and Teams interviews

Recorded 2026-10-30, 1:45 AM EDT, edge-dev3, Claude (implementer). Issue #253.

## 1. Automated gate (done-when tests)

`apps/brain/tests/test_interview.py` — `test_weekly_cap`, `test_stop_pauses`,
`test_answer_becomes_source`, `test_disabled_sends_nothing`, plus
`test_most_connected_person_is_chosen`, `test_skip_reopens_for_someone_else`,
`test_service_routes_need_token`, `test_admin_overview_pause_and_route`.
Local run against the edge-dev3 test Postgres: 8 passed; full brain suite 105 passed.
Browser: `apps/web/tests/map.spec.ts` "open-question page shows queue, history and
per-person pause" passed (3/3 in the file). Screenshot: `step12/questions-page.png`.

## 2. End-to-end proof with real HTTP and live models (throwaway database)

Script: `step12/step12_proof.py` (database `brain_step12`, never the shared test DB).
The real brain API ran under uvicorn; a local stand-in received the proactive call
in place of the Teams send. Then the interview answer went through the real read,
ScaleDown flat extraction, OpenRouter relations/resolve and community rebuild.

| Check | Result |
|---|---|
| Tick before the employee ever messaged the bot | asked 0, unrouted 1, nothing sent |
| Employee's first message | conversation reference stored; message falls through to the join command |
| Hourly tick | 1 question routed to the most-connected Person ("Jessica"), proactive call carried the exact plan message text and the shared token |
| Employee answer | reply "Thanks, that's recorded."; source `Interview answer — Jessica — 2026-10-30` (kind transcript); question state `answered` |
| Pipeline on the answer | 2 chunks (Oracle turn, employee turn); mentions incl. Marco, Legal, "checks his queue on Fridays" |
| Rebuild | resolve 2 frontier calls / 910 tokens; project 22 nodes / 13 edges; communities 25 reports (8 reused), 17 frontier calls / 22,999 tokens, 0 failed |
| Community report update | findings citing the interview answer: before 0, after 56 (e.g. "Marco only checks approval queue on Fridays, creating bottleneck adds approximately one week delay") |

## 3. Manual proof with Albert's own Teams account — NOT yet done

The plan asks for Albert to message the bot from his own Teams account. That needs
the brain hosted where the Vercel app can reach it (`BRAIN_BASE_URL`), which is
step 14 (Coolify). Until then the Teams path cannot reach a brain, and the locked
guardrail keeps `BRAIN_INTERVIEW_ENABLED=false`. No real employee was messaged.
This manual check is carried to step 14's first run; record it here with
screenshots when done.
