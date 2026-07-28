# R2 Responsibilities Gate

Date: 2026-07-28

Status: **BLOCKED. The third live reader scored 19/30 (63.3%), below the 90% gate.**

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
- Answer-key matcher `field-aware-v3` preserves exact matches and permits only deterministic,
  field-aware specialization: exact role, compatible action phrase, complete expected object-token
  coverage, and no negation change. Matching is exclusive and stable: one actual record can credit
  only one expected row, with exact matches ranked first. It reports per-answer evidence and rejects
  role swaps, object substitutions, unrelated one-token overlap, and negation flips.

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

## Earlier release gate evidence

- Production fixture document `79b0f629-4d42-4c8f-b6ad-e1e1dcf8befe` produced validated map
  `ebd13d54-215f-4bed-9d3c-14c63df4b624`, model run
  `3bea7c04-0316-4378-99a7-8a3a9a58d141`, and context pack
  `cc0fae90-b992-4d6a-9ebb-1f9515d6404d`. It covered 5/5 chunks and retained 98 responsibility
  records across three responsibility segments with zero responsibility drops.
- The old exact-string scorer reported 0/30 because harmless model phrasing changes could never
  match the terse answer key. That was a scorer failure, not proof of reader failure.
- Instrument history: exact-string v1 reported 0/30 (scorer failure); non-exclusive
  `field-aware-v2` reported 18/30; exclusive `field-aware-v3` initially reported 17/30, then the
  approved explicit `approvals` → `approval` token normalization correctly classified row 30,
  producing 18/30, or 60%. The remaining 12 misses are not being hidden with fuzzy matching.
  Several expected responsibilities are absent
  or have a materially different role/object, so the 90% reader gate remains failed.
- Local Batch B bumps the reader to `responsibility-read-v2.1-thin-source-faithful`. Its system and
  request prompts require exact source-owner labels, one duty and one destination per record, short
  action phrases, and preservation of concrete systems, portals, servers, forms, cadence, and timing.
  This prompt was deployed and failed its second live gate. Batch C then shipped and failed the
  third live gate at 19/30 (63.3%). Batch D is next; merge and apply remain forbidden.

## Field-aware-v3 production audit

Map: `ebd13d54-215f-4bed-9d3c-14c63df4b624`. This is a read-only rescore of 98 persisted
responsibility records. The table records the stable best candidate even when it is rejected.

| # | Expected role / action / object | Result | Best actual role / action / object | Quote excerpt | Chunk |
|---:|---|---|---|---|---|
| 1 | Licensed Team / prioritize / rush submissions | match, field-aware | Licensed Team / prioritize and email / rush approval submissions | prioritize submissions that are rush requests | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 2 | Licensed Team / email / licensor for rush approval | miss, record already consumed and object incomplete | Licensed Team / prioritize and email / rush approval submissions | email the licensor to request a rush approval | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 3 | Lic Manager / request / order value and units from Sales | match, field-aware | Lic Manager / reach out / Sales team to get order value and units | reach out to Sales team | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 4 | Licensed Team / check / legal lines logos and artwork against style guides | match, field-aware | Licensed Team / check / all legal lines logos and artwork against Licensor Style Guides | MUST check all legal lines | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 5 | Licensed Team / submit / concepts into licensor systems | match, field-aware | Licensed Team / submit / concepts into different Licensor Systems | submits concepts into the different Licensor Systems | `86e9e4ea-00f7-4b29-b591-a253fcb9e653` |
| 6 | Licensed Team / save / BA form to SharedLic server | match, field-aware | Licensed Team / save / BA form to SharedLic server | Save BA form to the SharedLic server | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 7 | Licensed Team / save / BA number to MasterData | match, field-aware | Licensed Team / save / BA number to MasterData | Save BA number to MasterData | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 8 | Licensed Team / save / BA number to DesignFlow | match, field-aware | Licensed Team / save / BA number to DesignFlow | Save BA number to DesignFlow | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 9 | Licensed Team / save / BA number to ColdLion | match, field-aware | Licensed Team / save / BA number to ColdLion | Save BA number to ColdLion | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 10 | Licensed Team / assign / revision to SKU designer | match, field-aware | Licensed Team / assign and inform / revision to Designer of SKU | Assign Revision to the Designer | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 11 | Licensed Team / update / Microsoft Loop licensor status | match, field-aware | Licensed Team / update and send / Microsoft Loop for Licensor Status | Update Microsoft Loop for Licensor Status | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 12 | Licensed Team / check / designer revision against licensor feedback | match, field-aware | Licensed Team / check / revision Designer provided against licensor feedback | Check the Revision that the Designer provided | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 13 | Licensed Team / resubmit / revised tech pack to licensor systems | match, field-aware | Licensed Team / resubmit / revised tech pack to Licensor Systems | Resubmit the revised tech pack | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 14 | Lic Coordinator / download / PPS photos from factory sample request email | miss | Lic Coordinator / provide / assets to partners | Licensed team provides assets to partners | `86e9e4ea-00f7-4b29-b591-a253fcb9e653` |
| 15 | Lic Coordinator / rename / PPS files by SKU number | miss | Lic Coordinator / provide / assets to partners | Licensed team provides assets to partners | `86e9e4ea-00f7-4b29-b591-a253fcb9e653` |
| 16 | Licensed Team / review / PPS photos against tech pack specifications | miss | Licensed Team / enter / tech pack submission date in MasterData | Enter the date when tech pack is submitted | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 17 | Licensed Team / submit / PPS photos in licensor portals | miss | Licensed Team / submit / photos for final licensor approval | submit photos again to receive final approval | `38ce9a67-8bb9-4c0c-ba4c-9b20a8c49f8a` |
| 18 | Licensed Team / submit / product safety tests | miss | Licensed Team / submit / concept submissions into Licensor Systems | submits into the Different Licensor Systems | `a80d437a-21f2-48a1-a085-2ac9a00f0a7c` |
| 19 | Lic Manager / fill out / Letter of Guarantee | miss | Lic Manager / fill out / Factory Authorization Request form | Fill out Factory Authorization Request form | `537111e5-d05c-4987-8185-12cf5dff5402` |
| 20 | Lic Manager / request / contractual sample exemption | match, field-aware | Lic Manager / request / Contractual Sample Exemption from Licensors | Request Contractual Sample Exemption | `38ce9a67-8bb9-4c0c-ba4c-9b20a8c49f8a` |
| 21 | Lic Manager / submit / factory audits into submission portal | miss, object incomplete | Lic Manager / submit / Factory Audits | Submit Factory Audits into the Submission Portal | `38ce9a67-8bb9-4c0c-ba4c-9b20a8c49f8a` |
| 22 | Lic Manager / enter / factory information into MasterData vendor tab | match, field-aware | Lic Manager / enter / Factory Information on Vendor tab in MasterData | Enter Factory Information from the Audits | `38ce9a67-8bb9-4c0c-ba4c-9b20a8c49f8a` |
| 23 | Lic Manager / request / factory audits before approval expiration | miss, object incomplete | Lic Manager / request / audits from Factories | Request audits at least 3 months before expiration | `38ce9a67-8bb9-4c0c-ba4c-9b20a8c49f8a` |
| 24 | Licensed Team / download / style guides to style guide server | miss | Licensed Team / download / techpacks or linesheets | downloads techpacks or linesheets | `86e9e4ea-00f7-4b29-b591-a253fcb9e653` |
| 25 | Licensed Team / organize / assets by file type | match, field-aware | Licensed Team / organize / Assets by File Type | Organizes the Assets by the File Type | `537111e5-d05c-4987-8185-12cf5dff5402` |
| 26 | Licensed Team / submit / quarterly royalty reports | miss, object incomplete | Licensed Team / submit / Royalty Reports | Submit the Reports | `537111e5-d05c-4987-8185-12cf5dff5402` |
| 27 | Lic Manager / request / trademark authorization forms | match, field-aware | Lic Manager / request / Trademark Authorization forms | Request Trademark Authorization forms | `537111e5-d05c-4987-8185-12cf5dff5402` |
| 28 | Lic Manager / maintain / contracts by licensor | match, field-aware | Lic Manager / ensure / Contracts by Licensor up to date | Ensure Contracts by Licensor are up to date | `86e9e4ea-00f7-4b29-b591-a253fcb9e653` |
| 29 | Licensed Team / provide / assets to partners | miss, action differs | Licensed Team / receive / request from partners for assets | receives a request from different partners | `86e9e4ea-00f7-4b29-b591-a253fcb9e653` |
| 30 | Licensed Team / maintain / 4 Seasons approval status sheet | match, field-aware | Licensed Team / maintain / Status Approvals on Google Sheet for 4 Seasons | Maintains Status Approvals on a Separate Google Sheet | `86e9e4ea-00f7-4b29-b591-a253fcb9e653` |

## Second production reader gate

The deployed `responsibility-read-v2.1-thin-source-faithful` reader ran on a new disposable copy of
the same pinned SHA. This result is worse than the first gate and remains blocked.

- Trigger run: `run_06fqc2v7c8kps1flqtfpjmts01`, worker `20260728.1`.
- Document: `d5f8ebaa-83bd-49eb-ac2d-9226250960c9`.
- Map: `242c84a3-d12b-4ff3-8ef8-35b6ef9245dc`, status `degraded`.
- Workflow model run: `a3781e5c-18c2-427c-8dc3-60607968ec53`.
- Context pack: `f0deefdb-b0fb-46ed-8059-d999b3dcc1a9`.
- Pipeline: `shape-reader-v5-r2-responsibilities`.
- Responsibility prompt: `responsibility-read-v2.1-thin-source-faithful`.
- Coverage: 5/5 supplied chunks covered; 82 responsibilities kept and 5 dropped.
- Whole map: 425 records kept and 12 dropped.
- Five responsibility drops were strict `markdown_document` quote mismatches in
  `licensed-team-and-manager-responsibilities`.
- Unchanged `field-aware-v3` score: 17/30, or 56.7%.
- Safety: merge and apply remained `false`; durable objects, versions, and proposals remained zero.

| # | Expected role / action / object | Result | Best actual role / action / object | Quote excerpt | Chunk |
|---:|---|---|---|---|---|
| 1 | Licensed Team / prioritize / rush submissions | match | Licensed Team / prioritize submissions / submissions that are rush requests | prioritize submissions that are rush requests | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 2 | Licensed Team / email / licensor for rush approval | match | Licensed Team / email / licensor to request rush approval in system | email the licensor to request a rush approval | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 3 | Lic Manager / request / order value and units from Sales | match | Lic Manager / reach out / Sales team to get order value and units | reach out to Sales team | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 4 | Licensed Team / check / legal lines logos and artwork against style guides | match | Licensed Team / check / legal lines logos and artwork against Licensor Style Guides | MUST check all legal lines | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 5 | Licensed Team / submit / concepts into licensor systems | match | Licensed Team / submit / concepts into Different Licensor Systems | submits into the Different Licensor Systems | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 6 | Licensed Team / save / BA form to SharedLic server | match | Licensed Team / save / BA form to SharedLic server | Save BA form to SharedLic server | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 7 | Licensed Team / save / BA number to MasterData | match | Licensed Team / save / BA number to MasterData | Save BA number to MasterData | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 8 | Licensed Team / save / BA number to DesignFlow | match | Licensed Team / save / BA number to DesignFlow | Save BA number to DesignFlow | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 9 | Licensed Team / save / BA number to ColdLion | match | Licensed Team / save / BA number to ColdLion | Save BA number to ColdLion | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 10 | Licensed Team / assign / revision to SKU designer | match | Licensed Team / assign / Revision to Designer of SKU | Assign Revision to the Designer | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 11 | Licensed Team / update / Microsoft Loop licensor status | miss | Licensed Team / update / DesignFlow status | Update DesignFlow status | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 12 | Licensed Team / check / designer revision against licensor feedback | match | Licensed Team / check / Revision Designer provided against licensor feedback | Check the Revision | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 13 | Licensed Team / resubmit / revised tech pack to licensor systems | match | Licensed Team / resubmit / revised tech pack to Licensor Systems | Resubmit the revised tech pack | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 14 | Lic Coordinator / download / PPS photos from factory sample request email | miss | Lic Coordinator / provide / assets to partners | provides assets to partners | `b028869c-18c1-477a-88d4-1daa0884859f` |
| 15 | Lic Coordinator / rename / PPS files by SKU number | miss | Lic Coordinator / provide / assets to partners | provides assets to partners | `b028869c-18c1-477a-88d4-1daa0884859f` |
| 16 | Licensed Team / review / PPS photos against tech pack specifications | miss | Licensed Team / enter / tech pack submission date in MasterData | Enter the date when tech pack is submitted | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 17 | Licensed Team / submit / PPS photos in licensor portals | miss | Licensed Team / submit improved production photos / improved photos after licensor comments | Submit improved production photos | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 18 | Licensed Team / submit / product safety tests | miss | Licensed Team / submit improved production photos / improved photos after comments | Submit improved production photos | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 19 | Lic Manager / fill out / Letter of Guarantee | miss | Lic Manager / save Approval Letter / Approval Letter to FAMA Server | Save the Approval Letter | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 20 | Lic Manager / request / contractual sample exemption | match | Lic Manager / request Contractual Sample Exemption / exemption from licensors | Request Contractual Sample Exemption | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 21 | Lic Manager / submit / factory audits into submission portal | match | Lic Manager / submit factory audits / audits into Submission Portal | Submit Factory Audits into the Submission Portal | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 22 | Lic Manager / enter / factory information into MasterData vendor tab | match | Lic Manager / enter factory information / information on Vendor tab in MasterData | Enter Factory Information | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 23 | Lic Manager / request / factory audits before approval expiration | miss, object 80% | Lic Manager / reach out to Factories to request audits / audits three months before approval expiration | Request audits AT LEAST 3 months before expiration | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 24 | Licensed Team / download / style guides to style guide server | miss | Licensed Team / download / techpacks or linesheets | downloads techpacks or linesheets | `b028869c-18c1-477a-88d4-1daa0884859f` |
| 25 | Licensed Team / organize / assets by file type | miss | Licensed Team / check / legal lines logos and artwork | check all legal lines | `dddcab4b-c3e3-4fb0-8258-4abe3b91f30b` |
| 26 | Licensed Team / submit / quarterly royalty reports | miss | Licensed Team / submit improved production photos / improved production photos | Submit improved production photos | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 27 | Lic Manager / request / trademark authorization forms | miss | Lic Manager / request audits / audits before expiration | Request audits | `27199df0-269d-4c6d-9d1d-f7b82293cfef` |
| 28 | Lic Manager / maintain / contracts by licensor | match | Lic Manager / ensure / Contracts by Licensor up to date | Ensure Contracts by Licensor are up to date | `b028869c-18c1-477a-88d4-1daa0884859f` |
| 29 | Licensed Team / provide / assets to partners | miss, action differs | Licensed Team / receive / request from partners for assets | receives a request from different partners | `b028869c-18c1-477a-88d4-1daa0884859f` |
| 30 | Licensed Team / maintain / 4 Seasons approval status sheet | match | Licensed Team / maintain / approval status on Google Sheet for 4 Seasons | Maintains Status Approvals on a Separate Google Sheet | `b028869c-18c1-477a-88d4-1daa0884859f` |

Diagnosis: v2.1 correctly split the combined rush duties and preserved the audit portal, but it did
not improve overall recall. It lost previously matched Loop, asset-organization, royalty-report,
and trademark-form duties, retained the longstanding PPS/safety/guarantee/style-guide/partner
misses, and introduced five strict quote drops. The next change must address reader completeness
and verbatim quote copying without weakening the matcher or evidence validator.
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
- The swimlane regression is green locally. The responsibilities reader has been deployed and
  tested three times, but all three live answer-key gates failed.

## Batch C shipped hardening

- Responsibility reads are sharded into deterministic single-chunk calls and merged in stable
  segment/chunk order. Base reads and every retry use separate deterministic prefixes, and a
  global uniqueness guard blocks duplicate element IDs before map persistence.
- A source-driven omission audit finds duty-bearing spans not covered by any kept exact quote and
  allows bounded focused retries under separate responsibility post-pass allowances and the shared read/token/cost budget.
- Responsibility quote repair is limited to root `quote_mismatch` records. It may change only the
  quote, may not move chunks, and is accepted only when the unchanged strict validator reduces
  exact-policy failures.
- Responsibility call diagnostics now retain output tokens, provider finish reason when present,
  and a derived truncation flag.
- Structured list candidates require a duty verb or a generic ownership/responsibility cue.
- The answer key and `field-aware-v3` scorer remain frozen.
- Batch C shipped in commit `f31f66a` and failed the third production gate at 19/30 (63.3%).
  Batch D is next. No shadow merge or apply work is authorized until recall reaches 90%.

The second gate created one disposable production fixture document and its normal ingestion
artifacts. At that checkpoint, neither merge nor apply was enabled, durable business objects and
versions remained zero, and no additional commit, push, deployment, or durable business-model write
was made.

## Third production reader gate

Commit `f31f66a` passed CI `30318748914`, including the populated double-migration test. Migration
97 applied through the normal runner. Trigger worker `20260728.2` deployment `qordtrim` registered
25 tasks; Vercel deployment `dpl_6RQw8FVgn9X8ueddE2pvAfLzW2z7` was READY and the live URL returned
HTTP 200. The third fresh gate still failed recall and is blocked.

- Pinned local source SHA-256 was rechecked before upload:
  `398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`.
- Trigger run: `run_06fqch0hiaiu9nte5rptja1b01`, completed normally on worker `20260728.2`.
- Disposable document: `b3fdae48-10a8-4922-b022-26c966511cb2`.
- Map: `df81b823-70d2-46fa-b15c-8215de53a1cc`, status `degraded`.
- Final workflow model run: `016126b8-fe3e-4e74-8925-061f21cace54`.
- Final context pack: `4e9d16eb-3f1d-4352-a924-09204ff71a7c`.
- Five source chunks were read. The responsibility layer kept 138 records and dropped 9 strict
  `markdown_document` quote mismatches.
- Omission audit found 28 uncovered spans. It used two retries, one each on C0 and C3, and accepted
  one new record from each retry.
- Quote repair used its one allowed attempt against 9 root mismatches. It was rejected because it
  produced no strict exact-quote improvement.
- Reader budget: 19/40 calls, 41,873/500,000 estimated input tokens, 1/1 general repair attempt,
  and estimated input cost `$0.209365` under the `$10` cap.
- Responsibility post-pass budget: 2/5 omission retries, at most 1 per chunk, and 1/1 quote repair.
- No responsibility call reported truncation. Recorded responsibility output tokens by execution
  were 4,449, 709, 1,144, 3,458, 2,908, 200, 4,020, and 3,301.
- Frozen `field-aware-v3` score: **19/30, or 63.3%**. This is below the 90% gate.
- Before and after the run, merge and apply were both `false`; post-pass settings remained `1/5/1`;
  `business_objects`, `business_object_versions`, and `business_model_changes` all remained zero.

Chunk aliases: C0 `bb2e226d-3cbf-489f-aa14-3eb1cc8cabeb`; C1
`958aa572-45b6-4c86-9925-1955e8e0e62f`; C2 `624d3164-5ab1-43ba-a3a7-cac5524ae72d`; C3
`4a0173c4-09f3-4d50-97ac-3e89ee5dbf45`; C4
`4d043ad7-0ac8-4089-87ef-c3d3eac41cdf`.

| # | Expected role / action / object | Result | Best actual role / action / object | Quote excerpt | Chunk |
|---:|---|---|---|---|---|
| 1 | Licensed Team / prioritize / rush submissions | match | Licensed Team / prioritize / submissions that are rush requests | prioritize submissions that are rush requests | C0 |
| 2 | Licensed Team / email / licensor for rush approval | match | Licensed Team / email / licensor to request rush approval in system | email the licensor to request a rush approval | C0 |
| 3 | Lic Manager / request / order value and units from Sales | match | Lic Manager / reach out / Sales team for order value and units | reach out to Sales team to get the value | C0 |
| 4 | Licensed Team / check / legal lines logos and artwork against style guides | match | Licensed Team / check / all legal lines logos and artwork against Licensor Style Guides | MUST check all legal lines | C0 |
| 5 | Licensed Team / submit / concepts into licensor systems | match | Licensed Team / submit / concepts into different Licensor Systems | submits concepts into the different Licensor Systems | C4 |
| 6 | Licensed Team / save / BA form to SharedLic server | match | Licensed Team / save / BA form to SharedLic server “SKU#_CRS” | Save BA form to SharedLic server | C0 |
| 7 | Licensed Team / save / BA number to MasterData | match | Licensed Team / save / BA number to MasterData | Save BA number to MasterData | C0 |
| 8 | Licensed Team / save / BA number to DesignFlow | match | Licensed Team / save / BA number to DesignFlow | Save BA number to DesignFlow | C0 |
| 9 | Licensed Team / save / BA number to ColdLion | match | Licensed Team / save / BA number to ColdLion | Save BA number to ColdLion | C0 |
| 10 | Licensed Team / assign / revision to SKU designer | match | Licensed Team / assign / Revision to Designer of SKU | Assign Revision to the Designer | C0 |
| 11 | Licensed Team / update / Microsoft Loop licensor status | miss | Licensed Team / update / DesignFlow status | Update DesignFlow status | C0 |
| 12 | Licensed Team / check / designer revision against licensor feedback | match | Licensed Team / check / Designer revision against licensor feedback | Check the Revision | C0 |
| 13 | Licensed Team / resubmit / revised tech pack to licensor systems | match | Licensed Team / resubmit / revised tech pack to Licensor Systems | Resubmit the revised tech pack | C0 |
| 14 | Lic Coordinator / download / PPS photos from factory sample request email | miss | Lic Coordinator / provide / assets to partners | provides assets to partners | C4 |
| 15 | Lic Coordinator / rename / PPS files by SKU number | miss | Lic Coordinator / provide / assets to partners | provides assets to partners | C4 |
| 16 | Licensed Team / review / PPS photos against tech pack specifications | miss | Licensed Team / enter / tech pack submission date in MasterData | Enter the date when tech pack is submitted | C0 |
| 17 | Licensed Team / submit / PPS photos in licensor portals | miss | Licensed Team / submit improved production photos / improved photos after PPS comments | Submit improved production photos | C2 |
| 18 | Licensed Team / submit / product safety tests | miss | Licensed Team / submit improved production photos / improved photos after PPS comments | Submit improved production photos | C2 |
| 19 | Lic Manager / fill out / Letter of Guarantee | miss | Lic Manager / fill out / Factory Authorization Request form | Fill out Factory Authorization Request form | C3 |
| 20 | Lic Manager / request / contractual sample exemption | match | Lic Manager / request Contractual Sample Exemption / exemption from licensors | Request Contractual Sample Exemption | C2 |
| 21 | Lic Manager / submit / factory audits into submission portal | match | Lic Manager / submit Factory Audits / audits into Submission Portal | Submit Factory Audits into the Submission Portal | C2 |
| 22 | Lic Manager / enter / factory information into MasterData vendor tab | match | Lic Manager / enter Factory Information / Vendor tab in MasterData | Enter Factory Information from the Audits | C2 |
| 23 | Lic Manager / request / factory audits before approval expiration | miss, object 80% | Lic Manager / reach out to Factories to request audits / audits three months before FAMA or NBC expiry | Request audits AT LEAST 3 months before expiration | C2 |
| 24 | Licensed Team / download / style guides to style guide server | miss | Licensed Team / download / techpacks or linesheets | downloads techpacks or linesheets | C4 |
| 25 | Licensed Team / organize / assets by file type | match | Licensed Team / organize / Assets by File Type | Organizes the Assets by the File Type | C3 |
| 26 | Licensed Team / submit / quarterly royalty reports | miss, object 67% | Licensed Team / submit / Reports for Royalty Reporting | Submit the Reports | C3 |
| 27 | Lic Manager / request / trademark authorization forms | match | Lic Manager / request / Trademark Authorization forms from each licensor | Request Trademark Authorization forms | C3 |
| 28 | Lic Manager / maintain / contracts by licensor | match | Lic Manager / ensure / Contracts by Licensor are up to date | Ensure Contracts by Licensor are up to date | C4 |
| 29 | Licensed Team / provide / assets to partners | miss | Licensed Team / provide information / contract information | licensor will ask for this information | C2 |
| 30 | Licensed Team / maintain / 4 Seasons approval status sheet | match | Licensed Team / maintain / Status Approvals Google Sheet for 4 Seasons | Maintains Status Approvals on a Separate Google Sheet | C4 |

Diagnosis, without changing code or settings: Batch C improved the second gate from 17 to 19
matches and restored asset organization plus trademark forms, but it did not solve owner-aware
coverage for the PPS duties, style-guide download, safety tests, Letter of Guarantee, royalty
reports, partner assets, or Microsoft Loop. The source audit still reported 28 uncovered spans,
yet only two focused retries ran and each added one record. Nine quote mismatches all came from the
first responsibility shard, and the one quote repair could not improve them. The gate remains
blocked. Do not enable merge or apply.
