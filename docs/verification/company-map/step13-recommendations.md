# Step 13 verification — recommendations

Recorded 2026-10-30 2:07 AM EDT, edge-dev3, Claude (implementer). Issue #254.

Gate: `apps/brain/tests/test_recommend.py` (7 passed incl. `test_fixture_licensing_stall_recommendation`, `test_no_numbers_without_metric_source`, `test_dedupe`); full brain suite 113 passed; `apps/web/tests/map.spec.ts` 4 passed (new recommendations page test, screenshot 07).

Live run (throwaway copy of the step-12 fixture map, live OpenRouter frontier + embeddings, `run_recommend`):

```
recommend: {"candidates": 5, "recommendations": 5, "duplicates": 0, "failed": 0, "capped": false, "frontier_calls": 5, "frontier_tokens": 11885}
--- Licensor sign-off creates a bottleneck in the licensing approval process, blocking purchase orders. The company has only one Licensing Manager (Jessica) who handles compliance review, submission to licensors, and recording sign-offs.
  explanations: 4 | incomplete: True
  options: 5 | no change: True
  percents in options: []
  experiment metric: Measure the elapsed days from artwork package submission (step 4.1) to sign-off recorded in Artwork Log (step 4.4) for 20 consecutive approvals, comparing before and after the change. | baseline_needed: True
--- Purchase orders cannot be created until the single Licensing Manager (Jessica) records licensor sign-off in the Artwork Log, creating a bottleneck that stalls the approval process.
  explanations: 4 | incomplete: True
  options: 4 | no change: True
  percents in options: []
  experiment metric: Time in hours from licensor approval receipt to sign-off recorded in Artwork Log, measured separately for Jessica-handled and newly-authorized-person-handled approvals. (the metric must be measured first) | baseline_needed: True
--- The licensing approval process requires the Licensing Manager to personally record every sign-off in the Artwork Log before purchase orders can be created, creating a single-person bottleneck.
  explanations: 4 | incomplete: True
  options: 4 | no change: True
  percents in options: []
  experiment metric: Time in hours from licensor approval receipt to sign-off recorded in Artwork Log, and count of data entry errors requiring correction. (the metric must be measured first) | baseline_needed: True
--- Licensor sign-off creates a bottleneck in the approval process because the Buyer cannot create purchase orders until the Licensing Manager records the sign-off date in the Artwork Log.
  explanations: 4 | incomplete: True
  options: 5 | no change: True
  percents in options: []
  experiment metric: Days from concept package submission to purchase order creation, measured before and after the change. | baseline_needed: True
--- The Licensing Manager is a single point of failure for recording licensor sign-offs, creating a bottleneck that delays purchase order creation and downstream work.
  explanations: 4 | incomplete: True
  options: 4 | no change: True
  percents in options: []
  experiment metric: Time (in hours) from licensor approval in the Licensing Portal to sign-off date recorded in the Artwork Log, measured for each approval. | baseline_needed: True
```

All 5 qualifying findings produced a recommendation with 4 explanations incl. 'data is incomplete', 4-5 options incl. 'no change', no percentages. Note: the 5 problems are close paraphrases of the same stall but scored below the plan's 0.9 cosine, so none were merged; the threshold is the plan's and was not changed.
