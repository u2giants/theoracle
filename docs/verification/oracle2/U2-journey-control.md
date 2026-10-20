# U2 journey control — offline evidence

Status: offline gate evidence stub (synthetic/invented only).
Recorded: 2026-10-20 (S03 U2 opaque request/CAS/cancellation bridge offline).

## Offline tests

test_replacement_journey_control.py (21 passed): happy paths for reserve,
CAS advance across control states, native1..N attempt tracking, spent-nonce
retention, independently admitted recovery consume, cancel preserving paid
liability, cancel as non-remote-stop proof, idempotent reserve, and full
state-machine reachability. Denial paths held: forged actor (principal and
workspace), double cancel, replayed spent attempt, CAS conflict (stale/zero/
future revision), expired authority on reserve and refresh, illegal
transitions, idempotency conflict on different request, terminal journey
advance/admit refusal, forged request identity fields, native attempt shape
guards, and no automatic retry after spent dispatch.

test_replacement_job_authority.py (23 passed): opaque job DTO exact-field
refusal (workspace/actor/provider/profile/admission/private/hmac/reading/
source_text), duplicate JSON key refusal, bad identity and lease refusal,
HMAC signature message binding and mutation/wrong-key rejection, nonce UUID
identity, journey actor context server-held-only and closed role pattern,
journey request private-journal-field refusal, canonical bytes seal guard,
envelope size bound, source-private journal exclusion from job authority rows,
and journey control metadata opacity.

Related retained suites: test_replacement_adversarial_journey_v1.py
(11 passed, 3 skipped Windows-blocked), test_replacement_source_authority.py,
test_replacement_result_v1.py, test_original_qualification_runtime.py.

## What is proven

1. Opaque request identity: request bodies never carry actor, workspace,
   provider, profile, admission or private journal fields. Server-held
   JourneyActorContextV1 is a separate record; forged actor or workspace is
   denied before any state change.
2. CAS compare-and-advance: every state change requires the exact current
   journey_revision. Stale, zero, future and non-integer revisions raise
   JourneyConflict. The record is unchanged after a conflict.
3. Idempotency: same key + same request returns the existing journey;
   same key + different request raises idempotency conflict.
4. Cancel preserves paid liability: spent native attempts retain their cost
   after cancel. Cancel is not remote-stop proof (remote_stop_proof is
   False in the envelope). A spent dispatch is never replayed or refunded.
5. native1..N: multiple native attempts across a journey are tracked as an
   ordered unique sequence. Spent nonces are retained and never replayed.
   A new attempt gets a fresh nonce and sequence. Repeated nonce is denied.
6. Independently admitted same-attempt consume is recovery-only: it returns
   the retained spent record and never un-spends or re-dispatches.
7. Refresh requires current authority: expired context is denied before
   serving any journey metadata.
8. No automatic rePOST, paid retry, new budget, horizon or epoch: a spent
   attempt cannot be consumed or re-admitted under the same nonce.
9. Opaque job DTOs (mTLS ingress envelope) accept exactly the fixed field
   set. Private source journal fields never appear in job authority rows.
10. HMAC signature binds method, path and body. Mutation and wrong key
    fail comparison.

## SQL custody

sql/014_replacement_source_custody.sql gains four functions:
- oracle2.reserve_replacement_journey(jsonb,uuid): creates the run +
  processing_journey_runs_v1 row at state 'pending' / journey_revision 1,
  records a 'create' event under the idempotency key. Actor is derived
  from _replacement_request_context(); source selectors are scope-checked.
- oracle2.current_replacement_journey_metadata(uuid): returns current
  CAS revision, state and cancel/paid-liability flags for the pinned actor.
- oracle2.compare_and_advance_replacement_journey(uuid,integer,jsonb,uuid):
  CAS-advances state under the expected journey_revision; writes a
  'correct' or 'confirm' event. Terminal states and cancel-requested are
  refused here.
- oracle2.request_replacement_cancel(uuid,integer,text,uuid): CAS-cancels
  the journey, sets cancelled_at, writes a 'cancel' event, and returns
  the envelope with remote_stop_proof=false and retained-attempt flag.

All four: SECURITY DEFINER, least-privilege REVOKE from PUBLIC and every
restricted group, GRANT EXECUTE to oracle2_replacement_requester only.
The state CHECK constraint is widened additively to accept the U6 journey
control states alongside the existing executor projection states.

## Not accepted

Not accepted: no private originals, no employees, no company data, no live
provider call, no production deployment, no browser/native U2 stage closure,
no real mTLS handshake (TLS context construction is configuration-only).
This stub does not close the U2 stage while browser/native acceptance remains
open. S14/S15/S16 business and live acceptance stay closed.
