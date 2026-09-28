# Oracle 2 environment inventory

Status: 2026-09-27 EDT. Only the isolated local and CI environments have
verified runtime credentials. Two synthetic-only Trigger preview projects exist; their first build failed
(see S02-dependencies.md). No production Oracle 2 deployment exists.

| Environment | Verified target | Credential reference and scope | Status |
|---|---|---|---|
| Local/CI synthetic | Loopback Docker Postgres, separate candidate and confirmed FalkorDB, LocalStack S3 | Generated synthetic values in `dev/oracle2/compose.yaml`; candidate, projector, and checkpoint roles are distinct | CI proved stores and role denial in run 36377021295 |
| Legacy Trigger | `proj_wgpzsvhmsopqhvwqaycn` | Existing `Trigger.dev Secret Key - The Oracle (local .env.local)` is an unverified historical reference; no Oracle 2 task uses it | Read-only inventory; not an isolated Oracle 2 target |
| Extractor preview `proj_esmuwkezljvasptkbiwr` | Created 2026-09-28; staging build failed (Python 3.11 image) | Candidate-only graph and Postgres credentials (no object-store endpoint set in S02), no confirmed graph or projector signing key | Needs exact reviewed project and credential provisioning |
| Projector preview `proj_jtaztxnmppzfchdsgvea` | Created 2026-09-28; not deployed after extractor stop rule | Confirmed-only graph and projector Postgres credentials, projection signing key, no candidate graph or source object credential | Needs exact reviewed project and credential provisioning |
| Current Oracle production database | `eqccjfbyrywsqkxxpjvg` per existing inventory | `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)` in `vibe_coding`; no value read or used here | Outside S02 deployment scope |

The local `OpenRouter API Key - The Oracle (local .env.local)` inventory item
is not approval for the replacement's model calls. Primary and fallback model
IDs, exact account/endpoints, processing policy, and a same-corpus evaluation
remain unverified. Synthetic CI uses no vendor model call. This inventory
contains no secrets and grants no permission to use a listed target.
