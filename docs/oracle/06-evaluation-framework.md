# Evaluation Framework

Status: mandatory phase gate for Oracle AI quality.

This document defines how Oracle-specific evals are built and run.

## Executive decision

Do not build an evaluation web UI at first.

Evals must start as CLI-run TypeScript tests/scripts using static fixtures.

The first goal is to prove extraction, validation, retrieval, and synthesis quality without creating a dashboard project that distracts from the core pipeline.

## Tooling decision

Initial evals should use repo-native TypeScript tooling:

- Vitest if the repo already has or adds it for test suites;
- otherwise a simple Node/tsx runner is acceptable;
- static JSON fixtures stored in the repo;
- console output and JSON result artifacts.

Do not introduce Braintrust, LangSmith, Promptfoo, or another external eval platform during the initial retrofit unless Albert explicitly approves it later.

External eval tooling can be reconsidered only after:

1. candidate-before-claim pipeline works;
2. OracleAIClient/provider adapters work;
3. context packs and usage logging work;
4. at least 5 local extraction fixtures exist;
5. costs and validation failures are measurable.

## Required commands

Add package scripts such as:

```bash
pnpm eval:extraction
pnpm eval:retrieval
pnpm eval:synthesis
pnpm eval:all
```

The exact package location may be chosen during implementation, but the commands must be documented and runnable locally.

## Fixture location

Recommended structure:

```text
packages/oracle-engines/evals/
  fixtures/
    extraction/
      transcript-01.json
      transcript-02.json
      transcript-03.json
      transcript-04.json
      transcript-05.json
    retrieval/
      erp-image-upload-question.json
      vendor-manual-contamination.json
    synthesis/
      brain-section-approval-flow.json
  runners/
    eval-extraction.ts
    eval-retrieval.ts
    eval-synthesis.ts
```

Fixture files should contain:

- source messages/document chunks;
- expected claim summaries or labels;
- expected exact quotes;
- expected domains/process stages/source types;
- expected rejects;
- expected sensitive/quarantined candidates;
- expected retrieval inclusions/exclusions.

## Extraction evals

Extraction evals must measure:

- exact quote validity;
- precision of extracted claims;
- recall of known expected claims;
- wrong-domain rate;
- duplicate candidate rate;
- sensitive material rejection/quarantine rate;
- schema validity;
- validation-loop circuit breaker behavior;
- cost per valid candidate if live model calls are enabled.

Initial fixture requirement:

- at least 5 hardcoded transcript/document fixtures;
- include at least one group-chat disagreement;
- include at least one paraphrase trap;
- include at least one synthesized-quote trap;
- include at least one sensitive/personal-material trap;
- include at least one duplicate-claim trap.

## Retrieval evals

Retrieval evals must prove the Oracle does not search the entire knowledge base blindly.

Required tests:

1. ERP image-upload question:
   - query asks when an image gets uploaded to Coldlion;
   - expected retrieval includes Coldlion/artwork/design/production claims;
   - expected retrieval excludes vendor manuals unless explicitly requested.
2. Vendor manual contamination:
   - query asks an internal handoff question;
   - expected retrieval excludes vendor manuals and customer routing guides.
3. Exact entity lookup:
   - query includes a SKU, customer code, factory code, licensor, or system name;
   - expected retrieval uses full-text/entity search, not vector search only.
4. Superseded claim exclusion:
   - current-operation query should exclude superseded claims unless history is requested.

Retrieval evals must output:

- retrieval plan;
- domains searched;
- domains excluded;
- source types searched;
- document classes searched;
- whether broadening occurred;
- final included IDs;
- expected vs actual pass/fail.

## Synthesis evals

Synthesis evals must measure:

- every material paragraph maps to approved claim IDs;
- no unsupported named people/systems/customers/process stages are introduced;
- rejected/sensitive candidates are not used;
- superseded claims are not used as current truth;
- structured diff validates;
- usefulness rating if human-rated output is available later.

Do not rely on model self-judgment for synthesis correctness.

Backend validation must check evidence support.

## Live vs mock mode

Evals should support two modes:

### Mock/deterministic mode

Uses canned model outputs to test validators, retrievers, and promotion logic without provider cost.

This mode must be available first.

### Live-provider mode

Calls the selected route through `OracleAIClient` and measures real model behavior/cost.

This mode must require an explicit flag, such as:

```bash
ORACLE_EVAL_LIVE=1 pnpm eval:extraction
```

Do not make live-provider evals the default.

## Output format

Each eval command should print a human-readable summary and optionally write JSON artifacts.

Example console output:

```text
Extraction eval summary
fixtures: 5
expected claims: 18
valid extracted claims: 16
precision: 0.89
recall: 0.78
exact quote validity: 1.00
wrong domain rate: 0.06
sensitive quarantine pass: true
duplicate rate: 0.00
cost: mock mode
PASS
```

## Phase gates

Do not enable broad background extraction until extraction evals pass.

Do not enable broad retrieval-backed chat until retrieval evals pass.

Do not enable automatic Brain section updates until synthesis evals pass.

Minimum initial gates:

- exact quote validity: 98%+ on test fixtures;
- sensitive quarantine: 100% on test fixtures;
- no known vendor-manual contamination in retrieval tests;
- no unsupported Brain synthesis paragraph in synthesis tests;
- no duplicate permanent claim creation in duplicate-promotion tests.

## What not to build yet

Do not build:

- a web eval dashboard;
- a complex annotation platform;
- third-party eval integration;
- model fine-tuning pipeline;
- RLHF workflow;
- automated prompt optimization service.

Start with simple CLI evals that are impossible to ignore during implementation.
