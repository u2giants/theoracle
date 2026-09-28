# Oracle 2 environment inventory

Status: 2026-09-28 EDT. Only the isolated local and CI environments have
verified runtime credentials. Two synthetic-only Trigger preview projects exist and passed the S02 preview
measurements (see S02-dependencies.md). No production Oracle 2 deployment exists.

| Environment | Verified target | Credential reference and scope | Status |
|---|---|---|---|
| Local/CI synthetic | Loopback Docker Postgres, separate candidate and confirmed FalkorDB, LocalStack S3 | Generated synthetic values in `dev/oracle2/compose.yaml`; candidate, projector, and checkpoint roles are distinct | CI proved stores and role denial in run 36377021295 |
| Legacy Trigger | `proj_wgpzsvhmsopqhvwqaycn` | Existing `Trigger.dev Secret Key - The Oracle (local .env.local)` is an unverified historical reference; no Oracle 2 task uses it | Read-only inventory; not an isolated Oracle 2 target |
| Extractor preview `proj_esmuwkezljvasptkbiwr` | Created 2026-09-28; staging version 20260928.4 (CPython 3.12.14), measured | Candidate-only graph and Postgres credentials (no object-store endpoint set in S02), no confirmed graph or projector signing key | Provisioned with reviewed synthetic staging values; delete when #26 closes |
| Projector preview `proj_jtaztxnmppzfchdsgvea` | Created 2026-09-28; staging version 20260928.1 (CPython 3.12.14), measured | Confirmed-only graph and projector Postgres credentials, projection signing key, no candidate graph or source object credential | Provisioned with reviewed synthetic staging values; delete when #26 closes |
| Current Oracle production database | `eqccjfbyrywsqkxxpjvg` per existing inventory | `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)` in `vibe_coding`; no value read or used here | Outside S02 deployment scope |

The local `OpenRouter API Key - The Oracle (local .env.local)` inventory item
is not approval for the replacement's model calls. Pinned primary and fallback
model IDs and a same-corpus synthetic evaluation under the default-deny
processing policy are recorded in `docs/verification/oracle2/S02-models.md`;
real-data processing approval (account, endpoint, data classes) remains
unapproved until S03. Synthetic CI uses no vendor model call. This inventory
contains no secrets and grants no permission to use a listed target.
