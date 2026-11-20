---
summary: "Step 2.3 archive replay results for four relations candidates and the GLM-to-Luna fallback in the private intake sandbox."
kind: proof
status: current
read-when: continuing the message intake relations comparison for issue 607
---

# Message intake relations comparison

All four archived candidates and the GLM-to-Luna fallback missed the 95% correctness gate. Luna led at 65.79%. Granting every withheld claim, its 95% upper bound was 70.03%. Step 2.3 stays open for the remaining variant and recall work. The 15-question comparison requires a qualifying candidate. Production was untouched.

## Evidence and scoring

The comparison used 57 passages from the 30 preregistered held-out threads in the private Coolify sandbox. The sandbox verified both earlier manifests, all 37 files they enumerate, the frozen source hash and the blinded pool hash. It replayed the relation and quote validators from main at `1313df44` and reproduced the archived attribution for all 1,920 lead-adjudicated claims. The 1,006 separately flagged quotes were outside the scoring sample.

Correctness counts distinct validated claims judged correct as written. Narrower corrections, rejections and withheld claims are excluded from the numerator. Quote validation counts raw relation items whose quote the application matcher locates. That matcher also accepts whitespace and quotation-mark normalization. Exact quote results are shown separately. The coverage column counts exact matches among 944 accepted reference claims and one verified omission. The 51 source-first observations can overlap those claims. Semantic equivalence and recall still need blind adjudication.

The comparison used 10,000 whole-thread resamples within the preregistered source and length strata, weighted by inverse selection probability. Threshold comparisons use one-sided 95% bounds. A 100% resampled bound reflects a sample with no observed misses. For zero first-reply truncations, the conservative one-sided upper bound treats the 30 threads as independent units.

| Candidate | Correctness, estimate / lower bound | Exact matches / 945 | Quote validation, estimate / lower bound | Exact quote, lower bound | Archived sync USD / 1,000 passages |
|---|---:|---:|---:|---:|---:|
| GPT-6 Luna | 65.79% / 57.07% | 358 | 98.58% / 96.81% | 96.76% | $1.106 |
| Claude Haiku 5.5 | 35.35% / 31.91% | 128 | 100.00% / 100.00% | 100.00% | $1.199 |
| GLM-5.3 Flash | 42.79% / 39.68% | 189 | 95.58% / 93.19% | 89.28% | $0.616 |
| DeepSeek 4.1 Flash | 44.80% / 42.12% | 284 | 99.65% / 99.35% | 99.35% | $2.340 |
| GLM → Luna on response or validation failure | 51.33% / 46.92% | 255 | 99.53% / 99.16% | 94.70% | $0.967 |

No first reply truncated in the corrected archive across 436 held-out passages per candidate, including 57 on the adjudicated sample. The sample upper bound was 9.50% against the 1% ceiling. Superseded failure records were outside that corrected-route calculation. The GLM scoring set had one malformed first reply and one successful retry. The other three had no malformed first replies. Synchronous costs include the recorded scoring attempts and retries for relations. Batch charges were unverified.

The GLM-to-Luna replay replaced 18 passages, one for a malformed reply and 17 for a quote or relation validation failure. It charged both attempts on replaced passages. A fallback triggered only by the malformed reply reached 43.12% correctness at $0.632 per 1,000 passages.

## Call variants

- Skipping passages with fewer than two mentions removed one call per candidate. Luna lost three exact reference matches, Haiku and DeepSeek lost one each, and GLM lost zero.
- The offline screen found 11 short threads eligible for a joint call. Even granting every reference match in those threads, the highest exact coverage would be 466 of 945 under the measured configuration for the other threads.
- A wider three-passage window would affect eight calls in two threads. Even granting every reference match in those threads, the highest exact coverage would be 585 of 945 under the measured configuration for the other threads.
- The same-origin near-duplicate screen at 95% normalized text similarity found zero pairs. No threads were dropped.

Joint and wider-context results are eligibility and sensitivity estimates. Fresh model replies and blind adjudication for those variants remain open. No model configuration was selected. Later model-dependent work remains gated on step 2.3.

The private aggregate and fallback receipts have SHA-256 digests `0dcccb54632b662b2f96d269028f7cdecaf1c2dc1c8e70079b13b72a3b75c498` and `48f042639a60da086d1c3491f4cf37af70873d43b364d00811ea63807317a5ed`. [Issue verification](https://github.com/u2giants/theoracle/issues/607#issuecomment-7041282853).
