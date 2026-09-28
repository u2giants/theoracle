# S01 baseline record

Date: 2026-09-27 EDT. Source revision: `7c47319ecf61b52212094cf3232044fdb19c6836` (S01 base); implementation revision is recorded by the PR that adds this file. Manifest version: public `manifest.schema.json` v1, `synthetic-cases.jsonl` v1. Validator: Python 3.14.4 standard library. Existing comparator source: current Oracle retrieval, reconciliation and business-answer journey at the S01 base revision. Direct long-context comparator: protocol specified, no run.

| Evidence | Result |
|---|---|
| Public synthetic manifest | 20 held-out acceptance, 10 separate development, 12 source/adversarial fixtures; validator passed |
| Missing evidence, uncovered source, relabeled or modified held-out case, split leakage, duplicate content, missing case | Eight regression checks passed |
| Current Oracle live quality | Unavailable; authorized flow and private reviewed cases not established |
| Direct long-context live quality | Unavailable for the same reason |
| Real answer-key process-owner review | Unavailable; Albert Hazan owns review and process-owner assignment; private manifest is pending before real-data comparison |

No accuracy, latency or cost score is inferred from unavailable runs. The private manifest location contract and review owner are specified in `evals/oracle2/acceptance-spec.md`. S03's real-data gate still requires a separately authorized journey and process-owner review. The S09 comparative quality gate uses the frozen A set and must retain its held-out status.
