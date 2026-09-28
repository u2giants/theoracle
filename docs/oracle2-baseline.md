# Oracle 2 baseline protocol

The current Oracle comparator is its existing retrieval and business-answer journey, including `searchWithRetrievalPlan`, eligible relationship claims and the final answer reconciliation/review. The direct long-context comparator receives the same authorized source revisions and the same permission-filtered material, but reads that material directly rather than using Oracle retrieval. Neither comparator gets extra source text, a different as-of date or broader access.

For every private case, record source revision hashes, principal/permission snapshot, question, as-of time, model/provider settings, prompt version, output, citations, elapsed time and cost in approved private evidence storage. Freeze both inputs before either run. Randomize output labels for process-owner review. Report per-category pass counts, abstentions, citation resolution, unsupported claims, omitted exceptions, and unavailable runs. Never enter `0` for an unavailable result. Keep real text, participant identity and answer keys outside the public repository.

Current live baseline availability: **unavailable**. No exact authorized production test flow, scoped private manifest, process-owner reviewed keys or verified access were established in S01. The local business-answer journey is a network-free contract guard, not a model-quality measurement. No production test messages were sent. The public synthetic manifest is ready for an isolated harness and later comparative runs; it makes no current accuracy claim.

Reproduce the synthetic manifest gate with `python3 scripts/oracle2/validate_manifest.py --synthetic`. The S01 result and versions are in `docs/verification/oracle2/S01-baseline.md`.
