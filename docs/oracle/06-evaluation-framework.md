# Evaluation Framework

Status: mandatory constraints for evaluation implementation.

## The Problem
The spec relies heavily on metrics like "cost per valid claim," "evidence quote validity," and "wrong-domain rate" to determine if a model route is approved for production. If left unbounded, an AI agent might attempt to build a massive, complex Web UI to manage these tests.

## The Constraint: CLI-Only Evaluations
Do not build a web UI for evaluations.

Evals will be executed strictly via local CLI scripts (using Jest, Vitest, or a native Node runner).

1. Create a `packages/ai/evals/` directory.
2. Store 3–5 hardcoded "Gold Standard" test transcripts as static `.json` files.
3. Build a runner (e.g., `pnpm run eval:extraction`) that feeds the transcripts through the `OracleAIClient`.
4. The runner must bypass the database and output the precision, recall, and quote-validity metrics directly to the developer console.
5. A model route configuration may only be promoted to `DEFAULT_ORACLE_MODEL_ROUTES` if it passes the CLI eval suite with ≥98% quote validity.
