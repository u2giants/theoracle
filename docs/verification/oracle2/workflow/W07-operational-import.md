# W07 — strict synthetic export ingestion implemented; actual export unavailable

Recorded October 11, 2026, 9:01 PM EDT.

Separate authorized event imports preserve exact raw bytes, explicit activity/process/scope mapping, original timestamps/zones, import/window/mapping hashes and private quarantine. CSV/XES limits reject oversized input, duplicate headers, invalid encoding/entities and unsupported object-centric correlation. Duplicate IDs quarantine all affected rows; invalid/out-of-window rows censor their cases. Naive time needs an explicit timezone; ambiguous/nonexistent local times are quarantined. Missing tie order never becomes an invented sequence. Atomic import manifest/index/outbox replay is covered.

## Verification and remaining acceptance

Synthetic event tests pass, including trace-level XES case inheritance, offsets, daylight transitions, duplicate quarantine, censoring, scoped import denial and raw-export replay verification. No admitted company export exists in this session. Actual data usefulness stays unavailable, with owner on #27/#58.

## Authenticated import path — October 12, 2026, 12:00 AM EDT

The real browser route, scoped source authority, opaque action record, fresh worker and immutable event ledger passed with an invented authoritative CSV. The route rejected a body over its 4 MiB web transport bound; the underlying parser retains its separately bounded contract. Completion reads recheck actor, exact selected release, process, current source revision and scoped import authority. Replaying the identical import preserves the same raw bytes and identity. Actual company exports and their acceptance remain unavailable.
