---
summary: "Step 2.2 results for GLM-5.3 Flash and two ScaleDown Extract configurations on the private intake reference."
kind: proof
status: done
read-when: choosing the message intake flat extractor or continuing issue 607
---

# Message intake flat extraction verification

**Decision**. Retain GLM-5.3 Flash for message intake. Both ScaleDown Extract configurations cost less and fell short of the required recall. No model-selection or production changes were made.

The Coolify sandbox verified the step 2.1 manifest and reused the archived GLM responses for the same packed passages. The held-out set contained 30 threads, 57 passages and 328 distinct verified mention anchors drawn from accepted relationship endpoints. The other 20 threads used for tuning supplied 38 passages. No held-out passages were used to choose the six entity descriptions changed for the tuned configuration.

Precision was reviewed blind for 50 randomly sampled typed mentions per run, with 223 unique mentions across the five samples. The interval shown counts ambiguous cases first as incorrect, then as correct. These are adjudication ranges for the sample. The recall denominator covers the verified anchors and does not count every mention in the threads.

| Extractor | Run | Verified mentions found | Recall | Precision sample range | Cost for 57 passages | Rejected requests |
|---|---:|---:|---:|---:|---:|---:|
| GLM-5.3 Flash | 1 | 316 / 328 | 96.3% | 72–90% | $0.044067 | 0 |
| ScaleDown Extract, current | 1 | 202 / 328 | 61.6% | 68–80% | $0.002684 | 6 |
| ScaleDown Extract, current | 2 | 198 / 328 | 60.4% | 64–76% | $0.002642 | 7 |
| ScaleDown Extract, tuned | 1 | 181 / 328 | 55.2% | 66–88% | $0.002496 | 10 |
| ScaleDown Extract, tuned | 2 | 188 / 328 | 57.3% | 68–86% | $0.002650 | 7 |

ScaleDown costs use reported input tokens at the published rate, before any free credits. The GLM figure uses the archived provider-reported cost. [ScaleDown pricing](https://www.scaledown.ai/).

The recall gate required at least 307 verified mentions, or 97% of GLM's 316. Even if the rejected ScaleDown requests had returned every otherwise missed anchor they contained, the best ScaleDown result would be 240 of 328. All four ScaleDown runs remained below the recall gate in the paired, thread-resampled comparison. Precision could not change the selection.

The source reference, prediction sets, precision decisions and verified manifest remain in the private Coolify sandbox. [Aggregate issue record and manifest checksum](https://github.com/u2giants/theoracle/issues/607#issuecomment-7027642220).
