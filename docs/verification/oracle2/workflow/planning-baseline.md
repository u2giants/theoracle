# Workflow integrity planning baseline

This is a focused deterministic engineering observation, not completion of W01,
full-store/browser proof, deployment, company-source audit or business acceptance.

- Source: [recovery commit](https://github.com/u2giants/theoracle/commit/36e91038ee6b1126f9d9c27adce7583a6b74c654).
- Planning/main has a different source and test inventory; this count does not apply to main.
- Interpreter: Python 3.12.14; GraphRAG SDK 1.4.0.
- Exact command from the qualified recovery repository: `services/oracle-brain/.venv/bin/python -m pytest services/oracle-brain/tests/test_holistic_graphrag.py -q -p no:cacheprovider`.
- Result: exit 0; 32 passed. Provider responses use public deterministic fixtures; no paid provider dispatch, company question or store migration.
- Retained warning: SDK class-based Pydantic config deprecation; no test failure.
- W01 must repeat at its accepted integration head and preserve versions, source/lock digests and the actual red-first findings regression.

Checked October 11, 2026 EDT.

Posted by Codex chat 01a12b2c-9fa9-72c0-a132-341a402873d8 on edge-dev3
