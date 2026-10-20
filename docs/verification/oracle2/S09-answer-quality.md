# S09 connected and company-wide answers — offline evidence

Status: offline building-block leaves landed (synthetic/invented only).
Recorded: 2026-10-20 (S09 offline leaves closeout).

## Offline tests

Named gate files, all collected and passing without skip (54 passed, 0 skipped):

| File | Tests | Result |
|---|---:|---|
| test_retrieval_modes.py | 14 | pass (import guard active — `oracle_brain.retrieval.planner` present) |
| test_query_bounds.py | 16 | pass (import guard active — `oracle_brain.retrieval.packing` present) |
| test_citation_entailment_contract.py | 9 | pass (rewritten from pure stub; real quote-level entailment assertions) |
| test_global_scope.py | 8 | pass (rewritten from pure stub; real coverage/revision/support assertions) |
| test_mcp_parity.py | 7 | pass (rewritten from pure stub; real bounded read-only parity assertions) |

Command: `.venv/Scripts/python.exe -m pytest -q tests/test_retrieval_modes.py tests/test_query_bounds.py tests/test_citation_entailment_contract.py tests/test_global_scope.py tests/test_mcp_parity.py`
(`uv run --extra test` blocked on this host by hnswlib/MSVC; minimal pydantic+pytest+psycopg venv used instead. Pure pytest is sufficient for these offline leaves.)

## Landed modules

All under `services/oracle-brain/oracle_brain/retrieval/`, pure Python, no I/O:

- `planner.py` — AccessBounds, HistorySpan, RetrievalPlan, plan_retrieval (ported from `origin/codex/oracle-s09-connected-answers`).
- `packing.py` — AssembledAnswer, CoverageBounds, SpanCandidate, assemble_answer, filter_by_access, filter_by_history (ported from the same hold branch).
- `citations.py` — quote-level entailment contract: QuoteCitation/SourceText, exact span alignment, deterministic token-subset entailment, unsupported claims rejected.
- `global_summary.py` — GlobalClaim/GlobalSupport/GlobalSummary: no company-wide claim without explicit CoverageBounds; partial vs complete labels; every published claim retains revision and support.
- `mcp_parity.py` — bounded read-only MCP adapter parity surface: PermissionBoundary shared with web retrieval (access-bounds filter, denied source refused), write/unknown tools refused, parity_report asserts web/MCP alignment.

## Not accepted

- Live/production acceptance is not claimed. S14/S15/S16 business and live acceptance stay closed.
- No company data, no employees, no production actions, no provider/network/DB calls in the modules.
- The legacy `apps/web/lib/mcp/` registry is not replaced; `mcp_parity` is the offline permission-boundary twin only.

This leaf set does not close #33. Remaining stage gaps: wiring these building blocks into the connected/company-wide answer path, live MCP adapter, and end-to-end S09 acceptance.
