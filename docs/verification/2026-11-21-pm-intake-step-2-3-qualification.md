---
summary: "Step 2.3 protected blind-review calibration, live call-shape variant and fallback results, and 350-thread forecast for issue 607."
kind: proof
status: current
read-when: reviewing message-intake relation qualification, blind-review calibration, or call-shape variants for issue 607
---

# Message intake step 2.3 qualification and blind-review check

No eligible L8 candidate, provider batch route, call-shape variant, or failure-only L8 fallback cleared the step 2.3 quality gates. Selection stopped under the plan's stop rule without falling back to a frontier model (L9). Production seats, database state, and intake flags were untouched.

## Custody, artifact digests, and 350-thread design verification

Checks ran inside `oracle-sandbox-private` (`quote-tools`, isolated Docker networks only, zero host port bindings) after read-only Coolify observer verification. All prerequisite manifests and sealed inputs matched their recorded SHA-256 digests:

- Step 2.1 reference manifest: `54809ee73480a1b91a05c69bb4c9d8d0b074ceace17cedd6b677c9812c611c82`
- Step 2.2 verification manifest: `ba0a75e691909432852a6871db64ea1473552598ce3e5d6af9a481d1ee6dcf07`
- 12-route blind packet manifest (`5,313` novel claims, `72` hidden controls, `1,063` second checks): `9d2f69be67b49af8dc08861fbfb6727334f372776889cff998196ba38ce06325`
- Luna batch reconciliation aggregate: `843c4f14f898f9e5c5959a63b82223136595f5ebb26393d6e7ff723254e26278`
- 350-thread expansion selection manifest: `4325180c2c273804ae3f345edd486728b11aff48a6a2590ce223c4b1c7eab9dd`
- 350-thread expanded source (`200` added threads, `801` turns): `eeec797996e49dbb1d8a23fd73219a68f9b698a9976f1b249285a28d8ca4dbfd`

Independent set checks confirmed `50` tuning threads, `150` initial held-out threads (`30` initial + `120` reserve), and `200` newly drawn held-out threads (`350` held-out total), with `0` overlap across all three splits. Conditioning on the initial draw and excluding tuning (`641`-thread target frame), maximizing zero-event hypergeometric probability across the remaining strata reproduces `P(0 | K = 5) = 7.47%` and `P(0 | K = 6) = 4.42%`, confirming the exact `5 / 641` (`0.78%`) 95% upper truncation bound when zero first-attempt truncations occur across all `350` held-out threads (`apps/brain/brain/intake/bakeoff.py`).

## Protected blind-review calibration (Track A)

Prior automated adjudicators missed hidden controls largely because `106` of `220` (`48.2%`) step 2.1 `reject` items lacked a byte-verbatim substring in a single raw source turn (`exact_source_evidence = false`), while `low`-effort graders evaluated normalized windows without per-turn structure.

Inside the ZDR-guarded `oracle-pm-intake-sandbox` workspace (`Oracle 607 no retention` guardrail; discount, I/O, and broadcast logging off; per-request `zdr = true` and `data_collection = deny`; zero raw or masked text in tool output), we built a two-stage non-author adjudicator (`protected-review-20261121`) using only the four permitted L8 models (`openai/gpt-6-luna` on `azure`, `anthropic/claude-haiku-5.5` on `google-vertex/global`, `deepseek/deepseek-v4.1-flash` on `fireworks/us`, and `z-ai/glm-5.3-flash` on `fireworks/us`, replacing the retired `z-ai/fp8` ZDR tag):

1. **Stage 1a (synthetic + 50-thread tuning check, `$0.028285`):** Deterministic single-turn verbatim quote gate plus `medium`-effort structured rubric checks (`c_boiler`, `c_type`, `c_scope`, `c_fact`) reached `7/8`–`8/8` on synthetic perturbations and `83.3%`–`91.7%` inter-family binary agreement across `48` tuning claims (`luna` vs `haiku`: `91.7%` binary, `83.3%` exact).
2. **Stage 1b (one-shot blind test on the 72 sealed packet controls, `$0.146877`):** Preregistered before reading control verdicts (`prereg_sha256`: `23b6c42f7aa23b1f53de9df44fcce6b997f2e37fd5d9e8e5006e57a0d1c64e1b`), requiring `0` unresolved items, `>= 60/72` (`83.3%`) binary accuracy, `<= 6/48` (`12.5%`) false-keep on `not-keep`, and `<= 2/24` (`8.3%`) false-keep on `reject`. Source-first thread ledgers, primary non-author verdicts (`R1`), distinct second non-author verdicts (`R2`), and third-family tie-breaks (`R3`) were sealed prior to scoring (`sealed_verdicts_sha256`: `08449b42c2d93465f1219a7cfb8af25388e5e9d764d1dc7bc6b2fe18a2a9c065`; `report_sha256`: `bcfa36cad57b00935150d28298b97f802e6b030319c0ab540a9983030bc31b08`):

| Reviewer arm | Unresolved | Binary match / 72 | Exact 4-way / 72 | False keep on `reject` / 24 | False keep on `correct` / 24 | Missed `keep` / 24 | Preregistered gate |
|---|---:|---:|---:|---:|---:|---:|---|
| Lead non-author (`R1`) | 0 | 54 (75.0%) | 49 (68.1%) | 2 (8.3%) | 7 (29.2%) | 9 (37.5%) | Fail (`< 60/72`) |
| Settled 3-family (`R1+R2+R3`) | 0 | 52 (72.2%) | 47 (65.3%) | 1 (4.2%) | 10 (41.7%) | 9 (37.5%) | Fail (`< 60/72`) |

Deterministic turn-quote gating plus structured rubric checks cut false accepts on `reject` controls from `60.0%` (`9/15` in prior strict runs) down to `4.2%` (`1/24`), with `0` unresolved items, but L8 models still disagreed with human/lead scope narrowing (`keep` vs `correct`) on ~33% of borderline claims. Per the handoff rule, automated novel-claim verdicts were rejected for qualification scoring.

## Live call-shape variants, batch fallbacks, and gate results

All four planned call-shape variants and L8 failure-only fallback pairs were evaluated on the `30` held-out threads (`57` passages) using `validate_response`, `10,000` whole-thread stratified resamples (`seed = 60723`), and both step 2.1 adjudicated correctness and optimistic **best-case correctness** (counting `100%` of unjudged novel claims as `keep`, penalizing only known step 2.1 `correct`/`reject` claims). Live ZDR runs for variants `(b)` and `(c)` are sealed under `variants-and-forecast-20261121` (`receipt_sha256`: `0e8b4e91eecf70faf00d5858eda7ca3ad5f7447d1ffd5a8e0f36de925d132866`).

| Route / variant | Quote valid, est / 95% LB | Adjudicated correctness, est / 95% LB | Best-case correctness, est / 95% LB | Exact gold links / 944 | First trunc / malformed | USD / 1,000 passages | Gate outcome |
|---|---|---|---|---:|---:|---:|---|
| GPT-6 Luna, OpenAI native batch | 98.93% / 97.28% | — | 96.07% / 93.28% | — | 0 / 0 | $0.5143 | Fail (quote, correctness) |
| GPT-6 Luna, OpenRouter pinned batch | 97.24% / 96.24% | — | 95.90% / 94.83% | — | 0 / 1 | $0.5743 | Fail (quote, correctness) |
| Claude Haiku 5.5, native batch | 100.00% / 100.00% | — | 96.24% / 93.70% | — | 0 / 0 | $0.6331 | Fail (correctness) |
| GLM-5.3 Flash, archived sync | 95.58% / 93.19% | 42.79% / 39.68% | 42.79% / 39.68% | 189 | 0 / 1 | $0.6161 | Fail (quote, correctness) |
| GPT-6 Luna, variant (b) joint `<400` tok | 98.65% / 96.98% | 73.77% / 68.34% | 80.52% / 77.14% | 257 | 0 / 0 | $1.1572 | Fail (quote, correctness) |
| Claude Haiku 5.5, variant (b) joint `<400` tok | 100.00% / 100.00% | 37.80% / 34.77% | 49.71% / 45.80% | 137 | 0 / 0 | $1.3057 | Fail (correctness) |
| GLM-5.3 Flash, variant (b) joint `<400` tok | 94.94% / 92.03% | 42.28% / 38.99% | 50.58% / 46.43% | 156 | 0 / 0 | $0.6565 | Fail (quote, correctness) |
| DeepSeek 4.1 Flash, variant (b) joint `<400` tok | 99.66% / 99.37% | 44.52% / 41.71% | 55.60% / 50.02% | 239 | 0 / 0 | $2.5875 | Fail (correctness) |
| GPT-6 Luna, variant (c) wider 4-passage ctx | 98.51% / 96.50% | 60.42% / 54.81% | 75.16% / 58.22% | 238 | 0 / 0 | $1.1023 | Fail (quote, correctness) |
| Claude Haiku 5.5, variant (c) wider 4-passage ctx | 100.00% / 100.00% | 35.73% / 31.30% | 52.79% / 35.51% | 138 | 0 / 0 | $1.2346 | Fail (correctness) |
| GLM-5.3 Flash, variant (c) wider 4-passage ctx | 94.38% / 92.60% | 49.39% / 41.62% | 62.52% / 44.88% | 167 | 0 / 0 | $0.6992 | Fail (quote, correctness) |
| DeepSeek 4.1 Flash, variant (c) wider 4-passage ctx | 99.83% / 99.46% | 50.51% / 44.26% | 67.31% / 47.60% | 247 | 0 / 0 | $2.4275 | Fail (correctness) |
| Fallback: Luna native batch → Haiku native batch (2 replaced) | 100.00% / 100.00% | 71.43% / 50.43% | 95.94% / 92.61% | 154 | 0 / 0 | $0.5713 | Fail (correctness) |
| Fallback: GLM Flash → Haiku native batch (17 replaced) | 100.00% / 100.00% | 44.34% / 40.40% | 59.42% / 55.86% | 182 | 0 / 0 | $0.8003 | Fail (correctness) |
| Fallback: GLM Flash → Luna sync (18 replaced, archived) | 99.53% / 99.16% | 51.33% / 46.92% | 51.33% / 46.92% | 255 | 0 / 1 | $0.9670 | Fail (correctness) |

- **Variant (a) (`< 2` flat mentions skip):** Previously verified; removes `1` of `57` calls, loses `0`–`3` exact matches, and leaves all correctness bounds below `95%`.
- **Variant (d) (`95%` 3-gram near-duplicate recurring digest screen):** Screened across all `50` tuning threads (`77` passages) and all `350` held-out threads (`867` passages); found `0` duplicate pairs at `95%` similarity (`0` tuning pairs and `1` held-out pair at `85%`), saving `0.0%` of calls.

Because every eligible L8 single route, call-shape variant, and fallback pair falls below the `95%` correctness lower bound even when granting `100%` of unjudged novel claims, paid extraction on the `200` added held-out threads was not dispatched.

## 350-thread packed sizing and expansion cost forecast

Packing all `350` held-out threads (`241,733` stored tokens) produces `867` passages (`57` in `initial_30`, `379` in `reserve_120`, and `431` in `added_200`). Using measured per-passage rates on the same packed distribution, completing a qualified route across the `431` added passages (or all `867` held-out passages) is forecast at:

| Candidate route | Measured USD / 1,000 | Added 200 threads (`431` passages) | Full 350 held-out threads (`867` passages) |
|---|---:|---:|---:|
| GPT-6 Luna, OpenAI native batch | $0.5143 | $0.2217 | $0.4459 |
| GPT-6 Luna, OpenRouter pinned batch | $0.5743 | $0.2475 | $0.4980 |
| GLM-5.3 Flash, sync | $0.6161 | $0.2656 | $0.5342 |
| Claude Haiku 5.5, native batch | $0.6331 | $0.2729 | $0.5489 |
| GPT-6 Luna, sync | $1.1058 | $0.4766 | $0.9587 |
| Claude Haiku 5.5, sync | $1.1986 | $0.5166 | $1.0392 |
| DeepSeek 4.1 Flash, sync | $2.3402 | $1.0086 | $2.0289 |
