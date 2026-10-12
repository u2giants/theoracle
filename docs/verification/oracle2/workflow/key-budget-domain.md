# Existing Oracle key budget coverage — preparation, not live acceptance

The owner's historical words were "$25 per day". The reviewed action recorded
in `plan_oracle_consultant_overhaul.md` changed only the existing theOracle key.
It explicitly preserved every other key and consumer. No account-wide cap,
new credential, workspace, purchase or change to unrelated application budgets
is implied here. The domain below requires independent technical review before
the coordinator issues any runtime admission.

## Coverage domain and controls

The reservation domain is every paid consumer holding that exact existing Oracle
credential, regardless of local machine, old recovery checkout, hosted worker or
application. Distinct provider credentials remain separate. Provider account
metadata is discovery evidence; a ten-key inventory does not prove control of
the Oracle key's holders. The provider's `/key` usage is key-specific.

Every paid consumer must use one current central atomic reservation ledger;
read-only catalog consumers and inactive preserved recovery consumers require
independent current receipts proving those dispositions. Retain their capability
and evidence. A queued call, unrecorded retry, outstanding batch, stale runtime
or unknown holder prevents admission. Do not manufacture a complete census from
repository searches or from absence of a local process.

`key_coverage.py` checks an externally admitted exact fingerprint, provider key
record, complete unique caller inventory, runtime revisions, ledger identity,
independent issuer/reviewer and zero unreserved callers/liabilities. Admission
must still be unexpired. Trusted coordinator readbacks of the current census,
ledger and liability receipts must agree; the live observation is at most
15 seconds old. The externally supplied reviewed admission hash is independent
of the receipt being checked. The native transport rejects arbitrary boolean
coverage and rechecks the key and ledger immediately before dispatch.

This verifier discovers no caller, secures no credential, deploys no ledger and
does not establish that any actual caller is controlled. A trusted runtime must
implement the readbacks and a separately admitted reservation path. Native
transport credentials must not be handed to an alternative caller that bypasses
the admitted adapter. Current code therefore remains preparation only.

Existing per-attempt $1, resumed-batch $5 and New York-day $25 reservations remain
binding. Monthly key usage plus BYOK is a conservative upper bound only away
from the UTC/New York month boundary; missing amounts, stale observations and
unfunded routes deny. Provider UTC daily reset never replaces the New York-day
ledger. Failed unknown charges retain the full reservation. Unresolved overruns
deny further dispatch. Current census/provider observations and reservations
must be checked for concurrent callers before a live receipt is issued.

## Required live evidence

1. Fingerprint the effective existing key for local source readers, recovery
   runtimes, Vercel web and Trigger production/development without printing it.
   Check deployed source revisions and all secret/config fallback paths; record
   read-only model-catalog calls separately from inference.
2. Establish every holder's live disposition and outstanding calls/batches.
   An inactive preserved reader has no standing private-processing admission;
   future resumption must enroll in the central reservation path first.
3. Verify the actual central store identity, schema/revision and permissions;
   exercise two concurrent synthetic consumers, exhaustion, crash/unknown cost,
   replay, day reset and revoked census against that same ledger.
4. Obtain independent exact-input review of coverage and runtime admission.
   Publish the review/hash and live proof on #27/#58; do not create a second
   leftover-proof issue. Only then may separately admitted private processing
   obtain per-call reservations. Questions, reports, employee messages and
   Ilona/Jessica grading remain paused.

All listed live evidence remains pending. Invented-source tests establish only
the verifier's rejection behavior, never real consumer coverage.
