# W05 — current-source denial and transitive invalidation implemented

Recorded October 11, 2026, 9:01 PM EDT.

Derived artifacts record exact upstream source revisions and optional permission/identity/artifact/event-window/compiler/dependency identities. Transitive invalidation appends deny records before a stale artifact can be served. Exact current original reading and scoped access are rechecked; a graph is never authority. Upload-alias grouping requires identical original/read/parser identities and keeps alias dependencies for authorization.

## Verification and remaining acceptance

Synthetic Postgres transitive invalidation and stale SDK/ledger denial passed. Automatic recomputation scheduling and fresh-store restore of all new artifact types remain open. Alias grouping is an explicit assembly input; an ungrouped extraction is not independent-source acceptance.

Append-only recompute requests are now committed atomically with transitive denial; replay cannot duplicate requests. Current rooted source-steward appointments require an explicitly supplied actor and source scope. Recompute verifies a newly sealed current-source artifact and its projection through the admitted worker callbacks; blocked callbacks leave old artifacts denied. Dependency self-cycles and absent upstream artifacts are rejected. The dedicated artifact outbox now reuses existing leases, verifies the actual finalized SDK projection, signs exact content/source/permission/graph receipts, acknowledges atomically and replays the original immutable receipt. Stale versions and outbox identity rewrites are denied. Hosted scheduling/provider admission and full private backup/restore remain open.
