# R2 Responsibilities Gate

Date: 2026-07-28

Status: **PAUSED FOR OWNER DECISION. The sixth live gate scored 14/30 (46.7%); the `<=23`
hard stop binds. No Batch G or implementation is authorized. R3 and later are blocked.**

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
  third live gate at 19/30 (63.3%). Batch D shipped in `d5df5b6` and its fourth live gate also
  scored 19/30 (63.3%); merge and apply remain forbidden.

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
  tested four times, but all four live answer-key gates failed.

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
  Batch D later shipped in `d5df5b6` and failed the fourth production gate at the same score.
  No shadow merge or apply work is authorized until recall reaches 90%.

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

## Fourth production reader gate

Batch D shipped in commit `d5df5b6`, green CI `30376445491`, Trigger worker `20260728.3`
deployment `7ws4iiak` with 25 tasks, and READY Vercel deployment
`dpl_DDJuRqwSrUREN93ppBShrsGCmP1a`. The fourth fresh production gate completed normally but again
scored 19/30 (63.3%). R2 remains blocked.

- Pinned source SHA-256: `398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`.
- Trigger run: `run_06fqivv0a0l8hh6e9aesqh5r01`; disposable document:
  `35421497-9216-4a88-a61c-14d1838a44a4`; map:
  `6e4da423-f73c-4891-9b5a-9e046bd79823`, status `degraded`.
- Final model run: `1d8e9609-f205-4254-835e-367adf550b4d`; final context pack:
  `be015668-ca3c-4833-a96a-858a94183849`.
- Pipeline `shape-reader-v5-r2-responsibilities` kept 190 responsibility records and dropped five
  strict `markdown_document` quote mismatches. The full map kept 441 and dropped 44 across all
  shapes.
- The six responsibility shards all used `responsibility-read-v2.2-field-faithful`. Ten base or
  retry calls used durable task `source-responsibility-read`.
- The one responsibility quote repair used task `source-responsibility-quote-repair` and prompt
  `responsibility-quote-repair-v2.2`. It selected
  `licensed_team_and_manager_responsibilities_overview__chunk_001`, had five eligible root quote
  mismatches before and five after, and was rejected as `no_strict_exact_improvement`.
- Omission audit started at 92 uncovered spans and ended at 89. Ranked retry order was C1, C0, C4,
  C3, C2. C1 was skipped as `no_source_read`; C0 accepted 6, C4 accepted 2, C3 accepted 11, and C2
  accepted 6. Each row selected six spans. The durable audit records counts and chunk selection,
  but not the text of each selected span.
- Post-pass use was four omission retries of the allowed five, no more than one per chunk, plus
  one of one quote repair.
- Reader budget: 21/40 calls, 45,496/500,000 estimated input tokens, one general repair attempt,
  and estimated input cost `$0.22748` under the `$10` cap.
- Durable model usage by task: segmentation 4,683 in / 1,292 out; workflow reads 20,606 in /
  27,914 out; workflow quote repair 1,646 in / 501 out; responsibility reads 17,687 in /
  24,607 out; responsibility quote repair 1,648 in / 295 out. Provider `cost_usd` remained null,
  so the reader's estimated input cost is the available cost record.
- No responsibility call reported truncation.
- Frozen `field-aware-v3` score: **19/30, or 63.3%**, below the required 27/30.
- Before and after the run, merge and apply were `false`; post-pass settings remained `1/5/1`;
  `business_objects`, `business_object_versions`, and `business_model_changes` remained zero.

Chunk aliases: C0 `f321002c-59dd-4500-81ea-3def42ab07f6`; C1
`b234f08e-e3c6-4e9d-83e4-812d502c9816`; C2 `dfd1c752-c99d-45f4-90ce-0ea24ce263f0`; C3
`fe750e59-764f-481f-9037-a9d4413f5c40`; C4 `1d6293c9-b4f1-4247-9880-f00e25409dbd`.

| # | Expected role / action / object | Result | Best actual role / action / object | Quote excerpt | Chunk |
|---:|---|---|---|---|---|
| 1 | Licensed Team / prioritize / rush submissions | match | Licensed Team / prioritize submissions / submissions that are rush requests | prioritize submissions that are rush requests | C0 |
| 2 | Licensed Team / email / licensor for rush approval | match | Licensed Team / email / licensor to request rush approval in system | email the licensor to request a rush approval | C0 |
| 3 | Lic Manager / request / order value and units from Sales | match | Lic Manager / reach out / Sales team for order value and units | reach out to Sales team to get the value | C0 |
| 4 | Licensed Team / check / legal lines logos and artwork against style guides | match | Licensed Team / check / all legal lines logos and artwork against Licensor Style Guides | MUST check all legal lines | C0 |
| 5 | Licensed Team / submit / concepts into licensor systems | match | Licensed Team / submit / concepts into different Licensor Systems | submits concepts into the different Licensor Systems | C4 |
| 6 | Licensed Team / save / BA form to SharedLic server | match | Licensed Team / save / BA form to SharedLic server “SKU#_CRS” | Save BA form to SharedLic server | C0 |
| 7 | Licensed Team / save / BA number to MasterData | match | Licensed Team / save / BA number to MasterData | Save BA number to MasterData | C0 |
| 8 | Licensed Team / save / BA number to DesignFlow | match | Licensed Team / save / BA number to DesignFlow | Save BA number to DesignFlow | C0 |
| 9 | Licensed Team / save / BA number to ColdLion | match | Licensed Team / save / BA number to ColdLion | Save BA number to ColdLion | C0 |
| 10 | Licensed Team / assign / revision to SKU designer | match | Licensed Team / assign / Revision to Designer of SKU | Assign Revision to the Designer | C0 |
| 11 | Licensed Team / update / Microsoft Loop licensor status | miss, object 50% | Licensed Team / update / DesignFlow status and Licensor comment | Update DesignFlow status | C0 |
| 12 | Licensed Team / check / designer revision against licensor feedback | match | Licensed Team / check / Designer revision against licensor feedback | Check the Revision | C0 |
| 13 | Licensed Team / resubmit / revised tech pack to licensor systems | match | Licensed Team / resubmit / revised tech pack to Licensor Systems | Resubmit the revised tech pack | C0 |
| 14 | Lic Coordinator / download / PPS photos from factory sample request email | miss | Lic Coordinator / provide / assets to partners | provides assets to partners | C4 |
| 15 | Lic Coordinator / rename / PPS files by SKU number | miss | Lic Coordinator / provide / assets to partners | provides assets to partners | C4 |
| 16 | Licensed Team / review / PPS photos against tech pack specifications | miss | Licensed Team / enter date / tech pack submission in MasterData | Enter the date when tech pack is submitted | C0 |
| 17 | Licensed Team / submit / PPS photos in licensor portals | miss, object 75% | Licensed Team / submit improved production photos / photos after PPS comments | Submit improved production photos | C2 |
| 18 | Licensed Team / submit / product safety tests | miss | Licensed Team / submit for partners / partner techpacks | Partners send their concepts as techpacks | C4 |
| 19 | Lic Manager / fill out / Letter of Guarantee | miss | Lic Manager / fill out / Factory Authorization Request form | Fill out Factory Authorization Request form | C3 |
| 20 | Lic Manager / request / contractual sample exemption | match | Lic Manager / request Contractual Sample Exemption / exemption from licensors | Request Contractual Sample Exemption | C2 |
| 21 | Lic Manager / submit / factory audits into submission portal | match | Lic Manager / submit Factory Audits / audits into Submission Portal | Submit Factory Audits into the Submission Portal | C2 |
| 22 | Lic Manager / enter / factory information into MasterData vendor tab | match | Lic Manager / enter Factory Information / Vendor tab in MasterData | Enter Factory Information from the Audits | C2 |
| 23 | Lic Manager / request / factory audits before approval expiration | miss, object 80% | Lic Manager / reach out to Factories to request audits / audits three months before expiry | Request audits AT LEAST 3 months before expiration | C2 |
| 24 | Licensed Team / download / style guides to style guide server | miss | Licensed Team / download / techpacks or linesheets | downloads techpacks or linesheets | C4 |
| 25 | Licensed Team / organize / assets by file type | match | Licensed Team / organize / Assets by File Type | Organizes the Assets by the File Type | C3 |
| 26 | Licensed Team / submit / quarterly royalty reports | miss, object 33% | Licensed Team / submit / Reports | Submit the Reports | C3 |
| 27 | Lic Manager / request / trademark authorization forms | match | Lic Manager / request / Trademark Authorization forms from each licensor | Request Trademark Authorization forms | C3 |
| 28 | Lic Manager / maintain / contracts by licensor | match | Lic Manager / ensure are up to date / Contracts by Licensor | Ensure Contracts by Licensor are up to date | C4 |
| 29 | Licensed Team / provide / assets to partners | miss | Licensed Team / receive / partner request for assets | receives a request from different partners | C4 |
| 30 | Licensed Team / maintain / 4 Seasons approval status sheet | match | Licensed Team / maintain / Status Approvals Google Sheet for 4 Seasons | Maintains Status Approvals on a Separate Google Sheet | C4 |

Diagnosis, without changing code or settings: Batch D greatly increased extracted responsibilities
and exercised all four allowed focused retries, but recall stayed exactly 19/30. The broad source
audit still reports 89 uncovered spans after retries, so the generic omission signal is too noisy
to focus the reader on the eleven answer-key duties. Several near misses preserve most of the duty
but lose a required target or qualifier. The same five exact-quote failures around the first shard
survived the dedicated repair. Stop here. Do not enable merge or apply.

## Batch D implementation and release

Batch D shipped in commit `d5df5b6` and is the code exercised by the fourth production gate above.

- Generic omission coverage now requires strict quote containment plus matching owner, duty action,
  and concrete object details. A long quote cannot hide an unrepresented duty.
- Omission retries re-audit after every attempt, rank remaining chunks by omission count and stable
  source order, and send at most six focused spans per call.
- Retry audit rows record pre/post omission counts, accepted records, `no_source_read`,
  `budget_exhausted`, and `zero_accept` instead of silently skipping.
- Prompt `responsibility-read-v2.2-field-faithful` requires the nearest explicit owner, unchanged
  direction and polarity, complete named targets and timing, and the shortest verbatim one-duty quote.
- Responsibility quote repair uses a dedicated quote-only schema. It keeps all non-quote fields and
  chunk IDs immutable and may accept a partial set only when strict mismatches decrease. Repair
  runs have distinct durable task/prompt identity, and the final omission count is recomputed after
  an accepted repair.
- The answer key, `field-aware-v3`, 90% threshold, merge/apply flags, and R0/R0.1 budgets are unchanged.
- AI and worker typechecks passed.
- R2 responsibility, source workflow, R0 validator, R1 cross-shape, macro-first lifecycle, and
  document-ingestion fallback checks passed.

## Fifth production reader gate

Batch E shipped in commit `b761df9`, green CI `30381079154`, and Trigger worker `20260728.4`
deployment `0xa17r8u`. The fifth fresh pinned production gate completed normally, but frozen
recall was only **20/30 (66.7%)**. R2 remains blocked.

- Pinned source SHA-256:
  `398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`.
- Frozen key: `licensed-team-responsibilities-v1`; matcher: `field-aware-v3`.
- Trigger run: `run_06fqjdgqlir7oi1sgdr1tvmj01`.
- Disposable document: `b01688b8-2d0c-4d0c-a546-464f154f7de9`.
- Map: `94a32c78-6adc-4af0-ae39-f60aa658331b`, terminal `degraded`.
- Source-workflow job: `65e91226-7aaf-4523-a41d-0455efc84494`, terminal `complete`, no error or
  retry.
- Final model run: `3eb7369d-11c9-4a0c-bc14-9254ec4dc5a7`.
- Final context pack: `9187710f-0075-4d15-a6f2-ebfc0a51d857`.
- Pipeline `shape-reader-v6-r2-batch-e` used five responsibility base reads. One was the durable
  synthetic segment `responsibility_duty_chunk_002`.
- Responsibility result: 179 kept, 11 dropped. Full map result: 485 kept, 31 dropped.
- Omission audit moved from 92 to 84. All five allowed retries ran, one per chunk, with accepted
  record counts `2`, `3`, `7`, `5`, and `4`.
- Every selected span has durable rank, text, SHA-256, result, and base-read membership. The final
  uncovered sample preserves the first 30 of 84 remaining spans.
- Grounded quote repair used its one attempt, was accepted, and reduced root quote failures from
  10 to 6. Ten repair rows each preserved 12 candidates plus returned text/SHA evidence.
- Reader budget: 25/40 calls, 62,680/500,000 estimated input tokens, 1/1 general repair, and
  `$0.3134/$10` estimated input cost.
- Responsibility calls: 10 calls, 18,861 input tokens, 24,272 output tokens, prompt
  `responsibility-read-v2.3-duty-complete`.
- Responsibility quote repair: one call, 12,600 input tokens, 618 output tokens, prompt
  `responsibility-quote-repair-v2.3-grounded`.
- No responsibility execution reported truncation. Provider `cost_usd` stayed null, so the
  reader's estimated input cost is the durable cost evidence.
- The outer document remained `processing` with no error because later claim extraction was still
  running. The R2 map and source-workflow job were terminal; the outer status is not an R2 failure.
- Before and after: merge `false`, apply `false`, post-pass limits `1/5/1`, and
  `business_objects`, `business_object_versions`, `business_model_changes` all `0`.

Chunk aliases: C0 `7f1604d8-febe-4bdc-9237-8d5dd20043f3`; C1
`c168a068-7faa-4e1b-a215-427ad0b364c2`; C2 `53a0d68f-1cb7-424a-adb1-5dbce5c7edf4`; C3
`92d03713-c9ae-411a-9239-4328dc5af49c`; C4
`b9ad26de-ffdd-4955-b9ae-4d45c130e0a6`.

| # | Expected role / action / object | Result | Best actual role / action / object | Object coverage |
|---:|---|---|---|---:|
| 1 | Licensed Team / prioritize / rush submissions | match | Licensed Team / prioritize submissions / submissions that are rush requests | 100% |
| 2 | Licensed Team / email / licensor for rush approval | match | Licensed Team / email / licensor to request rush approval in system | 100% |
| 3 | Lic Manager / request / order value and units from Sales | match | Lic Manager / reach out / Sales team for order value and units | 100% |
| 4 | Licensed Team / check / legal lines logos and artwork against style guides | match | Licensed Team / check / all legal lines, logos, and artwork against Licensor Style Guides | 100% |
| 5 | Licensed Team / submit / concepts into licensor systems | match | Licensed Team / submit / concepts into different Licensor Systems | 100% |
| 6 | Licensed Team / save / BA form to SharedLic server | match | Licensed Team / save / BA form to SharedLic server `SKU#_CRS` | 100% |
| 7 | Licensed Team / save / BA number to MasterData | match | Licensed Team / save / BA number to MasterData | 100% |
| 8 | Licensed Team / save / BA number to DesignFlow | match | Licensed Team / save / BA number to DesignFlow | 100% |
| 9 | Licensed Team / save / BA number to ColdLion | match | Licensed Team / save / BA number to ColdLion | 100% |
| 10 | Licensed Team / assign / revision to SKU designer | match | Licensed Team / assign / revision to Designer of SKU | 100% |
| 11 | Licensed Team / update / Microsoft Loop licensor status | match | Licensed Team / update / Microsoft Loop for Licensor Status and team feedback | 100% |
| 12 | Licensed Team / check / designer revision against licensor feedback | match | Licensed Team / check / revision against licensor feedback | 100% |
| 13 | Licensed Team / resubmit / revised tech pack to licensor systems | match | Licensed Team / resubmit / revised tech pack to Licensor Systems | 100% |
| 14 | Lic Coordinator / download / PPS photos from factory sample request email | miss | Lic Coordinator / download photos / Factory Sample Request email | 66.7% |
| 15 | Lic Coordinator / rename / PPS files by SKU number | miss | Lic Coordinator / rename files / according to SKU number | 25% |
| 16 | Licensed Team / review / PPS photos against tech pack specifications | miss | Licensed Team / review PPS photos / photos match tech pack specifications | 66.7% |
| 17 | Licensed Team / submit / PPS photos in licensor portals | miss | Licensed Team / submit improved production photos / photos after PPS comments | 75% |
| 18 | Licensed Team / submit / product safety tests | miss | Licensed Team / submit improved production photos / photos after PPS comments | 0% |
| 19 | Lic Manager / fill out / Letter of Guarantee | miss | Lic Manager / fill out LOG / hazardous-substance safety submission | 0% |
| 20 | Lic Manager / request / contractual sample exemption | match | Lic Manager / request / Contractual Sample Exemption | 100% |
| 21 | Lic Manager / submit / factory audits into submission portal | match | Lic Manager / submit Factory Audits / audits into Submission Portal | 100% |
| 22 | Lic Manager / enter / factory information into MasterData vendor tab | match | Lic Manager / enter Factory Information / Vendor tab in MasterData | 100% |
| 23 | Lic Manager / request / factory audits before approval expiration | miss | Lic Manager / request audits / audits three months before approval expiration | 80% |
| 24 | Licensed Team / download / style guides to style guide server | miss, action | Licensed Team / assist / Design Team downloading Style Guides to server | 100% |
| 25 | Licensed Team / organize / assets by file type | match | Licensed Team / organize / assets by file type | 100% |
| 26 | Licensed Team / submit / quarterly royalty reports | miss | Licensed Team / submit / reports | 33.3% |
| 27 | Lic Manager / request / trademark authorization forms | match | Lic Manager / request / Trademark Authorization forms | 100% |
| 28 | Lic Manager / maintain / contracts by licensor | match | Lic Manager / ensure / Contracts by Licensor are up to date | 100% |
| 29 | Licensed Team / provide / assets to partners | miss, direction | Licensed Team / receive request / partner request for assets | 100% |
| 30 | Licensed Team / maintain / 4 Seasons approval status sheet | match | Licensed Team / maintain Status Approvals / Google Sheet for 4 Seasons | 100% |

### Fifth-gate review and Batch F decision

Grok 4.5's verdict is **continue R2 with Batch F**. Batch E proved discovery and grounded quote
repair work, but 21 accepted retry records closed only eight omissions and gained one answer-key
row. The stable ten-row miss cluster is field fidelity, not scorer error or missing read capacity.
Do not run another free-form prompt/retry batch.

Batch F is bounded to the responsibility post-pass:

- Force one selected duty span to one validated role-action-object record.
- Validate action direction, named forms, systems, destinations, cadence, timing, and object
  completeness against the selected span, never the answer key.
- Prefer short list-structured, verb-starting, explicitly owned spans over long prose.
- Split multi-verb chains and reject field-thinned, wrong-form, or reversed-direction records.
- Limit focused retry evidence to the selected spans.
- Keep grounded quote repair quote-only.
- Keep the fixture, `field-aware-v3`, 27/30 threshold, strict quote policy, 40/500k/$10 reader
  limits, 1/5/1 post-pass limits, false merge/apply flags, and zero-write rule frozen.

After one independently reviewed Batch F release and one fresh gate:

- `>=27/30`: proceed to later R2 shadow-merge gates.
- `24–26/30`: stop code churn and run a bounded model bake-off only on the span-anchored path.
- `<=23/30`: stop completeness batches and require an owner decision between bake-off and deeper
  architecture.

## Sixth production reader gate and binding hard stop

Batch F shipped in commit `08c2631`, passed GitHub Actions run `30385119532`, and ran in Trigger
worker `20260728.5`, deployment `f7trr764`. Exactly one fresh pinned disposable production gate
ran. The frozen result was **14/30 (46.7%)**, so the precommitted `<=23` hard stop is binding.
R2 is paused for an owner decision. No Batch G or implementation is authorized.

- Fixture SHA-256:
  `398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`.
- Frozen key: `licensed-team-responsibilities-v1`; matcher: `field-aware-v3`.
- Trigger run: `run_06fqjpv1ci6sbrh4csk56mvd01`; one attempt on worker `20260728.5`.
- Disposable document: `7001cd1e-fd85-45d3-a8d6-bb5141e200d7`.
- Storage object:
  `admin/batch-f-gate/1785261937746-Licensed_Team_Responsibilities_2_tagged.txt`.
- Document-ingestion job: `2d698f4c-86af-4eaa-872b-c0ec85431d76`.
- Source-workflow job: `f145614a-e443-4202-bb6e-026a05a267a9`, terminal `complete`, no error,
  retry count zero.
- Map: `85fc772b-92c3-4101-8b2a-288ba9ad6d4a`, terminal `degraded`.
- Final model run: `88b87385-7ec0-4b8f-b0f9-c7546c291382`.
- Final context pack: `ad2a61b9-ce7c-4eb1-88a1-c910d8281d6a`.
- Pipeline: `shape-reader-v7-r2-batch-f`; prompt:
  `responsibility-read-v2.4-span-bound`.
- Full map: 465 kept and 170 dropped.
- Responsibilities: 92 kept; one durable synthetic base read.
- Reader budget: 23/40 calls, 59,279/500,000 estimated input tokens, 1/1 general repair,
  `$0.296395/$10` estimated input cost, concurrency four.
- All responsibility executions reported `truncated=false`.
- Five omission retries ran, one each on chunks
  `08f69afa-b43c-433d-a2d6-9573829e552d`,
  `6d617b84-3a2b-4704-8444-bfd89dc47381`,
  `81c1b43e-6b00-4ef4-ae66-d99a099d6274`,
  `cf169035-e94e-4628-876a-b9877d898472`, and
  `f2ab7986-5eaa-407f-8307-53a0c04bdb44`.
- Omission count started at 80, ended the retry sequence at 70, and ended at 67 after accepted
  quote repair. The durable final sample contains the first 30 of 67 uncovered spans.
- Each retry selected and audited six forced spans, for 30 field audits total. In execution order,
  accepted counts and omission movement were: `0` (`80 -> 80`, `zero_accept`), `3`
  (`80 -> 77`), `2` (`77 -> 75`), `3` (`75 -> 72`), and `2` (`72 -> 70`). Ten forced-span
  records were accepted and twenty were rejected.
- Forced-span output and validation are durable in the map's
  `responsibilityOmissionAudit`; selected rows use `forced_span_*` IDs and preserve selected
  span evidence, rank, source chunk, returned record, exact quote result, field-fidelity result,
  and rejection reason.
- The one grounded quote repair was accepted and reduced root quote failures from 10 to 4.
- Before and after the gate: `business_model_merge_enabled=false`,
  `business_model_apply_enabled=false`, post-pass limits `1/5/1`, and
  `business_objects`, `business_object_versions`, and `business_model_changes` all zero.
- The outer document remained in its later claim-processing phase with no processing error after
  the R2 job and map were terminal. This is not an R2 failure.

### Batch E to Batch F regression

| Signal | Batch E | Batch F | Change |
|---|---:|---:|---:|
| Frozen score | 20/30 | 14/30 | -6 |
| Responsibilities kept | 179 | 92 | -87 |
| Full-map drops | 31 | 170 | +139 |
| Quote root failures after repair | 6 | 4 | -2 |
| Reader calls | 25 | 23 | -2 |
| Estimated input cost | $0.3134 | $0.296395 | -$0.017005 |

Batch F lost Batch E matches `5, 7, 8, 9, 10, 13, 25` and gained only row `19`. The same
fixture, scorer, model family, budgets, and safety flags isolate the regression to the new
control path. Strict field checks now reject incomplete records, but only quote repair exists.
There is no field-completion repair. Cleaner surviving fields therefore came with severe
inventory loss.

### Complete sixth-gate score

Best actual text and coverage are recorded where they were captured by the terminal scorer.
For matched rows whose full best-actual text was not retained in the session summary, the
deterministic outcome is still recorded and the production map remains the durable source.

| # | Expected role / action / object | Result | Best actual or failure evidence | Coverage |
|---:|---|---|---|---:|
| 1 | Licensed Team / prioritize / rush submissions | match | matched | 100% |
| 2 | Licensed Team / email / licensor for rush approval | match | matched | 100% |
| 3 | Lic Manager / request / order value and units from Sales | match | matched | 100% |
| 4 | Licensed Team / check / legal lines logos and artwork against style guides | match | matched | 100% |
| 5 | Licensed Team / submit / concepts into licensor systems | miss | best had concepts/systems but negation conflicted | 66.7% |
| 6 | Licensed Team / save / BA form to SharedLic server | match | matched | 100% |
| 7 | Licensed Team / save / BA number to MasterData | miss | best used SharedLic, not MasterData | 33.3% |
| 8 | Licensed Team / save / BA number to DesignFlow | miss | destination not preserved | 33.3% |
| 9 | Licensed Team / save / BA number to ColdLion | miss | destination not preserved | 33.3% |
| 10 | Licensed Team / assign / revision to SKU designer | miss, action | best checked revision instead of assigning it | 66.7% |
| 11 | Licensed Team / update / Microsoft Loop licensor status | match | matched | 100% |
| 12 | Licensed Team / check / designer revision against licensor feedback | match | matched | 100% |
| 13 | Licensed Team / resubmit / revised tech pack to licensor systems | miss | object/action details thinned | 40% |
| 14 | Lic Coordinator / download / PPS photos from factory sample request email | miss, action | best created a folder rather than downloading photos | 16.7% |
| 15 | Lic Coordinator / rename / PPS files by SKU number | miss | incomplete object | 50% |
| 16 | Licensed Team / review / PPS photos against tech pack specifications | miss | incomplete object | 33.3% |
| 17 | Licensed Team / submit / PPS photos in licensor portals | miss | object matched, but polarity/negation conflicted | 100% |
| 18 | Licensed Team / submit / product safety tests | miss | no compatible actual | 0% |
| 19 | Lic Manager / fill out / Letter of Guarantee | match | matched; gained from Batch E | 100% |
| 20 | Lic Manager / request / contractual sample exemption | match | matched | 100% |
| 21 | Lic Manager / submit / factory audits into submission portal | match | matched | 100% |
| 22 | Lic Manager / enter / factory information into MasterData vendor tab | match | matched | 100% |
| 23 | Lic Manager / request / factory audits before approval expiration | miss | timing qualifier thinned | 20% |
| 24 | Licensed Team / download / style guides to style guide server | miss | no compatible actual | 0% |
| 25 | Licensed Team / organize / assets by file type | miss, action | best checked rather than organized | 33.3% |
| 26 | Licensed Team / submit / quarterly royalty reports | miss | cadence and report detail thinned | 33.3% |
| 27 | Lic Manager / request / trademark authorization forms | match | matched | 100% |
| 28 | Lic Manager / maintain / contracts by licensor | match | matched | 100% |
| 29 | Licensed Team / provide / assets to partners | miss, direction | best received partner requests instead of providing assets | 100% |
| 30 | Licensed Team / maintain / 4 Seasons approval status sheet | match | matched | 100% |

### Owner decision after the hard stop

Grok 4.5's final-text review is saved at
`.ai/reviews/grok-4.5-r2-batch-f-hard-stop-review.json`. It recommends **Option B, deeper
architecture**, because the `20 -> 14` regression is primarily control-system inventory
thrashing. The stable PPS, safety, timing, cadence, and direction misses still contain a model
field-emission problem. The review is decision support only. **OWNER APPROVAL REQUIRED.**

The only allowed choices are:

- **Option A, bounded model bake-off:** freeze Batch F and follow `MODEL_BAKEOFF_SPEC.md`. Isolate
  one eligible workflow-read model at a time, run two fresh pinned gates per candidate, and restore
  settings after each. Mean `>=27` may seat the winner; `24–26` requires architecture; `<=23`
  fails the bake-off and requires architecture with no second bake-off.
- **Option B, recommended deeper architecture:** after owner approval only, split inventory
  discovery from field completion; add one bounded source-span field-completion repair; emit one
  deterministic RAO for each explicit destination; align splitter and multi-verb rejection;
  persist quote/field/multi-verb/forced-missing/invalid-detail drop classes; and test polarity,
  cadence, multi-destination output, valid Batch E-style base acceptance, and zero writes.
  Freeze the fixture, scorer, 27/30 gate, strict quotes, 40/500k/$10 and 1/5/1 budgets, false
  merge/apply flags, and zero-write rule. Do not change models, build Batch G, polish prompts as
  the main fix, weaken scoring, hard-code fixture rows, leak the key, or enable shadow merge.
  Independently review one release and run exactly one fresh pinned gate. `>=27` proceeds;
  `24–26` permits a bake-off only on the redesigned path; `<=23` stops again for an owner choice.
  Responsibility inventory must not collapse below Batch E's 179 without a documented reason,
  full-map drops must not remain near 170 when quote roots are four, and rows 7/8/9 must recover
  without fixture-specific code.

## Seventh production gate: deeper architecture, binding hard stop

The independently approved deeper-reader release ran exactly one pinned production gate on
2026-07-29 and scored **12/30 (40%)**. The `<=23` rule is binding. R2 is stopped; Albert must choose
a bounded model bake-off or another deeper-architecture step. Do not run a second gate.

- Commit `dc1317f7f04bd23f3693ea04a4a23ae52044897b`; green CI `30417301245`.
- Worker `20260729.1`, deployment `g1jq296j`; production route `openai/gpt-4.1`.
- Grok approval session `019fabb5-5e45-73a3-a885-e1146746948f`: `APPROVED FOR CI AND LIVE
  REGATE`, no P0/P1.
- Frozen SHA `398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`;
  key `licensed-team-responsibilities-v1`; matcher `field-aware-v3`.
- Run `run_06fqnh151dmai294bc2uble701`; document `c4ba034f-fb6c-40ee-a98e-fd20166a438b`;
  storage `admin/r2-deeper-gate/1785293185660-Licensed_Team_Responsibilities_2_-_tagged.txt`.
- Document-ingestion job `27dfc7fb-316d-4ad4-9479-60fe19200bcf` was still running downstream
  without error when measured. Source-workflow job `a8146ec8-4e25-4317-b220-356fb459b12b`
  completed with retry zero.
- Map `193376a7-848e-48e8-b5ec-8cca51285b3f` was `degraded`; final model run
  `687df936-2a0c-4e5f-86e5-70cd0077bfd9`; context pack
  `292560c5-2007-4a9f-bc76-30005abfc5ac`.
- 83 responsibility records; 225 total kept; 170 dropped; omissions `80 -> 72`.
- Budget: 24/40 calls, 59,973/500,000 input tokens, 1/1 general repair,
  `$0.299865/$10`, concurrency four. Post-pass used one combined repair and five omission retries,
  one per chunk.
- Combined repair failed atomically: accepted false, `repair_failed`; six selected field repairs;
  field failures `6 -> 6`; root quote failures `15 -> 15`.
- Merge/apply stayed false. `business_objects`, `business_object_versions`, and
  `business_model_changes` stayed zero before and after.

## Owner-approved bounded model bake-off — 2026-08-06

Albert selected the bounded model bake-off. Production capability data made Claude Sonnet 5 and
Gemini 2.5 Pro ineligible for the deep workflow schema, so only GPT-4.1 ran. Two serialized fresh
maps over the frozen document scored **11/30** and **12/30**, mean **11.5/30**, under unchanged
`field-aware-v3`. The detailed runs, maps, budgets, restoration proof, and deviation log are in
`evals/bakeoffs/workflow-read.md`.

The precommitted `<=23` rule is binding: the bake-off failed, no second bake-off is allowed, and R2
requires another deeper-architecture step. Merge/apply remained false and the durable business-
model tables remained empty.
