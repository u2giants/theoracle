# Q2b target catalog proof — offline tooling only

Status: offline tooling only — actual target owner/caller/TLS remain UNKNOWN; this does not satisfy Q2b and does not authorize installation/live action.

Recorded: 2026-10-20 EDT. Branch `mimo/q2b-catalog-proof`. No company data, no employees, no production or shared database connection.

## Scope

Offline metadata-only catalog-proof TOOLING for `plan_oracle_source_processing_qualification.md` §9.1 / §13. The actual target read is separately admitted later and is NOT claimed here. Q2b remains OPEN.

Module: `services/oracle-brain/oracle_brain/operating_model/q2b_target_catalog_v1.py`
Tests: `services/oracle-brain/tests/test_q2b_target_catalog_v1.py` (52 passed, synthetic/isolated only)

## Six fact classes

The receipt records exactly these six classes, each may be `UNKNOWN`. Nothing is invented.

1. `pg_proc_owner` — actual `pg_proc` owner name per named helper function
2. `security_definer` — `SECURITY DEFINER` flag (`prosecdef`)
3. `search_path` — `proconfig` search_path, expected exactly `['search_path=pg_catalog, oracle2']`
4. `execute_grants` — EXECUTE grants via `aclexplode`/`proacl` including `is_grantable`
5. `role_memberships` — `pg_has_role` reachability (MEMBER/SET/USAGE) proving owner unreachability
6. `target_identity` — host/port/dbname/user + TLS (`ssl_in_use`, `sslmode`)

`admitted` stays `false` until a separate admission exists. This tooling never sets it true on its own.

## Synthetic tests

Reader emits the exact six fact classes (`test_reader_emits_exactly_the_six_fact_classes`).
UNKNOWN is recorded, never invented (`test_unknown_facts_are_recorded_not_invented`, `test_parse_helpers_keep_unknown_without_inventing_values`).
Damage denied:
- wrong owner (`test_damage_wrong_owner_denied`)
- missing SECURITY DEFINER (`test_damage_missing_security_definer_denied`)
- wrong search_path (`test_damage_wrong_search_path_denied`)
- PUBLIC EXECUTE grantable (`test_damage_public_execute_grantable_denied`)
- grantable EXECUTE (`test_damage_grantable_execute_denied`)
- owner reachable via MEMBER/SET/USAGE (`test_damage_owner_reachable_via_membership_denied`)
- owner in reachable role set (`test_damage_owner_in_reachable_roles_denied`)
- TLS not in use (`test_damage_tls_not_in_use_denied`)
- sslmode not verify-full (`test_damage_sslmode_not_verify_full_denied`)
- target identity mismatch (`test_damage_target_identity_mismatch_denied`)
- session role differs (`test_damage_session_role_differs_denied`)
- owner assumed via SET ROLE (`test_damage_owner_assumed_via_set_role_denied`)
Missing pins fail closed (`test_missing_pins_fail_closed`, `test_incomplete_grant_coverage_fails_closed`, `test_unlisted_signature_grants_fail_closed`, `test_reader_refuses_incomplete_descriptor_before_any_sql`).
Reader SQL text contains no source-data SELECTs (`test_reader_sql_text_contains_no_source_data_selects`, `test_non_metadata_sql_is_refused`, `test_reader_executes_only_the_three_catalog_statements`).
UNKNOWN blocks target execution (`test_unknown_blocks_target_execution`).

## Explicit non-claims

- Actual target `pg_proc` owner: UNKNOWN
- Actual caller/role membership: UNKNOWN
- Actual TLS/session identity: UNKNOWN
- Q2b: OPEN. This stub does not satisfy Q2b and does not authorize installation or any live target action.
- No substitute owner/admin path is created. UNKNOWN must not cause one.

## R8 reader seal and trust model

The application is verification-only. `read_target_catalog` collects the six
metadata classes but returns an unsealed, unadmitted receipt. It never invokes
a signer or knows a private-key path. An independent host authority must attest
the exact canonical fact payload (`q2b-reader-facts:v1`) and independently
authorize that same payload (`q2b-admission:v1`). The caller supplies both
signatures; `admit_target_catalog(..., admission_mac=...)` verifies them and
rechecks all pins. `require_target_catalog` repeats both signature and pin
checks. Both admission and every use require a new catalog read on an exact
trusted DB-API connection and compare the current facts with the host-attested
payload. Attestations include a signed observation time and at most a 60-second
validity window; absent connection or expired/currently changed facts deny. A
sealed connection wrapper cannot substitute a fake underlying driver.

An `admitted` boolean or matching caller-provided facts grant nothing.

The retained host signing executable is separate from the application. Its
fixed `/etc/oracle2/seal-signer.json` must be root-owned and not group/other
writable. Configuration pins a signer Unix identity distinct from the
application identity, a key readable only by that signer, and a separate grant
authority public key. Every signing request requires an independently signed,
unexpired grant binding the exact canonical purpose-tagged payload digest and
host audience. Configuration/key reads reject symlinks and check the opened
file ownership and permissions. Application environment key paths are ignored.

Canonical JSON arrays preserve every signed field boundary. Participation
proofs cover every setting and are retained/reverified at use sites.

Invented fixture tests simulate the independent host and exercise valid
admission, forged/tampered evidence refusal, and host grant policy. They do not
establish installed OS isolation. Actual host identity/configuration/key
installation and independent authority operation remain unproven and outside
this offline implementation. Actual target proof remains UNKNOWN; Q2b stays
OPEN. No host, production, company-data or employee action was performed.
