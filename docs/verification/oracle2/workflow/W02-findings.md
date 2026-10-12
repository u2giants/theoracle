# W02 — locally implemented ledger; acceptance remains open

Recorded October 11, 2026, 9:01 PM EDT.

Strict source receipts, occurrence-preserving observations and supported typed findings are sealed in private blobs. Postgres atomically records manifest, source/observation history, dependency rows and the separate projection outbox. Failed extraction remains durable and cannot serve. Scoped review appends history; it cannot promote legacy descriptions to facts. Conservative provider reservations enforce per-attempt, batch and New York daily ceilings before dispatch. No new private provider call occurred.

## Verification and remaining acceptance

Crash/replay, source access revocation, tampering, unsupported conflicts, failed-receipt reload, current authority and bounded provider adapters passed synthetic tests. Production role/race review, private extraction audit and hosted recovery remain open.
