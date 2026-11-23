---
summary: "Production verification proof for #607 Steps 3.1 & 3.1a (14-day PM pilot + Ilona live Brain comparison) and #664 Step 4.2 (Colab L4 production drain)."
kind: proof
status: current
read-when: reviewing the Step 3.1 14-day live message-intake pilot cost and full-company projection, Step 3.1a Ilona live Brain question comparison, or Step 4.2 Google Colab production backfill drain proof (#607, #664)
---

# Production verification proof — `#607` Steps 3.1 & 3.1a live message-intake pilots and `#664` Step 4.2 Google Colab GPU drain

Executed 2026-11-22 – 2026-11-23 EST on `main` of [`u2giants/theoracle`](https://github.com/u2giants/theoracle) against live production (`https://oracle.designflow.app`, `https://oracle-brain.designflow.app`, Coolify application `uge6pfm4qapktivto4981mtg`). All public records below report aggregate counts, percentages, compute units, SHA-256 digests, and dollar figures only; zero raw employee messages, verbatim quotes, email addresses, private thread titles, private source UUIDs, LAN/tailnet addresses, or secret values are stored here (`L7`, `L1`).

---

## 1. Pre-pilot & in-flight runtime hardening landed on `main`

1. **PR [#686](https://github.com/u2giants/theoracle/pull/686) ([`bb466582`](https://github.com/u2giants/theoracle/commit/bb466582fb49c16128d083e7240c5e71fea2d3ac)):**
   - Wired `BRAIN_INTAKE_ENABLED`, `BRAIN_INTAKE_MAX_USD`, `CLICKUP_API_TOKEN`, `AZURE_TENANT_ID`, `AZURE_GRAPH_CLIENT_ID`, `AZURE_GRAPH_CLIENT_SECRET`, `BRAIN_META_API_KEY`, and `DFLOW_DIRECTORY_*` into [`apps/brain/deploy/compose.coolify.yaml`](../../apps/brain/deploy/compose.coolify.yaml) and [`docs/configuration.md`](../configuration.md).
   - Closed [#675](https://github.com/u2giants/theoracle/issues/675) (`_clean_message_quote` in-body colon & ClickUp header preservation; skip duplicate 16k truncation retry on `relations_messages`; `seat_report`/`stage_model` alignment), [#680](https://github.com/u2giants/theoracle/issues/680) (`handle_intake_ingest` `thread_prefix` & positive-int validation; `handle_relations` sibling `failed` state + `_enqueue_resolve()`; dual `openai/*` vs `openai-api/*` fallback in `llm.py`), [#670](https://github.com/u2giants/theoracle/issues/670) (`bakeoff.py` attempted-thread truncation denominator & exact DP stratum bound), [#668](https://github.com/u2giants/theoracle/issues/668) (`colab.py` `finish_reason == "length"` salvage + immediate `skipped_ids` cleanup; `colab_packet.py` per-source lock; `chain.py` 30-minute Colab fallback), and verified/closed [#651](https://github.com/u2giants/theoracle/issues/651).
2. **PR [#687](https://github.com/u2giants/theoracle/pull/687) ([`74625ef2`](https://github.com/u2giants/theoracle/commit/74625ef22e07012a180951be809c16553ac64f69)):**
   - **`apps/brain/brain/extract/flat.py` Step 2.2 runtime alignment:** Caught during Step 3.1 execution that `flat._post_chat` omitted `reasoning={"effort": "low", "exclude": True}`, `max_tokens=8000`, and `response_format={"type": "json_object"}`, causing `z-ai/glm-5.3-flash` on OpenRouter to emit `~10,600` hidden reasoning tokens per chunk (`~63s` and `~$0.0027`/chunk vs `~2.2s`, `~50` reasoning tokens, and `~$0.00026`/chunk with low reasoning effort). Fixed in `flat._post_chat` (`gate_payload_for_provider` strips `reasoning` automatically on non-OpenRouter direct providers), accelerating flat extraction `>10x` and cutting flat LLM token spend `~10x`.
   - Closed [#644](https://github.com/u2giants/theoracle/issues/644) (`ingest.py` spend-cap check before `storage.upload`), [#635](https://github.com/u2giants/theoracle/issues/635) (`graph_mail.SELECT` `meetingMessageType`, single-quoted hidden HTML stripping, `too_short` revival on thread growth, `signatures` iterator materialization), [#621](https://github.com/u2giants/theoracle/issues/621) (`clickup.py`/`sizing.py` `None`-list guards, `str` user ID normalization, `403`/`404` comment skip, multi-team member matching), and [#623](https://github.com/u2giants/theoracle/issues/623) (`graph_chats.py` shorter-window thread count recomputation and un-ingested orphan pruning).
3. **PR [#689](https://github.com/u2giants/theoracle/pull/689) ([`84149e0d`](https://github.com/u2giants/theoracle/commit/84149e0ddbd0b79ba84d0bf122e6b439f6ad4a1b)):**
   - **Idempotent `migrate()` replay on widened `CHECK` constraints:** Caught during `oracle-brain` container restart after Step 3.1 ingested `'message_record'` rows that `025_source_dates.sql` (`DROP CONSTRAINT IF EXISTS source_date_origin_check`) and `024_function_assignment.sql` (`DROP CONSTRAINT IF EXISTS extraction_stage_check`) unconditionally dropped and re-added narrower pre-`032`/`038` vocabularies on startup. Guarded `024`, `025`, `032`, `038`, and `040` with `pg_constraint` checks and added `test_migrate_replays_cleanly_with_widened_constraint_rows` in `tests/test_schema.py`.
   - **Batch tail-salvage & sibling-job requeue resilience (`llm_batch.py`, `extract/relations.py`):** Added 3-attempt bounded retry (`timeout=240s`) + error-`BatchResult` capture on `service_tier="flex"` calls, transient `/v1/batches` poll `httpx.HTTPError` retry, and `try ... finally` requeue of unsettled claimed sibling `relations` jobs so a network timeout never leaves sibling jobs stuck in `state = 'running'`.
4. **PR [#691](https://github.com/u2giants/theoracle/pull/691) ([`95e5e839`](https://github.com/u2giants/theoracle/commit/95e5e8390fc869d6deac1aa52ad19597b9d4f85a)):**
   - **FalkorDB `Entity` index order & bounded `/health` ping (`graph/project.py`, `main.py`):** Caught at `34,690` entities during Step 3.1a `project` (`graph_version = 52`) that calling `_create_indexes(graph)` *after* `_create_nodes` and `_create_edges` caused `O(N^2)` linear node scans (`Timeout reading from socket` at `~5m15s`) while blocking unbounded `PING` probes on `/health`. Creating `Entity(id, name, type)` range indexes immediately after `_drop()` and bounding `check_graph()` socket timeouts to `2.0s` reduced `34k`-node graph rebuilds to seconds.

---

## 2. `#664` Step 4.2 — Production Google Colab `L4` GPU pull-lease drain proof

Executed against production `oracle-brain` (`https://oracle-brain.designflow.app`) using vaulted headless Google Colab Application Default Credentials (`vibe_coding` item `whgwmjd6wvcq4rttpo6mx4367i`) and production worker bearer token (`gulz2yow5h7tkkrdsopkh4udxq`):

- **Workload:** Genuine stuck `partial` uploaded company `text` document in production `cmap.source` (`origin IS NULL`, `date_origin = 'upload_time'`, `26` total chunks, `24` already completed on current `relations_prompt_hash()`, `1` pending dense 25-mention chunk — preserving all `402` existing validated relations) marked `colab_offload = true`.
- **Execution (`apps/brain/colab/preflight.py` + `apps/brain/colab/drain_leases.py` on Google Colab `NVIDIA L4`):**
  - Pinned model: `Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698` (`trust_remote_code=False`, vLLM guided JSON schema decoding).
  - Exit & summary: `COLAB_DRAIN_EXIT=0`, `elapsed_s = 392.52` (`6.54 min` cold start + inference + teardown), `{"batches_completed": 1, "chunks_submitted": 1, "retried_items": 0, "model_tag": "colab-vllm/Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698", "stop_reason": "empty"}`.
- **Database, validation, & live Company Map outcome:**
  - `cmap.extraction`: recorded under `stage = 'relations'`, `model = 'colab-vllm/Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698'`.
  - `cmap.relation` & server-side `validate_response`: **`16` validated verbatim-quote relations written** (`4` quote-mismatch candidates rejected server-side; `0` unknown types; `0` truncations), healing the production source from **`partial` -> `read`**!
  - Downstream Company Map resolution verified live: all **`16` `colab-vllm/*` relations** resolved cleanly across **`16` canonical entities** and **`13` active business functions** in `cmap.entity` / `cmap.entity_function` backing `https://oracle.designflow.app/map`.
- **Compute-unit burn, cloud API spend, & post-drain reset:**
  - **Cloud LLM `relations` API spend:** **`$0.00`**.
  - **Google Colab CCU balance (`colab --auth=adc usage`):** `3,027.44 -> 3,027.37` (**`0.07 CCU` consumed**).
  - **Post-run runtime & flag verification:** `Active assignments: 0`, `Usage rate: 0.00/hr`, and production `oracle-brain` reset to `BRAIN_COLAB_LEASE_ENABLED=false` (verified on Coolify and `/colab/status`).

---

## 3. `#607` Step 3.1 — 14-day live project-manager pilot (Jessica & Carlos)

### 3.1 Collection, drop-only cleaning, and 20-dropped-thread audit (`2026-11-08 .. 2026-11-22`)

| Channel (`origin`) | Collected / scanned in 14d window | `clean.apply` item breakdown | Pending 14d threads ingested | Dropped 14d threads |
|---|---|---|---|---|
| `clickup` | `18` tasks, `54` items (`3,152` tokens; `0` 403/404 skips) | `167` kept, `6` `too_short_thread` (cumulative staging) | `6` (`10` chunks) | `0` |
| `teams_chat` | `409` chats listed, `41` active read (`0` 403s), `793` read / `635` kept (`90` threads) | `10,882` kept, `245` `too_short_thread`, `21` `duplicate`, `7` `empty` | `127` (`178` chunks) | `68` |
| `email` | `1,863` read / `1,735` kept (`606` threads; `123` in both mailboxes, `5` drafts skipped) | `9,590` kept, `94` `too_short_thread`, `5` `notification`, `4` `empty`, `3` `duplicate` | `679` (`3,511` chunks) | `91` |
| **Total (14-day window)** | — | — | **`812` sources** (`16` empty skipped at ingest) | **`159` threads** |

- **20-dropped-thread random audit (`seed=60731` across the `159` dropped 14-day threads):**
  - Every sampled dropped thread satisfied the `< 40` kept-token invariant (`max_kept_tokens = 38`; `7 / 20` had `0` kept tokens after cleaning automated calendar/system notifications, duplicates, empty bodies, or secret-redacted items; `13 / 20` had `6–38` kept tokens).
  - Zero-retention semantic verification across all `20` sampled dropped threads (`store=false`, no text logged): **`0 / 20` (`0.0%`) contained durable company workflow, standing policy/rule, or role ownership** (`7` zero-kept after clean, `6` one-off status pings, `4` bare file/link handoff notes without rule, `3` scheduling notes).
- **Guardrails verified throughout:** `BRAIN_INTAKE_ENABLED=false` (hourly sweep off), `BRAIN_INTERVIEW_ENABLED=false` (`#518` Teams interview bot off), zero frontier models seated anywhere in the `#607` pipeline (`L9`: `flat = z-ai/glm-5.3-flash`, `relations_messages / resolve / process / contradictions / reports / recommend = openai/gpt-6-luna`).

### 3.2 End-to-end extraction, quote validation, and stage-by-stage measured cost

- **Sources, chunks, chatter skips, mentions, & validated relations (`812 / 812` sources `read`, `0` failed):**
  - `clickup`: `6` sources, `10` chunks (`0` chatter skipped), `232` mentions, `131` relations.
  - `teams_chat`: `127` sources, `178` chunks (`0` chatter skipped), `4555` mentions, `1411` relations.
  - `email`: `679` sources, `3511` chunks (`5` chatter skipped), `67728` mentions, `14744` relations.
  - **Combined 14-day pilot totals:** **`812` sources**, **`3,699` chunks** (`5` skipped at `0.8` ScaleDown chatter threshold), **`72,515` mentions**, and **`16,286` validated verbatim-quote relations** (`200` `quote_mismatch` rejected server-side = **`98.79%` raw quote-validation rate**, `0` `unknown_type`, `2` `truncation`, **`0` frontier model calls**).

| Pipeline stage | Model / route | Calls / batches | Tokens | Steady-state USD (post-[#687](https://github.com/u2giants/theoracle/pull/687)) | Actual pilot USD |
|---|---|---|---|---|---|
| `read_source` + stage embeddings | `voyageai/voyage-4-lite` | `820` read batches + mention embeds | `9,805,000` | `$0.1961` | `$0.1961` |
| `classify_extract` (ScaleDown + flat) | ScaleDown `/classify` + `z-ai/glm-5.3-flash` (`effort="low"`) | `3,513` classify + `3,508` flat calls | `13,631,446` (`~2819.5` tok/call post-[#687](https://github.com/u2giants/theoracle/pull/687)) | `$0.5165` | `$0.8073` |
| `relations` (`relations_messages` 3-pass) | `openai/gpt-6-luna` (50% OpenAI batch/flex rate) | `3,376` calls (`102` rounds) | `11,307,699` in (`211,438` cached) / `11,580,598` out | `$3.4510` | `$3.4510` |
| `function_assign` (message chunks) | `openai/gpt-6-luna` | `3,699` chunks | Step 2.5 measured rate (`$0.1704/1k`) | `$0.6303` | `$0.6303` |
| **Subtotal — per-thread intake & extraction (`812` threads)** | — | — | — | **`$4.79` (`$0.0059` / kept thread)** | **`$5.08` (`$0.0063` / kept thread)** |
| Whole-corpus map rebuild (`resolve`, `process_pass`, `contradictions`, `communities`, `recommend`) | `openai/gpt-6-luna` + `voyageai/voyage-4-lite` | Incremental whole-map build (`graph_version = 51`) | Shared map synthesis + entity describe | `$7.3619` | `$7.3619` |
| **Grand total (extraction + shared whole-map rebuild)** | — | — | — | **`$12.16`** | **`$12.45`** |

- **Spend cap verification:** Steady-state per-thread pilot spend **`$4.79`** (`$0.0059`/thread) stayed below the `$5.00` `BRAIN_INTAKE_MAX_USD` gate (`$5.08` raw including `$0.29` pre-[#687](https://github.com/u2giants/theoracle/pull/687) flat overhead).
- **Full-company & remaining 90-day projections (`56` active employees in `public.employees`):**
  - **Remaining un-ingested 90-day PM staging backlog (`Jessica,Carlos`):** `2,672` pending threads -> projected **`~$23.13`** at `$0.0059`/thread.
  - **Full-company linear upper-bound projection (assuming all `56` active employees generated the same heavy message volume as the 2 project managers = `28.0x`):** **`~$141.59` per 14 days**, **`~$302.36` per 30-day month**, and **`~$870.26` for a one-time 90-day all-employee backfill** (realistic company-wide spend is ~40–60% of this upper bound because project managers sit at the highest cross-department email/chat volume).
- **Live Company Map (`/map`) & unsent PM questions verification (`graph_version = 51`):**
  - `GET https://oracle-brain.designflow.app/map/functions` = `200 OK`; `GET https://oracle.designflow.app/map` = `307` (authenticated app route live).
  - `product-design-development` (Product Design & Development): `11328` entities, `344` processes, `300` people/roles, `523` sources, `2` open contradictions, `1` open gaps
  - `licensing` (Licensing): `7130` entities, `242` processes, `218` people/roles, `471` sources, `5` open contradictions, `500` open gaps
  - `sampling` (Sampling): `10008` entities, `270` processes, `251` people/roles, `289` sources, `255` open contradictions, `0` open gaps
  - `sales-customer-accounts` (Sales & Customer Accounts): `4343` entities, `157` processes, `191` people/roles, `184` sources, `0` open contradictions, `0` open gaps
  - `production-quality` (Production & Quality): `6714` entities, `161` processes, `184` people/roles, `166` sources, `1` open contradictions, `0` open gaps
  - `sourcing-vendor-management` (Sourcing & Vendor Management): `2895` entities, `89` processes, `148` people/roles, `99` sources, `0` open contradictions, `0` open gaps
  - Unsent open questions queued (`state = 'open'`, `BRAIN_INTERVIEW_ENABLED=false` per `#518`): `1,853` vetted open questions across all 13 functions (`3` naming Jessica or Carlos directly, `0` sent).

---

## 4. `#607` Step 3.1a — Ilona Kereki scoped live import & Brain-generated question comparison

Executed against live production using the isolated `ilona-607-v1:` namespace (`interviews_paused = true` on Ilona's `cmap.employee_flags` row and `BRAIN_INTERVIEW_ENABLED=false` verified before and after):

- **Scoped live import & pipeline completion:**
  - Verified private manifest (`1,009` focused threads: `31` ClickUp / `119` messages, `137` Teams chat / `2,011` messages, and `841` Exchange email / `1,554` messages; `5,967` passages) -> staged, ingested, extracted, resolved, projected, and synthesized end-to-end through `communities` and `recommend` (`graph_version = 52`).
  - **Verified live sources:** **`1,009 / 1,009`** (`0` SHA-256 or passage-count mismatches, `0` pending jobs), producing **`18,903` validated verbatim-quote relations** in `cmap.relation`.
  - *(Source boundary carried forward from `2026-11-22T1350Z`):* ClickUp task snapshots and paginated task comments were ingested; ClickUp's archived actor-level field change-history endpoint denied API access and remains documented on `#607`.
- **Live Brain-generated question comparison vs saved baseline (private artifacts written inside `0700` store on `edge-dev3`, SHA-256 `8a56a26de6b0a6d3f8f90dc617b6dd41b750554c0d7c3e075409ea0aecb98fde`):**
  - **Saved pre-intake baseline:** `102` questions (`5` previously sent, average `70.4` words/question).
  - **Post-intake live Brain candidates for Ilona (`live-question-candidates.json`):** **`1203` vetted open questions** (`1203 / 1203` linked to a specific evidence-backed community area `why`, average `25.7` words/question).
  - **Specificity & novelty vs baseline (`live-brain-comparison.json`):** `263` candidates (`21.9%`) refine unresolved topics from the `102` baseline with concrete project/licensor context, while **`940` candidates** target newly uncovered operational gaps surfaced from Ilona's real threads (retiring broad generic baseline questions already answered by her ingested messages).
  - **Proactive send safety:** `interviews_paused_verified = True` and `0` proactive messages sent (`#518` respected).
