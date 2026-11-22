---
summary: "Step 4.1 sandbox proof: 110-passage Colab L4 lease drain, 60s kill-mid-lease recovery, HTTP 409 conflict guard, and $0 cloud relations spend (#664)."
kind: proof
status: current
read-when: reviewing end-to-end Google Colab pull-lease drain behavior, kill-mid-lease recovery, or Step 4.1 verification for issue 664
---

# Google Colab GPU offload Step 4.1 — private Coolify sandbox lease-drain & kill-recovery proof

Executed 2026-11-21 / 2026-11-22 EST against an isolated Coolify sandbox stack running the merged `oracle-brain` image [`f858b6d9`](https://github.com/u2giants/theoracle/commit/f858b6d9a463986e9e0ee27b63fe8a51724977eb) (`ghcr.io/u2giants/theoracle-brain:f858b6d9a463986e9e0ee27b63fe8a51724977eb`, `pgvector/pgvector:pg16`, and `falkordb/falkordb:v4.20.7`). Production (`oracle.designflow.app`, `oracle-brain.designflow.app`) and `oracle-sandbox-private` message custody remained untouched throughout.

## 1. Environment & security boundary (`L1`, `L3`, `L4`)

- **Brain runtime flags:** `BRAIN_COLAB_LEASE_ENABLED=true`, `BRAIN_COLAB_MAX_BATCH_SIZE=64`, distinct bearer secret injected from 1Password `vibe_coding` item `naytnzqu4ldh4t7jutxbx7btzq` (`BRAIN_COLAB_WORKER_TOKEN`, verified unequal to `BRAIN_SHARED_TOKEN`).
- **Zero privileged secrets on Colab (`L1`):** `apps/brain/colab/preflight.py` enforced the forbidden-key block (`DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `BRAIN_SHARED_TOKEN`, `PROD_DIRECT_URL`) and transferred `BRAIN_COLAB_WORKER_TOKEN` via a `0600` ephemeral JSON file unlinked inside the Colab kernel before target code execution (zero secret tokens on `argv`).
- **Seeded workload:** `11` synthetic operational sources × `10` passages = **`110` passages** (`colab_offload = true`, `read_state = 'extracting'`, `220` seeded entity mentions).
- **Cloud-worker skip verified:** Running `relations` and `ensure_chain` jobs in `oracle-brain` skipped all `110` `colab_offload = true` passages with **`$0.00` OpenRouter `relations` API calls**, leaving `GET /colab/status` at `{"lease_enabled": true, "pending_chunks": 110, "active_leases": 0, "completed_chunks_24h": 0}`.

## 2. Kill-mid-lease recovery & concurrent non-overlap proof

With `BRAIN_COLAB_LEASE_TTL_SECONDS=60` configured on the sandbox container to exercise expiry deterministically:

1. **Simulated worker crash (`killed-worker-a`):** Leased `max_items = 64` via `POST /colab/lease` and terminated without calling `POST /colab/submit`. `GET /colab/status` reported `active_leases = 1`, `pending_chunks = 110`.
2. **Concurrent worker disjointness (`concurrent-worker-b`):** Immediately called `POST /colab/lease` (`max_items = 64`) while `killed-worker-a` was still active. `FOR UPDATE SKIP LOCKED` + partial unique index `colab_lease_one_active_chunk_idx` returned the exact remaining **`46` disjoint passages (`overlap = 0`)**.
3. **Automatic lease expiry & re-lease (`recovery-probe-c`):** After `60s` elapsed, the pre-lease expiry sweep marked both stale leases `expired` (`state = 'failed'` on items) and `recovery-probe-c` cleanly re-leased **`64` passages** with zero lost or wedged chunks.
4. **Late-submission clobber defense (`§9a`):** Submitting a late `POST /colab/submit` carrying `killed-worker-a`'s expired `lease_id` returned **`HTTP 409 Conflict`**, leaving active leases and `cmap.extraction` untouched.

After kill-recovery verification, the sandbox container was reset to the production default `BRAIN_COLAB_LEASE_TTL_SECONDS=900` (`15 minutes`, strictly within the 30-minute standing hold ceiling) with all `110` passages pending (`active_leases = 0`).

## 3. Live Google Colab `L4` GPU pull-lease drain

Executed headlessly via `apps/brain/colab/preflight.py` + `apps/brain/colab/drain_leases.py` on a live Google Colab **NVIDIA L4 (24 GB)** runtime (`--max-wall-minutes 25 --max-ccu 2`):

- **Pinned model:** `Qwen/Qwen2.5-14B-Instruct-AWQ` @ `539535859b135b0244c91f3e59816150c8056698` (`trust_remote_code=False`, vLLM V1 `GuidedDecodingParams(json=relations_schema)`).
- **Pull-lease execution trace:**
  - `POST /colab/lease` (batch 1): leased `64` passages → vLLM guided-JSON inference → `POST /colab/submit` `200 OK` (`completed_chunks_24h = 64`, `pending_chunks = 46`).
  - `POST /colab/lease` (batch 2): leased `46` passages → vLLM guided-JSON inference → `POST /colab/submit` `200 OK` (`completed_chunks_24h = 110`, `pending_chunks = 0`).
  - `POST /colab/lease` (batch 3): returned `items = []` (`200 OK`), exiting the worker loop cleanly.
- **Database & validation outcome:**
  - `cmap.colab_lease`: `2` completed leases totaling **`110` accepted chunks** (`0` active leases).
  - `cmap.extraction`: **`110 / 110` rows** written under `stage = 'relations'` with `model = 'colab-vllm/Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698'`.
  - Server-side `validate_response` drop counters: **`quote_mismatch = 0`, `unknown_type = 0`, `truncation = 0` (`100.0%` verbatim quote validation)**.
  - `cmap.source`: all **`11 / 11` sources** automatically transitioned from `extracting` to `read_state = 'read'` and enqueued downstream `resolve` (`cmap.job` verified running).
- **Compute-unit & cloud spend:**
  - **OpenRouter `relations` spend:** **`$0.00`**.
  - **Wall-clock time (including cold `vllm` wheel install + 8 GB model download + 110 passages + teardown):** `494.4s` (`8.24 min`).
  - **Actual Google Colab CCU burn (`L4` at `1.94 CCU/hr`):** **`~0.27 CCU` total** (`~2.45 CCUs` per 1,000 passages including cold start; `<0.5 CCU` per 1,000 passages warm).
- **Runtime & sandbox teardown:** `colab --auth=adc sessions` verified `0` active `L4` assignments post-drain, the ephemeral sandbox OpenRouter key was revoked (`HTTP 404` verified), and all temporary sandbox containers and networks were removed cleanly.
