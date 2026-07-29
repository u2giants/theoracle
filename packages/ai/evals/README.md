# Oracle CLI evals

Per `docs/oracle/06-evaluation-framework.md`. Evaluation execution remains
CLI-only. The read-only admin dashboard displays safe summaries after a run.

## Why CLI-only

> "Evals will be executed strictly via local CLI scripts (using Jest, Vitest,
> or a native Node runner)... [no] massive, complex Web UI to manage these
> tests."
> — `06-evaluation-framework.md` § The Constraint

## Layout

```
packages/ai/evals/
  fixtures/                 Static JSON test fixtures, organized by category
    extraction/
      transcript-01-*.json
      ...
  mocks/                    Canned LLM outputs paired by fixtureId
    canned-extraction-outputs/
      transcript-01.json
      ...
  runners/                  Per-category eval runners
    eval-extraction.ts
    shared/
      fixture-loader.ts
      metrics.ts
      report.ts
  runs/                     (gitignored) Per-run output artifacts
    extraction-<UTC-timestamp>/
      summary.json
      per-fixture.json
  published/                Safe, reviewable release summaries
    index.json
    extraction-<UTC-timestamp>.json
```

## Running

```bash
pnpm --filter @oracle/ai eval:extraction  # extraction eval over all fixtures, mock mode
```

Mock mode (the default) uses canned LLM outputs from `mocks/canned-*-outputs/`
matched by `fixtureId`. No network, no API keys, no DB. The runner exercises
the same pure validators the smoke gates exercise, but with per-fixture
`expected` blocks and aggregate metrics (precision / recall / quote validity /
sensitive quarantine pass / etc).

Live-provider mode is reserved for future use. The mock-mode runner is
sufficient to verify the deterministic pieces of the pipeline (R5 + R5.5
validators + R5 promotion decider) against realistic transcript shapes.

## How fixtures + mocks pair up

Every fixture file (`fixtures/<category>/<id>.json`) has a matching mock
file (`mocks/canned-<category>-outputs/<id-prefix>.json`) keyed by the
**numeric prefix** of the fixture file. So `transcript-01-routine-handoff.json`
pairs with `mocks/canned-extraction-outputs/transcript-01.json`.

Adding a new fixture:
1. Drop a new `fixtures/extraction/<id>.json` file matching `ExtractionFixture`
   from `docs/oracle/06-evaluation-framework.md` § Extraction fixture shape.
2. Drop a matching `mocks/canned-extraction-outputs/<id-prefix>.json` with the
   canned `ExtractionOutput` (matching `packages/ai/src/prompts/extraction-system.ts`
   `ExtractionOutputSchema`) the LLM would produce on this transcript.
3. Run `pnpm --filter @oracle/ai eval:extraction` — the new fixture is picked up automatically.

## What's covered today

| Category | Status |
|---|---|
| Extraction | ✅ mock-mode runner + 4 fixtures (routine handoff, paraphrase trap, sensitive PII trap, duplicate-rule trap) |
| Retrieval | not yet shipped |
| Synthesis | not yet shipped |
| Validation | covered by `verify:r5` (33 + 23 mapper) and `verify:r5.5` (45) |
| Segmentation | covered partially by `verify:r5.5` |
| Cache | covered by `verify:r7` (19) |

The extraction runner is intentionally first because it exercises the
deepest stack: extraction prompt output → `validateSourcePointer` → `validateQuote`
→ `validateTaxonomy` → `decidePromotion`. Everything else is incremental.

## Output

Each run writes:

```
runs/extraction-<UTC-timestamp>/
  summary.json        Aggregate metrics across all fixtures
  per-fixture.json    Per-fixture pass/fail breakdown with failure details
```

`runs/` is gitignored. It may contain source-derived failure details and must
never be published. The runner also writes a deliberately small summary to
`published/`: run time, exact commit SHA, fixture-set hash, route, gate result,
prompt version, counts, aggregate metrics, optional execution cost/usage, and a
safe summary link. It never includes prompts,
source text, per-fixture failure notes, provider payloads, or credentials.
Commit the safe summaries with the code only when they are intended as release
evidence. The admin dashboard is read-only; it never starts an eval.

Safe publishing is skipped when any tracked work outside `published/` is dirty.
This keeps the stored commit SHA truthful. Existing safe summary files are all
validated against the current allowlist before `index.json` is rebuilt.
