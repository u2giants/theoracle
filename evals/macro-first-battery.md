# Macro-First Battery / Gate Log

Append-only record for `MACRO_FIRST_REDESIGN.md` stage gates and acceptance-battery
runs.

## 2026-07-07 — Stage 2 Workflow Reader Gate — canonical swimlane fixture

Fixture: document `9d09fa89-3a46-465e-a98b-837287c9e22a`, `Pop Creations Flow 12112025 (1).png`.

Scope note: the destructive clean re-ingest path was blocked by the repo's provenance
guard before deletion: the document's old claims had 1 Brain citation and 2 gap
references. To preserve provenance, this gate ran `source-workflow-read` directly
against the existing persisted chunks and did not wipe the document.

Runs:

- `run_cmra2epx05qke0kmvp80vlrmd`: first workflow read, `validated`, map
  `5e120c73-2890-4627-acaf-b35857ae42d7`, `keptCount=151`, `droppedCount=0`.
- `run_cmra2g75q5z1m0wmvs9b47pz9`: same-content redispatch, `skipped_existing`
  against map `5e120c73-2890-4627-acaf-b35857ae42d7`.
- `run_cmra2gfri5u5l0mmzn7adxwj0`: forced rerun, `validated`, map
  `2615f242-897b-4724-9091-6e08108aec63`, old map superseded.
- `run_cmra2iihl5v400mmzp0rich66`: controlled failure with a deliberately invalid
  workflow-read route, failed loudly, wrote a failed map, and set
  `documents.macro_health='failed'`.
- `run_cmra2j6p95vxv0imzxsmqvsly`: restored settings and repaired the fixture,
  `validated`, map `86f33611-9bce-4f65-be2a-702c288ea478`.
- `run_cmra2ork561l00jonzlrqxfcv`: final run after making OpenAI primary,
  `validated`, active map `72ed0ef9-8ea7-4e60-84a3-a7e9236eb7c8`,
  `nodes=63`, `edges=71`, `lanes=14`, `paths=1`, `keptCount=149`,
  `droppedCount=0`.

Final DB state:

- `documents.status='complete'`, `documents.macro_health='complete'`,
  `processing_error IS NULL`.
- Exactly 1 non-superseded source workflow map remains for the document:
  `72ed0ef9-8ea7-4e60-84a3-a7e9236eb7c8`.
- Final active map attempt used `openai/gpt-4.1` as primary and succeeded.
- Prod settings now read:
  `default_workflow_read_route='openai/gpt-4.1'`;
  `model_pool_workflow_read=['openai/gpt-4.1','anthropic/claude-sonnet-5','google/gemini-2.5-pro']`.

Answer-key coverage, scored against `fix_enhancement.md` section 2.1:

- Stage-group recall: 9/9. The active map includes buyer engagement, creative
  direction, design execution, costing/factory sourcing, new-vs-existing branching,
  tech-pack revision loop, licensor concept approval, sampling/PPS audit, and
  order/production/shipment.
- Branch/loop recall: pass. The active map includes buyer price approval,
  new-vs-existing product branches, licensor legal-line/packaging vs creative-design
  branches, PPS audit pass/fail, re-sampling, and ship-to-US terminal flow.
- Systems recall: pass. The map includes DFlow, RFQ, ClickUp, ColdLion, MasterData,
  SKU creation, and PPT/library references.
- Lane/owner recall: pass. The map captured 14 lanes, including the expected
  Buyer/Sales/Creative/Technical/Junior/Sourcing/Production/Carlos/Gina/Licensing/
  Licensor/Factories roles. This exceeds the original rough 9-lane answer-key
  grouping because the diagram has additional named swimlanes/roles.
- Validation survival: pass. Final run kept 149/149 emitted elements after
  deterministic validation (`droppedRatio=0`), above the Stage 2 >=90% gate.

Gate result: PASS with one limitation. The full destructive re-ingest portion of the
gate was not run because provenance guards correctly blocked deleting live cited
claims. The workflow-reader, validation, same-hash idempotency, supersede semantics,
failure visibility, final health restoration, and route setting hardening were all
verified live.
