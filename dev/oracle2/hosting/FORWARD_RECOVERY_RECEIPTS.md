# Forward invented recovery receipt contract

Owner: Oracle coordinator on #27/#58. This source depends on the fixed forward
scenario implementation. Retire after W11 acceptance or consolidate into the
existing restore verifier after its hosted scope is independently qualified.
Existing local five-service stop/restore helpers remain unchanged.

The pure `restore_receipts` module validates supplied metadata and bounded local
protected bytes. It never contacts a host/database, quiesces a writer, backs up,
restores, creates a resource, issues a credential, runs SDK/provider code or
accepts hosted/business/serving state. All three acceptance flags stay false.
Hashes of claimed operational receipts cannot authenticate their origin.
Independent capture, exact-host readback and release admission remain required.
The synthetic test archive and role bundle are deliberately non-authorizing.

Only public-invented-forward-v2 is accepted: fixed namespace/job/source seal,
new source/image, exact 18-profile image/status closure, distinct physical
container/volume/network identity and original unextended one-hour worker/source
authority. Captures require one consumed admission and no pending work. Spent
request envelopes remain immutable even after their expiry; consumption must
have occurred before expiry. This does not renew a request or permit execution.

Required custody: custom PostgreSQL archive plus canonical TOC association,
protected opaque role-bootstrap credential bundle and canonical role/privilege
association, exact two source receipts, canonical artifact blob, exact completed
native pack, consumed claimed job, empty lock and every consumed nonce seal.
Aggregate bound is 1GiB and each file 512MiB. The source/result/blob/claimed/nonce
bytes are independently checked. Role bundles are only hash checked and must be
independently admitted and decrypted through the existing protected credential
route. Custody root and every directory are 0700, files 0600, current owner,
no symlink/extra/special entry, and every ancestor is opened with nofollow.
Runtime ownership is recorded separately. The empty runtime lock may retain its
original 0644 mode beneath the private 0700 spool; other files require 0600.
Receipt digests use canonical sorted JSON without trailing whitespace.

Fresh restore receipts must reference the exact backup, unchanged active
original authority and identical pre-delivery file seals/result, a distinct
empty instance with no original container/network/volume, unchanged permission
contract with a distinct permission observation, stock SDK1.4.0 empty-build-load
receipts and exact graph/artifact/record seals, plus old-job/spent-admission/
wrong-actor-source denials and native result delivery. Copying a graph or
returning node counts is insufficient. The validator reports metadata
consistency; only independently admitted live observations can establish proof.

## Remaining executable operation scope for root review

1. Exact forward-only quiesce/capture operator: verify live resource/image/role
   identities and authority freshness; stop only forward writers through the
   platform, preserve one-shot completion; capture PostgreSQL custom dump and
   actual TOC, original role-bootstrap bundle, blob/spool corpus and canonical
   pack into approved protected custody with bounded hashes/readback. Never
   capture the old application, raw environment, provider keys or health logs.
2. Separate empty forward restore operator: independently prove target emptiness
   and isolation, recreate only admitted login/role bootstrap from the unchanged
   original forward bundle, restore full schema/data/ACL and protected blobs/
   spool, and prove exact bytes/permissions. Do not rerun seed data or admission.
3. Separate stock-SDK fresh graph rebuild/reload: restore authoritative artifact
   first, build the same sealed generation into an empty fresh candidate store,
   compare records/load and result. Prove no route/mount to the original store.
4. Fresh nonce result-only delivery under still-active unchanged authority;
   refuse old/spent jobs and wrong actor/source. A dedicated native browser
   bridge remains a separate source/runtime gate. No old-core cutover or
   retirement is authorized by any of these receipts.

The separate compile_restore_roles compiler reuses the original fixed parameter
validation and login statements, creates only the scoped NOLOGIN groups and
logins transactionally, and never emits source/appointment/job data. Expired
original parameters and arbitrary verifiers refuse. Legacy seed byte parity
remains a verification gate.
The executable source is now implemented in forward_recovery.py, with bounded
Docker metadata/dump/TOC/corpus/empty-restore/SDK commands and separate result-only
mTLS delivery. No live operation is admitted by this source. Source quiescence
and new platform resource creation remain separate root-owned actions. Restore
target ledger-init stays CREATED and never runs its seed; gateway/executor and
projector stay unstarted until their separately checked recovery phases.
Candidate and confirmed volume identities are pinned and distinct too. Capture
derives real dump/corpus seals into a new immutable manifest rather than requiring
an impossible precomputed PostgreSQL archive digest. Every command rechecks the
unchanged original authority before and after it.


## Output custody and real operation budgets

Capture output must be a fresh oracle-forward-capture-* leaf directly beneath
existing TMPDIR coordinator custody. Every ancestor opens with nofollow, the
parent must already be owned0700, and both leaf and manifest must be absent
before any Docker command. Existing parent/foreign modes are never changed.
New nested output directories and0600 files are created via anchored dirfds;
parent inode movement refuses output. Failed partial custody is retained.

Every command requires its fixed timeout plus15seconds remaining in the
original authority before dispatch, with freshness rechecked afterward.
PostgreSQL commands use an independently probed in-container timeout executable
with TERM/kill-after budgets and bounded server statement/lock settings.
The pinned isolated PostgreSQL fixture qualified the required-s/-k flags.
Forward projector/reload entrypoints also arm fixed OS process alarms only
under the unchanged sealed original policy; legacy entrypoints stay unchanged.
These guards do not assert that Docker client timeout stops daemon work or
remove partial graphs/role creation/captures. There is no retry or renewal.
