# S13 current replacement recovery — quarantined source, acceptance open

This record belongs to parent #24. It does not close S13, grant an operation,
install SQL026, admit a database/container/private root, authorize a provider or
company operation, or satisfy business acceptance. Source/parser/file tests,
reviewed and merged source, actual installation, an invented disaster exercise,
measured scale/RTO/RPO, private/company runtime and business acceptance are
separate outcomes. No complete replacement disaster exercise, RTO≤60 minutes or
RPO≤15 minutes is presently claimed by this source increment.

The earlier dated offline receipt (2026-10-20) recorded12 passed and2
skipped. Its statements about absent recovery source were historical. The
existing operations/recovery.py now reconciles supplied descriptive records and
classifies UNKNOWN without dispatch authority. It is not an operational restore.
The old ForwardRecovery constructor, fixed scenario, Backup/Restore records and
closed command grammar retain their exact purpose and authority restrictions.
They cannot be replayed as authority for the current replacement. Existing
PostgresSaver ownership binding alone is not current membership, source access,
workflow resume, provider or send authority.

## Current closed source owners

The SAME hosting/forward_recovery.py and hosting/restore_receipts.py own private
archive/TOC validation and the additive quarantined replacement orchestration.
operating_model/recovery_contracts_v1.py owns the strict immutable metadata records;
operating_model/recovery_authority_v1.py owns the concrete fixed own-role SQL026
consumer. It reuses operating_model/protected_inputs_v1.py for protected-file
and canonical parsing, protected_sql_connection_v1.py for the actual psycopg
connection, and request_deadline_v1.py for the original wall/monotonic fence and
every SQL send/commit/close. No second connector, clock, registry, truth ledger,
cost allowance, requester impersonation, callback authority or grant issuer is
introduced. Importing the source performs no operation.

The new private archive validator refuses unknown/missing/duplicate members,
symlinks/devices/traversal, mismatched exact private UID/mode/size/hash, truncated
bytes and aggregate/count overflow. The supplied actual PGDMP/complete TOC must
match exact declared table/data population and actual dump hash. Those supplied
bytes are descriptive custody evidence, never authenticated capture authority,
snapshot consistency, retained-vector completeness or graph readiness. The
initial archive inspector has no dump/restore/ready callback.

## Capture, restore and the intact original control plane

Capture and restore are different independently installed operations. Capture
has no future manifest hash or restore target. Restore references an EXISTING
immutable backup manifestSHA and original captureUUID and uses fresh separately
current custody/retention/technical restore authority. Expiration of the capture
authority does not destroy the backup, authorize a new read, or renew capture,
provider, source, principal, password, grant, paid purpose or original horizon.
An operation is finite≤3600seconds. Every actual request retains its original
wall and monotonic bound≤30seconds; a later read lease cannot extend a phase.

The immutable global operation/phase master lives ONLY on the intact original
control SQL plane, descriptor.current_control_source. Global uniqueness is
operationUUID+phase, excluding admission/runtime/reinstallation/allocation
identity. A duplicate exact claim retains the original identity/deadline with
fresh:false; it never permits another possibly effected attempt. Different or
lost effects remain UNKNOWN. A new operation cannot replay or overwrite the
same partially restored physical database/private root. Physical target
reservations are immutable and independent of generation/admission.

The initial target is a genuinely empty, distinct actual physical DB/catalog
with an existing independently installed bounded restore-executor identity.
Its emptiness is observed BEFORE restore and retained; it is not called empty
after restore. No target SQL026 admission/phase master is preinstalled to fake
emptiness. The concrete source must reread actual authenticated ORIGINAL
control currentness/master before and after every target effect, without SQL
locks across network/private file/target work. Loss of original control leaves
quarantine and RPO UNKNOWN. A surviving original primary/control/once/cost plane
is a limited rehearsal, not proof of replicated completeness under total loss.

The descriptor's sorted purpose_bindings are closed
{schema_version:1,phase_authority,principal_id,sql_identity}. They are selected
by fixed source code, never a request override. Duplicate phases and shared own
roles refuse. Master/current-denials/observe use purpose-distinct direct roles
on the SAME actual original physical control plane. The descriptor enumerates
complete sorted workspace/rooted appointment coverage, explicit canonical and
checkpoint DBs, every covered-key ledger, every private input/target root,
complete canonical migration inventory, accepted graph identities and archive
bounds. Physical source DBs occur once even with multiple purposes. Every
covered ledger resolves an explicit actual participant; omitted known owners,
foreign workspaces, ambiguous roots or actual owner/catalog/source drift refuse.

SQLIdentity pins actual system identifier/DB OID/name/owner/own SESSION_USER,
single verify-full hostname+numeric hostaddr+port, actual protected URL and CA
path/hash/dev/inode/uid/mode600, and complete actual catalogSHA. No DNS/multihost,
PG environment defaults, caller URL, missing CA or target override is accepted.
Private root pins are actual absolute path/rootUUID/dev/inode/uid/mode700 and
profileSHA. Runtime cannot create/chmod a root, role, grant or admission.

## Independent postrestore and custody installation

After restore, an external independently reviewed TEST issuer may observe the
actual target/catalog/roles and install a NEW closed PostRestoreBindingV1 and
target deny-only/observe admission. Runtime never issues it. Its exact fields
are schema_version1/protocol, restore_operation_id, original_capture_operation_id,
backup_manifest_sha256, descriptor_sha256, master_phase:'restore',
master_claimed_at, original_phase_deadline, target_physical_identity,
actual_postrestore_catalog_sha256, exactly two sorted purpose_bindings
(deny-only-target and observe), issuer_actor, reviewer_actor, issued_at,
expires_at, original_horizon. Issuer/reviewer and target principals are distinct.
The target physical identity must match the original pre-restore target;
actual catalog pins come AFTER restore, never from a fabricated future OID or
catalog. Its expiry/horizon cannot exceed the exact original retained restore
claim deadline. It references the same original master/claim/manifest/capture
and cannot reset replay or renew the old phase.

All restored application roles stay NOLOGIN/passwordless; old positive grants
are historical. The first quarantined target accepts only the separately
installed recovery role bindings. No serve/dispatch activation exists. Fresh
read roles, if later independently installed by the TEST issuer after the
actual overlay, remain a separate source/currentness proof and never follow
from a recovery observation or status:'complete'. No passwords, TLS private
keys or credentials may be copied into a backup/positive restored permission.

The separately installed BackupCustodyV1 amendment is required before an actual
capture/restore actuator. Capture must name a preinstalled output root disjoint
from every input root, with actual current rooted custody permission, and may
create only its own UUID-scoped immutable files without a future manifestSHA.
Restore must name the actual existing protected manifest and actual archive
files within independently current retained custody; all byte hashes and file
identity tuples must match descriptor.backup_manifest_sha256. Root scope and
retention metadata need actual appointments; retention is not deletion
permission. A hash alone supplies neither a locator nor private-byte authority.
The first connected deny-only slice does not pretend this actuator exists.

## SQL026 fixed operational contract

SQL026 source creates immutable operational admissions/revocations, global
claims/target reservations, observations and ADD-DENY imports/overlays. There
is no new truth store, spend allowance, permission issuer, runtime INSERT on
admissions, role/grant creation or serving activation. Four public signatures
are fixed:

- recovery_current_v1(uuid,timestamptz) → jsonb
- claim_recovery_phase_v1(uuid,text,timestamptz) → jsonb
- observe_recovery_phase_v1(uuid,text,bytea,timestamptz) → jsonb
- import_recovery_denials_v1(uuid,bytea,timestamptz) → jsonb

Purpose authority is EXACT capture|current-denials|deny-only-target|observe.
Capture requires its actual capture and deny-census rooted scope in every
workspace. Current-denials reads only the fresh current census for the restore
operation; it cannot capture, claim an effect, restore or grant. Deny-only-target
permits only separately scoped quarantined phase reservation/import/observation
and ADD-DENY/fence state, never a positive grant. Observe is independently
current finite metadata-only authority; it may record an old phase result after
that phase expired without changing its original horizon or dispatch state.

Every call independently verifies current actual direct lowpriv LOGIN, no
memberships/SET/USAGE/privileged roles, own immutable admission/principal/runtime/
registry/operation/descriptor SHA, actual rooted ancestor chain and complete
coverage, TLS/target/owner and exact current function OIDs/bodies/security-definer/
search_path/full ACL. Private helpers remain owner-only; public grants may only
be direct lowpriv LOGIN/no grant option under the fixed capabilities. The
concrete consumer also checks actual complete namespace catalog identity and
rereads every existing protected file before/after. No ducktyped resolver or
supplied hash/record substitutes for actual own SQL.

Current metadata includes only the fixed context, actual retained claims with
fresh:false and imported census hashes, never a new permit. A claimed observation
references the actual retained claim and byte-for-byte original deadline. A
separate preclaim-refusal record has no claim/start/deadline/result/success fields.
If no current observation authority exists, preserve local refusal only. All
observations/imports remain explicitly descriptive with serving_authorized:false,
dispatch_authorized:false, automatic_retry_allowed:false. Possibly committed
SQL/close/currentness failure is UNKNOWN; do not retry or reclassify it as a safe
unattempted operation.

## Complete actual current DENY and operational census

The actual original fixed TLS getter reads the mandatory policy tables in one
bounded consistent SQL transaction, with complete row counts and SHA digests of
actual full canonical rows. It returns no table payload, question, private key
or arbitrary data dictionary. SourceState status is the actual SQL002 enum
processing|draft|confirmed|error; missing original hash stays null. It includes
actual current source state, all original withdrawals and current rooted,
revoked/expired/disabled authority observations. Unknown owners/enums, foreign
or incomplete scope, ambiguity, quota overflow and body/catalog/source mismatch
refuse the WHOLE affected operation, never partial complete:true.

ALL56 SQL020/021/023/024/025/027 tables are mandatory. Their exact closed names and
source pins are literal OPERATIONAL_TABLES_V1 and OPERATIONAL_OWNER_SOURCE_PINS_V1
in recovery_contracts_v1.py. Frozen source SHA pins are02079c6d0c2…3ed7e,
021959a7755…2f7c,0234cec9e31…c66,024e6f956c4…91aa,
02559471db4…1b2b,027034d60c2…91143. The020 pin includes current supervisor/pre-STOP readback and
private pre_stop_observation tuple receipt_id/claim_id/operation_id/bot_id/
metadata_sha256. Further unattended producer work is not inferred complete.
No list limit, optional schema discovery or bounded dashboard substitutes for
the complete census. Native-only015/016 remain excluded from the canonical
migration union; existing canonical source order and once-only setup remain.

OperationalDenialV1 is a closed per-owner union, not a generic reason string:
owner_table from the56, record_kind, matching exact typed actual PK record_key,
actual full-row metadata SHA and effective_at from a retained actual timestamp
or null. It has thirteen key shapes: admission UUID, revocation UUID,
workspace+meeting, claim UUID, fetch-claim UUID, intent UUID, run UUID, operation UUID,
observation UUID, workspace+research source+revision, and workspace+recommendation
artifact+version, inventory+entry sequence and inventory+legacy citation. Exact per-kind owner/reason combinations live in the typed
source, never a caller dictionary. Its original23 reasons are source-disabled,
source-rights-unconfirmed, participant-epoch-revoked, final-mapping-revoked,
create-stop-relation-revoked, host-disabled, admission-revoked,
admission-expired, operation-window-ended, admission-not-effective,
capture-closed, operation-UNKNOWN, possible-effect-unreconciled,
proactive-disabled, proactive-limit-reached, proactive-cooldown,
active-intent-present, operation-suppressed, effect-already-observed,
registration-superseded, refresh-exhausted, refresh-not-due and
parent-model-superseded. Nine precise legacy reasons add document-custody-unavailable,
source-bytes-unavailable, original-missing, storage-read-unavailable,
object-precondition-failed, capture-incomplete, unsupported-document-media,
capture-coverage-gap and citation-revision-changed, each prefixed legacy-.
No current clock is invented as historical onset.
Unknown/unmapped persisted conditions or ambiguous/missing joins quarantine.

Denials retain capability granularity. Ended capture never denies independently
current STOP; proactive-disable/cooldown never denies an independently permitted
direct reply; not-due/nonpublic-fetch rights never rewrites authorized historical
read; a stale parent denies new recommendation actions rather than deleting
history. Business approvals remain in force until withdrawn, even when an old
approver loses authority. Current source/access/withdrawal and corrected-version
controls still deny; old approvals do not inherit to a new version.

Target import is ADD-DENY/fence only, and the concrete factory obtains the census
ONLY from the actual original current getter, with actual original master and
current denials checked before/after the target effect. A supplied packet/hash
cannot authenticate the source or lift quarantine. The retained original global
once claim blocks a second target attempt after a possibly effected result.

## Financial, private, graph, checkpoint and resume obligations still separate

The complete current policy census is not a complete program recovery proof.
Every actual covered-key partition needs the SAME existing three central Budget
owners: operating_dispatch_reservations, operating_dispatch_receipts and
operating_dispatch_diagnoses, including original reservation/maximum/actual
liability/current ledger/allocation/account binding and retained original wire
custody. A covered ledger may live in another explicitly pinned DB; canonical
SQL cannot infer that foreign tail or invent a replicated watermark. Missing,
stale or lost once/cost tail quarantines and blocks new native spend for the
affected partition. A fresh admission/database/allocation cannot reset a real
account's UNKNOWN liability. No source/read renewal may suppress actual costs;
metadata-only settlement uses only independently current finite ORIGINAL cost
settlement authority and the exact retained reservation/job/wire. No extra
allowance or automatic paid/send retry is created.

Consistent backup must include canonical SQL/history/operational ledgers,
checkpoint SQL, all private originals/model/native/job custody and independently
retained immutable ORIGINAL embedding-vector wire bytes. Same accepted logical
graph/name/generation and receipt/timestamps must remain exact. Rebuild cannot
call an expired PaidProjectionEmbedder, adopt/write an ACK, mint a qualification,
re-embed or claim digest-only readiness. Exact retained vector/model/license/
current full source scope and a real read-only SDK complete SUPPORT/vector census
are required; absent proof quarantines that capability. Current source withdrawal
and all denials must apply BEFORE any company/private read. Freshly restored
PostgresSaver data does not authorize resume. Actual current SQL019 employee/
thread/source/purpose authority must preserve pending questions, count≤8,
corrections/pause/resume/idempotency and immutable original text. UNKNOWN paid,
write, send and checkpoint effects cannot automatically resume or duplicate.

The future fresh-instance exercise must measure actual elapsed RTO and observed
capture age/RPO at stated scale and limits, show intact ORIGINAL current control/
once/cost positive and missing/stale/lost-tail negatives, prove every owned
resource cleanup and unchanged source, and preserve all real installation,
private/company runtime and separate business-acceptance holds. No database or
restore action occurs before the complete current-main consumer/source manifest,
fresh correct stronger gate and independent exact-resource review permit it.
No weaker class, omitted protected source, split proof or expired authority replay.

## Structural capture/restore custody contract (source successor)

The current frozen SQL020 successor includes all final-fetch, ingress-to-final
processing and queue custody: four mandatory tables expand the020–025 union to43.
Final-fetch and enqueue claims retain exact global uniqueness, actual original
effect deadline and processing horizon. Processing links/queue receipts retain
actual originating complete event/raw custody, never a new fetch/send grant.
Two closed added denial kinds reuse the existing23 reasons: actual ended effect
window, or possible-effect-unreconciled with null onset. Full parent/admission/
context/population/actual-final-payload/queue-wire joins are checked before complete
census. Missing/foreign/malformed rows quarantine the whole operation. Positive
immutable links survive capture expiry; STOP/history/unrelated scope stay distinct.
The exact frozen027 successor adds thirteen mandatory legacy-migration owners,
bringing this operational union to56. Unknown added operational/migration tables
still refuse;56 is not complete program recovery, installed authority or a
blessing for a newer catalog. Its exact source pin reflects the independently
reviewed PostgreSQL-compatible ETag predicate correction, not a lifecycle pass.

The separately installed `BackupCustodyV1` binds operation/kind/descriptor SHA,
actual own principal and capture or deny-only-target purpose, exact private root
identity, complete rooted workspace appointment coverage, exact native database
participants, independent issuer/reviewer, finite issued/expires/original horizon,
and independently installed retention-policy SHA/minimum-retain time. Capture
pins only an ACTUAL already-private output root disjoint from every input and
target root; manifest/archive/inventory pointers are null because their content
does not exist yet. Restore requires all three ACTUAL EXISTING protected files,
inside its independently current retained-custody root, with exact path/device/
inode/UID/0600/bytes SHA; descriptor pins the actual existing manifest. A fresh
restore never renews old capture, source, provider, grant or spending authority.
Retention time is not deletion authority. Runtime cannot create/chmod the root,
write credentials, replace files, install profiles, issue appointments or grants.

Every workspace requires its actual complete rooted capture-output or retained-
backup-read leaf plus the exact retention-policy leaf. Startup optionally pins
the protected custody file; absence preserves the original deny-only metadata
API but refuses native custody. The immutable SQL026 admission separately pins
that actual file SHA. Actual own SQL -> protected bytes -> actual own SQL and
settings rereads bracket every native/private boundary. A caller-created profile,
hash, root, file path, container selector or callback confers no authority.

Native participants pin exact source/target container ID/image/name and a
preinstalled participant-scoped private service file plus exact native physical
SQL/TLS identity. Native system identifier/database OID/name/owner/SESSION_USER
must match the descriptor; separately pinned container-local connection details
cannot replace physical equality. Docker inspection requests only ID, Image,
Name and Running, never Config/Env. Credentials/TLS keys never appear in argv,
logs or output; service bytes stay in private pipes. The original bounded Docker
execution body is shared, while the old constructor/command grammar/ceilings
remain unchanged. No arbitrary argv, runner, shell, SQL, host or path is added.

The source actuator contract allows only fixed inspect/stat/copy, PostgreSQL16
identity/version, custom dump using the actual exported snapshot, actual
pg_restore list, and transactional no-owner/no-ACL restore to the exact previously
inspected empty target. Required native permissions must already be independently
installed. RLS/permission failures refuse: no administrator, owner, BYPASSRLS,
row_security override or default-role fallback is permitted. TOC and actual
complete table/column inventory must exclude credential/password/TLS-secret
material; no-owner/no-ACL alone does not exclude table data or prove safe ACLs.
All restored application LOGINs remain NOLOGIN/passwordless. Actual postrestore
safe function ACLs/catalog and new deny-only/observe roles require a separately
installed profile; runtime never grants or activates serving.

Each participant snapshot records actual physical SQL/owner/role, server-issued
exported snapshot and transaction snapshot, observation time, fixed dump member,
byte count/SHA and actual TOC SHA. Its actual repeatable-read export remains open
only while its ONE bounded dump runs, without policy/currentness locks spanning
native work. Private-root enumeration records complete before/after population
hashes, exact root identity, counts/bytes and times; racing, linked, special,
foreign, credential-bearing, over-limit or changing material refuses/quarantines.
Archive ceilings remain 4096 files, 512 MiB per member and 1 GiB aggregate.
Immutable output uses exclusive private creation/fsync and derived operation-
scoped names only. Partial/uncertain output is retained without cleanup/retry.

The immutable backup manifest retains the exact original capture descriptor and
actual retained capture claim, actual canonical capture census member/hash,
retention metadata, original start/finish, archive/inventory hashes, complete
participant snapshots/private-root observations and explicit consistency UNKNOWN.
Restore reads exact historical capture claims/observations from the ORIGINAL
master only; no renewed capture horizon or user-selected history is accepted.
Separate capture and current-restore census protocols share the same full actual
census implementation and preserve their respective own-role authority.

There is no cross-participant common-cut proof. `snapshot-inconsistent` remains
mandatory and serving/dispatch/automatic-retry are false. Single-participant
structural capability must be retained, while enterprise consistency and RPO
remain UNKNOWN. The separate writer-quiescence design is still open. No source
record, inspection seam, manifest, test count or descriptive status grants an
actual native operation or proves whole-program recovery, RTO/RPO, installation,
private/company behavior or business acceptance.

Native identity records now carry the explicit `container-local` location tag.
Their URL and CA protected pointers are read only through fixed same-container
stat/copy, with every ancestor's independently pinned device/inode/UID/mode and
no-link type checked. Container UIDs are never replaced by the host process UID.
The source reader compares complete canonical conninfo (sorted explicit keys)
with exactly one private service, numeric address/port/role/verify-full/CA path,
and performs a fixed read-only native physical/TLS query with cleared ambient
PG defaults and original bounded connection/statement limits. Native client
certificate/key authentication is explicitly unsupported until separately pinned
custody exists; the supported prospective owned fixture uses password/SCRAM and
verify-full. Existing external SQL connector behavior is unchanged.

The current successor exposes read-only inspection/service/physical verification
and pure complete archive construction only. Actual dump/restore dispatch,
credential-column census, immutable output, exported-snapshot lifetime and
postrestore structural verification remain implementation work, not delivered
capabilities. No native operation has been invoked during this source work.

The internal immutable output mechanic now reuses the existing dirfd/O_EXCL/
0600/fsync save owner, requires an ACTUAL retained original capture master claim
and current independently pinned custody before/after, checks exact existing root
identity, uses only operation UUID plus three fixed names, preserves installed
smaller archive limits, and reports possibly written/late outcomes UNKNOWN
without cleanup/retry. Real invented-file tests prove exclusive/no-overwrite,
symlink refusal, root-mode preservation and retained postwrite uncertainty with
recording SQL seams. This is not a connected public capture producer or actual
SQL/native proof.

Future legacy-migration operational tables are also rejected by the current
static owner census until that owner's complete frozen source/union is included.
A newer independently installed general catalog pin cannot silently omit them.
Opaque PostgresSaver checkpoint/blob content is not credential-safe merely
because its column name is known: the existing writer forwards arbitrary
checkpoint/metadata/write payloads after its owner check. Nonempty unproved
opaque checkpoint custody quarantines the WHOLE participant rather than dropping
blobs, inferring safe serialization or claiming a complete backup. Independently
pinned full participant table/column inventory is separate from the unchanged
oracle2 control catalog fingerprint.


The separately pinned native dump inventory now binds complete actual supported
schemas/relations/owners/RLS/ACLs, column types/modifiers/collation/identity/
generated/default hashes, constraints/triggers/policies/indexes/views/sequences,
function complete-definition/body/config/security hashes, types/extensions and
collations. The original oracle2 control fingerprint is byte-for-byte unchanged.
Unknown schema/object/DDL/body, foreign objects and unsupported constructs refuse
whole participants. The actual inventory and original native wire hashes are
separate. Read-only observation is not an exported capture snapshot, a payload-
safety proof, a restore admission or source qualification. Native inventory pins
are optional for existing read-only profiles, mandatory before any dump; no caller
can supply/renew them. Opaque checkpoint safety still requires actual finite
source-owned payload evidence, independently of complete DDL metadata.

Exactly two source020 noncredential fingerprint columns are retained despite
credential-like names: meeting_capture_admissions_v1.verifier_secret_sha256 and
meeting_capture_admissions_v1.queue_credential_sha256. They are one-way protected
input bindings under the actual webhook/queue owners, not accepted authentication
credentials or password hashes. The exception is exact schema/table/column and
text type, with complete actual DDL/source pins still mandatory; no suffix-based
hash/password/SCRAM/auth-schema/opaque-checkpoint exception exists. Actual raw
credential/TLS client-key files are neither copied into backup nor returned.

Correction to earlier source reports: StrictRecord already inherited schema_version1.
Explicit declarations added to nested records were redundant; no missing-version
SQL bug was established or repaired. Direct SQL-shaped nested wire/version/UUID/
deadline tests remain useful, but do not replace actual database execution. Native full-catalog observation
and pure metadata comparisons remain read-only, with no dump/restore dispatch.

## Retained native staging amendment

Only the fixed operation-scoped pending participant dump and bounded TOC names
are added beneath the same preinstalled private output root. The actual original
master claim and current custody precede exclusive0600 creation. Opened file and
pathname device/inode/UID/mode/nlink1 and ancestor custody must match. No public
request accepts an fd, path, participant selector, argv or callback. The existing
bounded subprocess owner has a private retained-output-fd variant; the old API,
command grammar, limits and temporary-output behavior remain unchanged.

Actual timeout/nonzero/late-zero output stays in the already-created private file
as UNKNOWN without retry, unlink, rename, overwrite or acceptance. An already
opened effect may finish late; expired permission cannot start a new private
read/write/pack/archive. Complete output requires actual fsync, byte hash, bounds,
TOC and currentness before it can enter the one immutable final archive. A later
forensic read requires its own independently current custody. Retained pending
files do not create cleanup/deletion authority.

Closed successful manifest staging evidence names each exact operation/participant
and dump/TOC kind, complete actual private file tuple/hash/count and observed zero
exit. Incomplete/UNKNOWN/late/empty/foreign/missing staging cannot satisfy it.
These historical tuples never require re-opening expired capture paths during
fresh restore: current retained archive custody remains independently necessary.
The original archive ceilings stay4096 members,512 MiB each and1 GiB aggregate;
actual pending aggregate/resource capacity and complete pipeline proof remain
required. Source-only recording subprocess/file tests do not prove a native run.


## Resource accounting clarification

The unchanged descriptor ceiling A bounds the complete final archive plus inventory
plus manifest, not each one independently. All retained pending dump and TOC files
together also fit A; therefore these logical files require at most 2*A bytes. This
is not a disk quota or proof of free capacity. Before any create or dump, a current
independently installed resource profile must cover that finite bound plus explicit
filesystem allocation/inode/other-usage headroom, with the actual filesystem/root
identity and observed available capacity checked. A lower actual resource allowance
refuses the operation rather than changing the archive limits.

New current-custody metadata decoders may use only an explicit descriptor-derived
bound up to A. Existing metadata APIs keep their 1 MiB default. The earlier proposed
1 MiB inventory plus 1 MiB manifest assumption was not justified: 4096 permitted
member paths alone can exceed it. Complete canonical actual bytes, hashes and the
combined final size remain mandatory. Peak parsing and archive-buffer memory must
also be independently budgeted before effects; a finite byte ceiling alone does
not establish a safe Python heap bound. These source checks grant no effects.


The closed optional physical_resource custody record pins filesystem ID/device,
physical byte allowance, explicit nonzero headroom and independently reviewed
resource evidence hash. Old read-only custody bytes may omit it; missing cannot
permit native capture. The concrete read-only observation checks the actual open
root and pathname identity, actual fstatvfs filesystem ID, available bytes and
finite required inode count. Its result explicitly proves neither quota nor safe
memory nor dispatch. A profile/hash constructed by a caller supplies no authority.

The current source checkpoint audit found no production caller of the generic
PostgresSaver and no checkpoint-enabled graph. Its ownership guard can upsert an
owner row and forwards arbitrary checkpoint/metadata/write payloads; it is not
current membership, source scope or a closed credential-free serialization proof.
Existing saver APIs remain intact. Populated opaque checkpoint participants stay
quarantined whole. Actual durable interview pause state lives in SQL019 threads
and immutable events, including total question count, sole pending question,
correction ancestry and once identities. Recovery cannot invoke resume or replay
uncertain effects; later resume requires its actual current employee admission.


## Streaming and memory-isolation boundary

Old byte archive APIs keep their behavior; the same member reader now also
provides private streaming verification, while both writers share the exact USTAR
member constructor. New private mechanisms take only already-open actual retained
file descriptors and exact seals selected internally by the concrete owner. They
chunk-hash and recheck full file identity/time/link/size/UID/mode, enforce exact
population and bounds, retain partial output on errors and return no payload or
serve/dispatch authority. Original wall/monotonic fences precede staging creates
and each streaming write/read. A small invented allocation regression test is
not a general memory/resource admission.

Potentially large canonical metadata parsing/reserialization and archive checking
must run only in a fixed source-pinned local child with independently installed
actual interpreter/complete dependency closure and enforced per-child RLIMIT_AS.
The same original absolute wall and monotonic end must propagate; startup never
creates a new window. Closed small control input and three distinct actual private
read-only inherited FDs are required; no SQL/provider/credentials/path/argv
selectors. Original watchdog/actual rusage/exit/limit observations are mandatory;
nonzero/OOM/timeout/late/mismatch stays UNKNOWN, retained and nonretryable.

Existing inspected dependency_bundle/native runtime/program owners prove selected
imports/versions, own Python source or a single program label, not the complete
actual local interpreter/stdlib/dependency/native-library byte closure. A complete
protected installed manifest under this same custody/resource owner needs parent
ratification and implementation. No child/native operation is enabled by these
streaming mechanisms. Full capture/restore integration remains open.

The closed child control record is <=65536 canonical bytes, three distinct
inherited private input FD/inode identities (never stdin/stdout/stderr), exact
sizes/hashes, operation/descriptor/current custody/runtime-closure SHA, descriptor
aggregate A, actual installed memory ceiling and the unchanged original UTC and
finite monotonic end. Its structural result can carry actual usage/limit and
hash/count observations only, always false source/serve/dispatch/retry authority.
These records neither start a child nor appoint a loader/runtime. The future
runtime manifest is pinned independently beside custody by the SAME protected
startup; it binds the complete custody SHA, while custody has no runtime-manifest
pointer, avoiding a circular future hash. Actual native loader enforcement remains
unavailable: Python audit hooks or observed maps alone cannot prevent or prove
arbitrary future dlopen. No child or native effect is enabled by these records.


## Legacy migration tail and exact retained metadata

All thirteen027 owners participate: admissions/revocations, inventories/entries,
stable source bindings/body versions, cursor heads, globally once intents, events,
intake observations, separately evidenced resolutions, citation bindings and
current-document capture observations. Complete row digests/counts are private
metadata; no original question/body/command/capture payload enters the public
census. Role/runtime/rooted admission, origin/workspace/principal, immutable
parent identities, exact body/count/media and014 reservation/original custody,
resolution ordering and private capture receipt joins are required. Unknown or
foreign/missing/ambiguous rows quarantine the whole operation. The cursor is not
legacy CDC, writer quiescence or a complete current source tail.

Migration writer expiry/end only blocks that writer/effect. Independently current
read/reconcile/citation scopes may inspect exact retained observations, without
resend, new identity or renewal. UNKNOWN cannot be erased by a later positive:
exact retained resolution ancestry is required. Missing bytes/capture/media
conditions retain their exact reasons rather than being mislabeled permission
denials. Intentionally excluded derived entries are not missing originals or
positive permission. Citation mapping remains metadata-only; current independent
viewer/read/qualification and historical permission controls remain mandatory.

New current operations/settings/SQL require the exact complete027 tuple and
frozen source pins. Exact known prior026 capture descriptors and43-table captured
censuses remain readable solely as historical backup metadata using separate
retained parsers with unchanged timestamps, fields, hashes and closed old denial
subset. No wildcard version, mixed43/56 tuple, auto-repin or new operation may
use them. A retained026 manifest requires explicit missing-current-tail quarantine
(once-cost-tail-unproved); it grants no current capture/read/restore/serve/dispatch.
Current getters reject even already-typed retained census objects. Unknown source
versions refuse. Actual027 lifecycle proof and full recovery proof remain distinct.

The generic checkpoint owner remains unchanged. Actual recovery proof must retain
SQL019 paused state, total eight-question budget, sole pending question and
immutable events through restore/readback with zero provider actions; later resume
requires a separate actual current employee capability. A populated opaque saver
participant remains whole-participant quarantine, never whole-program DR success.

The optional archive-runtime startup pin now identifies one small canonical
header (at most65536 bytes) and an immutable canonical NDJSON file census. Each
record is bounded to65536 bytes before parsing; count is bounded to65536 files,
installed roots to32, and actual file bytes to32GiB. These are finite source
support limits, not archive-limit changes, installed memory qualification or
permission to enlarge resources. The unchanged archive caps remain4096 members,
512MiB/member and1GiB aggregate. Header binds full current custody SHA; custody
has no pointer back to runtime. Interpreter/entrypoint/actual source, standard
library, dependency and native-loader files must appear in the sorted complete
census, with protected physical identity and actual content hashes. Protected
configuration/credential/census files and private-original/backup roots must be
disjoint from runtime roots. No caller supplies these paths or pins.

The concrete read-only observer streams bounded records and files, rejects
unlisted/changed/duplicate/hardlinked/symlink/foreign filesystem entries, and
rechecks actual own-role SQL admission, custody and protected settings before
and after. Memory availability is merely observed, never an allocation or
proof of child safety. This byte census always reports native-loader enforcement,
runtime qualification and child-invocation authority FALSE. Arbitrary future
native dlopen enforcement is not supplied by the repository or by this census;
that installed enforcement/qualification remains a genuine prerequisite. No
archive child is launched, no native dump/restore is invoked and no recovery
activation is authorized by this increment. Recording SQL seams in tests are
not actual SQL installation proof. Existing startup configurations may omit the
optional pointer and retain their previous behavior.

Direct SQL calls are an independent boundary: a properly installed LOGIN can
invoke the four fixed functions without the Python client. SQL026 now checks
the actual complete SAME existing recovery catalog expression against the
independently installed identity's schema_catalog_sha256 on every original
context check, before and after each existing entry/effect. It checks the exact
retained014 canonicalizer source body BEFORE using that helper to canonicalize
anything; that helper cannot authenticate a changed implementation of itself.
All eight/four function signatures, admission columns, original fingerprint
meaning, native inventory separation and existing Python checks are preserved.
Source equality tests tie the embedded expression to the existing catalog owner.
External canonicalizer/ISO/immutability helper or other owner function, schema,
column, trigger, policy, owner, ACL and enum drift must deny direct callers before
claims/observations/imports. These are source obligations and prepared synthetic
proof cases, not an executed database/restore result or installed authority.

An installed appointment ID is not proof of valid delegation. Every recovery
context edge now requires the actual parent's actor to equal the child's
recorded grantor, the same workspace, and parent scope equal to the exact
installed leaf scope or root. The same edge rule applies to deny-census lineage
and phase-horizon recursion. The terminal exact pinned root, sixteen-node/cycle
limits, current revocation and original expiry remain unchanged. Broken actor,
unrelated scope, foreign workspace/root and cycles deny direct entry points;
other broken leaves remain explicit missing-current-root census denials.
Valid same-scope delegation remains supported. No reparenting, issuer, automatic
repair or new authority is introduced by these source checks.
