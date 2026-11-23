---
summary: "Production verification proof for #607 Step 4.1 full-window intake (Jessica Cortazar 90d, Carlos Corral Oct 1+, Laura Arevalo 90d) alongside Ilona Kereki."
kind: proof
status: current
read-when: reviewing the #607 Step 4.1 full-window ingestion counts, 20-thread verbatim quote spot-check, 5 cited live answers, or post-run guardrails
---

# Production verification proof — `#607` Step 4.1 full-window run (Jessica 90d, Carlos Oct 1+, Laura 90d)

Executed 2026-11-23 EST on `main` of [`u2giants/theoracle`](https://github.com/u2giants/theoracle) (deployed SHA [`a2a951e9`](https://github.com/u2giants/theoracle/commit/a2a951e90eea4dabc5f7c58f9aa9f67a01891e66), including PR [#693](https://github.com/u2giants/theoracle/pull/693) omitting subtype-only `meetingMessageType` from Microsoft Graph `/messages` `$select` and PR [#695](https://github.com/u2giants/theoracle/pull/695) skipping full-corpus document similarity scans for message-intake sources). All records below are aggregate counts, percentages, and dollars only; zero raw employee text, quotes, emails, thread subjects, source UUIDs, LAN/tailnet IPs, or secrets appear here (`L7`).

## 1. Owner scope & ruling (2026-11-23 9:47 AM EST, verbatim)

- *"keeping exact word-for-word quotes at $0.0059 per thread. ingest Jessica Cortazar's 90 day activity and go back to Oct 1 for carlos. Also, add 90 days of Laura Arevalo. She is Ilona's counterpart and without her you only have half the picture of the licensing department."*
- Pre-existing un-ingested staging rows from the earlier 90-day `Jessica,Carlos` collection were cleared before re-collection so zero pre-October-1 Carlos-only threads could enter the Brain; all previously ingested pilot (`812`) and Ilona (`1,009`) sources remained intact.

## 2. Collection, drop-only cleaning, & ingest

- **ClickUp:** `14` tasks / `400` items for Jessica + Laura (90d); `28` tasks / `60` items for Carlos (Oct 1+); `0` comment errors; `clean`: `{'kept': 456, 'duplicate': 3, 'secret': 1, 'too_short_thread': 3}`.
- **Teams chats:** `570` chats listed / `144` read / `1` 403 / `13,623` kept messages (`1,055` threads) for Jessica + Laura (90d); `82` chats listed / `23` read / `0` 403 / `4,169` kept messages (`281` threads) for Carlos (Oct 1+); `clean`: `{'empty': 801, 'kept': 12288, 'too_short_thread': 306, 'duplicate': 1283, 'reaction': 38, 'secret': 1}`.
- **Exchange email:** `8,646` read for Jessica (90d), `8,401` read for Laura (90d), `1,067` read for Carlos (Oct 1+) -> `6,771` unique threads (`14,289` unique messages, `3,768` cross-mailbox duplicates collapsed); `clean`: `{'kept': 13140, 'duplicate': 150, 'notification': 915, 'too_short_thread': 1217, 'empty': 122, 'secret': 92, 'reaction': 2}`.
- **Ingest result:** `created = 5,665`, `versioned = 143`, `unchanged = 753` (`sha256` deduped at `$0`), `empty = 8`, `estimated_usd = $25.75` (`stopped_at_cap = false`).

## 3. End-to-end extraction, quote validation, & cost (`graph_version = 54`)

| Origin | Sources | Chunks (0.8 chatter skipped) | Mentions | Validated relations |
|---|---|---|---|---|
| `clickup` | `33` (`33` read, `0` failed) | `68` (`0` chatter skipped) | `1,390` | `392` |
| `email` | `5,102` (`5,102` read, `0` failed) | `15,634` (`19` chatter skipped) | `193,383` | `41,453` |
| `teams_chat` | `673` (`673` read, `0` failed) | `1,187` (`17` chatter skipped) | `31,356` | `9,533` |
| **Step 4.1 total** | **`5,808` (`5,808` read, `0` failed)** | **`16,889` (`36` skipped)** | **`226,129`** | **`51,378`** |

- **Server-side quote validation & zero-frontier check (`L1`, `L9`):** **`97.70%`** raw quote-validation rate (`1,211` `quote_mismatch` rejected server-side, `0` `unknown_type`, `4` `truncation`); extraction models verified: `flat=scaledown/classify` (`16,879`), `flat=z-ai/glm-5.3-flash` (`16,846`), `function=openai/gpt-6-luna` (`16,889`), `relations=openai/gpt-6-luna` (`16,889`) (**`0` frontier model calls**).
- **Measured extraction cost (direct OpenAI standard `GPT-6 Luna` + low-reasoning `GLM-5.3 Flash` + `Voyage 4 Lite`):**
  - Embeddings: `$0.6491`, `classify_extract` (flat): `$9.2155`, `relations_messages`: `$26.1232`, `function_assign`: `$2.8779` -> **`$38.87` total (`$0.0067` / ingested thread)**.

## 4. 20-thread spot-check, 5 cited live answers, live `/map`, & guardrails

- **20-random-thread verbatim-quote spot-check (`seed=60741`):** `20` threads sampled, **`289 / 291` (`99.31%`)** relations verified as exact substrings in their stored source passages.
- **5 live operational questions (`POST https://oracle-brain.designflow.app/answer`, `5/5` `HTTP 200` citing message-derived sources):**
  - Q1: `HTTP 200`, `7` total citations (`2` message-derived: `{'document': 5, 'email': 2}`).
  - Q2: `HTTP 200`, `21` total citations (`20` message-derived: `{'email': 19, 'teams_chat': 1, 'document': 1}`).
  - Q3: `HTTP 200`, `6` total citations (`5` message-derived: `{'email': 5, 'document': 1}`).
  - Q4: `HTTP 200`, `8` total citations (`8` message-derived: `{'teams_chat': 4, 'email': 4}`).
  - Q5: `HTTP 200`, `22` total citations (`21` message-derived: `{'email': 19, 'teams_chat': 2, 'document': 1}`).
- **Live Company Map & unsent open questions (`graph_version = 54`):**
  - `GET https://oracle-brain.designflow.app/map/functions` = `HTTP 200` (`13` functions); `GET https://oracle.designflow.app/map` = `HTTP 307`.
  - Unsent open questions (`state = 'open'`, `BRAIN_INTERVIEW_ENABLED=false`, `sent_since_start = 0`): `6,211` total (`21` Jessica, `19` Carlos, `36` Laura, `39` Ilona).
- **Post-run Coolify `oracle-brain` settings:** Deployed [`a2a951e9`](https://github.com/u2giants/theoracle/commit/a2a951e90eea4dabc5f7c58f9aa9f67a01891e66), `/health` = `200 {"ok": true, "db": true, "graph": true}`, `BRAIN_INTAKE_ENABLED=true`, `BRAIN_INTAKE_MAX_USD=5.00`, `BRAIN_INTERVIEW_ENABLED=false` (`#518`), `BRAIN_COLAB_LEASE_ENABLED=false`.
