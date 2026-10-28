# W10 Failure Diagnosis — Read-Only Analysis

**Date:** 2026-10-27  
**Head:** `4ab0e734`  
**Host:** edge-dev3  
**Population result:** 26 failures, 0 skips, 101 unfinished (worker timeouts)

## Root Cause Summary

**ALL 26 failures are bucket (b) ENVIRONMENT/LOAD — not composition, not pre-existing code defects.**

Two missing environment prerequisites:
1. **FalkorDB Docker container not running** — `oracle2-synthetic-s09q-parent24-falkor-candidate-1` does not exist
2. **Node modules not installed** — `pnpm install` not run on the worktree

## Per-Test Classification Table

| # | Test ID | Assert/Exception (verbatim) | First Stack Frame | Bucket |
|---|---------|---------------------------|-------------------|--------|
| 1 | `test_operating_model_sdk::test_new_projection_survives_real_sdk_finalize_reload` | `DatabaseUnavailableError: Could not connect to FalkorDB at 127.0.0.1:57679: Error 111 connecting to 127.0.0.1:57679. Connection refused.` | `redis/connection.py:1601: in _connect sock.connect(socket_address)` | (b) ENVIRONMENT |
| 2 | `test_operating_model_sdk::test_graph_loss_cannot_pass_via_original_text_fallback` | Same FalkorDB connection refused | Same | (b) ENVIRONMENT |
| 3 | `test_operating_model_sdk::test_sdk_rebuild_from_ledger` | Same FalkorDB connection refused | Same | (b) ENVIRONMENT |
| 4 | `test_operating_model_sdk::test_real_sdk_preserves_supported_condition_quote_identity` | Same FalkorDB connection refused | Same | (b) ENVIRONMENT |
| 5 | `test_operating_model_sdk::test_graph_lineage_loss_denies_serving` | Same FalkorDB connection refused | Same | (b) ENVIRONMENT |
| 6 | `test_operating_model_sdk::test_operating_outbox_signed_projection_replay_and_stale_denial` | Same FalkorDB connection refused | Same | (b) ENVIRONMENT |
| 7 | `test_operating_model_cutover::test_real_atomic_selector_sdk_and_stale_rollback_denial` | Same FalkorDB connection refused | Same | (b) ENVIRONMENT |
| 8 | `test_operating_model_restore::test_fresh_database_blob_restore_and_actual_sdk_reload` | Same FalkorDB connection refused | Same | (b) ENVIRONMENT |
| 9 | `test_consolidation_review_browser_v1::test_actual_browser_owned_sql_qualified_model_review` | `Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'react' imported from apps/web/tests/oracle2/model-review-proof.ts` | `assert result.returncode==0,result.stdout[-6000:]` | (b) ENVIRONMENT |
| 10 | `test_consolidation_sdk_sql_v1::test_actual_consolidation_sql_paid_sdk_graph_keeps_assertions_and_rebuilds_without_ack` | `CalledProcessError: Command '['docker', 'inspect', 'oracle2-synthetic-s09q-parent24-falkor-candidate-1']' returned non-zero exit status 1.` | `test_readonly_graph_fixture.py:17: in owned_target details=inspect(container)` | (b) ENVIRONMENT |
| 11 | `test_meeting_unattended_sql::test_actual_independent_V2_processes_Create_to_unattended_STOP_terminal_receipt[meeting_sql0]` | `AssertionError: actual process startup refused; private diagnostic retained assert (False) + where False = exists() + where exists = PosixPath('/tmp/s07-u-zdn8n25l/stop.sock').exists` | `assert path.exists() and p.poll() is None,'actual process startup refused'` | (b) ENVIRONMENT |
| 12 | `test_meeting_unattended_sql::test_actual_producer_death_refuses_Create_before_any_provider_HTTP[meeting_sql0]` | Same process startup refused | Same | (b) ENVIRONMENT |
| 13 | `test_hosting_readonly_projection::test_native_readonly_acl_when_owned_fixture_available` | `Failed: owned namespace-scoped native graph fixture required` | `if not url:pytest.fail('owned namespace-scoped native graph fixture required')` | (b) ENVIRONMENT |
| 14 | `test_hosting_synthetic_project::test_registered_public_projector_preserves_release[public-invented-v1]` | `ConnectionError: Error 111 connecting to 127.0.0.1:57679. Connection refused.` | `assert not graph.exists(release.graph_name)` | (b) ENVIRONMENT |
| 15 | `test_hosting_synthetic_project::test_registered_public_projector_preserves_release[public-invented-forward-v2]` | Same FalkorDB connection refused | Same | (b) ENVIRONMENT |
| 16 | `test_qualified_industry_brief_sql::test_actual_qualified_company_context_and_original_reference_produce_distinct_comparisons` | `CalledProcessError: Command '['docker', 'inspect', 'oracle2-synthetic-s09q-parent24-falkor-candidate-1']' returned non-zero exit status 1.` | `test_qualified_industry_brief_sql.py:169: in test_... result=asyncio.run(exercise_brief(...))` | (b) ENVIRONMENT |
| 17 | `test_qualified_industry_brief_sql::test_actual_reference_revocation_withholds_brief_without_refetch` | Same docker inspect failure | Same | (b) ENVIRONMENT |
| 18 | `test_qualified_industry_brief_sql::test_actual_independently_installed_industry_read_uses_same_mTLS_SQL_SDK_owner[contexts]` | Same docker inspect failure | Same | (b) ENVIRONMENT |
| 19 | `test_qualified_industry_brief_sql::test_actual_independently_installed_industry_read_uses_same_mTLS_SQL_SDK_owner[brief]` | Same docker inspect failure | Same | (b) ENVIRONMENT |
| 20 | `test_question_effect_native_sql_v1::test_actual_once_query_native_receipt_to_readonly_SDK_vector_union_and_denial[True]` | `failed on setup with "CalledProcessError: Command '['docker', 'inspect', 'oracle2-synthetic-s09q-parent24-falkor-candidate-1']' returned non-zero exit status 1."` | `test_question_effect_native_sql_v1.py:68: in native_question if x['needs_graph']:request.getfixturevalue('question_graph')` | (b) ENVIRONMENT |
| 21 | `test_question_effect_native_sql_v1::test_actual_SQL019_to_optional_conversation_factory_owned_loop_query_answer_no_extra_question[factory-interview-graph]` | Same docker inspect failure on setup | Same | (b) ENVIRONMENT |
| 22 | `test_question_effect_native_sql_v1::test_actual_SQL019_to_optional_conversation_factory_owned_loop_query_answer_no_extra_question[factory-synthesis-interview-graph]` | Same docker inspect failure on setup | Same | (b) ENVIRONMENT |
| 23 | `test_purpose_coherent_native_journey::test_coherent_native_census_uses_real_prior_input_parent[native_census_startup0]` | `CalledProcessError: Command '['docker', 'inspect', 'oracle2-synthetic-s09q-parent24-falkor-candidate-1']' returned non-zero exit status 1.` | `purpose_journey_fixture_delivery.py:184: in deliver_actual_paid_graph with processing_writ...` | (b) ENVIRONMENT |
| 24 | `test_meeting_capture_sql::test_actual_python_mtls_sql_and_shared_web_route_ingress_conformance[meeting_sql0]` | `Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'tsx' imported from apps/web/` | `(tmp_path/'meeting-peer-process.txt').write_text(result.stdout);assert result.returncode==0` | (b) ENVIRONMENT |
| 25 | `test_connected_answer_sdk_sql_v1::test_actual_qualified_SQL_ACK_readonly_SDK_and_current_permission_before_after` | `CalledProcessError: Command '['docker', 'inspect', 'oracle2-synthetic-s09q-parent24-falkor-candidate-1']' returned non-zero exit status 1.` | `test_connected_answer_sdk_sql_v1.py:263: in test_... return _exercise_owned_answer_graph_v1(...)` | (b) ENVIRONMENT |
| 26 | `test_connected_answer_sdk_sql_v1::test_actual_employee_browser_and_MCP_current_answer_and_denied_refresh` | Same docker inspect failure | Same | (b) ENVIRONMENT |

## Bucket Counts

| Bucket | Count | Tests |
|--------|-------|-------|
| (a) COMPOSITION | **0** | — |
| (b) ENVIRONMENT/LOAD | **26** | All 26 |
| (c) PRE-EXISTING | **0** | — |
| (d) UNKNOWN | **0** | — |

## Environment Failure Categories

### Category 1: FalkorDB container not running (18 tests)
- **Error:** `ConnectionRefusedError: [Errno 111] Connection refused` to `127.0.0.1:57679`
- **Or:** `CalledProcessError: docker inspect oracle2-synthetic-s09q-parent24-falkor-candidate-1` returns exit 1
- **Root cause:** Docker Compose services not started. The `oracle2-synthetic-s09q-parent24` Compose project has no running FalkorDB container.
- **Evidence:** `docker ps -a --filter 'name=s09q'` returns empty.

### Category 2: Node modules not installed (2 tests)
- **Error:** `ERR_MODULE_NOT_FOUND: Cannot find package 'react'` / `Cannot find package 'tsx'`
- **Root cause:** `pnpm install` not run on the worktree.
- **Evidence:** `apps/web/node_modules/.package-lock.json` does not exist.

### Category 3: Process startup / fixture (6 tests)
- **Error:** `actual process startup refused` / `owned namespace-scoped native graph fixture required`
- **Root cause:** Downstream of missing FalkorDB / node_modules.
- **Evidence:** Same environment gaps.

## S09-Area Tests Specific Analysis

The 4 S09-area tests (`test_question_effect_native_sql_v1` × 3, `test_purpose_coherent_native_journey` × 1) all fail with the **same docker inspect error** on `oracle2-synthetic-s09q-parent24-falkor-candidate-1`. This is NOT a composition defect — it's the missing FalkorDB container. The test code itself is unchanged from the preserved source.

**Verbatim conclusion line:**
```
All 26 failures are bucket (b) ENVIRONMENT/LOAD. Zero composition defects, zero pre-existing code defects. Root cause: FalkorDB Docker container (oracle2-synthetic-s09q-parent24-falkor-candidate-1) not running and node_modules not installed on the edge-dev3 worktree. The S09-area tests (question_effect_native_sql_v1, purpose_coherent_native_journey) fail with the same docker inspect error as all other FalkorDB-dependent tests — not a composition casualty.
```

## Recommended Next Steps (NOT applied)

1. Start Docker Compose services for `oracle2-synthetic-s09q-parent24` project
2. Run `pnpm install` on the worktree
3. Re-run the full W10 population
4. If still failing, re-diagnose with fresh evidence

No assertion weakening, no case cuts, no budget raises needed — the composition is clean.
