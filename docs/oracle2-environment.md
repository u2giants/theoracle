<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob ef97201586bee2b7d28e27cc93fc55c5a951e0a1 at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
# Oracle 2 environment inventory

Status: 2026-09-28 EDT. Only the isolated local and CI environments have
verified runtime credentials. Two synthetic-only Trigger preview projects exist and passed the S02 preview
measurements (see S02-dependencies.md). No production Oracle 2 deployment exists.

| Environment | Verified target | Credential reference and scope | Status |
|---|---|---|---|
| Local/CI synthetic | Loopback Docker Postgres, separate candidate and confirmed FalkorDB, LocalStack S3 | Generated synthetic values in `dev/oracle2/compose.yaml`; candidate, projector, and checkpoint roles are distinct | CI proved stores and role denial in run 36377021295 |
| Legacy Trigger | `proj_PRIVATE_REFERENCE_SHA256_9f596b7f49dd981243eda05436fe11207bc7a91b39b7806c41a831504c04bb01` | Existing `Trigger.dev Secret Key - The Oracle (local .env.local)` is an unverified historical reference; no Oracle 2 task uses it | Read-only inventory; not an isolated Oracle 2 target |
| Extractor preview `proj_PRIVATE_REFERENCE_SHA256_5ac719234cae50874f21f058a58195aea057b037473342b561250e996f9cbf9d` | Created 2026-09-28; staging version 20260928.4 (CPython 3.12.14), measured | Candidate-only graph and Postgres credentials (no object-store endpoint set in S02), no confirmed graph or projector signing key | Provisioned with reviewed synthetic staging values; delete when #26 closes |
| Projector preview `proj_PRIVATE_REFERENCE_SHA256_1be33553a1432811f3b085bbf640ff84aa12c5a94d7f7a822296cdc5d78f8285` | Created 2026-09-28; staging version 20260928.1 (CPython 3.12.14), measured | Confirmed-only graph and projector Postgres credentials, projection signing key, no candidate graph or source object credential | Provisioned with reviewed synthetic staging values; delete when #26 closes |
| Current Oracle production database | `PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d` per existing inventory | `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, PRIVATE_REFERENCE_SHA256_9190ea2866aa7bf92e2806946d58e5728957851544cade4e900fa8436872652d)` in `vibe_coding`; no value read or used here | Outside S02 deployment scope |

The local `OpenRouter API Key - The Oracle (local .env.local)` inventory item
is not approval for the replacement's model calls. Pinned primary and fallback
model IDs and a same-corpus synthetic evaluation under the default-deny
processing policy are recorded in `docs/verification/oracle2/S02-models.md`;
real-data processing approval (account, endpoint, data classes) remains
unapproved until S03. Synthetic CI uses no vendor model call. This inventory
contains no secrets and grants no permission to use a listed target.
