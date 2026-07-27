# R2 Responsibilities Gate

Date: 2026-07-27

Status: **IN PROGRESS. Local deterministic contracts pass. Live/model gates are not yet proven.**

Pinned fixture manifest:

- Source: `Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`
- Size: 16,945 bytes on disk.
- SHA-256: `398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`
- Expected dominant shape: `responsibilities`.
- Prior segmentation evidence: 5 chunks and 15 mixed process/responsibilities/ruleset segments.
- Answer-key version: `licensed-team-responsibilities-v1`, pinned at
  `apps/workers/src/__fixtures__/licensed-team-responsibilities-v1.json` with 30 explicit
  role-action-object records.

## Implemented and proven locally

- Strict flat responsibility schema requires one role-action-object record per responsibility.
- Every accepted record points to one covered chunk in the same document.
- Quotes use the shared deterministic source policy. Invalid quotes are dropped with bounded
  diagnostics. Covered same-document cross-segment quotes are accepted and counted; foreign and
  segmentation-uncovered chunks are rejected. Diagnostics retain policy, method, alternate-policy,
  cross-segment, root/cascade, bounded quote, and bounded raw-output audit fields.
- Accepted records persist in the generic source map as `shape=responsibilities`,
  `elementKind=responsibility`, with typed role/action/object/trigger/system fields.
- The shape registry supplies the extraction directive, primary coverage denominator, typed detail
  validation, and merge prompt fragment.
- Candidate semantic keys are responsibility-specific and never authorize identity.
- Proposal input hashing covers immutable map ID, base version, prompt/model version, map refs,
  claims, and semantic keys.
- Create guards turn exact namespace collisions and plausible existing matches into
  `needs_review`.
- A one-record change validates as one bounded `update_responsibility` operation.
- Shadow proposals store evidence quotes and operations for read-only admin rendering.
- The worker resolves the configured `model_merge` route and ordered pool, calls the strict merge
  schema through `OracleAIClient`, and persists context-pack, model-run, usage, and attempt records.
- Existing-object shortlisting uses exact namespace plus compatible semantic, owner, and top-domain
  signals. Current version IDs and durable element keys gate confirm/refine operations.
- R2 intentionally does not add embedding similarity to this shortlist. Exact namespace plus
  deterministic semantic, owner, and top-domain signals are the approved low-risk first slice;
  embeddings remain a later measured enhancement, not an implied current behavior.
- Only evidenced candidates enter merge. Up to 10% may remain as explicit unevidenced omissions;
  create verdicts must dispose every evidenced candidate through an operation or model omission.
- Automatic dispatch runs only after deterministic responsibility coverage reaches 90% and the
  merge flag is enabled. Same-input persistence serializes on a transaction advisory lock.
- `business_model_apply_enabled=false` is enforced inside the transaction service. Shadow proposals
  also carry `applyEligible=false` and are rejected even if the global flag changes.
- No migration was required. R1 already provides every R2 storage field and constraint.

## Commands and results

- `pnpm --filter @oracle/ai typecheck`: pass.
- `pnpm --filter @oracle/engines typecheck`: pass.
- `pnpm --filter @oracle/workers typecheck`: pass.
- `pnpm --filter @oracle/web typecheck`: pass.
- `pnpm --filter @oracle/engines verify:r2-responsibilities`: pass.
- `pnpm --filter @oracle/workers verify:r2-responsibilities`: pass.
  This includes ordered primary/fallback model-route injection, success provenance callback,
  production payload exclusion, dispatch threshold, stable concurrency lock, 90% evidence
  coverage, version-target, cross-segment, answer-key pin, and dual apply-lockout contracts.
- `pnpm --filter @oracle/workers verify:source-workflow-read`: pass.
- `pnpm --filter @oracle/workers verify:r0-reader-validator`: pass.
- `pnpm --filter @oracle/engines verify:r1-cross-shape`: pass.
- `pnpm --filter @oracle/engines verify:macro-first`: pass.
- `pnpm --filter @oracle/workers verify:document-ingestion-fallback`: pass.

## Unproven release gates

- The pinned `Licensed Team Responsibilities 2 - tagged.txt` answer key has not been run through the
  new pass-2 reader, so the required 90% responsibility recall is not yet proven.
- The fixture has not completed map-directed claim extraction, so 90% valid evidence-claim coverage
  is not yet proven.
- The responsibilities read and model-merge bake-off has not run.
- Role/owner/department/system resolution passes its local registry contract and retains honest raw
  names when unresolved. It has not been measured against the pinned fixture or live registry.
- No real shadow proposal has been written. Create, same-map redispatch, sequential reread confirm,
  near-match review, doctored refine, and live namespace collision remain deterministic fixture
  proofs only.
- The read-only admin rendering typechecks, but its desktop and narrow-width visual gate has not run
  against a real shadow proposal.
- The swimlane regression is green locally, but the new responsibilities reader has not been
  deployed or tested against live data.

No production data, deployment, commit, push, or database setting was changed by this work.
